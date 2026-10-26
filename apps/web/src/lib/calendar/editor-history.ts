import { canonical, object } from "@/lib/planning-cycles/contracts";
import { readReceipt, ref } from "@/lib/athlete-setup/contracts";
import type { Calendar, Receipt as AvailabilityReceipt } from "@/lib/athlete-setup/contracts";
import { requireValue } from "./contracts";
import { readEditorPending, readProposal, readScheduleReceipt } from "./constraints";
import type { Details, EditorPending, Receipt, Schedule, ScheduleContext } from "./constraints";

export const EDITOR_UNDO = "paddletrainer.calendar-editor.undo.v1";
type Saved = Receipt | AvailabilityReceipt;
export type Recovery = EditorPending & { history?: { before: Saved | null; isUndo: boolean } };
export type UndoRecord = { version: "calendar-undo-v0.1"; owner: string; operation: EditorPending["operation"]; before: Saved | null; after: Saved };
async function verified(value: unknown, operation: EditorPending["operation"], owner: string, body?: string): Promise<Saved> {
  if (operation === "constraints") return readScheduleReceipt(value, owner, body);
  const r = await readReceipt(value, body ? { schema_version: "athlete-pending-v0.1", operation: "availability", body } : undefined);
  requireValue(r.artifact.kind === "availability" && r.artifact.athlete_id === owner, "Másik sportolóhoz vagy művelethez tartozó visszavonás.");
  return r;
}
export function withHistory(pending: EditorPending, context: ScheduleContext, isUndo: boolean): Recovery {
  requireValue(pending.owner === context.athlete_id);
  return { ...pending, history: { before: pending.operation === "constraints" ? context.saved : context.availability, isUndo } };
}
export async function readRecovery(raw: string): Promise<Recovery> {
  const p = readEditorPending(raw) as Recovery;
  if (p.history !== undefined) {
    const h = object(p.history);
    requireValue(typeof h.isUndo === "boolean");
    const before = h.before === null ? null : await verified(h.before, p.operation, p.owner);
    requireValue(p.operation === "constraints" || before !== null);
    requireValue(canonical(object(JSON.parse(p.body)).previous_reference) === canonical(before ? ref(before.artifact) : null),
      "A mentés előzménye nem egyezik a visszavonási adatokkal.");
    p.history = { before, isUndo: h.isUndo };
  }
  return p;
}
export async function makeUndo(pending: Recovery, receipt: Saved): Promise<UndoRecord | null> {
  if (!pending.history || pending.history.isUndo) return null;
  const after = await verified(receipt, pending.operation, pending.owner, pending.body);
  return readUndo(JSON.stringify({ version: "calendar-undo-v0.1", owner: pending.owner, operation: pending.operation,
    before: pending.history.before, after }));
}
export async function readUndo(raw: string): Promise<UndoRecord> {
  const u = object(JSON.parse(raw));
  requireValue(u.version === "calendar-undo-v0.1" && typeof u.owner === "string" &&
    /^[a-f0-9-]{36}$/.test(u.owner) && ["constraints", "availability"].includes(String(u.operation)));
  const operation = u.operation as EditorPending["operation"];
  const after = await verified(u.after, operation, u.owner);
  const before = u.before === null ? null : await verified(u.before, operation, u.owner);
  requireValue(operation === "constraints" || before !== null);
  requireValue(canonical(after.artifact.proposal.previous_reference) === canonical(before ? ref(before.artifact) : null),
    "A visszavonás nem az egymást követő mentésekhez tartozik.");
  return { version: "calendar-undo-v0.1", owner: u.owner, operation, before, after };
}
export function undoAvailable(u: UndoRecord, context: ScheduleContext) {
  const current = u.operation === "constraints" ? context.saved : context.availability;
  return u.owner === context.athlete_id && !context.timezone_review_required && !!current &&
    object(current.artifact.proposal.data).timezone_name === object(u.after.artifact.proposal.data).timezone_name &&
    (!u.before || object(u.before.artifact.proposal.data).timezone_name === context.timezone_name) &&
    canonical(ref(current.artifact)) === canonical(ref(u.after.artifact));
}
export function undoChanges(u: UndoRecord): { title: string; current: string; restored: string }[] {
  const details = (d: Details) => `${d.title} · ${d.start_time}–${d.end_time}${d.ends_next_day ? " (másnap)" : ""}${d.max_minutes !== null ? ` · legfeljebb ${d.max_minutes} edzésperc` : ""}${d.location ? ` · ${d.location}` : ""}${d.notes ? ` · ${d.notes}` : ""}`;
  if (u.operation === "constraints") {
    const a = u.after.artifact.proposal.data as Schedule, b = u.before?.artifact.proposal.data as Schedule | undefined;
    const result = [...new Set([...a.rules, ...b?.rules ?? []].map(r => r.id))].flatMap(id => {
      const from = a.rules.find(r => r.id === id), to = b?.rules.find(r => r.id === id);
      const describe = (r: typeof from) => r ? `${details(r.details)} · ${r.start_date}–${r.end_date ?? "határozatlan"}${r.repeat === "weekly" ? " · heti ismétlődés" : ""}` : "Nincs ilyen idősáv";
      return canonical(from ?? null) === canonical(to ?? null) ? [] : [{ title: "Idősáv / ismétlődés", current: describe(from), restored: describe(to) }];
    });
    for (const key of new Set([...a.exceptions, ...b?.exceptions ?? []].map(e => `${e.rule_id}:${e.date}`))) {
      const from = a.exceptions.find(e => `${e.rule_id}:${e.date}` === key), to = b?.exceptions.find(e => `${e.rule_id}:${e.date}` === key);
      const describe = (e: typeof from) => e ? e.replacement ? details(e.replacement) : "Kihagyott alkalom" : "Az ismétlődő szabály szerint";
      if (canonical(from ?? null) !== canonical(to ?? null)) result.push({ title: `Alkalom · ${(from ?? to)!.date}`, current: describe(from), restored: describe(to) });
    }
    return result;
  }
  const a = u.after.artifact.proposal.data as Calendar, b = u.before!.artifact.proposal.data as Calendar;
  return [...new Set([...a.days, ...b.days].map(d => d.date))].flatMap(date => {
    const from = a.days.find(d => d.date === date), to = b.days.find(d => d.date === date);
    const describe = (d: typeof from) => d ? `${d.windows.map(w => `${w.start_time}–${w.end_time}${w.ends_next_day ? " (másnap)" : ""} · ${w.max_minutes} p`).join(", ") || "Nincs megadott ablak"} · napi keret: ${d.max_total_minutes ?? "ismeretlen"}` : "A megadott időszakon kívül";
    return canonical(from ?? null) === canonical(to ?? null) ? [] : [{ title: date, current: describe(from), restored: describe(to) }];
  });
}
export function prepareUndo(context: ScheduleContext, u: UndoRecord) {
  requireValue(undoAvailable(u, context), "Újabb vagy másik fiókhoz tartozó módosítás történt. A régi állapot nem írható vissza.");
  const proposal = readProposal({ request_id: crypto.randomUUID(), previous_reference: context.reference, data: structuredClone(context.data) });
  let body: string, availability: unknown;
  if (u.operation === "constraints") {
    proposal.data = structuredClone(u.before ? (u.before as Receipt).artifact.proposal.data
      : { timezone_name: context.timezone_name, rules: [], exceptions: [] });
    body = JSON.stringify(readProposal(proposal));
  } else {
    availability = { request_id: crypto.randomUUID(), previous_reference: ref(context.availability!.artifact),
      data: structuredClone(u.before!.artifact.proposal.data) as Calendar };
    body = JSON.stringify(availability);
  }
  return { proposal, availability, first: context.start_date, last: context.end_date,
    pending: { version: "calendar-editor-pending-v0.1" as const, owner: context.athlete_id, operation: u.operation, body } };
}
