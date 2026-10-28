import type { PlannedPart, PlannedPhase, Series } from "./contracts";

export type Boundary = { ms: number; labels: string[] };
export type ManualReference = { version: "manual-plan-reference-v0.1"; first_ms: number; work_ms: number; recovery_ms: number; count: number };
export type PhaseGap = { id: string; from_ms: number; to_ms: number; kind: "wait" | "unassigned" };
export type PhaseTransition = { id: string; label: string; end_ms: number; next_ms: number | null; advance: "MANUAL" | "UNKNOWN" };
export type DistanceAlignment = { part: PlannedPart | null; distanceUsed: boolean; source: Series | null; reasons: string[]; gaps: PhaseGap[]; transitions: PhaseTransition[] };
const validTime = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && v <= 1e12;
export function readReference(value: unknown): ManualReference {
  if (!value || typeof value !== "object") throw new Error("A kézi tervjelölés nem olvasható.");
  const v = value as ManualReference;
  if (v.version !== "manual-plan-reference-v0.1" || !validTime(v.first_ms) || !validTime(v.work_ms) || v.work_ms === 0 || !validTime(v.recovery_ms) ||
      !Number.isInteger(v.count) || v.count < 1 || v.count > 99 || v.first_ms + v.count * v.work_ms + (v.count - 1) * v.recovery_ms > 1e12)
    throw new Error("Add meg a kezdőpontot, a munkaszakasz és a köztes pihenő hosszát, valamint 1–99 ismétlést. Nulla pihenőt is külön adj meg.");
  return v;
}
export function readClock(value: string): number {
  const match = /^(?:(\d+):([0-5]\d):|([0-9]+):)([0-5]\d)(?:[.,](\d{1,3}))?$/.exec(value.trim());
  if (!match) throw new Error("Az idő formátuma perc:mp, például 20:00 vagy 0:00. Óra:perc:mp is megadható.");
  const ms = ((match[1] ? Number(match[1]) * 3600 + Number(match[2]) * 60 : Number(match[3]) * 60) + Number(match[4])) * 1000 + Number((match[5] ?? "").padEnd(3, "0"));
  if (!validTime(ms)) throw new Error("A megadott idő túl nagy.");
  return ms;
}
export function manualPart(value: ManualReference): PlannedPart {
  const v = readReference(value), phases: PlannedPhase[] = []; let cursor = 0;
  function append(label: string, length: number) {
    phases.push({ id: "manual-" + phases.length, label, source_block_id: null, from_ms: cursor, to_ms: cursor + length, duration_ms: length });
    cursor += length;
  }
  if (v.first_ms > 0) append("Munka előtti rész", v.first_ms);
  for (let i = 0; i < v.count; i++) {
    append(`${i + 1}. munka`, v.work_ms);
    if (i < v.count - 1 && v.recovery_ms > 0) append(`${i + 1}. köztes pihenő`, v.recovery_ms);
  }
  return { index: 0, phases, total_ms: cursor, issues: [] };
}

// Project the prescription onto this exercise's original cumulative distance clock.
// A crossing is the first recorded sample reaching the goal, never a guessed lap.
export function alignDistancePhases(part: PlannedPart | null, series: Series[], starts: Record<string, number> = {}, clockIssues: string[] = []): DistanceAlignment {
  if (!part) return { part: null, distanceUsed: false, source: null, reasons: [], gaps: [], transitions: [] };
  const reasons = new Set<string>(), candidates = series.filter(s => s.metric_key === "distance_m" && s.source_type === "DISTANCE" && !s.derived);
  const oneExercise = new Set(series.map(s => s.exercise_index)).size === 1;
  const source = oneExercise && candidates.length === 1 ? candidates[0] : null;
  const interval = source?.interval_ms ?? null;
  const points: { index: number; value: number }[] = [];
  let distanceValid = source !== null && interval !== null && interval > 0, previous = -Infinity;
  for (const [index, value] of (source?.values ?? []).entries()) {
    if (value === null) continue;
    if (!Number.isFinite(value) || value < 0 || value < previous) distanceValid = false;
    previous = value; points.push({ index, value });
  }
  function crossing(from: number, goal: number): number | null {
    if (goal === 0) return from;
    if (!source) { reasons.add(candidates.length > 1 || !oneExercise ? "DISTANCE_SOURCE_AMBIGUOUS" : "DISTANCE_SOURCE_MISSING"); return null; }
    if (!distanceValid || interval === null) { reasons.add("DISTANCE_CLOCK_INVALID"); return null; }
    const start = from / interval, baseline = source.values[start];
    if (!Number.isInteger(start) || baseline === undefined || baseline === null) {
      reasons.add("DISTANCE_START_UNKNOWN"); return null;
    }
    const target = baseline + goal;
    if (!Number.isFinite(target) || target <= baseline) { reasons.add("DISTANCE_CLOCK_INVALID"); return null; }
    let low = 0, high = points.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (points[middle].value < target) low = middle + 1; else high = middle;
    }
    const point = points[low];
    if (!point || point.index * interval > 1e12) { reasons.add("DISTANCE_GOAL_NOT_REACHED"); return null; }
    // A missing sample immediately before the crossing leaves its time uncertain.
    if (point.index === 0 || source.values[point.index - 1] === null || source.values[point.index - 1] === undefined) {
      reasons.add("DISTANCE_CROSSING_GAP"); return null;
    }
    // The chart's 0:00 is its first observed sample, which need not read 0 m.
    // Keep the native counter intact and use its known value as the reference.
    // This is a nominal observed-clock alignment, not a provider phase event.
    if (from === 0 && baseline > 0) reasons.add("DISTANCE_INITIAL_OFFSET");
    return point.index * interval;
  }
  const observationEnd = Math.max(0, ...series.filter(s => s.interval_ms !== null && s.values.length > 0).map(s => (s.values.length - 1) * s.interval_ms!));
  const gaps: PhaseGap[] = [], transitions: PhaseTransition[] = [];
  let cursor: number | null = clockIssues.length ? null : 0, distanceUsed = false, lastKnown = 0;
  if (clockIssues.length) reasons.add("RECORDING_CLOCK_UNRESOLVED");
  const phases = part.phases.map((phase, index) => {
    const from = cursor;
    let end: number | null = null;
    if (from !== null && phase.duration_ms !== null) {
      if (from + phase.duration_ms <= 1e12) end = from + phase.duration_ms;
      else reasons.add("PLAN_TIME_TOO_LARGE");
    } else if (from !== null && phase.distance_m !== undefined) {
      end = crossing(from, phase.distance_m);
      if (end !== null && phase.distance_m > 0) distanceUsed = true;
    } else if (from !== null) reasons.add("PLAN_DURATION_UNKNOWN");
    if (end !== null) lastKnown = end;
    cursor = end;
    if (end !== null && index < part.phases.length - 1 && end > observationEnd) {
      cursor = null; reasons.add("PHASE_GOAL_AFTER_RECORDING_END");
    } else if (end !== null && index < part.phases.length - 1 && (phase.advance === "MANUAL" || phase.advance === "UNKNOWN")) {
      const next = starts[phase.id];
      const valid = validTime(next) && next >= end && next <= observationEnd;
      transitions.push({ id: phase.id, label: phase.label, end_ms: end, next_ms: valid ? next : null, advance: phase.advance });
      if (valid) {
        if (next > end) gaps.push({ id: "wait-" + phase.id, from_ms: end, to_ms: next, kind: "wait" });
        cursor = next; lastKnown = next;
      } else {
        cursor = null;
        reasons.add(phase.advance === "MANUAL" ? "MANUAL_ADVANCE_TIME_UNKNOWN" : "ADVANCE_MODE_UNKNOWN");
      }
    }
    return { ...phase, from_ms: from, to_ms: end };
  });
  const issues = part.issues.filter(i => i !== "PLAN_DURATION_UNKNOWN");
  if (cursor === null) issues.push("PLAN_DURATION_UNKNOWN");
  if (lastKnown < observationEnd) gaps.push({ id: "unassigned", from_ms: lastKnown, to_ms: observationEnd, kind: "unassigned" });
  return { part: { ...part, phases, total_ms: cursor, issues }, distanceUsed, source: distanceUsed ? source : null, reasons: [...reasons], gaps, transitions };
}

export function readTransitions(value: unknown, part: PlannedPart): Record<string, number> {
  if (!value || typeof value !== "object") throw new Error("A kézi kezdőpontok nem olvashatók.");
  const v = value as { version: string; part_index: number; starts: Record<string, unknown> };
  if (v.version !== "phase-transitions-v0.1" || v.part_index !== part.index || !v.starts || typeof v.starts !== "object" || Array.isArray(v.starts) || Object.keys(v.starts).length > 2048) throw new Error("A kézi kezdőpontok másik tervrészhez tartoznak.");
  const result: Record<string, number> = {};
  for (const [id, ms] of Object.entries(v.starts)) {
    if (!part.phases.some(p => p.id === id && (p.advance === "MANUAL" || p.advance === "UNKNOWN")) || !validTime(ms)) throw new Error("A kézi kezdőpont nem ehhez a szakaszhoz tartozik.");
    result[id] = ms;
  }
  return result;
}
export function planBoundaries(part: PlannedPart | null): Boundary[] {
  const result = new Map<number, Set<string>>();
  for (const phase of part?.phases ?? []) for (const [ms, kind] of [[phase.from_ms, "kezdete"], [phase.to_ms, "vége"]] as const) {
    if (ms === null) continue;
    const labels = result.get(ms) ?? new Set<string>(); labels.add(phase.label + " " + kind); result.set(ms, labels);
  }
  return [...result].sort((a, b) => a[0] - b[0]).map(([ms, labels]) => ({ ms, labels: [...labels] }));
}
export function visibleBoundaries(boundaries: Boundary[], from: number, to: number) {
  return boundaries.filter(b => b.ms >= from && b.ms <= to);
}
export function positionedBoundaries(boundaries: Boundary[], from: number, to: number) {
  const result: { boundary: Boundary; x: number; showLabel: boolean }[] = []; let previous = -Infinity;
  for (const boundary of visibleBoundaries(boundaries, from, to)) {
    const x = 76 + (boundary.ms - from) / Math.max(1, to - from) * 794, showLabel = x - previous >= 75;
    if (showLabel) previous = x;
    result.push({ boundary, x, showLabel });
  }
  return result;
}
