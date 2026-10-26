// A closed, same-origin frontend boundary for the existing demo-owner API.
const resources = new Set([
  "macrocycle-plans",
  "mesocycle-protocols",
  "measurements",
  "assessments",
]);
const noStore = { "Cache-Control": "no-store" };
function failure(status: number, code: string) {
  return Response.json({ detail: { code } }, { status, headers: noStore });
}

export async function forwardGoals(
  request: Request,
  path: string[],
  backend: string,
  send: typeof fetch = fetch,
): Promise<Response> {
  const url = new URL(request.url),
    method = request.method;
  const resource = path[0];
  const cyclePrograms =
    path.length === 2 && resource === "cycles" && path[1] === "programs";
  const cycleRevision =
    path.length === 2 &&
    resource === "cycles" &&
    ["competition-revisions", "boundary-revisions"].includes(path[1]);
  const cyclePreview =
    path.length === 2 && resource === "cycles" && path[1] === "preview";
  const cycleCatalog =
    path.length === 2 && resource === "cycles" && path[1] === "catalog";
  const cycleDetail =
    path.length === 3 &&
    resource === "cycles" &&
    path[1] === "programs" &&
    /^pt-cycle:[0-9a-f]{64}$/.test(path[2]);
  const athleteRead =
    path.length === 2 &&
    resource === "athlete" &&
    ["context", "history"].includes(path[1]);
  const athleteWrite =
    path.length === 2 &&
    resource === "athlete" &&
    ["profiles", "availability", "polar-imports"].includes(path[1]);
  const athletePreview =
    path.length === 3 &&
    resource === "athlete" &&
    path[1] === "availability" &&
    path[2] === "preview";
  const athleteDetail =
    path.length === 3 &&
    resource === "athlete" &&
    ["profiles", "availability"].includes(path[1]) &&
    /^pt-athlete:[0-9a-f]{64}$/.test(path[2]);
  const collection =
    (path.length === 1 && resources.has(resource)) || cyclePrograms;
  const detail =
    path.length === 2 &&
    resources.has(resource) &&
    /^pt-goal(?:-assessment|-measurement)?:[0-9a-f]{64}$/.test(path[1]);
  const vocabulary = path.length === 1 && resource === "catalog";
  const periods = path.length === 1 && resource === "periods";
  if (!(
    collection ||
    detail ||
    vocabulary ||
    periods ||
    cycleRevision ||
    cyclePreview ||
    cycleCatalog ||
    cycleDetail ||
    athleteRead ||
    athleteWrite ||
    athletePreview ||
    athleteDetail
  ))
    return failure(404, "GOAL_ROUTE_NOT_FOUND");
  if (
    (method === "GET" &&
      (cycleRevision || cyclePreview || athleteWrite || athletePreview)) ||
    (method !== "GET" &&
      !(
        method === "POST" &&
        (collection ||
          cycleRevision ||
          cyclePreview ||
          athleteWrite ||
          athletePreview)
      ))
  )
    return failure(405, "GOAL_METHOD_NOT_ALLOWED");
  const allowedQuery =
    method === "GET" && athleteRead
      ? ["start_date", "end_date"]
      : method === "GET" && collection
        ? ["limit", "offset"]
        : method === "GET" && detail
          ? ["available_by"]
          : [];
  const seen = new Set<string>();
  for (const [key] of url.searchParams) {
    if (!allowedQuery.includes(key) || seen.has(key))
      return failure(422, "GOAL_QUERY_INVALID");
    seen.add(key);
  }
  let body: string | undefined;
  if (method === "POST") {
    // Next's Node adapter can construct request.url with its internal hostname.
    // The incoming Host identifies the browser-facing origin; no forwarded host is trusted.
    const host = request.headers.get("host");
    let expectedOrigin: string;
    try {
      expectedOrigin = host
        ? new URL(`${url.protocol}//${host}`).origin
        : url.origin;
    } catch {
      return failure(403, "GOAL_ORIGIN_REJECTED");
    }
    if (request.headers.get("origin") !== expectedOrigin)
      return failure(403, "GOAL_ORIGIN_REJECTED");
    if (
      request.headers.get("content-type")?.split(";")[0].trim() !==
      "application/json"
    )
      return failure(415, "GOAL_JSON_REQUIRED");
    const reader = request.body?.getReader(),
      chunks: Uint8Array[] = [];
    let size = 0;
    try {
      if (reader)
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          size += part.value.byteLength;
          if (size > 1048576) {
            await reader.cancel();
            return failure(413, "GOAL_BODY_TOO_LARGE");
          }
          chunks.push(part.value);
        }
      const bytes = new Uint8Array(size);
      let start = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, start);
        start += chunk.byteLength;
      }
      body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      return failure(422, "GOAL_BODY_INVALID");
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
      return failure(503, "GOAL_API_CONFIGURATION_INVALID");
    const relative =
      resource === "athlete"
        ? "api/v1/planning/athlete/" +
          path.slice(1).map(encodeURIComponent).join("/")
        : resource === "cycles"
          ? "api/v1/planning/cycles/" +
            path.slice(1).map(encodeURIComponent).join("/")
          : periods
            ? "api/v1/training-periods"
            : "api/v1/planning/goals/" + path.map(encodeURIComponent).join("/");
    const target = new URL(relative, root);
    target.search = url.search;
    const result = await send(target, {
      method,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(60000),
      headers: {
        Accept: "application/json",
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
      },
    });
    if (!result.headers.get("content-type")?.includes("application/json"))
      return failure(502, "GOAL_API_RESPONSE_INVALID");
    return new Response(result.body, {
      status: result.status,
      headers: { ...noStore, "Content-Type": "application/json" },
    });
  } catch {
    return failure(502, "GOAL_API_UNAVAILABLE");
  }
}
