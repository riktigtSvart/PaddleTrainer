import { addDays, object, sha } from "./contracts";
import type { TrainingReview } from "./training-plan";
import { spacingHours } from "./training-load";

export type CoordinatedBlock = {
  key: string;
  mesocycle_id: string;
  ordinal: number;
  start_date: string;
  end_date: string;
  kind: "steady" | "entry" | "build" | "consolidation";
  volume_percent: number;
  max_sessions: number;
  max_minutes: number;
};
export type MesocycleCoordination = {
  schema_version: "training-mesocycle-coordination-v0.1";
  rules_version: "training-mesocycle-policy-v0.1";
  mode: "coordinated" | "short_review";
  wave_percentages: number[];
  date_basis: "civil_days_from_saved_mesocycle_start";
  above_starting_budget_allowed: false;
  intensity_progression_applied: false;
  personal_response_model_applied: false;
  recommended_end_date: string;
  recommended_mesocycle_ids: string[];
  blocks: CoordinatedBlock[];
};
export const waveLabels: Record<CoordinatedBlock["kind"], string> = {
  steady: "Egyenletes időkeret",
  entry: "Rávezető szakasz",
  build: "Építő szakasz",
  consolidation: "Könnyebb szakasz",
};
const invalid = () =>
  Error(
    "A mezociklusok összehangolása eltér a mentett szakaszoktól vagy terhelési kerettől.",
  );
const days = (a: string, b: string) =>
  (Date.parse(b) - Date.parse(a)) / 86400000 + 1;
async function same(actual: unknown, expected: unknown) {
  if ((await sha(actual)) !== (await sha(expected))) throw invalid();
}

export async function validateMesocycleCoordination(
  review: Record<string, unknown>,
) {
  const result = object(review.result);
  if (result.mesocycle_coordination === undefined) {
    if (
      [
        "training-plan-policy-v0.6",
        "training-plan-policy-v0.7",
        "training-plan-policy-v0.8", "training-plan-policy-v0.9", "training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15",
      ].includes(String(object(result.policy ?? {}).version))
    )
      throw invalid();
    return;
  }
  const inputs = object(review.inputs),
    context = object(result.mesocycle_coordination),
    budget = object(object(result.prescription_context).starting_budget),
    first = String(review.start_date),
    last = String(review.end_date);
  if (
    ![
      "training-plan-policy-v0.6",
      "training-plan-policy-v0.7",
      "training-plan-policy-v0.8", "training-plan-policy-v0.9", "training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15",
    ].includes(String(object(result.policy ?? {}).version))
  )
    throw invalid();
  if (!Array.isArray(inputs.periods) || !Array.isArray(inputs.days))
    throw invalid();
  const periods = inputs.periods
    .map(object)
    .filter((p) => p.period_type === "MESOCYCLE")
    .sort(
      (a, b) =>
        String(a.start_date).localeCompare(String(b.start_date)) ||
        String(a.id).localeCompare(String(b.id)),
    );
  const known = new Set<string>();
  for (const p of periods) {
    if (
      typeof p.id !== "string" ||
      known.has(p.id) ||
      typeof p.start_date !== "string" ||
      typeof p.end_date !== "string" ||
      !Number.isInteger(days(p.start_date, p.end_date)) ||
      days(p.start_date, p.end_date) < 1
    )
      throw invalid();
    addDays(p.start_date, 0);
    addDays(p.end_date, 0);
    known.add(p.id);
  }
  if (typeof review.coordinate_mesocycles !== "boolean") throw invalid();
  const future = periods.filter((p) => String(p.end_date) >= first).slice(0, 2),
    coordinated = review.coordinate_mesocycles;
  const blocks: CoordinatedBlock[] = [];
  for (const period of periods) {
    const start = String(period.start_date),
      end = String(period.end_date);
    if (end < first || start > last) continue;
    const count = Math.ceil(days(start, end) / 7);
    for (let i = 0; i < count; i++) {
      const low = addDays(start, i * 7),
        high =
          addDays(start, i * 7 + 6) < end ? addDays(start, i * 7 + 6) : end;
      if (high < first || low > last) continue;
      let percent = 100,
        kind: CoordinatedBlock["kind"] = "steady";
      if (coordinated && count > 1) {
        if (i === count - 1 && days(low, high) >= 4) {
          percent = 70;
          kind = "consolidation";
        } else if (count === 2) kind = "build";
        else {
          percent = [80, 90, 100, 70][i % 4];
          if (
            percent === 70 &&
            i === count - 2 &&
            days(addDays(start, (count - 1) * 7), end) >= 4
          )
            percent = 100;
          kind =
            percent === 70
              ? "consolidation"
              : percent === 80
                ? "entry"
                : "build";
        }
      }
      const minutes = coordinated
        ? Math.floor(
            Math.floor(
              (Number(budget.max_minutes_per_7_days) *
                percent *
                days(low, high)) /
                700,
            ) / 5,
          ) * 5
        : Number(budget.max_minutes_per_7_days);
      blocks.push({
        key: `${period.id}:${i + 1}`,
        mesocycle_id: String(period.id),
        ordinal: i + 1,
        start_date: low,
        end_date: high,
        kind,
        volume_percent: percent,
        max_sessions: Math.min(
          Number(budget.max_sessions_per_7_days),
          days(low, high),
        ),
        max_minutes: minutes,
      });
    }
  }
  const suggested = String(future.at(-1)?.end_date ?? last);
  await same(context, {
    schema_version: "training-mesocycle-coordination-v0.1",
    rules_version: "training-mesocycle-policy-v0.1",
    mode: coordinated ? "coordinated" : "short_review",
    wave_percentages: [80, 90, 100, 70],
    date_basis: "civil_days_from_saved_mesocycle_start",
    above_starting_budget_allowed: false,
    intensity_progression_applied: false,
    personal_response_model_applied: false,
    recommended_end_date:
      suggested < addDays(first, 365) ? suggested : addDays(first, 365),
    recommended_mesocycle_ids: future.map((p) => p.id),
    blocks,
  });
  const dates = new Set<string>();
  const candidateLists = [
    ...(result.proposals as unknown[]),
    ...((result.alternatives as unknown[] | undefined) ?? []).flatMap(
      (g) => object(g).candidates as unknown[],
    ),
  ];
  for (const value of candidateLists) {
    const c = object(value),
      block = blocks.find(
        (b) => b.start_date <= String(c.date) && String(c.date) <= b.end_date,
      );
    const sourceDay = inputs.days.map(object).find((d) => d.date === c.date);
    if (
      !block ||
      c.training_period_id !== block.mesocycle_id ||
      sourceDay?.mesocycle_id !== block.mesocycle_id
    )
      throw invalid();
    if (coordinated && c.sport !== "STRENGTH") {
      const meta = object(
        object(object(result.prescription_context).by_candidate)[
          String(c.candidate_key)
        ],
      );
      const swim = meta.swimming ? object(meta.swimming) : null;
      const swimCaps = swim ? [swim.observed_cap_seconds, swim.declared_cap_seconds].filter(v => typeof v === "number") as number[] : [];
      const sourceCap = swim ? (swimCaps.length ? Math.min(...swimCaps) : swim.mode === "continuous" ? 1800 : 1200) : Number(meta.reference_cap_seconds ?? 1800);
      const cap = Math.min(sourceCap, Number(meta.maximum_seconds));
      const ceiling = Math.max(
        Number(meta.minimum_seconds),
        Math.floor((cap * block.volume_percent) / 100),
      );
      if (Number(c.duration_sec) > ceiling) throw invalid();
    }
  }
  for (const value of result.proposals as unknown[]) {
    const c = object(value);
    if (dates.has(String(c.date))) throw invalid();
    dates.add(String(c.date));
  }
  if (!coordinated && !["training-plan-policy-v0.9", "training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version))) return;
  // Rebuild the fixed commitments exactly as the server does: linked plans
  // never duplicate a completion; replaceable in-range plans are proposals.
  const absent = new Set(
    (result.events as unknown[])
      .map(object)
      .filter((e) => e.kind === "not_recorded_after_sync")
      .map((e) => e.workout_id),
  );
  const loads = (inputs.recent_sessions as unknown[]).map(object).map((s) => ({
    date: civilDay(String(review.timezone_name), String(s.started_at)),
    seconds: s.duration_sec,
    missed: false,
    at: s.started_at,
    sport: s.sport,
    known: false,
    rpe: s.rpe,
  }));
  for (const value of review.plan_snapshots as unknown[]) {
    const p = object(value),
      w = object(p.workout);
    if (
      w.status === "CANCELLED" ||
      p.linked === true ||
      (p.replaceable === true &&
        first <= String(w.date) &&
        String(w.date) <= last) ||
      (absent.has(w.id) && p.owned_sample !== true)
    )
      continue;
    loads.push({
      date: String(w.date),
      seconds:
        w.duration_sec ??
        (p.duration_estimate ? object(p.duration_estimate).upper_sec : null),
      missed: w.status === "SKIPPED" || absent.has(w.id),
      at:
        w.status === "SKIPPED" || absent.has(w.id)
          ? null
          : w.planned_start_time,
      sport: w.sport,
      known: p.owned_sample === true,
      rpe: null,
    });
  }
  const proposed = (result.proposals as unknown[]).map(object);
  for (const c of proposed) {
    const all = [
      ...loads,
      ...proposed.map((v) => ({
        date: String(v.date),
        seconds: v.duration_sec,
        missed: false,
        at: v.start_at,
      })),
    ];
    for (let offset = 0; offset < 7; offset++) {
      const low = addDays(String(c.date), -offset),
        high = addDays(low, 6);
      const entries = all.filter((v) => low <= v.date && v.date <= high);
      if (
        entries.length > Number(budget.max_sessions_per_7_days) ||
        entries.some((v) => v.seconds === null && !v.missed) ||
        entries.reduce((sum, v) => sum + Number(v.seconds ?? 0), 0) >
          Number(budget.max_minutes_per_7_days) * 60
      )
        throw invalid();
    }
    if (
      [
        ...loads.map((v) => ({at:v.at,sport:v.sport,known:v.known,rpe:v.rpe})),
        ...proposed
          .filter((v) => v.candidate_key !== c.candidate_key)
          .map((v) => ({at:v.start_at,sport:v.sport,known:true,rpe:null})),
      ].some(
        (v) =>
          v.at &&
          Math.abs(Date.parse(String(v.at)) - Date.parse(String(c.start_at))) <
            (object(result.policy).spacing_rules_version === "training-start-spacing-v0.1" ? spacingHours(v.sport,c.sport,v.known,v.rpe) : 36) * 3600000,
      )
    )
      throw invalid();
  }
  if (!coordinated) return;
  for (const block of blocks) {
    const fixed = loads.filter(
      (v) => block.start_date <= v.date && v.date <= block.end_date,
    );
    const planned = proposed.filter(
      (c) =>
        block.start_date <= String(c.date) && String(c.date) <= block.end_date,
    );
    if (!planned.length) continue; // Existing protected load may already exceed a ceiling.
    if (
      fixed.some((v) => v.seconds === null && !v.missed) ||
      fixed.length + planned.length > block.max_sessions ||
      fixed.reduce((sum, v) => sum + Number(v.seconds ?? 0), 0) +
        planned.reduce((sum, c) => sum + Number(c.duration_sec), 0) >
        block.max_minutes * 60
    )
      throw invalid();
  }
}

function civilDay(zone: string, instant: string) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(instant));
}

export function blockProposals(
  review: TrainingReview,
  block: CoordinatedBlock,
) {
  const candidates = review.result.proposals.filter(
    (c) => block.start_date <= c.date && c.date <= block.end_date,
  );
  return {
    count: candidates.length,
    minutes: candidates.reduce((sum, c) => sum + c.duration_sec / 60, 0),
    capabilities: [...new Set(candidates.map((c) => c.capability_key))],
  };
}
