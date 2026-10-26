import { object } from "@/lib/planning-cycles/contracts";
import { readContext, readReceipt } from "./contracts";
import type { Candidate, Pending } from "./contracts";
const root = "/api/goal-workflow/athlete/";
const labels: Record<string, string> = {
  ATHLETE_OVERNIGHT_DAY_UNAVAILABLE:
    "Az éjfél után végződő ablak második napját nem jelölheted teljesen elérhetetlennek.",
  ATHLETE_REVISION_CONFLICT_RELOAD:
    "A profil vagy a naptár másik lapon megváltozott. Töltsd újra, és tekintsd át a friss adatokat.",
  ATHLETE_TIME_DOES_NOT_EXIST:
    "Az időablak az óraátállítás miatt nem létező helyi időpontot tartalmaz.",
  ATHLETE_TIME_IS_AMBIGUOUS:
    "Az időablak ismétlődő órába esik. Válaszd ki az első vagy a második előfordulást.",
  ATHLETE_WINDOW_DURATION_INVALID:
    "Az edzés ideje férjen bele a megadott időablakba (legfeljebb 24 óra).",
  ATHLETE_WINDOWS_OVERLAP:
    "Az edzésablakok átfedik egymást. Pontosítsd a kezdetüket és a végüket.",
  ATHLETE_DAILY_BUDGET_INVALID:
    "A napi összes edzésidő nem lehet több az ablakokban megadott időnél.",
  ATHLETE_MESOCYCLE_DATES_CHANGED:
    "A mezociklus dátumai megváltoztak. Válaszd ki újra a friss időszakot.",
  ATHLETE_POLAR_NOT_CONNECTED:
    "Még nincs Polar-kapcsolat. A kézi adatbevitel elérhető.",
  ATHLETE_POLAR_SCOPE_MISSING:
    "Ehhez az adatkörhöz a Polar-kapcsolat nem kapott hozzáférést.",
  ATHLETE_POLAR_RECONNECT_REQUIRED:
    "A Polar-kapcsolat új engedélyezést igényel.",
  ATHLETE_POLAR_UNAVAILABLE_OR_REJECTED:
    "A Polar-lekérés nem sikerült. Az eddigi nyers adatok megmaradtak; a kérés megismételhető.",
  ATHLETE_SOURCE_CHANGED_OR_NOT_FOUND:
    "Egy kiválasztott forrás megváltozott. Töltsd be újra az átvételi javaslatokat.",
  ATHLETE_SOURCE_DUPLICATE_CHOOSE_ONE:
    "Ugyanannak a megfigyelésnek több változatát választottad ki. Válassz egyet a profilhoz.",
  ATHLETE_HISTORY_TOO_LARGE_CHOOSE_SHORTER_RANGE:
    "Sok adat található: kérj le rövidebb időszakot.",
  ATHLETE_INPUT_INVALID: "Ellenőrizd a mezőket, dátumokat és mértékegységeket.",
};
export class SetupHTTPError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(root + path, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error(
      "A szerver válasza nem olvasható. Mentésnél az eredmény még nem ismert.",
    );
  }
  if (!response.ok) {
    const detail = object(value).detail;
    const code =
      detail && typeof detail === "object" ? String(object(detail).code) : "";
    throw new SetupHTTPError(
      labels[code] ?? `A művelet nem sikerült (${code || response.status}).`,
      response.status,
    );
  }
  return value;
}
export async function loadContext(signal?: AbortSignal) {
  return readContext(await request("context", { signal }));
}
export async function history(
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<Candidate[]> {
  const page = object(
    await request(
      "history?" + new URLSearchParams({ start_date: start, end_date: end }),
      { signal },
    ),
  );
  if (
    page.schema_version !== "athlete-history-candidates-v0.1" ||
    page.start_date !== start ||
    page.end_date !== end ||
    page.has_more !== false ||
    page.absence_means_zero !== false ||
    !Array.isArray(page.items)
  )
    throw new Error(
      "A történelmi adatok időszaka vagy teljessége nem igazolt.",
    );
  return page.items as Candidate[];
}
export async function send(pending: Pending) {
  return readReceipt(
    await request(pending.operation, { method: "POST", body: pending.body }),
    pending,
  );
}
export async function previewCalendar(body: string) {
  return request("availability/preview", { method: "POST", body });
}
