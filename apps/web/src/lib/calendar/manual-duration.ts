/** Reconcile an authored timetable locally; never change the prescribed work. */
import { localParts } from "./contracts";
import type { ScheduleContext } from "./constraints";
import type { ManualDraft } from "./manual-workouts";
import { manualPhaseSeconds } from './manual-workouts';
import { durationHMS } from '@/lib/duration';

function localInstant(day: string, clock: string, zone: string, fold: 0 | 1 | null): number | null {
  const wall = Date.parse(day + "T" + (clock.length === 5 ? clock + ":00" : clock) + "Z");
  if (!Number.isFinite(wall)) return null;
  const offsets = new Set<number>();
  for (const delta of [-36, -12, 0, 12, 36]) {
    const probe = wall + delta * 3600000, p = localParts(new Date(probe).toISOString(), zone);
    offsets.add(Date.parse(p.date + "T00:00:00Z") + Math.round(p.minute * 60000) - probe);
  }
  const candidates = [...offsets].map(offset => wall - offset).filter(value => {
    const p = localParts(new Date(value).toISOString(), zone);
    return p.date === day && Math.round(p.minute * 60000) === wall - Date.parse(day + "T00:00:00Z");
  }).sort((a, b) => a - b);
  if (!candidates.length || candidates.length > 1 && fold === null) return null;
  return candidates[Math.min(fold ?? 0, candidates.length - 1)];
}

/** Remaining declared room is advisory for manual plans; absence is not a zero. */
export function manualDurationRoom(draft: ManualDraft, schedule: ScheduleContext | null | undefined, owner: string, zone: string): number | null {
  if (!schedule || schedule.athlete_id !== owner || schedule.timezone_name !== zone || schedule.timezone_review_required || draft.date < schedule.start_date || draft.date > schedule.end_date) return null;
  const availability = schedule.availability?.artifact.proposal.data;
  const day = availability && 'days' in availability ? availability.days.find(d => d.date === draft.date) : undefined;
  if (day?.status === "unavailable") return 0;
  const civil = Date.parse(draft.date + 'T00:00:00Z');
  if (!Number.isFinite(civil)) return null;
  const preceding = new Date(civil - 86400000).toISOString().slice(0, 10);
  const relevant = schedule.opportunities.filter(o => o.source_date === draft.date || o.source_date === preceding && o.intervals.some(i => localParts(i.start_at, zone).date <= draft.date && localParts(i.end_at, zone).date >= draft.date));
  if (!relevant.length) return null;
  const start = draft.start_time ? localInstant(draft.date, draft.start_time, zone, draft.start_fold) : null;
  if (draft.start_time && start === null) return null; // DST remains explicitly resolved by the existing save validator.
  const floor = draft.start_time ? start : localInstant(draft.date, "00:00", zone, 0);
  if (floor === null) return null;
  let best = 0, unknown = false;
  for (const o of relevant) {
    if (o.constraints?.sports?.length && !o.constraints.sports.includes(draft.sport)) continue;
    if (draft.location.trim() && o.constraints?.location?.trim() && draft.location.trim().toLocaleLowerCase("hu-HU") !== o.constraints.location.trim().toLocaleLowerCase("hu-HU")) continue;
    if (!o.known) { unknown = true; continue; }
    for (const interval of o.intervals) {
      const a = Date.parse(interval.start_at), b = Date.parse(interval.end_at);
      if (start !== null && (start < a || start >= b)) continue;
      const seconds = Math.floor((b - Math.max(a, floor)) / 1000);
      best = Math.max(best, Math.min(seconds, o.max_minutes * 60, (o.daily_max_minutes ?? 1440) * 60));
    }
  }
  return unknown ? null : Math.max(0, best);
}

export function alignManualDuration(draft: ManualDraft): { draft: ManualDraft; adjusted: boolean; issue: string | null } {
  let required = 0;
  for (const phase of draft.phases) {
    if (!Number.isSafeInteger(phase.repeat_count) || phase.repeat_count < 1 || phase.repeat_count > 100 || phase.duration_sec !== null && (!Number.isSafeInteger(phase.duration_sec) || phase.duration_sec < 1 || phase.duration_sec > 86400)) return { draft, adjusted: false, issue: null };
    if (phase.recovery_duration_sec != null && (!Number.isSafeInteger(phase.recovery_duration_sec) || phase.recovery_duration_sec < 0 || phase.recovery_duration_sec > 86400)) return { draft, adjusted: false, issue: null };
    required += manualPhaseSeconds(phase);
  }
  if (!required || draft.duration_sec !== null && (!Number.isSafeInteger(draft.duration_sec) || draft.duration_sec < 0)) return { draft, adjusted: false, issue: null };
  const duration = Math.max(60, required);
  if (duration > 86400) return { draft, adjusted: false, issue: "A szakaszok összes ideje meghaladja a támogatott 24:00:00 időtartamot. Rövidítsd az edzést vagy bontsd több alkalomra." };
  if (draft.duration_sec !== null && draft.duration_sec >= required) return { draft, adjusted: false, issue: null };
  return { draft: { ...draft, duration_sec: duration }, adjusted: true, issue: null };
}

/** Explain loaded schedule conflicts without granting or denying write authority. */
export function manualScheduleWarnings(draft: ManualDraft, schedule: ScheduleContext | null | undefined, owner: string, zone: string, dates: string[] = [draft.date]): string[] {
  if (!schedule || schedule.athlete_id !== owner || schedule.timezone_name !== zone || schedule.timezone_review_required || !Number.isSafeInteger(draft.duration_sec) || draft.duration_sec === null || draft.duration_sec <= 0 || draft.duration_sec > 86400) return [];
  const warnings: string[] = [];
  for (const date of new Set(dates)) {
    if (date < schedule.start_date || date > schedule.end_date) continue;
    const value = { ...draft, date };
    const start = draft.start_time ? localInstant(date, draft.start_time, zone, draft.start_fold) : null;
    if (draft.start_time && start === null) continue;
    const end = start === null ? null : start + draft.duration_sec * 1000;
    const busy = start === null || end === null ? [] : schedule.occurrences.filter(o => o.details.kind === 'busy' && !o.issue && o.start_at && o.end_at && Date.parse(o.start_at) < end && start < Date.parse(o.end_at));
    if (busy.length) {
      const titles = [...new Set(busy.map(o => o.details.title.trim() || 'Elfoglaltság'))];
      warnings.push(`${date}: az edzés ütközik ezzel: ${titles.join(', ')}.`);
    } else {
      const room = manualDurationRoom(value, schedule, owner, zone);
      if (room !== null && draft.duration_sec > room) warnings.push(`${date}: a ${durationHMS(draft.duration_sec)} edzésidő nem fér a megadott kezdéshez és helyszínhez tartozó ismert ${durationHMS(room)} időkeretbe.`);
    }
  }
  return warnings;
}
