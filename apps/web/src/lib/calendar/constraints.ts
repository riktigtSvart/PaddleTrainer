import { canonical, day, object, sha } from "@/lib/planning-cycles/contracts";
import { addDays, dateDistance, requireValue, validInstant } from "./contracts";
import { readReceipt as readAvailabilityReceipt } from "@/lib/athlete-setup/contracts";
import type { Calendar, Receipt as AvailabilityReceipt } from "@/lib/athlete-setup/contracts";
import { readDurationEstimate } from "./duration-estimate";
import type { DurationEstimate } from "./duration-estimate";

export type Details = {
  kind: "busy" | "available";
  category: "work" | "travel" | "personal" | "other" | "training";
  title: string;
  firmness: "fixed" | "flexible";
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  start_fold: 0 | 1 | null;
  end_fold: 0 | 1 | null;
  max_minutes: number | null;
  sport_scope: "unknown" | "any" | "specified";
  sports: string[];
  effort_cap: "unknown" | "easy" | "moderate" | "any";
  resources: string[];
  location: string;
  notes: string;
};
export type Rule = {
  id: string;
  start_date: string;
  end_date: string | null;
  repeat: "once" | "weekly";
  weekdays: number[];
  details: Details;
};
export type Exception = { rule_id: string; date: string; replacement: Details | null };
export type Schedule = { timezone_name: string; rules: Rule[]; exceptions: Exception[] };
export type Reference = { artifact_id: string; content_hash: string };
export type Proposal = { request_id: string; previous_reference: Reference | null; data: Schedule };
export type Occurrence = {
  key: string;
  rule_id: string;
  source_date: string;
  repeat: "once" | "weekly";
  overridden: boolean;
  details: Details;
  start_at: string | null;
  end_at: string | null;
  elapsed_minutes: number | null;
  issue: string | null;
};
export type Conflict = {
  plan_id: string; plan_title: string; occurrence_key: string;
  constraint_title: string; date: string; severity: "fixed" | "flexible" | "review"; code: string;
};
export type Opportunity = {
  key: string; source_date: string; start_at: string | null; end_at: string | null;
  max_minutes: number; daily_max_minutes: number | null; source: string;
  known: boolean; usable_minutes: number | null;
  intervals: { start_at: string; end_at: string }[];
};
export type Receipt = {
  identity_scope: "APPLICATION_DEMO_USER"; committed: true; reused: boolean;
  durable_available_at: string; planning_authorized: false; workouts_changed: false;
  artifact: { schema_version: "calendar-constraints-v0.1"; artifact_id: string; athlete_id: string;
    content_hash: string; created_at: string; revision: number; proposal: Proposal;
    planning_authorized: false; workouts_changed: false };
};
export type ScheduleContext = {
  duration_estimates?: Record<string, DurationEstimate>;
  schema_version: "calendar-constraints-v0.1"; athlete_id: string; timezone_name: string;
  local_today: string; start_date: string; end_date: string; retrieved_at: string;
  reference: Reference | null; saved: Receipt | null; data: Schedule;
  availability: AvailabilityReceipt | null; occurrences: Occurrence[]; conflicts: Conflict[];
  opportunities: Opportunity[]; timezone_review_required: boolean; proposal_hash: string | null;
  availability_proposal_hash: string | null;
  has_more: false; absence_means_free: false; opportunities_are_required: false;
  planning_authorized: false; workouts_changed: false;
};
export type EditorPending = {
  version: "calendar-editor-pending-v0.1"; owner: string;
  operation: "constraints" | "availability"; body: string;
};
export const EDITOR_PENDING = "paddletrainer.calendar-editor.pending.v1";
export const categoryLabels: Record<Details["category"], string> = {
  work: "Munka", travel: "Utazás", personal: "Személyes elfoglaltság",
  other: "Egyéb elfoglaltság", training: "Edzéslehetőség",
};
export const weekLabels = ["H", "K", "Sze", "Cs", "P", "Szo", "V"];
export const issueLabels: Record<string, string> = {
  ATHLETE_TIME_DOES_NOT_EXIST: "Óraátállítás: ez a helyi időpont nem létezik.",
  ATHLETE_TIME_IS_AMBIGUOUS: "Óraátállítás: válaszd ki az első vagy a második előfordulást.",
  CALENDAR_CONSTRAINT_CAPACITY_INVALID: "Az edzéspercek nem férnek az időablakba.",
  CALENDAR_CONSTRAINT_DURATION_INVALID: "A kezdés és a befejezés nem ad érvényes időablakot.",
};
export const conflictLabels: Record<string, string> = {
  OTHER_TRAINING_TIME_UNKNOWN: "A másik edzés végideje hiányzik; az átfedés nem dönthető el.",
  TRAINING_OVERLAP: "Másik tervezett vagy teljesített edzéssel átfedi egymást.",
  ESTIMATED_TRAINING_OVERLAP: "Becslés alapján másik edzéssel átfedés lehetséges.",
  WORKOUT_OVERLAP: "Az edzés és az elfoglaltság átfedi egymást.",
  START_IN_COMMITMENT: "Az edzés az elfoglaltság idején kezdődik.",
  PLAN_END_UNKNOWN: "Az edzés végideje hiányzik; az átfedés nem dönthető el.",
  PLAN_TIME_UNKNOWN: "Az edzés kezdése hiányzik; az átfedés nem dönthető el.",
  COMMITMENT_TIME_UNKNOWN: "Az elfoglaltság pontos időpontja felülvizsgálandó.",
  TRAINING_DAY_UNAVAILABLE: "Erre a napra nem adtál meg edzéslehetőséget: elérhetetlennek jelölted.",
  OUTSIDE_OPPORTUNITY: "Az edzés nem fér a megadott edzésablakba vagy az időkeretébe.",
  OPPORTUNITY_FIT_UNKNOWN: "A megadott edzésablakba illeszkedés nem dönthető el.",
  ESTIMATED_WORKOUT_OVERLAP: "A becsült időtartam alapján átfedés várható.",
  ESTIMATED_OVERLAP_POSSIBLE: "A becslési tartomány érinti az elfoglaltságot; átfedés lehetséges.",
  ESTIMATED_OPPORTUNITY_FIT_REVIEW: "A becslési tartomány felső része már nem fér az edzésablakba.",
  ESTIMATED_OUTSIDE_OPPORTUNITY: "A becsült időtartam nem fér a megadott edzésablakba vagy keretbe.",
};
export function conflictKind(c: Conflict): "conflict" | "estimate" | "unknown" {
  return c.code.startsWith("ESTIMATED_") ? "estimate" : c.severity === "review" ? "unknown" : "conflict";
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const identity = /^pt-calendar-constraints:[a-f0-9]{32}:[a-f0-9]{32}$/;
const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
function checkedDay(value: unknown): asserts value is string {
  requireValue(typeof value === "string"); day(value);
  requireValue(value >= "1900-01-01" && value <= "2100-12-31");
}
function checkedReference(value: unknown): Reference | null {
  if (value === null) return null;
  const r = object(value);
  requireValue(typeof r.artifact_id === "string" && identity.test(r.artifact_id) &&
    typeof r.content_hash === "string" && /^[a-f0-9]{64}$/.test(r.content_hash));
  return r as Reference;
}
export function readDetails(value: unknown): Details {
  const d = object(value);
  requireValue(["busy", "available"].includes(String(d.kind)) &&
    Object.hasOwn(categoryLabels, String(d.category)) &&
    (d.kind === "available") === (d.category === "training") &&
    typeof d.title === "string" && d.title.length > 0 && d.title.length <= 100 && d.title.trim() === d.title &&
    ["fixed", "flexible"].includes(String(d.firmness)) &&
    typeof d.start_time === "string" && clock.test(d.start_time) &&
    typeof d.end_time === "string" && clock.test(d.end_time) && typeof d.ends_next_day === "boolean");
  for (const name of ["start_fold", "end_fold"])
    requireValue(d[name] === null || d[name] === 0 || d[name] === 1);
  requireValue(d.kind === "busy" ? d.max_minutes === null
    : Number.isInteger(d.max_minutes) && Number(d.max_minutes) >= 1 && Number(d.max_minutes) <= 1440);
  const minutes = (s: string) => Number(s.slice(0, 2)) * 60 + Number(s.slice(3));
  let span = minutes(d.end_time as string) - minutes(d.start_time as string) + (d.ends_next_day ? 1440 : 0);
  if (!d.ends_next_day && d.start_fold === 0 && d.end_fold === 1 && span <= 0 && span > -60) span += 60;
  requireValue(span > 0 && span <= 1440, "A befejezés legyen a kezdés után; éjfél átlépésekor jelöld a másnapot.");
  requireValue(d.max_minutes === null || Number(d.max_minutes) <= span, "Az edzéspercek nem férnek a megadott időablakba.");
  requireValue(["unknown", "any", "specified"].includes(String(d.sport_scope)) &&
    ["unknown", "easy", "moderate", "any"].includes(String(d.effort_cap)));
  for (const key of ["sports", "resources"])
    requireValue(Array.isArray(d[key]) && d[key].every((x) => typeof x === "string") && new Set(d[key]).size === d[key].length);
  requireValue((d.sport_scope === "specified") === !!(d.sports as string[]).length &&
    typeof d.location === "string" && typeof d.notes === "string");
  return d as Details;
}
export function occurs(rule: Rule, date: string) {
  const weekday = (new Date(date + "T12:00:00Z").getUTCDay() + 6) % 7;
  return date >= rule.start_date && (!rule.end_date || date <= rule.end_date) &&
    (rule.repeat === "once" ? date === rule.start_date : rule.weekdays.includes(weekday));
}
export function readSchedule(value: unknown): Schedule {
  const s = object(value);
  requireValue(typeof s.timezone_name === "string");
  new Intl.DateTimeFormat("hu-HU", { timeZone: s.timezone_name }).format();
  requireValue(Array.isArray(s.rules) && s.rules.length <= 512 && Array.isArray(s.exceptions) && s.exceptions.length <= 4096);
  const ids = new Map<string, Rule>();
  for (const value of s.rules) {
    const r = object(value);
    requireValue(typeof r.id === "string" && uuid.test(r.id) && !ids.has(r.id));
    checkedDay(r.start_date); if (r.end_date !== null) checkedDay(r.end_date);
    requireValue(r.end_date === null || r.end_date >= r.start_date);
    requireValue(["once", "weekly"].includes(String(r.repeat)) && Array.isArray(r.weekdays) &&
      r.weekdays.every((n) => Number.isInteger(n) && Number(n) >= 0 && Number(n) <= 6) &&
      canonical([...new Set(r.weekdays)].sort()) === canonical(r.weekdays));
    requireValue(r.repeat === "once" ? r.end_date === r.start_date && r.weekdays.length === 0 : r.weekdays.length > 0);
    readDetails(r.details); ids.set(r.id, r as Rule);
  }
  const seen = new Set<string>();
  for (const value of s.exceptions) {
    const e = object(value); checkedDay(e.date);
    requireValue(typeof e.rule_id === "string");
    const rule = ids.get(e.rule_id), key = e.rule_id + ":" + e.date;
    requireValue(rule && occurs(rule, e.date) && !seen.has(key)); seen.add(key);
    if (e.replacement !== null) readDetails(e.replacement);
  }
  return s as Schedule;
}
export function readProposal(value: unknown): Proposal {
  const p = object(value);
  requireValue(Object.keys(p).sort().join() === "data,previous_reference,request_id" &&
    typeof p.request_id === "string" && uuid.test(p.request_id));
  checkedReference(p.previous_reference); readSchedule(p.data);
  return p as Proposal;
}
export async function readScheduleReceipt(value: unknown, owner: string, body?: string): Promise<Receipt> {
  const r = object(value), a = object(r.artifact), p = readProposal(a.proposal);
  const { content_hash, ...raw } = a;
  requireValue(r.identity_scope === "APPLICATION_DEMO_USER" && r.committed === true &&
    typeof r.reused === "boolean" && validInstant(r.durable_available_at) &&
    r.planning_authorized === false && r.workouts_changed === false &&
    a.schema_version === "calendar-constraints-v0.1" && a.athlete_id === owner &&
    a.artifact_id === `pt-calendar-constraints:${owner.replaceAll("-", "")}:${p.request_id.replaceAll("-", "")}` &&
    a.planning_authorized === false && a.workouts_changed === false && validInstant(a.created_at) &&
    Number.isSafeInteger(a.revision) && Number(a.revision) >= 1 &&
    (a.revision === 1) === (p.previous_reference === null) && content_hash === await sha(raw));
  if (body) requireValue(canonical(p) === canonical(readProposal(JSON.parse(body))));
  return r as Receipt;
}
export async function readScheduleContext(value: unknown): Promise<ScheduleContext> {
  const c = object(value);
  requireValue(c.schema_version === "calendar-constraints-v0.1" && typeof c.athlete_id === "string" && uuid.test(c.athlete_id) &&
    typeof c.timezone_name === "string" && validInstant(c.retrieved_at) && c.has_more === false &&
    c.absence_means_free === false && c.opportunities_are_required === false &&
    c.planning_authorized === false && c.workouts_changed === false && typeof c.timezone_review_required === "boolean");
  checkedDay(c.local_today); checkedDay(c.start_date); checkedDay(c.end_date);
  requireValue(dateDistance(c.start_date, c.end_date) >= 0 && dateDistance(c.start_date, c.end_date) < 366);
  const state = readSchedule(c.data), ref = checkedReference(c.reference);
  requireValue(c.proposal_hash === null || typeof c.proposal_hash === "string" && /^[a-f0-9]{64}$/.test(c.proposal_hash));
  requireValue(c.availability_proposal_hash === null || typeof c.availability_proposal_hash === "string" && /^[a-f0-9]{64}$/.test(c.availability_proposal_hash));
  if (c.saved !== null) {
    const saved = await readScheduleReceipt(c.saved, c.athlete_id);
    requireValue(canonical(ref) === canonical({ artifact_id: saved.artifact.artifact_id, content_hash: saved.artifact.content_hash }));
    if (c.proposal_hash === null) requireValue(canonical(saved.artifact.proposal.data) === canonical(state));
  } else requireValue(ref === null);
  if (c.availability !== null) {
    const saved = await readAvailabilityReceipt(c.availability);
    requireValue(saved.artifact.kind === "availability" && saved.artifact.athlete_id === c.athlete_id);
  }
  requireValue(Array.isArray(c.occurrences) && c.occurrences.length <= 4000 &&
    Array.isArray(c.conflicts) && c.conflicts.length <= 4000 && Array.isArray(c.opportunities));
  const keys = new Set<string>();
  if (c.duration_estimates !== undefined)
    for (const [id, estimate] of Object.entries(object(c.duration_estimates))) readDurationEstimate(estimate, id, c.athlete_id);
  for (const value of c.occurrences) {
    const o = object(value); checkedDay(o.source_date); readDetails(o.details);
    const rule = state.rules.find((r) => r.id === o.rule_id);
    const exception = state.exceptions.find((e) => e.rule_id === o.rule_id && e.date === o.source_date);
    requireValue(rule && occurs(rule, o.source_date) && o.key === `${o.rule_id}:${o.source_date}` &&
      typeof o.key === "string" && !keys.has(o.key) && o.overridden === !!exception && o.repeat === rule.repeat &&
      canonical(o.details) === canonical(exception ? exception.replacement : rule.details));
    keys.add(o.key);
    if (o.start_at === null) requireValue(o.end_at === null && o.elapsed_minutes === null && typeof o.issue === "string");
    else requireValue(validInstant(o.start_at) && validInstant(o.end_at) && o.issue === null &&
      typeof o.elapsed_minutes === "number" && o.elapsed_minutes > 0 &&
      Math.abs((Date.parse(o.end_at) - Date.parse(o.start_at)) / 60000 - o.elapsed_minutes) < 1e-7);
  }
  for (const value of c.conflicts) {
    const f = object(value); checkedDay(f.date);
    requireValue(typeof f.plan_id === "string" && uuid.test(f.plan_id) && typeof f.plan_title === "string" &&
      typeof f.occurrence_key === "string" && (keys.has(f.occurrence_key) || f.occurrence_key === "availability:" + f.date) && typeof f.constraint_title === "string" &&
      ["fixed", "flexible", "review"].includes(String(f.severity)) && typeof f.code === "string");
  }
  const opportunityKeys = new Set();
  for (const value of c.opportunities) {
    const w = object(value); checkedDay(w.source_date);
    requireValue(typeof w.key === "string" && !opportunityKeys.has(w.key) && Number.isInteger(w.max_minutes) && Number(w.max_minutes) > 0 && Number(w.max_minutes) <= 1440 &&
      (w.daily_max_minutes === null || Number.isInteger(w.daily_max_minutes) && Number(w.daily_max_minutes) > 0) &&
      ["athlete_availability", "calendar_rule"].includes(String(w.source)) &&
      typeof w.known === "boolean" && Array.isArray(w.intervals) &&
      (w.known ? typeof w.usable_minutes === "number" && w.usable_minutes >= 0 && w.usable_minutes <= Number(w.max_minutes)
        : w.usable_minutes === null && w.intervals.length === 0));
    opportunityKeys.add(w.key);
    for (const part of w.intervals) {
      const i = object(part); requireValue(validInstant(i.start_at) && validInstant(i.end_at) && Date.parse(i.end_at) > Date.parse(i.start_at));
    }
  }
  return c as ScheduleContext;
}
export function readEditorPending(raw: string): EditorPending {
  const p = object(JSON.parse(raw));
  requireValue(p.version === "calendar-editor-pending-v0.1" && typeof p.owner === "string" && uuid.test(p.owner) &&
    ["constraints", "availability"].includes(String(p.operation)) && typeof p.body === "string");
  if (p.operation === "constraints") readProposal(JSON.parse(p.body));
  else {
    const a = object(JSON.parse(p.body));
    requireValue(Object.keys(a).sort().join() === "data,previous_reference,request_id" && typeof a.request_id === "string" && uuid.test(a.request_id));
    const calendar = object(a.data); checkedDay(calendar.start_date); checkedDay(calendar.end_date);
    requireValue(typeof calendar.timezone_name === "string" && Array.isArray(calendar.days));
  }
  return p as EditorPending;
}
export function currentCalendar(context: ScheduleContext): Calendar | null {
  return context.availability?.artifact.proposal.data as Calendar | undefined ?? null;
}
export function defaultDetails(kind: Details["kind"] = "busy"): Details {
  return { kind, category: kind === "busy" ? "work" : "training", title: kind === "busy" ? "Munka" : "Edzéslehetőség",
    firmness: "fixed", start_time: "18:00", end_time: "19:00", ends_next_day: false,
    start_fold: null, end_fold: null, max_minutes: kind === "available" ? 60 : null,
    sport_scope: "unknown", sports: [], effort_cap: "unknown", resources: [], location: "", notes: "" };
}
export function changeSchedule(state: Schedule, rule: Rule, source: Occurrence | null, scope: "occurrence" | "future", remove = false): Schedule {
  const value = structuredClone(state);
  if (!source) { requireValue(!remove); value.rules.push(rule); return readSchedule(value); }
  const original = value.rules.find((r) => r.id === source.rule_id);
  requireValue(original && occurs(original, source.source_date), "Az eredeti alkalom közben megváltozott.");
  if (original.repeat === "once") {
    value.rules = remove ? value.rules.filter((r) => r.id !== original.id)
      : value.rules.map((r) => r.id === original.id ? { ...rule, id: original.id } : r);
    value.exceptions = value.exceptions.filter((e) => e.rule_id !== original.id);
  } else if (scope === "occurrence") {
    value.exceptions = value.exceptions.filter((e) => e.rule_id !== original.id || e.date !== source.source_date);
    if (remove || canonical(rule.details) !== canonical(original.details))
      value.exceptions.push({ rule_id: original.id, date: source.source_date, replacement: remove ? null : rule.details });
  } else {
    const future = value.exceptions.filter((e) => e.rule_id === original.id && e.date > source.source_date);
    value.exceptions = value.exceptions.filter((e) => e.rule_id !== original.id || e.date < source.source_date);
    if (source.source_date === original.start_date) value.rules = value.rules.filter((r) => r.id !== original.id);
    else original.end_date = addDays(source.source_date, -1);
    if (!remove) {
      requireValue(rule.id !== original.id, "Az új szabályhoz új azonosító kell.");
      value.rules.push({ ...rule, start_date: source.source_date });
      value.exceptions.push(...future.filter((e) => occurs({ ...rule, start_date: source.source_date }, e.date))
        .map((e) => ({ ...e, rule_id: rule.id })));
    }
  }
  return readSchedule(value);
}
