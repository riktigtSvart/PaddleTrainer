import { canonical, day, object, sha } from "@/lib/planning-cycles/contracts";
export type MassItem = { measurement_id: string; value_kg: string; recorded_on: string; recorded_at: string; source: string; source_reference: { artifact_id: string; content_hash: string }; note: string };
export type MassProjection = { schema_version: "body-mass-projection-v0.1"; athlete_id: string; current: MassItem | null; total: number; latest_by: string; content_hash: string };
export type NutritionKind = "weight_loss" | "weight_maintenance" | "weight_gain" | "recomposition";
export type BodyArtifact = { schema_version: "body-and-nutrition-v0.1"; artifact_id: string; athlete_id: string; kind: "body_mass_measurement" | "nutrition_goal"; proposal: Record<string, unknown>; source: unknown; created_at: string; content_hash: string; planning_authorized: false; workouts_created: false; diet_created: false };
export type BodyState = { schema_version: "body-and-nutrition-v0.1"; athlete_id: string; local_today: string; current: MassItem | null; items: MassItem[]; total: number; limit: number; offset: number; has_more: boolean; latest_by: string; nutrition_goal: BodyArtifact | null; legacy_goals: { program_title: string; program_reference: { artifact_id: string; content_hash: string }; goal: "weight_loss" | "weight_maintenance"; body_mass?: { current_kg: string; target_kg?: string } }[]; diet_planning_available: false; content_hash: string };
export type BodyPending = { version: "body-pending-v0.1"; owner: string; operation: "body-mass" | "nutrition-goal"; body: string };
export const bodyPendingKey = (owner: string) => `paddletrainer.body.pending.v1:${owner}`;
export const bodyChangedKey = (owner: string) => `paddletrainer.body.changed.v1:${owner}`;
export const nutritionLabels: Record<NutritionKind, string> = { weight_loss: "Testsúlycsökkentés", weight_maintenance: "Testsúly megtartása", weight_gain: "Testsúlynövelés", recomposition: "Testösszetétel javítása azonos tömeg mellett" };
const fail = () => { throw Error("A testtömeg vagy testsúlycél adatai nem igazoltak."); };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const instant = (value: unknown): value is string => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
export function massNumber(raw: string) {
  const value = raw.trim().replace(",", ".");
  if (!/^(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$/.test(value) || Number(value) <= 0) throw Error("Pozitív testtömeget adj meg kilogrammban.");
  return value;
}
export function readMassItem(value: unknown): MassItem {
  const v = object(value), ref = object(v.source_reference);
  if (typeof v.value_kg !== "string" || massNumber(v.value_kg) !== v.value_kg || typeof v.recorded_on !== "string" || typeof v.recorded_at !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(v.recorded_at) || !Number.isFinite(Date.parse(v.recorded_at)) || typeof v.measurement_id !== "string" || typeof v.source !== "string" || typeof v.note !== "string" || typeof ref.artifact_id !== "string" || !/^[0-9a-f]{64}$/.test(String(ref.content_hash))) return fail();
  day(v.recorded_on); return v as MassItem;
}
async function hash(value: Record<string, unknown>) { const { content_hash, ...body } = value; if (await sha(body) !== content_hash) fail(); }
export async function readMassProjection(value: unknown, owner: string): Promise<MassProjection> {
  const v = object(value); await hash(v);
  if (v.schema_version !== "body-mass-projection-v0.1" || v.athlete_id !== owner || v.latest_by !== "measurement_day_then_recorded_at" || !Number.isInteger(v.total) || Number(v.total) < 0 || ((v.current === null) !== (v.total === 0))) return fail();
  if (v.current) readMassItem(v.current); return v as MassProjection;
}
async function artifact(value: unknown, owner: string): Promise<BodyArtifact> {
  const a = object(value), p = object(a.proposal); await hash(a);
  if (a.schema_version !== "body-and-nutrition-v0.1" || a.athlete_id !== owner || a.planning_authorized !== false || a.workouts_created !== false || a.diet_created !== false || !["body_mass_measurement", "nutrition_goal"].includes(String(a.kind)) || !uuid.test(String(p.request_id)) || !instant(a.created_at) || typeof p.note !== "string") return fail();
  const prefix = a.kind === "body_mass_measurement" ? "pt-body:" : "pt-nutrition:";
  if (a.artifact_id !== prefix + await sha({ owner, kind: a.kind, request_id: p.request_id })) return fail();
  if (a.kind === "body_mass_measurement") { if (typeof p.value_kg !== "string" || massNumber(p.value_kg) !== p.value_kg || typeof p.recorded_on !== "string") return fail(); day(p.recorded_on); }
  else {
    if (!Object.hasOwn(nutritionLabels, String(p.goal))) return fail();
    if (["weight_loss", "weight_gain"].includes(String(p.goal))) { if (typeof p.target_kg !== "string" || massNumber(p.target_kg) !== p.target_kg) return fail(); }
    else if (p.target_kg !== null) return fail();
    if (p.previous_reference !== null) { const ref = object(p.previous_reference); if (!/^pt-nutrition:[0-9a-f]{64}$/.test(String(ref.artifact_id)) || !/^[0-9a-f]{64}$/.test(String(ref.content_hash))) return fail(); }
  }
  return a as BodyArtifact;
}
export async function readBodyState(value: unknown, owner: string, limit = 100, offset = 0): Promise<BodyState> {
  const v = object(value); await hash(v);
  if (v.schema_version !== "body-and-nutrition-v0.1" || v.athlete_id !== owner || v.limit !== limit || v.offset !== offset || !Array.isArray(v.items) || v.items.length > limit || !Number.isInteger(v.total) || Number(v.total) < v.items.length || v.has_more !== (offset + v.items.length < Number(v.total)) || v.latest_by !== "measurement_day_then_recorded_at" || v.diet_planning_available !== false || !Array.isArray(v.legacy_goals) || typeof v.local_today !== "string") return fail();
  day(v.local_today); v.items.forEach(readMassItem);
  if (v.items.length !== Math.min(limit, Math.max(0, Number(v.total) - offset)) || new Set(v.items.map((r) => object(r).measurement_id)).size !== v.items.length) return fail();
  for (let i = 0; i < v.items.length; i++) {
    const row = readMassItem(v.items[i]);
    if (row.recorded_on > v.local_today) return fail();
    if (i > 0) { const before = readMassItem(v.items[i - 1]); if (before.recorded_on < row.recorded_on || (before.recorded_on === row.recorded_on && Date.parse(before.recorded_at) < Date.parse(row.recorded_at))) return fail(); }
  }
  if ((v.current === null) !== (v.total === 0)) return fail();
  if (v.current) { const current = readMassItem(v.current); if (offset === 0 && object(v.items[0]).measurement_id !== current.measurement_id) return fail(); }
  if (v.nutrition_goal && (await artifact(v.nutrition_goal, owner)).kind !== "nutrition_goal") return fail();
  for (const value of v.legacy_goals) { const g = object(value), ref = object(g.program_reference); if (!["weight_loss", "weight_maintenance"].includes(String(g.goal)) || typeof g.program_title !== "string" || !/^pt-cycle:[0-9a-f]{64}$/.test(String(ref.artifact_id)) || !/^[0-9a-f]{64}$/.test(String(ref.content_hash))) return fail(); if (g.body_mass) { const b = object(g.body_mass); if (typeof b.current_kg !== "string") return fail(); massNumber(b.current_kg); if (b.target_kg !== undefined && b.target_kg !== null) massNumber(String(b.target_kg)); } }
  return v as BodyState;
}
export function readBodyPending(raw: string, owner: string): BodyPending {
  const p = object(JSON.parse(raw));
  if (p.version !== "body-pending-v0.1" || p.owner !== owner || !["body-mass", "nutrition-goal"].includes(String(p.operation)) || typeof p.body !== "string" || new TextEncoder().encode(raw).length > 10000) return fail();
  const proposal = object(JSON.parse(p.body)); if (!uuid.test(String(proposal.request_id))) return fail();
  return p as BodyPending;
}
const labels: Record<string, string> = { ATHLETE_OBSERVATION_IN_FUTURE: "A mérés napja nem lehet jövőbeli.", NUTRITION_CURRENT_MASS_REQUIRED: "Előbb rögzíts egy testtömegmérést.", NUTRITION_TARGET_DIRECTION: "Fogyásnál a céltömeg legyen kisebb, növelésnél nagyobb a legutóbbi mért tömegnél.", NUTRITION_GOAL_CHANGED: "A testsúlycél közben megváltozott. Olvasd újra, majd ellenőrizd a módosítást.", BODY_REQUEST_CONFLICT: "Ehhez a mentéshez már más adat tartozik." };
export class BodyHTTPError extends Error { constructor(public status: number, code: string) { super(labels[code] ?? `A testtömegadat nem menthető (${code || status}).`); } }
async function request(path: string, body?: string) {
  const response = await fetch(`/api/goal-workflow/athlete/${path}`, { method: body === undefined ? "GET" : "POST", body, cache: "no-store", headers: body === undefined ? undefined : { "Content-Type": "application/json" } });
  const value: unknown = await response.json();
  if (!response.ok) throw new BodyHTTPError(response.status, String(object(object(value).detail).code ?? ""));
  return value;
}
export async function loadBodyState(owner: string, offset = 0) { return readBodyState(await request(`body-mass?limit=100&offset=${offset}`), owner, 100, offset); }
export async function sendBody(pending: BodyPending) {
  const v = object(await request(pending.operation, pending.body));
  if (v.committed !== true || typeof v.reused !== "boolean" || !instant(v.durable_available_at)) return fail();
  const a = await artifact(v.artifact, pending.owner);
  if (a.kind !== (pending.operation === "body-mass" ? "body_mass_measurement" : "nutrition_goal") || canonical(a.proposal) !== canonical(JSON.parse(pending.body))) return fail();
  return a;
}
