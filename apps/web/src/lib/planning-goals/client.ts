import { object, readPage, readReceipt } from "./contracts";
import type { PendingRequest } from "./contracts";
import type { Resource } from "./types";

export class GoalHTTPError extends Error {
  constructor(public status: number) {
    super(
      status === 404
        ? "A kért ciklus vagy mentett verzió nem érhető el az alkalmazás felhasználójának."
        : status === 409
          ? "A kérés ütközik a rögzített verzióval vagy a protokoll szabályaival. Ellenőrizd a verziót, a cikluskapcsolatokat, az időablakokat és a követelményeket."
          : status === 422
            ? "Az űrlap adatai nem fogadhatók el. Ellenőrizd a kötelező mezőket, számokat és időpontokat."
            : status === 413
              ? "A kérés túl nagy. Rövidítsd a szöveges leírásokat."
              : status === 403
                ? "A mentési kérés eredete nem fogadható el. Nyisd meg újra az alkalmazás saját címét."
                : status >= 500
                  ? "A szerver nem tudta igazolni a művelet eredményét. A mentés ugyanazzal a kéréssel újrapróbálható."
                  : `A művelet nem sikerült (HTTP ${status}).`,
    );
    this.name = "GoalHTTPError";
  }
}
export async function getJSON(
  path: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const result = await fetch("/api/goal-workflow/" + path, {
    cache: "no-store",
    signal,
    headers: { Accept: "application/json" },
  });
  if (!result.ok) throw new GoalHTTPError(result.status);
  return result.json();
}
export async function loadPage(
  resource: Resource,
  offset = 0,
  signal?: AbortSignal,
) {
  return readPage(
    await getJSON(`${resource}?limit=25&offset=${offset}`, signal),
    resource,
    offset,
  );
}
export async function sendPending(pending: PendingRequest) {
  const result = await fetch("/api/goal-workflow/" + pending.resource, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: pending.body,
  });
  if (!result.ok) throw new GoalHTTPError(result.status);
  return readReceipt(await result.json(), pending.resource);
}
export function readPeriods(value: unknown) {
  if (!Array.isArray(value)) throw new Error("Hiányos cikluslista.");
  return value.map((item) => {
    const period = object(item);
    if (
      ["id", "period_type", "title", "start_date", "end_date"].some(
        (key) => typeof period[key] !== "string",
      ) ||
      !(period.parent_id === null || typeof period.parent_id === "string")
    )
      throw new Error("Hiányos ciklusadat.");
    return period as {
      id: string;
      parent_id: string | null;
      period_type: string;
      title: string;
      start_date: string;
      end_date: string;
    };
  });
}
