import { object } from "@/lib/planning-cycles/contracts";
import { readOptionsContext, readOptionsReceipt } from "./contracts";
import type { OptionsPending } from "./contracts";

export class OptionsHTTPError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
const messages: Record<string, string> = {
  TRAINING_OPTIONS_REVISION_CONFLICT:
    "Az edzési lehetőségek közben megváltoztak. Olvasd újra, és egyeztesd a módosításokat.",
  TRAINING_OPTIONS_REQUEST_CONFLICT:
    "Ezzel a kérésazonosítóval már más tartalom került mentésre.",
  TRAINING_OPTIONS_TIMEZONE_CHANGED:
    "Az időzóna megváltozott. A helyi időpontokat felül kell vizsgálni.",
  ATHLETE_INPUT_INVALID:
    "Ellenőrizd a helyszíneket, az időpontokat és a dátumokat.",
  ATHLETE_TIME_IS_AMBIGUOUS:
    "Ismétlődő óra: válaszd ki az első vagy második időpontot.",
  ATHLETE_TIME_DOES_NOT_EXIST:
    "Az óraátállítás miatt ez a helyi időpont nem létezik.",
};
async function request(path: string, init: RequestInit = {}) {
  const response = await fetch("/api/goal-workflow/training-options" + path, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw Error("A mentési válasz nem olvasható; az eredmény még nem ismert.");
  }
  if (!response.ok) {
    const detail = object(value).detail,
      code =
        detail && typeof detail === "object" ? String(object(detail).code) : "";
    throw new OptionsHTTPError(
      messages[code] ??
        `Az edzési lehetőségek művelete nem sikerült (${code || response.status}).`,
      response.status,
    );
  }
  return value;
}
export async function loadOptions(
  range?: { start: string; end: string },
  signal?: AbortSignal,
) {
  const c = await readOptionsContext(
    await request(
      range
        ? "?" +
            new URLSearchParams({
              start_date: range.start,
              end_date: range.end,
            })
        : "",
      { signal },
    ),
  );
  if (range && (c.start_date !== range.start || c.end_date !== range.end))
    throw Error("Másik időszak lehetőségei érkeztek.");
  return c;
}
export async function sendOptions(pending: OptionsPending) {
  return readOptionsReceipt(
    await request("", { method: "POST", body: pending.body }),
    pending.owner,
    pending.body,
  );
}
