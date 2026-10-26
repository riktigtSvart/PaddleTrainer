/** Closed configured-owner routes. Secrets and incoming cookies stay outside the proxy. */
export async function forwardConnections(
  request: Request,
  path: string[],
  backend: string,
  send: typeof fetch = fetch,
): Promise<Response> {
  const headers = { "Cache-Control": "no-store" },
    fail = (status: number, code: string) =>
      Response.json({ detail: { code } }, { status, headers });
  const statusRoute = path.length === 1 && path[0] === "status",
    sync = path.length === 1 && path[0] === "sync",
    run =
      path.length === 2 &&
      path[0] === "runs" &&
      /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(path[1]);
  const connect =
    path.length === 2 && path[0] === "polar" && path[1] === "connect";
  if (!statusRoute && !sync && !run && !connect)
    return fail(404, "DATA_SYNC_ROUTE_NOT_FOUND");
  if (request.method !== (sync ? "POST" : "GET"))
    return fail(405, "DATA_SYNC_METHOD_NOT_ALLOWED");
  const url = new URL(request.url);
  if (url.search) return fail(422, "DATA_SYNC_QUERY_INVALID");
  let root: URL;
  try {
    root = new URL(backend.endsWith("/") ? backend : backend + "/");
    if (
      !["http:", "https:"].includes(root.protocol) ||
      root.username ||
      root.password ||
      root.search ||
      root.hash
    )
      throw new Error();
  } catch {
    return fail(503, "DATA_SYNC_API_CONFIGURATION_INVALID");
  }
  // Explicit browser navigation to the existing OAuth entry point; no proxying of tokens.
  if (connect)
    return new Response(null, {
      status: 303,
      headers: {
        ...headers,
        Location: new URL("api/v1/integrations/polar/connect", root).href,
      },
    });
  let body: string | undefined;
  if (sync) {
    let origin: string;
    try {
      origin = request.headers.get("host")
        ? new URL(`${url.protocol}//${request.headers.get("host")}`).origin
        : url.origin;
    } catch {
      return fail(403, "DATA_SYNC_ORIGIN_REJECTED");
    }
    if (request.headers.get("origin") !== origin)
      return fail(403, "DATA_SYNC_ORIGIN_REJECTED");
    if (
      request.headers.get("content-type")?.split(";")[0].trim() !==
      "application/json"
    )
      return fail(415, "DATA_SYNC_JSON_REQUIRED");
    const reader = request.body?.getReader(),
      chunks: Uint8Array[] = [];
    let total = 0;
    try {
      if (reader)
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          total += part.value.byteLength;
          if (total > 16384) {
            await reader.cancel();
            return fail(413, "DATA_SYNC_BODY_TOO_LARGE");
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
      return fail(422, "DATA_SYNC_BODY_INVALID");
    }
  }
  try {
    const response = await send(
      new URL("api/v1/data-connections/" + path.join("/"), root),
      {
        method: request.method,
        body,
        redirect: "error",
        cache: "no-store",
        signal: AbortSignal.timeout(sync ? 210000 : 30000),
        headers: {
          Accept: "application/json",
          ...(sync ? { "Content-Type": "application/json" } : {}),
        },
      },
    );
    if (!response.headers.get("content-type")?.includes("application/json"))
      return fail(502, "DATA_SYNC_API_RESPONSE_INVALID");
    return new Response(response.body, {
      status: response.status,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch {
    return fail(502, "DATA_SYNC_API_UNAVAILABLE");
  }
}
