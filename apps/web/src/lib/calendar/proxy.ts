/** Closed demo-owner boundary: no arbitrary backend routes or forwarded credentials. */
export async function forwardCalendar(
  request: Request,
  path: string[],
  backend: string,
  send: typeof fetch = fetch,
): Promise<Response> {
  const headers = { "Cache-Control": "no-store" };
  const fail = (status: number, code: string) =>
    Response.json({ detail: { code } }, { status, headers });
  const url = new URL(request.url),
    route = path.join("/"),
    method = request.method;
  const moveContext = /^(?:moves|sessions)\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(route);
  if (!moveContext && !["moves", "moves/preview", "feed", "goals", "constraints", "constraints/preview"].includes(route))
    return fail(404, "CALENDAR_ROUTE_NOT_FOUND");
  if (!(route === "constraints" ? ["GET", "POST"].includes(method) : method === (route === "feed" || moveContext ? "GET" : "POST")))
    return fail(405, "CALENDAR_METHOD_NOT_ALLOWED");
  const seen = new Set<string>();
  for (const [key] of url.searchParams) {
    if (
      method !== "GET" || moveContext ||
      !["start_date", "end_date"].includes(key) ||
      seen.has(key)
    )
      return fail(422, "CALENDAR_QUERY_INVALID");
    seen.add(key);
  }
  let body: string | undefined;
  if (method === "POST") {
    let expected: string;
    try {
      expected = request.headers.get("host")
        ? new URL(`${url.protocol}//${request.headers.get("host")}`).origin
        : url.origin;
    } catch {
      return fail(403, "CALENDAR_ORIGIN_REJECTED");
    }
    if (request.headers.get("origin") !== expected)
      return fail(403, "CALENDAR_ORIGIN_REJECTED");
    if (
      request.headers.get("content-type")?.split(";")[0].trim() !==
      "application/json"
    )
      return fail(415, "CALENDAR_JSON_REQUIRED");
    const reader = request.body?.getReader(),
      chunks: Uint8Array[] = [];
    let total = 0;
    try {
      if (reader)
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          total += part.value.byteLength;
          if (total > (route.startsWith("constraints") ? 1048576 : 16384)) {
            await reader.cancel();
            return fail(413, "CALENDAR_BODY_TOO_LARGE");
          }
          chunks.push(part.value);
        }
      const bytes = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      return fail(422, "CALENDAR_BODY_INVALID");
    }
  }
  try {
    const root = new URL(backend.endsWith("/") ? backend : backend + "/");
    if (
      !["http:", "https:"].includes(root.protocol) ||
      root.username ||
      root.password ||
      root.search ||
      root.hash
    )
      return fail(503, "CALENDAR_API_CONFIGURATION_INVALID");
    const target = new URL("api/v1/planning/calendar/" + route, root);
    target.search = url.search;
    const response = await send(target, {
      method,
      body,
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
      headers: {
        Accept: "application/json",
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (!response.headers.get("content-type")?.includes("application/json"))
      return fail(502, "CALENDAR_API_RESPONSE_INVALID");
    return new Response(response.body, {
      status: response.status,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch {
    return fail(502, "CALENDAR_API_UNAVAILABLE");
  }
}
