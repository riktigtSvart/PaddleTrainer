import {addDays, canonical, object} from './contracts';
import {localDay} from './plan-view';
import {effectiveLightRule, readDaylightContext} from '@/lib/training-options/daylight';
import {lightIntervals} from '@/lib/training-options/solar';
import {areaLightIntervals} from '@/lib/training-options/area-daylight';
import type {Candidate, TrainingReview} from './training-plan';

type Row = Record<string, unknown>;
export type AlternativeTiming = {
  window_start_at: string; window_end_at: string; day_end_at: string;
  duration_sec: number; expires_at: string; expires_inclusive: boolean;
  limiting_factors: string[]; goal_role: string; goal_rank: number; goal_key: string;
};
export type AlternativeAvailability = {
  schema_version: 'training-alternative-availability-v0.1';
  weather_evaluated: false; requires_fresh_check: true;
  by_candidate: Record<string, AlternativeTiming>;
};
const ranks: Record<string, number> = {primary_development: 0, secondary_development: 1, maintenance: 2};
export const goalRoleLabels: Record<string, string> = {
  primary_development: 'Fő célt fejlesztő edzés',
  secondary_development: 'Alcélt fejlesztő edzés',
  maintenance: 'Fenntartó edzés',
};
const check = (value: unknown) => {if (!value) throw Error('Az edzésalternatíva lejárata vagy célbesorolása nem ellenőrizhető.');};
const instant = (value: unknown) => typeof value === 'string' ? Date.parse(value) : NaN;

/** Recalculate from the captured opportunity and solar rule, not a claimed date. */
export async function validateAlternativeAvailability(review: Row) {
  const result = object(review.result);
  if (result.alternative_availability === undefined) return; // immutable older reviews
  const context = object(result.alternative_availability), rows = object(context.by_candidate), inputs = object(review.inputs);
  check(context.schema_version === 'training-alternative-availability-v0.1' && context.weather_evaluated === false && context.requires_fresh_check === true);
  const candidates = new Map<string, Row>();
  for (const raw of [...result.proposals as unknown[], ...(result.alternatives as unknown[]).map(object).flatMap(g => g.candidates as unknown[])]) {
    const c = object(raw); candidates.set(String(c.candidate_key), c);
  }
  check(canonical(Object.keys(rows).sort()) === canonical([...candidates.keys()].sort()));
  const data = await readDaylightContext(inputs, String(review.athlete_id));
  const cache = new Map<string, [number, number][]>();
  for (const [key, c] of candidates) {
    const value = object(rows[key]), day = (inputs.days as unknown[]).map(object).find(d => d.date === c.date);
    const group = (day?.opportunities as unknown[] | undefined)?.map(object).find(g => g.key === c.opportunity_key);
    check(group && canonical(Object.keys(value).sort()) === canonical(['window_start_at', 'window_end_at', 'day_end_at', 'duration_sec', 'expires_at', 'expires_inclusive', 'limiting_factors', 'goal_role', 'goal_rank', 'goal_key'].sort()));
    const start = instant(c.start_at), end = instant(c.end_at);
    const intervals = (group!.intervals as unknown[]).map(object).map(i => [instant(i.start_at), instant(i.end_at)] as [number, number]);
    const cacheKey = `${c.date}:${c.opportunity_key}:${c.sport}`;
    if (!cache.has(cacheKey)) {
      const {rule, point, area} = data ? effectiveLightRule(data, c.location_id, c.sport) : {};
      const allowed = !rule || rule.mode === 'none' ? intervals : intervals.flatMap(([a, b]) =>
        (area ? areaLightIntervals(a / 1000, b / 1000, area, rule) : point ? lightIntervals(a / 1000, b / 1000, point, rule) : []).map(([x, y]) => [x * 1000, y * 1000] as [number, number]));
      cache.set(cacheKey, allowed);
    }
    const window = cache.get(cacheKey)!.find(([a, b]) => a <= start && end <= b), raw = intervals.find(([a, b]) => a <= start && end <= b);
    check(window && raw);
    const dayEnd = instant(value.day_end_at), zone = String(review.timezone_name);
    check(Number.isFinite(dayEnd) && localDay(zone, new Date(dayEnd)) === addDays(String(c.date), 1) && localDay(zone, new Date(dayEnd - 1)) === c.date);
    const lastFit = window![1] - Number(c.duration_sec) * 1000, factors = ['availability_end'];
    if (window![1] < raw![1]) factors.push('daylight_end');
    if (dayEnd <= lastFit) factors.push('local_day_end');
    const role = (day!.capability_roles as unknown[]).map(object).find(r => r.capability_key === c.capability_key)?.role;
    check(instant(value.window_start_at) === window![0] && instant(value.window_end_at) === window![1] && value.duration_sec === c.duration_sec &&
      instant(value.expires_at) === Math.min(lastFit, dayEnd) && value.expires_inclusive === (lastFit < dayEnd) &&
      canonical(value.limiting_factors) === canonical(factors) && value.goal_key === c.capability_key && value.goal_role === c.role &&
      value.goal_role === role && value.goal_rank === ranks[String(role)]);
  }
}

export function alternativeExpired(review: TrainingReview, candidate: Candidate, now: number) {
  const timing = review.result.alternative_availability?.by_candidate[candidate.candidate_key];
  if (!timing) return false; // unknown is not the same as expired; request a fresh check
  const end = Date.parse(timing.expires_at);
  return timing.expires_inclusive ? now > end : now >= end;
}

export function remainingAlternatives(review: TrainingReview, candidates: Candidate[], recommended: string, preferredGoal: string, now: number) {
  const rows = candidates.filter(c => !alternativeExpired(review, c, now));
  const rank = (c: Candidate) => ranks[c.role] ?? 3;
  const fallback = [...rows].sort((a, b) => rank(a) - rank(b) || Number(b.capability_key === preferredGoal) - Number(a.capability_key === preferredGoal))[0];
  return {candidates: rows, recommended: rows.some(c => c.candidate_key === recommended) ? recommended : fallback?.candidate_key ?? null,
    expiredCount: candidates.length - rows.length};
}

export function goalImpact(review: TrainingReview, candidate: Candidate, preferredGoal: string) {
  const day = review.inputs?.days?.find(d => d.date === candidate.date);
  const previousRole = day?.capability_roles?.find(r => r.capability_key === preferredGoal)?.role;
  return {label: goalRoleLabels[candidate.role] ?? 'Más edzéscél', changed: candidate.capability_key !== preferredGoal,
    previousRole, otherSessionsForPreviousGoal: review.alternatives_for ? null : review.result.proposals.filter(c => c.date !== candidate.date &&
      c.capability_key === preferredGoal && c.training_period_id === candidate.training_period_id).length};
}
