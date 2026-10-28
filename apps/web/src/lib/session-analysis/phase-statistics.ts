import type { HeartRateZones, MetricZones, Plan, PlannedPart, PlannedPhase, Series } from "./contracts";
import type { PhaseGap } from "./plan-boundaries";
import { graphTargets } from "./presentation";
import type { GraphTarget } from "./presentation";

export type PhaseZones = { heart_rate: HeartRateZones | null; speed: MetricZones | null; power: MetricZones | null };
export type WindowMean = { value: number | null; known_ms: number; observed_ms: number };
export type GoalTime = { below_ms: number; inside_ms: number; above_ms: number; known_ms: number; missing_ms: number };
export type PhaseResult = { id: string; label: string; kind: "phase" | "wait" | "unassigned"; phase: PlannedPhase | null;
  from_ms: number | null; to_ms: number | null; observed_ms: number | null; partial: boolean;
  distance_m: number | null; heart_rate: WindowMean; speed: WindowMean; power: WindowMean;
  target: GraphTarget | null; goal_time: GoalTime | null };

export function phaseTarget(phase: PlannedPhase, plan: Plan | null, zones: PhaseZones): GraphTarget | null {
  if (phase.target) {
    const proxy: Plan = { id: "phase-reference", date: "", title: "", description: null, sport: "", status: "", planned_start_time: null,
      duration_sec: null, distance_m: null, blocks: [{ id: phase.source_block_id ?? phase.id, position: 0, block_type: "WORK", name: phase.label,
        duration_sec: null, distance_m: null, intensity_type: phase.target.type, intensity_min: phase.target.low, intensity_max: phase.target.high,
        repeat_count: 1, parent_block_id: null }] };
    return graphTargets(proxy, zones)[0] ?? null;
  }
  return graphTargets(plan, zones).find(t => t.id === phase.source_block_id) ?? null;
}

/** Each interval [i*dt,(i+1)*dt) uses its left value, only with two valid endpoints.
 * Missing observations are not bridged. The final point is never extrapolated.
 */
export function windowMean(series: Series | null, from: number, to: number, target: GraphTarget | null = null): { mean: WindowMean; goal: GoalTime | null } {
  const observed = Math.max(0, to - from), mean: WindowMean = { value: null, known_ms: 0, observed_ms: observed };
  const goal: GoalTime | null = target && target.low !== null && target.high !== null ? { below_ms: 0, inside_ms: 0, above_ms: 0, known_ms: 0, missing_ms: observed } : null;
  if (!series || series.interval_ms === null || to <= from) return { mean, goal };
  const dt = series.interval_ms, first = Math.max(0, Math.floor(from / dt)), last = Math.min(series.values.length - 2, Math.ceil(to / dt) - 1);
  let average = 0;
  for (let i = first; i <= last; i++) {
    const v = series.values[i], next = series.values[i + 1];
    if (v === null || next === null || !Number.isFinite(v) || !Number.isFinite(next)) continue;
    const weight = Math.max(0, Math.min(to, (i + 1) * dt) - Math.max(from, i * dt));
    if (!weight) continue;
    const total = mean.known_ms + weight;
    average = average * (mean.known_ms / total) + v * (weight / total);
    mean.known_ms = total;
    if (goal && target) {
      goal.known_ms += weight;
      if (v < target.low!) goal.below_ms += weight;
      else if (v > target.high!) goal.above_ms += weight;
      else goal.inside_ms += weight;
    }
  }
  mean.value = mean.known_ms > 0 && Number.isFinite(average) ? average : null;
  if (goal) goal.missing_ms = Math.max(0, observed - goal.known_ms);
  return { mean, goal };
}

export function windowDistance(series: Series | null, from: number, to: number): number | null {
  if (!series || series.interval_ms === null || to <= from) return null;
  const a = from / series.interval_ms, b = to / series.interval_ms;
  if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b >= series.values.length) return null;
  let previous = series.values[a];
  if (previous === null) return null;
  for (let i = a + 1; i <= b; i++) {
    const v = series.values[i];
    if (v === null || !Number.isFinite(v) || v < previous) return null;
    previous = v;
  }
  const first = series.values[a];
  return first !== null && Number.isFinite(previous - first) ? previous - first : null;
}

export function phaseResults(part: PlannedPart | null, gaps: PhaseGap[], series: Series[], plan: Plan | null, zones: PhaseZones): PhaseResult[] {
  if (!part || new Set(series.map(s => s.exercise_index)).size !== 1) return [];
  const end = Math.max(0, ...series.filter(s => s.interval_ms !== null && s.values.length).map(s => (s.values.length - 1) * s.interval_ms!));
  function one(key: Series["metric_key"]) { const matching = series.filter(s => s.metric_key === key); return matching.length === 1 ? matching[0] : null; }
  const hr = one("heart_rate_bpm"), speed = one("speed_kmh"), power = one("power_w"), distance = one("distance_m");
  function result(id: string, label: string, kind: PhaseResult["kind"], phase: PlannedPhase | null, from: number | null, to: number | null): PhaseResult {
    const known = from !== null && to !== null, a = Math.min(end, from ?? 0), b = Math.max(a, Math.min(end, to ?? 0));
    const target = phase ? phaseTarget(phase, plan, zones) : null;
    const empty = { value: null, known_ms: 0, observed_ms: 0 };
    const adherence = known && target ? windowMean(target.family === "heart_rate" ? hr : target.family === "speed" ? speed : power, a, b, target).goal : null;
    return { id, label, kind, phase, from_ms: from, to_ms: to, observed_ms: known ? b - a : null, partial: known && to! > end,
      distance_m: known ? windowDistance(distance, a, b) : null,
      heart_rate: known ? windowMean(hr, a, b).mean : empty, speed: known ? windowMean(speed, a, b).mean : empty,
      power: known ? windowMean(power, a, b).mean : empty, target, goal_time: adherence };
  }
  return [...part.phases.map(p => result(p.id, p.label, "phase", p, p.from_ms, p.to_ms)),
    ...gaps.map(g => result(g.id, g.kind === "wait" ? "Várakozás / szakaszok között" : "Tervszakaszhoz nem rendelt idő", g.kind, null, g.from_ms, g.to_ms))]
    .sort((a, b) => (a.from_ms ?? Infinity) - (b.from_ms ?? Infinity) || (a.to_ms ?? Infinity) - (b.to_ms ?? Infinity));
}
