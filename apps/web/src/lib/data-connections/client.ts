import { object } from "@/lib/planning-cycles/contracts";
import { continuationOnly, datasetLabels, preservedPlanResult, preservedPlansOnly, readReceipt, readStatus } from "./contracts";
import type { DatasetResult, Pending, Run } from "./contracts";

const messages: Record<string, string> = {
  DATA_SYNC_DETAILS_PENDING: "A részletes edzésadatok egy része megérkezett. Újabb szinkronizálással folytatható az átvétel; először a legutóbbi edzések kerülnek sorra.",
  DATA_SYNC_DETAILS_SOURCE_CONFLICT: "Néhány részletes forrásadat eltér a megőrzött edzésadattól. A korábbi adat megmaradt; ellenőrzés szükséges.",
  DATA_SYNC_DETAILS_NOT_RETURNED: "A Polar néhány tárolt edzés részleteit még nem adta vissza. A többi edzés átvétele megmaradt.",
  DATA_SYNC_ALREADY_RUNNING:
    "Ennél a szolgáltatónál már folyamatban van egy frissítés.",
  DATA_SYNC_RECONNECT_REQUIRED:
    "A szolgáltatói kapcsolatot újra engedélyezni kell.",
  DATA_SYNC_PERMISSION_MISSING:
    "Ehhez az adatfajtához további szolgáltatói hozzáférés szükséges.",
  DATA_SYNC_CONFIGURATION_REQUIRED:
    "A Polar-kapcsolat szerveroldali beállítása még hiányzik.",
  DATA_SYNC_NOT_CONNECTED: "Először kapcsolódj a Polar-fiókodhoz.",
  DATA_SYNC_PROVIDER_UNAVAILABLE:
    "Ehhez a szolgáltatóhoz még nincs bekötött adatkapcsolat.",
  DATA_SYNC_PROVIDER_REJECTED: "A szolgáltató elutasította az adatlekérést.",
  DATA_SYNC_PROVIDER_NETWORK_UNAVAILABLE: "A szolgáltató most nem érhető el.",
  DATA_SYNC_RATE_LIMITED:
    "A szolgáltató túl sok lekérést jelzett. Később próbáld újra.",
  DATA_SYNC_TIMEOUT: "A frissítés nem fejeződött be az időkereten belül.",
  DATA_SYNC_SOURCE_RECORDS_SKIPPED:
    "Néhány forrásrekord kimaradt az adatátvételből.",
  DATA_SYNC_PROTECTED_PLANS_SKIPPED:
    "A védett vagy kézi terveket megőriztük.",
  DATA_SYNC_PAIRING_REVIEW_REQUIRED:
    "Néhány tervkapcsolat külön ellenőrzést igényel. A meglévő kapcsolatokat megőriztük.",
  DATA_SYNC_PAIRING_FAILED:
    "Az átvett adatok mentése után a tervkapcsolatok frissítése nem fejeződött be.",
  DATA_SYNC_IMPORT_FAILED:
    "Az adatátvétel nem fejeződött be. Korábban mentett adatok már lehetnek az adatbázisban.",
  DATA_SYNC_INTERRUPTED:
    "Az előző futás befejezése nem igazolható. Új frissítés indítható.",
  DATA_SYNC_STORAGE_INVALID: "A frissítés tárolt előzménye nem ellenőrizhető.",
};
export function resultDetails(result: DatasetResult): string[] {
  const labels: Record<string, string> = {
    protected_plan: "Védett vagy kézi terv megőrizve",
    invalid_record: "Hiányos forrásrekord",
    missing_target_id: "Tervazonosító nélkül",
    missing_session_id: "Teljesítésazonosító nélkül",
    missing_start: "Kezdési idő nélkül",
    details_batch_pending: "Következő részletes átvételre vár",
    details_not_returned: "A Polar nem küldte vissza a részleteit",
    details_source_changed: "Közben megváltozott edzésforrás",
    details_source_conflict: "Eltérő megőrzött részletes forrás",
  };
  const lines = Object.entries(result.skip_reasons ?? {}).map(([reason, count]) =>
    `${Object.hasOwn(labels, reason) ? labels[reason] : `Ismeretlen kihagyási ok (${reason})`}: ${count}`);
  if (result.pairing) {
    const p = result.pairing;
    lines.push(`Tárolt Polar-teljesítések új tervkapcsolatai: ${p.linked}`);
    if (p.unmatched) lines.push(`A hivatkozott terv még nincs meg: ${p.unmatched}`);
    if (p.missing_reference) lines.push(`Polar-tervhivatkozás nélkül: ${p.missing_reference}`);
    if (p.conflicts) lines.push(`Eltérő meglévő tervkapcsolat: ${p.conflicts}`);
    if (p.ambiguous) lines.push(`Nem egyértelmű tervazonosító: ${p.ambiguous}`);
  }
  if (result.details) {
    const d = result.details;
    lines.push(`Korábban ellenőrzött részletek: ${d.already_complete}`);
    lines.push(`Most lekért edzésrészletek: ${d.fetched_sessions} · mintasorral: ${d.with_samples} · mintasor nélkül: ${d.without_samples}`);
    if (d.pending_sessions) lines.push(`További átvételre vár: ${d.pending_sessions} edzés, ${d.pending_days} napon`);
  }
  return lines;
}
export function resultCounts(result: DatasetResult) {
  if (result.state !== "succeeded")
    return result.state === "not_attempted" ? "Nem került sorra" : "Nem fejeződött be";
  if (result.dataset === "session_details" && result.details)
    return `Lekért részletek: ${result.details.fetched_sessions} · korábban ellenőrzött: ${result.details.already_complete} · hátralévő: ${result.details.pending_sessions}`;
  const disposition = preservedPlanResult(result) ? "megőrzött" : "kihagyott";
  return `Új: ${result.imported ?? "ismeretlen"} · frissített: ${result.updated ?? "ismeretlen"} · ${disposition}: ${result.skipped ?? "ismeretlen"}`;
}
export function errorText(code: string) {
  const upstream = /^DATA_SYNC_PROVIDER_HTTP_([45]\d{2})$/.exec(code);
  if (upstream) {
    const status = Number(upstream[1]);
    if (status === 400 || status === 422)
      return `A szolgáltató hibás kérésként utasította el az adatlekérést (HTTP ${status}).`;
    if (status === 404)
      return "A szolgáltatói adatvégpont nem található (HTTP 404).";
    if (status >= 500)
      return `A szolgáltató szerverhibát jelzett (HTTP ${status}).`;
    return `A szolgáltató elutasította az adatlekérést (HTTP ${status}).`;
  }
  return messages[code] ?? `Az adatkapcsolati művelet nem sikerült (${code}).`;
}
export function runMessages(run: Run): string[] {
  if (continuationOnly(run)) {
    const pending = run.datasets.find(d => d.dataset === "session_details")!.details!;
    return [`A részletes átvétel folytatható: még ${pending.pending_sessions} edzés, ${pending.pending_days} napon. Újabb szinkronizálással a következő adag kerül sorra.`,
      ...(run.datasets.some(preservedPlanResult) ? [messages.DATA_SYNC_PROTECTED_PLANS_SKIPPED] : [])];
  }
  if (preservedPlansOnly(run)) return [messages.DATA_SYNC_PROTECTED_PLANS_SKIPPED];
  const actual = run.datasets.filter(d => d.error_code && !preservedPlanResult(d));
  const lines = actual.map(d => `${datasetLabels[d.dataset]}: ${errorText(d.error_code!)} (${d.error_code})`);
  if (run.error_code && !actual.some(d => d.error_code === run.error_code)) lines.push(`${errorText(run.error_code)} (${run.error_code})`);
  return lines.length ? lines : run.state === "failed" || run.state === "interrupted" ? [errorText("DATA_SYNC_IMPORT_FAILED")] : [];
}
export class ConnectionError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(errorText(code));
  }
}
async function json(response: Response) {
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new Error("Az adatkapcsolati válasz nem értelmezhető.");
  }
  if (!response.ok) {
    const detail = object(value).detail;
    throw new ConnectionError(
      response.status,
      detail && typeof detail === "object"
        ? String(object(detail).code ?? "UNKNOWN")
        : "UNKNOWN",
    );
  }
  return value;
}
export async function loadStatus(signal?: AbortSignal) {
  return readStatus(
    await json(
      await fetch("/api/data-connections/status", {
        cache: "no-store",
        signal,
      }),
    ),
  );
}
export async function sendSync(pending: Pending) {
  return readReceipt(
    await json(
      await fetch("/api/data-connections/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: pending.body,
        cache: "no-store",
      }),
    ),
    pending,
  );
}
export async function findSync(pending: Pending, signal?: AbortSignal) {
  const request = JSON.parse(pending.body);
  return readReceipt(
    await json(
      await fetch("/api/data-connections/runs/" + request.request_id, {
        cache: "no-store",
        signal,
      }),
    ),
    pending,
  );
}
