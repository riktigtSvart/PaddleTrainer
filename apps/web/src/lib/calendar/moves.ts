import { canonical, object, sha } from "@/lib/planning-cycles/contracts";
import { requireDay, requireValue, validInstant, localParts } from "./contracts";
import { readDurationEstimate } from "./duration-estimate";
import type { Conflict } from "./constraints";
import type { DurationEstimate } from "./duration-estimate";
export const MOVE_PENDING = "paddletrainer.calendar-move.pending.v1", MOVE_UNDO = "paddletrainer.calendar-move.undo.v1";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash = /^[a-f0-9]{64}$/;
export type Timing = { date: string; planned_start_time: string | null };
export type MoveRef = { artifact_id: string; content_hash: string };
export type MoveProposal = { request_id: string; plan_id: string; expected_source_hash: string; previous_reference: MoveRef | null; timezone_name: string; date: string; start_time: string | null; start_fold: 0 | 1 | null };
export type MoveContext = { schema_version: string; athlete_id: string; plan_id: string; title: string; timezone_name: string; current: Timing; source_hash: string; previous_reference: MoveRef | null; restore: Timing | null; allowed: boolean; blocked_reason: string | null };
export type MoveReview = { schema_version: string; athlete_id: string; plan_id: string; title: string; proposal: MoveProposal; proposal_hash: string; before: Timing; after: Timing; review_hash: string; conflicts: Conflict[]; duration_estimate: DurationEstimate | null; timezone_review_required: boolean; period_warning: string | null };
export type MoveReceipt = { identity_scope: string; artifact: { schema_version: string; artifact_id: string; athlete_id: string; proposal: MoveProposal; revision: number; created_at: string; before: Timing; after: Timing; source_before: unknown; review_hash: string; content_hash: string }; committed: boolean; reused: boolean; durable_available_at: string };
export type MovePending = { version: "calendar-move-pending-v0.1"; owner: string; body: string; undo: boolean };
export type MoveUndo = { receipt: MoveReceipt; consumed: boolean };
export type MoveUndoState = { createdAt: string; planId: string; owner: string; disabled: boolean; explanation: string };
export const moveRef = (a: MoveReceipt["artifact"]) => ({ artifact_id: a.artifact_id, content_hash: a.content_hash });
function flags(x: Record<string, unknown>) { requireValue(x.planning_authorized === false && x.training_dose_changed === false && x.provider_writeback === false); }
function timing(v: unknown) { const x = object(v); requireDay(x.date); requireValue(x.planned_start_time === null || validInstant(x.planned_start_time)); return x as Timing; }
function reference(v: unknown) { if (v === null) return; const x = object(v); requireValue(typeof x.artifact_id === "string" && /^pt-workout-move:[a-f0-9]{64}:[a-f0-9]{32}$/.test(x.artifact_id) && typeof x.content_hash === "string" && hash.test(x.content_hash)); }
export function readMoveProposal(v: unknown): MoveProposal {
  const x = object(v);
  requireValue(Object.keys(x).sort().join() === ["request_id","plan_id","expected_source_hash","previous_reference","timezone_name","date","start_time","start_fold"].sort().join());
  requireValue(typeof x.request_id === "string" && uuid.test(x.request_id) && typeof x.plan_id === "string" && uuid.test(x.plan_id) && typeof x.expected_source_hash === "string" && hash.test(x.expected_source_hash));
  reference(x.previous_reference); requireDay(x.date); requireValue(x.start_time !== null || x.start_fold === null);
  requireValue(typeof x.timezone_name === "string" && (x.start_time === null || typeof x.start_time === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(x.start_time)) && [null,0,1].includes(x.start_fold as null));
  new Intl.DateTimeFormat("hu-HU",{timeZone:x.timezone_name}).format();
  return x as MoveProposal;
}
export function readMoveContext(v: unknown, owner: string, plan: string): MoveContext {
  const x = object(v); flags(x);
  requireValue(x.schema_version === "calendar-workout-move-v0.1" && x.athlete_id === owner && x.plan_id === plan && typeof x.title === "string" && typeof x.timezone_name === "string" && typeof x.source_hash === "string" && hash.test(x.source_hash));
  timing(x.current); if (x.restore !== null) timing(x.restore); reference(x.previous_reference);
  requireValue(typeof x.allowed === "boolean" && (x.allowed ? x.blocked_reason === null : typeof x.blocked_reason === "string"));
  new Intl.DateTimeFormat("hu-HU",{timeZone:x.timezone_name as string}).format(); return x as MoveContext;
}
export async function readMoveReview(v: unknown, proposal: MoveProposal, owner: string): Promise<MoveReview> {
  const x = object(v); flags(x);
  requireValue(x.schema_version === "calendar-workout-move-v0.1" && x.athlete_id === owner && x.plan_id === proposal.plan_id && canonical(x.proposal) === canonical(proposal) && x.proposal_hash === await sha(proposal) && x.timezone_review_required === false && typeof x.title === "string");
  requireValue(x.period_warning === null || typeof x.period_warning === "string");
  timing(x.before); const after = timing(x.after); requireValue(after.date === proposal.date && (after.planned_start_time === null) === (proposal.start_time === null));
  if(proposal.start_time !== null) { const local = localParts(after.planned_start_time!,proposal.timezone_name); requireValue(local.date === proposal.date && local.clock === proposal.start_time.slice(0,5) && new Date(after.planned_start_time!).getUTCSeconds() === Number(proposal.start_time.slice(6) || 0)); }
  requireValue(Array.isArray(x.conflicts) && x.conflicts.length <= 4000);
  for(const c of x.conflicts as unknown[]) { const r=object(c); requireDay(r.date); requireValue(r.plan_id === proposal.plan_id && ["fixed","flexible","review"].includes(String(r.severity)) && ["plan_title","occurrence_key","constraint_title","code"].every(k=>typeof r[k] === "string")); }
  if(x.duration_estimate !== null) readDurationEstimate(x.duration_estimate,proposal.plan_id,owner);
  const {review_hash, ...raw} = x;
  const stable = {...raw, duration_estimate: x.duration_estimate ? Object.fromEntries(Object.entries(object(x.duration_estimate)).filter(([k])=>k !== "as_of")) : null};
  requireValue(review_hash === await sha(stable)); return x as MoveReview;
}
export async function readMoveReceipt(v: unknown, owner: string, body?: string): Promise<MoveReceipt> {
  const x = object(v), a = object(x.artifact); flags(x); flags(a);
  const p = readMoveProposal(a.proposal);
  const prefix = "pt-workout-move:" + await sha({athlete_id:owner,plan_id:p.plan_id}) + ":" + p.request_id.replaceAll("-","");
  requireValue(x.identity_scope === "APPLICATION_DEMO_USER" && x.committed === true && typeof x.reused === "boolean" && validInstant(x.durable_available_at) && a.schema_version === "calendar-workout-move-v0.1" && a.athlete_id === owner && a.artifact_id === prefix && a.calendar_timing_changed === true && validInstant(a.created_at) && Number.isInteger(a.revision) && Number(a.revision)>0 && (a.revision === 1) === (p.previous_reference === null));
  const before=timing(a.before), after=timing(a.after), source=object(object(a.source_before).workout);
  requireValue(source.id === p.plan_id && canonical(before) === canonical({date:source.date,planned_start_time:source.planned_start_time}) && await sha(a.source_before) === p.expected_source_hash && after.date === p.date && (after.planned_start_time === null) === (p.start_time === null));
  if(p.start_time !== null) { const local=localParts(after.planned_start_time!,p.timezone_name); requireValue(local.date===p.date && local.clock===p.start_time.slice(0,5) && new Date(after.planned_start_time!).getUTCSeconds()===Number(p.start_time.slice(6)||0)); }
  const reviewed=await readMoveReview(a.review,p,owner); requireValue(reviewed.review_hash===a.review_hash && canonical(reviewed.before)===canonical(before) && canonical(reviewed.after)===canonical(after));
  const {content_hash,...raw}=a; requireValue(content_hash === await sha(raw));
  if(body) {const expected = object(JSON.parse(body)); requireValue(canonical(expected.proposal) === canonical(p) && expected.review_hash === a.review_hash);}
  return x as MoveReceipt;
}
export function readMovePending(raw: string): MovePending {
  const x = object(JSON.parse(raw)); requireValue(x.version === "calendar-move-pending-v0.1" && typeof x.owner === "string" && uuid.test(x.owner) && typeof x.body === "string" && typeof x.undo === "boolean");
  const b=object(JSON.parse(x.body as string)); readMoveProposal(b.proposal); requireValue(typeof b.review_hash === "string" && hash.test(b.review_hash) && Object.keys(b).sort().join() === "proposal,review_hash"); return x as MovePending;
}
export const moveMessages: Record<string,string> = {
  CALENDAR_MOVE_ALREADY_EXECUTED:"Ehhez az edzéshez már teljesítés tartozik. A korábbi időpont megmarad.",
  CALENDAR_MOVE_STATUS_BLOCKED:"Ez az edzésállapot már nem helyezhető át.",
  CALENDAR_MOVE_APPROVED_PLAN_REVIEW_REQUIRED:"Ez az edzés véglegesített terv része. Áthelyezéséhez a terv felülvizsgálata szükséges.",
  CALENDAR_MOVE_SOURCE_CHANGED:"Az edzés közben megváltozott. Olvasd újra és tekintsd át az új időpontot.",
  CALENDAR_MOVE_REVISION_CONFLICT:"Másik időpontmódosítás történt. Olvasd újra a naptárt.",
  CALENDAR_MOVE_REVIEW_CHANGED:"Az előnézet óta változtak az ütközések vagy az adatok. Készíts új előnézetet.",
  CALENDAR_MOVE_NO_CHANGE:"Az új időpont megegyezik a jelenlegivel.",
  CALENDAR_MOVE_TIMEZONE_CHANGED:"Az időzóna megváltozott. Olvasd újra a napirendet.",
  ATHLETE_TIME_DOES_NOT_EXIST:"Az óraátállítás miatt ez a helyi időpont nem létezik.",
  ATHLETE_TIME_IS_AMBIGUOUS:"Ez az óra kétszer fordul elő. Válassz az első és második előfordulás közül.",
};
export class MoveHTTPError extends Error { constructor(public status:number, public code:string) {super(moveMessages[code] ?? `Az áthelyezés nem sikerült (${code || status}).`);} }
async function request(path: string, body?: string, signal?: AbortSignal) {
  const r=await fetch("/api/calendar/moves"+path,{method:body ? "POST":"GET",body,signal,cache:"no-store",headers:{Accept:"application/json",...(body ? {"Content-Type":"application/json"}:{})}});
  let v:unknown;try{v=await r.json();}catch{throw Error("A válasz nem olvasható. Mentés esetén az eredmény még nem ismert.");}
  if(!r.ok)throw new MoveHTTPError(r.status,String(object(object(v).detail).code ?? "UNKNOWN"));return v;
}
export async function loadMove(plan:string,owner:string,signal?:AbortSignal) { requireValue(uuid.test(plan)); return readMoveContext(await request("/"+plan,undefined,signal),owner,plan); }
export async function previewMove(p:MoveProposal,owner:string) {return readMoveReview(await request("/preview",JSON.stringify(p)),p,owner);}
export async function sendMove(p:MovePending) {return readMoveReceipt(await request("",p.body),p.owner,p.body);}
