import { addDays, object } from "./contracts";
import type { Reference } from "./contracts";

export type ExecutionReconciliation = {
  schema_version: "training-execution-reconciliation-v0.1";
  athlete_id: string;
  sync_windows: {
    start_reference: Reference;
    result_reference: Reference;
    provider: "POLAR";
    started_at: string;
    finished_at: string;
    from_at: string;
    to_exclusive_at: string;
    timezone_name: string;
    sessions: { imported: number; updated: number; skipped: 0 };
  }[];
  resolved_links: {
    session_id: string;
    workout_id: string;
    basis: "provider_exact";
    provider: "POLAR";
  }[];
  ambiguous_workout_ids: string[];
};

const invalid = () =>
  Error("A teljesítés-egyeztetés forrása vagy időbeli lefedése hibás.");
function instant(value: unknown) {
  if (
    typeof value !== "string" ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    throw invalid();
  return Date.parse(value);
}
function reference(value: unknown, prefix: string) {
  const result = object(value);
  if (
    typeof result.artifact_id !== "string" ||
    !result.artifact_id.startsWith(prefix) ||
    !/^[a-f0-9]{32}$/.test(result.artifact_id.slice(prefix.length)) ||
    typeof result.content_hash !== "string" ||
    !/^[a-f0-9]{64}$/.test(result.content_hash)
  )
    throw invalid();
  return result as unknown as Reference;
}
function midnight(value: number, zone: string, date: string) {
  const parts = new Map(
    new Intl.DateTimeFormat("sv-SE", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(value)
      .map((part) => [part.type, part.value]),
  );
  return (
    `${parts.get("year")}-${parts.get("month")}-${parts.get("day")}` === date &&
    ["hour", "minute", "second"].every(
      (key) => parts.get(key as Intl.DateTimeFormatPartTypes) === "00",
    )
  );
}

export function validateExecutionReconciliation(
  review: Record<string, unknown>,
) {
  const result = object(review.result),
    events = result.events as unknown[];
  if (result.execution_reconciliation === undefined) {
    if (
      events.some((value) => object(value).kind === "not_recorded_after_sync")
    )
      throw invalid();
    return;
  }
  const context = object(result.execution_reconciliation),
    inputs = object(review.inputs);
  if (
    context.schema_version !== "training-execution-reconciliation-v0.1" ||
    context.athlete_id !== review.athlete_id ||
    !Array.isArray(context.sync_windows) ||
    !Array.isArray(context.resolved_links) ||
    !Array.isArray(context.ambiguous_workout_ids) ||
    !Array.isArray(inputs.recent_sessions)
  )
    throw invalid();
  const cutoff = instant(inputs.captured_at);
  const plans = new Map(
    (review.plan_snapshots as unknown[]).map((value) => {
      const snapshot = object(value);
      return [String(object(snapshot.workout).id), snapshot];
    }),
  );
  const sessions = new Map(
    inputs.recent_sessions.map((value) => {
      const session = object(value);
      return [String(session.id), session];
    }),
  );
  const sources = new Map<string, Record<string, unknown>>();
  const prefix = `pt-data-sync:${String(review.athlete_id).replaceAll("-", "")}:POLAR:`;
  for (const value of context.sync_windows) {
    const source = object(value),
      start = reference(source.start_reference, prefix),
      end = reference(source.result_reference, prefix),
      counts = object(source.sessions);
    if (
      source.provider !== "POLAR" ||
      start.artifact_id !== end.artifact_id ||
      start.content_hash === end.content_hash ||
      sources.has(end.content_hash) ||
      instant(source.started_at) > instant(source.finished_at) ||
      instant(source.finished_at) > cutoff ||
      instant(source.from_at) >= instant(source.to_exclusive_at) ||
      typeof source.timezone_name !== "string" ||
      counts.skipped !== 0 ||
      [counts.imported, counts.updated].some(
        (count) => !Number.isSafeInteger(count) || Number(count) < 0,
      )
    )
      throw invalid();
    new Intl.DateTimeFormat("hu-HU", { timeZone: source.timezone_name });
    sources.set(end.content_hash, source);
  }
  const linked = new Set<string>();
  for (const value of context.resolved_links) {
    const link = object(value),
      session = sessions.get(String(link.session_id)),
      snapshot = plans.get(String(link.workout_id));
    if (
      link.basis !== "provider_exact" ||
      link.provider !== "POLAR" ||
      !session ||
      !snapshot ||
      session.planned_workout_id !== null ||
      snapshot.linked !== true ||
      linked.has(String(link.session_id))
    )
      throw invalid();
    linked.add(String(link.session_id));
  }
  const ambiguous = context.ambiguous_workout_ids;
  if (
    new Set(ambiguous).size !== ambiguous.length ||
    ambiguous.some((id) => typeof id !== "string" || !plans.has(id))
  )
    throw invalid();
  for (const value of events) {
    const event = object(value);
    if (event.kind !== "not_recorded_after_sync") continue;
    const ref = reference(event.sync_reference, prefix),
      source = sources.get(ref.content_hash),
      snapshot = plans.get(String(event.workout_id));
    if (
      !source ||
      !snapshot ||
      object(source.result_reference).artifact_id !== ref.artifact_id ||
      event.can_confirm_missed !== false ||
      event.session_id !== undefined ||
      event.checked_through !== source.started_at ||
      ambiguous.includes(event.workout_id) ||
      snapshot.linked === true
    )
      throw invalid();
    const workout = object(snapshot.workout),
      span = object(event.absence_window),
      first = instant(span.from_at),
      last = instant(span.to_exclusive_at);
    if (
      ["COMPLETED", "SKIPPED", "CANCELLED"].includes(String(workout.status)) ||
      first >= last ||
      first < instant(source.from_at) ||
      last > instant(source.to_exclusive_at) ||
      last > instant(source.started_at)
    )
      throw invalid();
    if (workout.planned_start_time && workout.duration_sec !== null) {
      if (
        first !== instant(workout.planned_start_time) ||
        last - first !== Number(workout.duration_sec) * 1000
      )
        throw invalid();
    } else if (
      typeof workout.date !== "string" ||
      typeof review.timezone_name !== "string" ||
      !midnight(first, review.timezone_name, workout.date) ||
      !midnight(last, review.timezone_name, addDays(workout.date, 1))
    )
      throw invalid();
  }
}
