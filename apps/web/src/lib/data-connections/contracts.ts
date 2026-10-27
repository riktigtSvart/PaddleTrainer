import { canonical, object, sha } from "@/lib/planning-cycles/contracts";

export type Dataset = "sessions" | "targets" | "session_details";
export type Body = {
  request_id: string;
  provider: string;
  datasets: Dataset[];
  past_days: number;
  future_days: number;
};
export type PairingResult = {
  linked: number;
  already_linked: number;
  unmatched: number;
  missing_reference: number;
  conflicts: number;
  ambiguous: number;
};
export type DatasetResult = {
  dataset: Dataset;
  state: "succeeded" | "failed" | "not_attempted";
  imported: number | null;
  updated: number | null;
  skipped: number | null;
  error_code: string | null;
  pairing?: PairingResult;
  skip_reasons?: Record<string, number>;
  details?: { requested_sessions: number; already_complete: number; fetched_sessions: number;
    with_samples: number; without_samples: number; pending_sessions: number; processed_days: number; pending_days: number };
};
export type Run = {
  request_id: string;
  provider: string;
  state: "running" | "succeeded" | "partial" | "failed" | "interrupted";
  started_at: string;
  deadline_at: string;
  finished_at: string | null;
  requested_datasets: Dataset[];
  datasets: DatasetResult[];
  error_code: string | null;
  may_have_saved_data: boolean;
  window: {
    from_date: string;
    sessions_to_exclusive: string;
    targets_to_exclusive: string;
    timezone_name: string;
  };
};
export type Provider = {
  key: string;
  label: string;
  implemented: boolean;
  delivery: string;
  connection_state:
    | "connected"
    | "not_connected"
    | "configuration_required"
    | "reconnect_required"
    | "unavailable";
  manual_sync_supported: boolean;
  datasets: Dataset[];
  allowed_datasets: Dataset[];
  last_run: Run | null;
  last_success_at: string | null;
  last_success_datasets: Dataset[];
  latest_session_at: string | null;
};
export type Status = {
  schema_version: "data-connections-v0.1";
  athlete_id: string;
  timezone_name: string;
  retrieved_at: string;
  providers: Provider[];
  has_more: false;
  planning_authorized: false;
};
export type Receipt = {
  schema_version: "data-sync-receipt-v0.1";
  athlete_id: string;
  committed: true;
  reused: boolean;
  start: Record<string, unknown>;
  result: Record<string, unknown> | null;
  run: Run;
  planning_authorized: false;
};
export type Pending = {
  version: "data-sync-pending-v0.1";
  owner: string;
  body: string;
};
export const PENDING_KEY = "paddletrainer.data-sync.pending.v1";
export const UPDATED_EVENT = "paddletrainer:data-synced";
export const datasetLabels: Record<Dataset, string> = {
  sessions: "Teljesített edzések",
  targets: "Polar-edzéstervek",
  session_details: "Részletes edzésadatok és grafikonok",
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function requireValue(condition: unknown): asserts condition {
  if (!condition)
    throw new Error("Az adatkapcsolati válasz nem ellenőrizhető.");
}
function timestamp(value: unknown, nullable = false) {
  if (nullable && value === null) return;
  requireValue(
    typeof value === "string" &&
      /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
      Number.isFinite(Date.parse(value)),
  );
}
function datasets(value: unknown): asserts value is Dataset[] {
  requireValue(
    Array.isArray(value) &&
      value.length <= 3 &&
      new Set(value).size === value.length &&
      value.every((x) => x === "sessions" || x === "targets" || x === "session_details"),
  );
}
export function readBody(value: unknown): Body {
  const b = object(value);
  requireValue(
    Object.keys(b).sort().join() ===
      "datasets,future_days,past_days,provider,request_id",
  );
  requireValue(
    typeof b.request_id === "string" &&
      uuid.test(b.request_id) &&
      ["POLAR", "GARMIN", "SUUNTO"].includes(String(b.provider)),
  );
  datasets(b.datasets);
  requireValue(b.datasets.length > 0);
  requireValue(
    Number.isInteger(b.past_days) &&
      Number(b.past_days) >= 1 &&
      Number(b.past_days) <= 89 &&
      Number.isInteger(b.future_days) &&
      Number(b.future_days) >= 0 &&
      Number(b.future_days) <= 30,
  );
  return b as Body;
}
export function readPending(raw: string): Pending {
  const p = object(JSON.parse(raw));
  requireValue(
    p.version === "data-sync-pending-v0.1" &&
      typeof p.owner === "string" &&
      uuid.test(p.owner) &&
      typeof p.body === "string",
  );
  readBody(JSON.parse(p.body));
  return p as Pending;
}
function readRun(value: unknown): Run {
  const r = object(value);
  requireValue(
    typeof r.request_id === "string" &&
      uuid.test(r.request_id) &&
      typeof r.provider === "string" &&
      ["running", "succeeded", "partial", "failed", "interrupted"].includes(
        String(r.state),
      ),
  );
  timestamp(r.started_at);
  timestamp(r.deadline_at);
  timestamp(r.finished_at, true);
  datasets(r.requested_datasets);
  requireValue(r.requested_datasets.length > 0);
  requireValue(
    Array.isArray(r.datasets) &&
      typeof r.may_have_saved_data === "boolean" &&
      (r.error_code === null || typeof r.error_code === "string"),
  );
  for (const item of r.datasets) {
    const d = object(item);
    requireValue(
      r.requested_datasets.includes(d.dataset as Dataset) &&
        ["succeeded", "failed", "not_attempted"].includes(String(d.state)),
    );
    for (const key of ["imported", "updated", "skipped"])
      requireValue(
        d[key] === null || (Number.isInteger(d[key]) && Number(d[key]) >= 0),
      );
    requireValue(d.error_code === null || typeof d.error_code === "string");
    if ("pairing" in d) {
      const p = object(d.pairing);
      requireValue(Object.keys(p).sort().join() ===
        "already_linked,ambiguous,conflicts,linked,missing_reference,unmatched");
      requireValue(Object.values(p).every((n) => Number.isInteger(n) && Number(n) >= 0));
    }
    if ("skip_reasons" in d) {
      const reasons = object(d.skip_reasons);
      requireValue(Object.entries(reasons).every(([key, n]) =>
        key.length > 0 && Number.isInteger(n) && Number(n) >= 0));
      requireValue(Object.values(reasons).reduce<number>((sum, n) => sum + Number(n), 0) === d.skipped);
    }
    if ("details" in d) {
      const detail = object(d.details);
      requireValue(d.dataset === "session_details" && Object.keys(detail).sort().join() ===
        "already_complete,fetched_sessions,pending_days,pending_sessions,processed_days,requested_sessions,with_samples,without_samples");
      requireValue(Object.values(detail).every(n => Number.isInteger(n) && Number(n) >= 0));
      requireValue(Number(detail.already_complete) + Number(detail.fetched_sessions) + Number(detail.pending_sessions) === detail.requested_sessions &&
        Number(detail.with_samples) + Number(detail.without_samples) === detail.fetched_sessions &&
        detail.fetched_sessions === d.updated && detail.pending_sessions === d.skipped);
    }
  }
  const w = object(r.window);
  for (const key of [
    "from_date",
    "sessions_to_exclusive",
    "targets_to_exclusive",
  ])
    requireValue(
      typeof w[key] === "string" &&
        /^\d{4}-\d{2}-\d{2}$/.test(w[key] as string),
    );
  requireValue(typeof w.timezone_name === "string");
  return r as Run;
}
export function readStatus(value: unknown): Status {
  const s = object(value);
  requireValue(
    s.schema_version === "data-connections-v0.1" &&
      s.has_more === false &&
      s.planning_authorized === false &&
      typeof s.athlete_id === "string" &&
      uuid.test(s.athlete_id) &&
      typeof s.timezone_name === "string" &&
      Array.isArray(s.providers),
  );
  timestamp(s.retrieved_at);
  new Intl.DateTimeFormat("hu-HU", { timeZone: s.timezone_name });
  const keys = new Set();
  for (const value of s.providers) {
    const p = object(value);
    requireValue(
      typeof p.key === "string" &&
        !keys.has(p.key) &&
        typeof p.label === "string" &&
        typeof p.implemented === "boolean" &&
        typeof p.manual_sync_supported === "boolean" &&
        typeof p.delivery === "string" &&
        [
          "connected",
          "not_connected",
          "configuration_required",
          "reconnect_required",
          "unavailable",
        ].includes(String(p.connection_state)),
    );
    keys.add(p.key);
    datasets(p.datasets);
    datasets(p.allowed_datasets);
    datasets(p.last_success_datasets);
    requireValue(
      p.allowed_datasets.every((x) => (p.datasets as Dataset[]).includes(x)),
    );
    requireValue(
      p.implemented ||
        (p.connection_state === "unavailable" &&
          p.manual_sync_supported === false &&
          p.allowed_datasets.length === 0),
    );
    timestamp(p.last_success_at, true);
    timestamp(p.latest_session_at, true);
    if (p.last_run !== null)
      requireValue(readRun(p.last_run).provider === p.key);
  }
  return s as Status;
}
async function verifyArtifact(value: unknown, body: Body, owner: string) {
  const a = object(value),
    { content_hash, ...content } = a;
  requireValue(
    a.schema_version === "data-sync-run-v0.1" &&
      a.athlete_id === owner &&
      a.planning_authorized === false &&
      canonical(a.proposal) === canonical(body),
  );
  requireValue(
    a.artifact_id ===
      `pt-data-sync:${owner.replaceAll("-", "")}:${body.provider}:${body.request_id.replaceAll("-", "")}` &&
      a.request_hash === (await sha(body)) &&
      content_hash === (await sha(content)),
  );
  timestamp(a.created_at);
  return a;
}
export async function readReceipt(
  value: unknown,
  pending: Pending,
): Promise<Receipt> {
  const r = object(value),
    body = readBody(JSON.parse(pending.body));
  requireValue(
    r.schema_version === "data-sync-receipt-v0.1" &&
      r.athlete_id === pending.owner &&
      r.committed === true &&
      r.planning_authorized === false &&
      typeof r.reused === "boolean",
  );
  const start = await verifyArtifact(r.start, body, pending.owner),
    run = readRun(r.run);
  requireValue(
    start.stage === "started" &&
      run.request_id === body.request_id &&
      run.provider === body.provider &&
      run.started_at === start.created_at &&
      run.deadline_at === start.deadline_at &&
      canonical(run.window) === canonical(start.window) &&
      canonical(run.requested_datasets) === canonical(body.datasets),
  );
  if (r.result !== null) {
    const end = await verifyArtifact(r.result, body, pending.owner),
      ref = object(end.start_reference);
    requireValue(
      end.stage === "finished" &&
        ref.artifact_id === start.artifact_id &&
        ref.content_hash === start.content_hash &&
        end.outcome === run.state &&
        run.finished_at === end.created_at &&
        canonical(end.datasets) === canonical(run.datasets) &&
        run.error_code === end.error_code &&
        run.may_have_saved_data === end.may_have_saved_data,
    );
    requireValue(
      run.state !== "running" &&
        run.state !== "interrupted" &&
        canonical(run.datasets.map((x) => x.dataset)) ===
          canonical(body.datasets),
    );
  } else
    requireValue(
      ["running", "interrupted"].includes(run.state) &&
        run.finished_at === null,
    );
  return r as Receipt;
}
export function displayTime(value: string | null, timezone: string) {
  return value
    ? new Intl.DateTimeFormat("hu-HU", {
        timeZone: timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "Még nincs rögzítve";
}
export function preservedPlanResult(d: DatasetResult) {
  return d.dataset === "targets" && d.state === "succeeded" &&
    d.error_code === "DATA_SYNC_PROTECTED_PLANS_SKIPPED" &&
    Number.isSafeInteger(d.skipped) && Number(d.skipped) > 0 &&
    d.skip_reasons !== undefined &&
    Object.keys(d.skip_reasons).length === 1 &&
    d.skip_reasons.protected_plan === d.skipped;
}
// Presentation only: immutable receipts keep their original partial outcome.
// Recognize a complete census, with no other omission or pairing problem.
export function preservedPlansOnly(run: Run | null) {
  return !!run && run.state === "partial" && run.finished_at !== null &&
    run.error_code === "DATA_SYNC_PROTECTED_PLANS_SKIPPED" &&
    run.requested_datasets.length > 0 &&
    new Set(run.requested_datasets).size === run.requested_datasets.length &&
    run.datasets.length === run.requested_datasets.length &&
    run.datasets.some(preservedPlanResult) &&
    run.datasets.every((d, i) =>
      d.dataset === run.requested_datasets[i] && d.state === "succeeded" &&
      [d.imported, d.updated, d.skipped].every((n) =>
        Number.isSafeInteger(n) && Number(n) >= 0) &&
      (!d.pairing || d.pairing.conflicts === 0 && d.pairing.ambiguous === 0) &&
      (preservedPlanResult(d) || d.skipped === 0 && d.error_code === null),
    );
}
export function hasSuccessfulTransfer(p: Provider) {
  return !!p.last_success_at || p.last_run?.state === "succeeded" ||
    preservedPlansOnly(p.last_run);
}
export function continuationOnly(run: Run | null) {
  if (!run || run.state !== "partial" || run.finished_at === null ||
      !["DATA_SYNC_DETAILS_PENDING", "DATA_SYNC_PROTECTED_PLANS_SKIPPED"].includes(run.error_code ?? "") ||
      !run.requested_datasets.length || new Set(run.requested_datasets).size !== run.requested_datasets.length ||
      run.datasets.length !== run.requested_datasets.length) return false;
  let pending = false;
  return run.datasets.every((d, i) => {
    if (d.dataset !== run.requested_datasets[i] || d.state !== "succeeded" ||
        ![d.imported, d.updated, d.skipped].every(n => Number.isSafeInteger(n) && Number(n) >= 0) ||
        d.pairing && (d.pairing.conflicts !== 0 || d.pairing.ambiguous !== 0)) return false;
    if (d.dataset === "session_details" && d.error_code === "DATA_SYNC_DETAILS_PENDING") {
      const detail = d.details;
      pending = !!detail && Number(d.skipped) > 0 && detail.pending_sessions === d.skipped && detail.pending_days > 0 &&
        d.skip_reasons !== undefined && Object.keys(d.skip_reasons).length === 1 && d.skip_reasons.details_batch_pending === d.skipped &&
        detail.fetched_sessions === d.updated && detail.with_samples + detail.without_samples === detail.fetched_sessions &&
        detail.already_complete + detail.fetched_sessions + detail.pending_sessions === detail.requested_sessions;
      return pending;
    }
    return preservedPlanResult(d) || d.skipped === 0 && d.error_code === null;
  }) && pending;
}
export function lastRunTime(p: Provider, timezone: string) {
  if (!p.last_run) return displayTime(null, timezone);
  if (p.last_run.state === "running") return "Folyamatban";
  return p.last_run.finished_at
    ? displayTime(p.last_run.finished_at, timezone) : "Nem igazolható";
}
export function connectionAttention(p: Provider) {
  return p.implemented && (
    p.connection_state !== "connected" ||
    p.allowed_datasets.length < p.datasets.length ||
    ["DATA_SYNC_RECONNECT_REQUIRED", "DATA_SYNC_PERMISSION_MISSING",
      "DATA_SYNC_CONFIGURATION_REQUIRED", "DATA_SYNC_NOT_CONNECTED"].includes(
      p.last_run?.error_code ?? "") || p.last_run?.datasets.some(d =>
        ["DATA_SYNC_RECONNECT_REQUIRED", "DATA_SYNC_PERMISSION_MISSING", "DATA_SYNC_CONFIGURATION_REQUIRED", "DATA_SYNC_NOT_CONNECTED"].includes(d.error_code ?? ""))
  );
}
export function providerState(p: Provider) {
  if (p.connection_state !== "connected")
    return {
      not_connected: "Kapcsolódás szükséges",
      reconnect_required: "Újracsatlakozás szükséges",
      configuration_required: "Kapcsolat beállítása szükséges",
      unavailable: "Későbbi integráció",
    }[p.connection_state];
  if (p.allowed_datasets.length < p.datasets.length)
    return "Hiányzó adathozzáférés";
  const codes = [p.last_run?.error_code, ...(p.last_run?.datasets.map(d => d.error_code) ?? [])];
  if (codes.includes("DATA_SYNC_RECONNECT_REQUIRED")) return "Újracsatlakozás szükséges";
  if (codes.includes("DATA_SYNC_PERMISSION_MISSING")) return "Hiányzó adathozzáférés";
  if (preservedPlansOnly(p.last_run)) return "Frissítés befejezve";
  if (continuationOnly(p.last_run)) return "Átvétel folytatható";
  return p.last_run
    ? {
        running: "Frissítés folyamatban",
        succeeded: "Frissítés befejezve",
        partial: "Részben sikerült",
        failed: "Frissítés sikertelen",
        interrupted: "Megszakadt vagy nem igazolható",
      }[p.last_run.state]
    : "Még nincs rögzített szinkron";
}
export function attention(p: Provider) {
  return (
    p.implemented &&
    (connectionAttention(p) ||
      (!!p.last_run &&
        ["partial", "failed", "interrupted"].includes(p.last_run.state) &&
        !preservedPlansOnly(p.last_run) && !continuationOnly(p.last_run)))
  );
}
