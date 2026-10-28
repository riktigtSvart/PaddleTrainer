import type { PlannedPart, Series } from "./contracts";
import { alignDistancePhases, readTransitions } from "./plan-boundaries";
import type { DistanceAlignment } from "./plan-boundaries";

// Deliberately tentative motion hypotheses, following phase_reconciliation.py.
// These rules never establish a provider event and never inspect heart rate.
export const candidateRules = "motion-transition-v0.1";
export const motionPolicy = Object.freeze({ low_kmh: 2, moving_kmh: 4, low_ms: 3000, moving_ms: 5000,
  resume_ms: 60000, horizon_ms: 300000, margin_ms: 5000, max_options: 8 });
export type PhaseCandidate = { id: string; transition_id: string; phase_label: string; next_label: string;
  goal_ms: number; start_ms: number; from_ms: number; to_ms: number; lead_ms: number;
  low_from_ms: number; low_to_ms: number; moving_ms: number; preview_to_ms: number;
  interval_ms: number; kind: "short_phase_before_motion" | "motion_start" };
export type CandidateResult = { options: PhaseCandidate[]; reasons: string[]; truncated: boolean };
export type CandidateReceipt = { rules: typeof candidateRules; candidate_id: string; start_ms: number; suggested_ms: number;
  from_ms: number; to_ms: number; lead_ms: number; goal_ms: number };
export type SavedTransitions = { version: "phase-transitions-v0.1"; part_index: number;
  starts: Record<string, number>; motion_receipts?: Record<string, CandidateReceipt> };
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const time = (v: unknown): v is number => finite(v) && Number.isSafeInteger(v) && v <= 1e12;

export function transitionCandidates(part: PlannedPart | null, series: Series[], alignment: DistanceAlignment, clockIssues: string[] = []): CandidateResult {
  const result: CandidateResult = { options: [], reasons: [], truncated: false };
  const stop = (reason: string) => ({ ...result, reasons: [reason] });
  if (!part || alignment.part === null) return stop("PLAN_UNAVAILABLE");
  if (clockIssues.length) return stop("RECORDING_CLOCK_UNRESOLVED");
  const pending = alignment.transitions.find(t => t.next_ms === null);
  if (!pending) return stop("NO_PENDING_TRANSITION");
  if (pending.advance !== "MANUAL") return stop("ADVANCE_MODE_UNKNOWN");
  const index = part.phases.findIndex(p => p.id === pending.id), next = part.phases[index + 1], following = part.phases[index + 2];
  if (index < 0 || !next) return stop("PLAN_UNAVAILABLE");
  const speed = series.filter(s => s.source_type === "SPEED" && s.metric_key === "speed_kmh" && !s.derived);
  const distance = series.filter(s => s.source_type === "DISTANCE" && s.metric_key === "distance_m" && !s.derived);
  if (new Set(series.map(s => s.exercise_index)).size !== 1 || speed.length !== 1 || distance.length !== 1)
    return stop("MOTION_SOURCE_AMBIGUOUS_OR_MISSING");
  const s = speed[0], d = distance[0], dt = s.interval_ms;
  if (s.exercise_index !== part.index) return stop("PLAN_EXERCISE_CLOCK_MISMATCH");
  if (s.unit !== "km/h" || d.unit !== "m" || dt === null || !Number.isSafeInteger(dt) || dt <= 0 || dt > 5000 || d.interval_ms !== dt || s.values.length !== d.values.length)
    return stop("MOTION_GRID_UNSUITABLE");
  const n = s.values.length, last = (n - 1) * dt;
  if (n < 3 || n > 360000 || !time(last)) return stop("MOTION_GRID_UNSUITABLE");
  const missing = new Uint32Array(n + 1);
  let previous = -Infinity;
  for (let i = 0; i < n; i++) {
    const value = d.values[i];
    missing[i + 1] = missing[i] + (finite(value) ? 0 : 1);
    if (value !== null && (!finite(value) || value < previous)) return stop("DISTANCE_COUNTER_INVALID");
    if (finite(value)) previous = value;
  }
  const lowCount = Math.max(2, Math.ceil(motionPolicy.low_ms / dt));
  const movingCount = Math.max(2, Math.ceil(motionPolicy.moving_ms / dt));
  const high = new Uint32Array(n + 1), nextHigh = new Int32Array(n + 1);
  nextHigh[n] = -1;
  for (let i = n - 1; i >= 0; i--) {
    high[i] = finite(s.values[i]) && s.values[i]! >= motionPolicy.moving_kmh ? high[i + 1] + 1 : 0;
    nextHigh[i] = high[i] >= movingCount + 1 ? i : nextHigh[i + 1];
  }
  const shortLead = next.advance === "AUTOMATIC" && time(next.duration_ms) && next.duration_ms > 0 && next.duration_ms <= 30000 && following &&
    (finite(following.distance_m) && following.distance_m > 0 || time(following.duration_ms) && following.duration_ms >= 30000) ? next.duration_ms : 0;
  const leads = shortLead > 0 ? [shortLead, 0] : [0];
  const margin = Math.max(motionPolicy.margin_ms, 2 * dt);
  for (let i = 0; i < n;) {
    if (!finite(s.values[i]) || s.values[i]! > motionPolicy.low_kmh) { i++; continue; }
    const lowStart = i;
    while (i < n && finite(s.values[i]) && s.values[i]! <= motionPolicy.low_kmh) i++;
    const lowEnd = i, resumed = nextHigh[lowEnd];
    if (lowEnd - lowStart < lowCount || resumed < 0 || (resumed - lowEnd) * dt > motionPolicy.resume_ms || resumed * dt < pending.end_ms || resumed * dt > pending.end_ms + motionPolicy.horizon_ms) continue;
    // No missing motion sample is crossed between low speed and the resumption.
    if (s.values.slice(lowStart, resumed + movingCount + 1).some(v => !finite(v))) continue;
    const through = resumed + movingCount;
    if (missing[through + 1] !== missing[lowStart] || !finite(d.values[resumed]) || !finite(d.values[through]) || d.values[through]! <= d.values[resumed]!) continue;
    for (const lead of leads) {
      const proposed = resumed * dt - lead, from = Math.max(pending.end_ms, proposed - margin), to = Math.min(last - lead, proposed + margin);
      if (!time(proposed) || proposed < pending.end_ms || proposed > last || from > proposed || to < proposed) continue;
      if (result.options.length === motionPolicy.max_options) return { ...result, truncated: true };
      // Check the proposed continuation on the same observed distance clock.
      const trial = alignDistancePhases(part, series, { ...Object.fromEntries(alignment.transitions.filter(t => t.next_ms !== null).map(t => [t.id, t.next_ms!])), [pending.id]: proposed }, clockIssues);
      if (trial.part?.phases[index + 1]?.from_ms !== proposed) continue;
      const id = `${candidateRules}:${pending.id}:${pending.end_ms}:${lowStart * dt}:${lowEnd * dt}:${resumed * dt}:${lead}`;
      const option: PhaseCandidate = { id, transition_id: pending.id, phase_label: pending.label, next_label: next.label,
        goal_ms: pending.end_ms, start_ms: proposed, from_ms: from, to_ms: to, lead_ms: lead,
        low_from_ms: lowStart * dt, low_to_ms: lowEnd * dt, moving_ms: resumed * dt,
        preview_to_ms: Math.min(last, resumed * dt + 15000), interval_ms: dt,
        kind: lead > 0 ? "short_phase_before_motion" : "motion_start" };
      if (result.options.length < motionPolicy.max_options) result.options.push(option);
      else result.truncated = true;
    }
  }
  if (!result.options.length) result.reasons.push("NO_SUPPORTED_MOTION_PATTERN");
  return result;
}

export function candidateReceipt(option: PhaseCandidate, selected = option.start_ms): CandidateReceipt {
  return { rules: candidateRules, candidate_id: option.id, start_ms: selected, suggested_ms: option.start_ms,
    from_ms: option.from_ms, to_ms: option.to_ms, lead_ms: option.lead_ms, goal_ms: option.goal_ms };
}

export function readSavedTransitions(value: unknown, part: PlannedPart): { starts: Record<string, number>; receipts: Record<string, CandidateReceipt> } {
  const starts = readTransitions(value, part), raw = (value as SavedTransitions).motion_receipts;
  const receipts: Record<string, CandidateReceipt> = {};
  if (raw === undefined) return { starts, receipts };
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || Object.keys(raw).length > 2048) throw new Error("Az elfogadott becslések nem olvashatók.");
  for (const [id, r] of Object.entries(raw)) {
    if (!r || r.rules !== candidateRules || typeof r.candidate_id !== "string" || !r.candidate_id.startsWith(candidateRules + ":" + id + ":") || r.candidate_id.length > 2000 ||
        ![r.start_ms, r.suggested_ms, r.from_ms, r.to_ms, r.lead_ms, r.goal_ms].every(time) || r.lead_ms > 30000 || r.goal_ms > r.start_ms || r.from_ms < r.goal_ms || r.from_ms > r.suggested_ms || r.suggested_ms > r.to_ms || starts[id] !== r.start_ms)
      throw new Error("Az elfogadott becslés másik kezdőponthoz tartozik.");
    receipts[id] = { rules: r.rules, candidate_id: r.candidate_id, start_ms: r.start_ms, suggested_ms: r.suggested_ms,
      from_ms: r.from_ms, to_ms: r.to_ms, lead_ms: r.lead_ms, goal_ms: r.goal_ms };
  }
  return { starts, receipts };
}

export function reviseTransition(part: PlannedPart, alignment: DistanceAlignment, starts: Record<string, number>, receipts: Record<string, CandidateReceipt>, id: string, ms: number | null, receipt?: CandidateReceipt) {
  const index = part.phases.findIndex(p => p.id === id && (p.advance === "MANUAL" || p.advance === "UNKNOWN"));
  if (index < 0) throw new Error("A kezdőpont nem ehhez a szakaszhoz tartozik.");
  const row = alignment.transitions.find(t => t.id === id);
  if (ms !== null && (!time(ms) || !row || ms < row.end_ms)) throw new Error("A kezdés nem előzheti meg az előző cél elérését.");
  const updated = { ...starts }, kept = { ...receipts };
  if (ms !== starts[id]) for (const phase of part.phases.slice(index + 1)) { delete updated[phase.id]; delete kept[phase.id]; }
  delete kept[id];
  if (ms === null) delete updated[id];
  else { updated[id] = ms; if (receipt) kept[id] = receipt; }
  const value: SavedTransitions = { version: "phase-transitions-v0.1", part_index: part.index, starts: updated, motion_receipts: kept };
  readSavedTransitions(value, part);
  return value;
}

export function pickedCandidateTime(option: PhaseCandidate, ms: number): number {
  // The following distance phase still begins on an actual source sample.
  const point = Math.round((ms + option.lead_ms) / option.interval_ms) * option.interval_ms - option.lead_ms;
  return Math.max(option.goal_ms, Math.min(option.preview_to_ms, point));
}
