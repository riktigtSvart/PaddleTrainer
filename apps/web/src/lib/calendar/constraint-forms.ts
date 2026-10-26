import { canonical } from "@/lib/planning-cycles/contracts";
import { dates, ref, resizeCalendar, validateCalendar } from "@/lib/athlete-setup/contracts";
import type { Calendar, Window } from "@/lib/athlete-setup/contracts";
import { addDays, requireValue } from "./contracts";
import type { CalendarEvent } from "./contracts";
import { categoryLabels, changeSchedule, currentCalendar, defaultDetails, readDetails, readProposal } from "./constraints";
import type { Details, EditorPending, Occurrence, Rule, ScheduleContext } from "./constraints";

export type Draft = {
  date: string; end: string; repeat: "once" | "weekly"; weekdays: number[];
  details: Details; scope: "occurrence" | "future"; daily: string;
};
export function draftFor(date: string, event: CalendarEvent | null): Draft {
  const o = event?.occurrence, w = event?.window;
  const details = o ? structuredClone(o.details) : w ? readDetails({ ...defaultDetails("available"),
    ...Object.fromEntries(Object.keys(defaultDetails("available")).filter((key) => key in w).map((key) => [key, w[key as keyof typeof w]])), title: "Edzéslehetőség" }) : defaultDetails();
  return { date: o?.source_date ?? date, end: "", repeat: o?.repeat ?? "once", weekdays: [(new Date(date + "T12:00Z").getUTCDay() + 6) % 7],
    details, scope: "occurrence", daily: "" };
}
export function ruleFor(draft: Draft, context: ScheduleContext, source: Occurrence | null): Rule {
  const original = source ? context.data.rules.find((r) => r.id === source.rule_id) : null;
  const once = draft.repeat === "once";
  return { id: crypto.randomUUID(), start_date: source?.source_date ?? draft.date,
    end_date: once ? draft.date : draft.end || null, repeat: draft.repeat,
    weekdays: once ? [] : [...draft.weekdays].sort(), details: { ...draft.details, title: draft.details.title.trim(),
      category: draft.details.kind === "available" ? "training" : draft.details.category,
      firmness: draft.details.kind === "available" ? "fixed" : draft.details.firmness,
    }, ...(original?.repeat === "once" ? { start_date: draft.date, end_date: draft.date } : {}) };
}
export function legacyChange(calendar: Calendar, event: CalendarEvent, draft: Draft, remove: boolean): Calendar {
  requireValue(event.kind === "availability" && !!event.window && !event.occurrence);
  const result = structuredClone(calendar), d = result.days.find((d) => d.date === event.date);
  const original = d?.windows.find((w) => w.key === event.window!.key);
  requireValue(d && original && Object.entries(original).filter(([key]) => !["start_fold", "end_fold"].includes(key)).every(([key, value]) => canonical(value) === canonical(event.window![key as keyof typeof event.window])), "Az edzésablak közben megváltozott.");
  const fields = Object.fromEntries(Object.entries(draft.details).filter(([key]) => key in original));
  const w: Window = { ...original, ...fields, key: event.window.key, max_minutes: draft.details.max_minutes! };
  d.windows = remove ? d.windows.filter((w) => w.key !== event.window!.key) : d.windows.map((old) => old.key === w.key ? w : old);
  d.status = d.windows.length ? "available" : "unknown";
  d.max_total_minutes = d.windows.length && draft.daily !== "" ? Number(draft.daily) : null;
  if (d.max_total_minutes !== null) requireValue(Number.isInteger(d.max_total_minutes) && d.max_total_minutes > 0, "A napi keret egész, pozitív perc legyen.");
  validateCalendar(result);
  return result;
}
// Kept explicit: extending a legacy census never drops its earlier dates or data.
export function extendCalendar(calendar: Calendar | null, date: string, zone: string) {
  const first = calendar && calendar.start_date < date ? calendar.start_date : date;
  const last = calendar && calendar.end_date > date ? calendar.end_date : date;
  dates(first, last);
  return resizeCalendar(calendar, first, last, zone,
    calendar?.start_date === first && calendar.end_date === last ? calendar.mesocycle_id : null);
}
export function prepareEdit(context: ScheduleContext, draft: Draft, event: CalendarEvent | null, remove: boolean): {
  pending: EditorPending; proposal: ReturnType<typeof readProposal>; availability?: unknown; first: string; last: string;
} {
  requireValue(!context.timezone_review_required, "Előbb vizsgáld felül a megváltozott időzónát.");
  const base = { request_id: crypto.randomUUID(), previous_reference: context.reference, data: structuredClone(context.data) };
  let operation: EditorPending["operation"] = "constraints", body: string, availability: unknown;
  if (event?.window && !event.occurrence) {
    const calendar = currentCalendar(context);
    requireValue(calendar && context.availability, "Az eredeti edzésablak nem olvasható.");
    availability = { request_id: crypto.randomUUID(), previous_reference: ref(context.availability.artifact), data: legacyChange(calendar, event, draft, remove) };
    operation = "availability"; body = JSON.stringify(availability);
  } else {
    const rule = ruleFor(draft, context, event?.occurrence ?? null);
    base.data = changeSchedule(context.data, rule, event?.occurrence ?? null, draft.scope, remove);
    body = JSON.stringify(readProposal(base));
  }
  const first = draft.date < context.start_date ? draft.date : context.start_date;
  const end = draft.details.ends_next_day ? addDays(draft.date, 1) : draft.date;
  const last = end > context.end_date ? end : context.end_date;
  dates(first, last);
  return { pending: { version: "calendar-editor-pending-v0.1", owner: context.athlete_id, operation, body },
    proposal: readProposal(base), availability, first, last };
}
export function constraintEvents(context: ScheduleContext): CalendarEvent[] {
  return context.occurrences.map((o) => ({ key: "constraint:" + o.key, entityId: o.rule_id,
    kind: o.details.kind === "available" ? "availability" : "constraint", title: o.details.title,
    date: o.source_date, start: o.start_at, end: o.end_at, duration: o.elapsed_minutes === null ? null : o.elapsed_minutes * 60,
    endEstimated: false, sport: o.details.sport_scope === "specified" ? o.details.sports.join(", ") : "UNKNOWN",
    goal: null, goalTag: null, occurrence: o,
  }));
}
export function constraintDescription(event: CalendarEvent) {
  const o = event.occurrence;
  return o ? `${categoryLabels[o.details.category]} · ${o.details.firmness === "fixed" ? "rögzített" : "rugalmas"}${o.overridden ? " · napi kivétel" : ""}${o.issue ? " · pontosítandó időpont" : ""}` : "Edzéslehetőség";
}
