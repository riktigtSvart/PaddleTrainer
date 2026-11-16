import { canonical } from "@/lib/planning-cycles/contracts";
import { MAX_WEEKLY_SLOTS } from "./contracts";
import type { OptionsData, SlotDetails, WeeklySlot } from "./contracts";
import { scheduleContent } from "./synchronization";

type Content = ReturnType<typeof scheduleContent>;
export type ScheduleDraft = { source: Content; baseline: Content; draft: Content; editing: WeeklySlot | null };
export const DRAFT_SCHEMA = "training-schedule-draft-v0.1";
export function scheduleDraftKey(owner?: string, zone?: string) {
  return owner && zone ? `paddletrainer.training-schedule.draft.v1:${owner}:${zone}` : null;
}
export function splitWeeklySlots(data: OptionsData): OptionsData {
  const copy = structuredClone(data), mapping = new Map<string, Map<number, string>>();
  copy.weekly_slots = data.weekly_slots.flatMap(slot => slot.weekdays.map((day, i) => {
    const id = i === 0 ? slot.id : crypto.randomUUID();
    if (!mapping.has(slot.id)) mapping.set(slot.id, new Map());
    mapping.get(slot.id)!.set(day, id);
    return { ...structuredClone(slot), id, weekdays: [day] };
  }));
  copy.exceptions = data.exceptions.map(item => ({ ...structuredClone(item),
    slot_id: mapping.get(item.slot_id)?.get((new Date(item.date + "T12:00:00Z").getUTCDay() + 6) % 7) ?? item.slot_id }));
  return copy;
}
export function initialScheduleDraft(data: OptionsData, today: string): ScheduleDraft {
  const draft = scheduleContent({ ...splitWeeklySlots(data), schedule_start_date: data.schedule_start_date ?? today });
  return { source: structuredClone(scheduleContent(data)), baseline: structuredClone(draft), draft, editing: null };
}
export function scheduleDraftDirty(value: ScheduleDraft) {
  return canonical(value.draft) !== canonical(value.baseline);
}
export function reconcileScheduleDraft(cached: ScheduleDraft, data: OptionsData, today: string) {
  const current = canonical(scheduleContent(data));
  if (current === canonical(cached.source)) return cached;
  if (current === canonical(cached.draft)) {
    // A verified server read already contains all adopted edits. An unfinished
    // editor still belongs to the user and must remain open with its values.
    return { ...initialScheduleDraft(data, today), editing: cached.editing };
  }
  if (!scheduleDraftDirty(cached) && !cached.editing) return initialScheduleDraft(data, today);
  return cached;
}
export function writeScheduleDraft(state: ScheduleDraft, owner: string, zone: string) {
  const raw = JSON.stringify({ schema_version: DRAFT_SCHEMA, owner, timezone_name: zone, ...state });
  if (raw.length > 2_000_000) throw Error("Az órarend-piszkozat túl nagy a helyi megőrzéshez.");
  return raw;
}
// A local draft deliberately accepts incomplete times and invalid minute
// budgets. These are editable input, never an authorized server proposal.
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const string = (v: unknown, max: number): v is string => typeof v === "string" && v.length <= max;
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join("|") === [...names].sort().join("|");
function requireDraft(v: unknown): asserts v { if (!v) throw Error("A korábbi helyi órarend-piszkozat nem olvasható. Megőriztük; a mentett órarend külön betölthető."); }
function details(v: unknown): asserts v is SlotDetails {
  requireDraft(record(v));
  requireDraft(keys(v, ["start_time", "end_time", "ends_next_day", "start_fold", "end_fold", "max_minutes", "location_ids", "effort_cap", "combine_allowed", "notes"]));
  requireDraft(string(v.start_time, 8) && string(v.end_time, 8) && typeof v.ends_next_day === "boolean" &&
    [null, 0, 1].includes(v.start_fold as null | number) && [null, 0, 1].includes(v.end_fold as null | number) &&
    typeof v.max_minutes === "number" && Number.isFinite(v.max_minutes) &&
    Array.isArray(v.location_ids) && v.location_ids.length <= 32 && new Set(v.location_ids).size === v.location_ids.length &&
    v.location_ids.every(id => typeof id === "string" && uuid.test(id)) &&
    ["any", "easy", "moderate"].includes(String(v.effort_cap)) && typeof v.combine_allowed === "boolean" && string(v.notes, 2000));
}
function slot(v: unknown): asserts v is WeeklySlot {
  requireDraft(record(v));
  requireDraft(keys(v, ["id", "start_date", "end_date", "weekdays", "details"]));
  requireDraft(typeof v.id === "string" && uuid.test(v.id) && string(v.start_date, 10) &&
    (v.end_date === null || string(v.end_date, 10)) && Array.isArray(v.weekdays) && v.weekdays.length > 0 && v.weekdays.length <= 7 &&
    new Set(v.weekdays).size === v.weekdays.length && v.weekdays.every(n => Number.isInteger(n) && Number(n) >= 0 && Number(n) <= 6));
  details(v.details);
}
function content(v: unknown): asserts v is Content {
  requireDraft(record(v));
  requireDraft(keys(v, ["schedule_start_date", "schedule_end_date", "weekly_slots", "exceptions"]));
  requireDraft((v.schedule_start_date === null || string(v.schedule_start_date, 10)) &&
    (v.schedule_end_date === null || string(v.schedule_end_date, 10)) && Array.isArray(v.weekly_slots) &&
    v.weekly_slots.length <= MAX_WEEKLY_SLOTS * 7 && Array.isArray(v.exceptions) && v.exceptions.length <= 1024);
  const ids = new Set();
  for (const s of v.weekly_slots) { slot(s); requireDraft(!ids.has(s.id)); ids.add(s.id); }
  for (const e of v.exceptions) {
    requireDraft(record(e) && keys(e, ["slot_id", "date", "replacement"]) && typeof e.slot_id === "string" && uuid.test(e.slot_id) && string(e.date, 10));
    if (e.replacement !== null) details(e.replacement);
  }
}
export function readScheduleDraft(raw: string, owner: string, zone: string): ScheduleDraft {
  requireDraft(raw.length <= 2_000_000);
  const v: unknown = JSON.parse(raw);
  requireDraft(record(v) && v.schema_version === DRAFT_SCHEMA && v.owner === owner && v.timezone_name === zone);
  content(v.source); content(v.baseline); content(v.draft);
  if (v.editing !== null) slot(v.editing);
  return { source: v.source, baseline: v.baseline, draft: v.draft, editing: v.editing as WeeklySlot | null };
}
