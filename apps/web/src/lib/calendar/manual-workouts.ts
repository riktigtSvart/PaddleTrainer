import { object } from "@/lib/planning-cycles/contracts";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { calendarRead, calendarTransportMessages } from "./read-request";

export const MANUAL_SCHEMA = "manual-workout-v0.1";
export const manualSports: Record<string, string> = { KAYAK: "Kajak", RUNNING: "Futás", SWIMMING: "Úszás", STRENGTH: "Kondi", CYCLING: "Kerékpár", OTHER: "Egyéb" };
export const phaseLabels: Record<string, string> = { WARMUP: "Bemelegítés", WORK: "Főrész", RECOVERY: "Pihenő", COOLDOWN: "Levezetés" };
export type ManualPhase = { block_type: string; name: string; duration_sec: number | null; distance_m: number | null; repeat_count: number; recovery_duration_sec?: number | null; notes: string; intensity_type?: string | null; intensity_min?: number | null; intensity_max?: number | null };
export type ManualExercise = { exercise_id: string | null; name: string; sets: number; reps: number | null; hold_seconds: number | null; load_mode: "kg" | "bodyweight" | "none"; weight_kg: string | null; load_basis: "total" | "per_hand"; rest_seconds: number; reserve_reps: number | null; notes: string };
export type ManualDraft = { date: string; start_time: string | null; start_fold: 0 | 1 | null; sport: string; title: string; duration_sec: number | null; distance_m: number | null; description: string; location: string; intensity_type?: string | null; primary_goal: string | null; mesocycle_id: string | null; phases: ManualPhase[]; exercises: ManualExercise[] };
export type ManualProjection = { schema_version: typeof MANUAL_SCHEMA; editable: boolean; recipe: ManualDraft | null };
type Reference = { artifact_id: string; content_hash: string };
export type ManualContext = { schema_version: typeof MANUAL_SCHEMA; athlete_id: string; timezone_name: string; local_today: string; mesocycles: { id: string; title: string; start_date: string; end_date: string }[]; exercises: { id: string; label: string }[]; workout: { id: string; source_hash: string; source: string; goal_reference: Reference | null; draft: ManualDraft; editable: boolean; copyable: boolean; blocked_reason: string | null; status: string } | null; provider_writeback: false };
export type ManualSave = { request_id: string; operation: "create" | "update" | "cancel"; timezone_name: string; workout_id: string | null; expected_source_hash: string | null; expected_goal_reference: Reference | null; draft: ManualDraft | null; repeat_dates: string[]; copy_from: string | null; copy_source_hash: string | null };
export type ManualReceipt = { schema_version: typeof MANUAL_SCHEMA; athlete_id: string; request_id: string; operation: ManualSave["operation"]; committed: true; reused: boolean; workout_ids: string[]; artifact_id: string; content_hash: string; warnings: { code: "OTHER_WORKOUT_ON_DAY"; date: string }[]; provider_writeback: false; actual_training_changed: false };
export type ManualRequest = { mode: "create" | "edit" | "copy"; date: string; start_time?: string; workout_id?: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const sha = /^[a-f0-9]{64}$/;
const goals = { ...capabilityLabels, RECOVERY: "Regeneráció", MIXED: "Vegyes cél" };
function check(value: unknown): asserts value { if (!value) throw new Error("A saját edzés adatai nem értelmezhetők. Olvasd újra az adatokat."); }
function int(value: unknown, lo: number, hi: number) { return Number.isSafeInteger(value) && Number(value) >= lo && Number(value) <= hi; }
function text(value: unknown, max: number) { return typeof value === "string" && value.length <= max; }
function day(value: unknown): value is string { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= "1900-01-01" && value <= "2100-12-31" && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value; }
function distance(value: unknown) { return value === null || typeof value === "number" && Number.isFinite(value) && value > 0 && value <= 1000000; }

export function blankManualDraft(date: string): ManualDraft {
  return { date, start_time: null, start_fold: null, sport: "KAYAK", title: "", duration_sec: 3600, distance_m: null, description: "", location: "", primary_goal: null, mesocycle_id: null, phases: [], exercises: [] };
}
export function manualPhaseSeconds(p: ManualPhase): number {
  return (p.duration_sec ?? 0) * p.repeat_count + (p.recovery_duration_sec ?? 0) * Math.max(0, p.repeat_count - 1);
}
export function validateManualDraft(d: ManualDraft): string[] {
  const errors: string[] = [];
  if (!day(d.date)) errors.push("Adj meg érvényes edzésnapot.");
  if (!d.title.trim() || d.title.length > 200) errors.push("Az edzés neve 1–200 karakter legyen.");
  if (!Object.hasOwn(manualSports, d.sport)) errors.push("Válassz sportágat.");
  if (!int(d.duration_sec, 60, 86400)) errors.push("A teljes edzésidő 00:01:00 és 24:00:00 közé essen, óra:perc:másodperc formában.");
  if (!distance(d.distance_m)) errors.push("A távolság pozitív szám legyen, legfeljebb 1 000 000 méter.");
  if (d.start_time !== null && !/^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(d.start_time)) errors.push("Adj meg érvényes kezdési időt, vagy hagyd üresen.");
  if (d.start_fold !== null && (!int(d.start_fold, 0, 1) || d.start_time === null)) errors.push("Óraátállítási választáshoz kezdési idő szükséges.");
  if (d.primary_goal !== null && !Object.hasOwn(goals, d.primary_goal)) errors.push("Az edzés célja nem ismert.");
  if (d.mesocycle_id !== null && !uuid.test(d.mesocycle_id)) errors.push("A mezociklus nem ismert.");
  if (!text(d.description, 20000) || !text(d.location, 200)) errors.push("A leírás legfeljebb 20 000, a helyszín 200 karakter lehet.");
  if (d.intensity_type != null && !text(d.intensity_type, 32)) errors.push("Az intenzitásjelölés legfeljebb 32 karakter lehet.");
  if (d.phases.length > 50) errors.push("Legfeljebb 50 edzésszakasz adható meg.");
  for (const [i, p] of d.phases.entries()) {
    if (!Object.hasOwn(phaseLabels, p.block_type) || !p.name.trim() || !text(p.name, 120) || !int(p.repeat_count, 1, 100) || p.duration_sec !== null && !int(p.duration_sec, 1, 86400) || !distance(p.distance_m) || !text(p.notes, 2000)) errors.push(`${i + 1}. szakasz: név, érvényes idő vagy távolság és 1–100 közötti ismétlés szükséges.`);
    if (p.intensity_type != null && !text(p.intensity_type, 32) || [p.intensity_min, p.intensity_max].some(v => v != null && (typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1000000)) || p.intensity_min != null && p.intensity_max != null && p.intensity_min > p.intensity_max) errors.push(`${i + 1}. szakasz: ellenőrizd az intenzitás típusát és határait.`);
    if (p.recovery_duration_sec != null && !int(p.recovery_duration_sec, 0, 86400)) errors.push(`${i + 1}. szakasz: a pihenő 00:00:00 és 24:00:00 közé essen, óra:perc:másodperc formában.`);
  }
  if (d.phases.reduce((n, p) => n + (p.recovery_duration_sec ? 2 * p.repeat_count - 1 : 1), 0) > 1000) errors.push('Legfeljebb 1000 tényleges munkaszakasz és pihenő tervezhető egy alkalomba.');
  if (d.duration_sec !== null && d.phases.reduce((n, p) => n + manualPhaseSeconds(p), 0) > d.duration_sec) errors.push("A szakaszok összes ideje hosszabb a teljes edzésidőnél. Az ismétléseket és a köztük lévő pihenőket is beleszámítjuk.");
  if (d.exercises.length > 40) errors.push("Legfeljebb 40 erősítő gyakorlat adható meg.");
  if (d.exercises.length && d.sport !== "STRENGTH") errors.push("Erősítő gyakorlatokhoz válaszd a Kondi sportágat, vagy töröld a gyakorlatsort.");
  for (const [i, e] of d.exercises.entries()) {
    const prefix = `${i + 1}. gyakorlat: `;
    if (!e.name.trim() || !text(e.name, 160)) errors.push(prefix + "adj meg nevet (legfeljebb 160 karakter).");
    if (!int(e.sets, 1, 20)) errors.push(prefix + "1–20 munkasorozat adható meg.");
    if ((e.reps === null) === (e.hold_seconds === null) || e.reps !== null && !int(e.reps, 1, 1000) || e.hold_seconds !== null && !int(e.hold_seconds, 1, 3600)) errors.push(prefix + "ismétlésszámot (1–1000) vagy tartási időt (1–3600 mp) adj meg.");
    if (!["kg", "bodyweight", "none"].includes(e.load_mode) || e.load_mode === "kg" && (!e.weight_kg || !/^(?:0|[1-9]\d{0,3})(?:\.\d{1,3})?$/.test(e.weight_kg) || Number(e.weight_kg) <= 0) || e.load_mode !== "kg" && e.weight_kg !== null) errors.push(prefix + "a súlyt pozitív számmal, legfeljebb három tizedessel add meg.");
    if (!int(e.rest_seconds, 0, 3600) || e.reserve_reps !== null && !int(e.reserve_reps, 0, 10) || !["total", "per_hand"].includes(e.load_basis) || !text(e.notes, 2000)) errors.push(prefix + "ellenőrizd a pihenőt (0–3600 mp), a tartalékot (0–10) és a megjegyzést.");
  }
  return errors;
}

function readDraft(value: unknown, strict = true): ManualDraft {
  const d = object(value);
  for (const field of ["date", "sport", "title", "description", "location"]) check(typeof d[field] === "string");
  check(Array.isArray(d.phases) && Array.isArray(d.exercises));
  for (const p of d.phases) { const x = object(p); check(typeof x.block_type === "string" && typeof x.name === "string" && typeof x.notes === "string"); }
  for (const e of d.exercises) { const x = object(e); check(typeof x.name === "string" && typeof x.notes === "string" && (x.exercise_id === null || typeof x.exercise_id === "string")); }
  const draft = d as ManualDraft;
  if (strict) check(validateManualDraft(draft).length === 0);
  return draft;
}
export function readManualProjection(value: unknown): ManualProjection | undefined {
  try {
    const p = object(value);
    check(p.schema_version === MANUAL_SCHEMA && typeof p.editable === "boolean");
    return { schema_version: MANUAL_SCHEMA, editable: p.editable, recipe: p.recipe === null ? null : readDraft(p.recipe) };
  } catch { return undefined; }
}
export function readManualContext(value: unknown, owner: string, workoutId?: string): ManualContext {
  const c = object(value);
  check(c.schema_version === MANUAL_SCHEMA && c.athlete_id === owner && typeof c.timezone_name === "string" && day(c.local_today) && c.provider_writeback === false);
  new Intl.DateTimeFormat("hu", { timeZone: c.timezone_name }).format();
  check(Array.isArray(c.mesocycles) && c.mesocycles.length <= 1000 && Array.isArray(c.exercises));
  for (const v of c.mesocycles) { const p = object(v); check(typeof p.id === "string" && uuid.test(p.id) && typeof p.title === "string" && day(p.start_date) && day(p.end_date) && p.start_date <= p.end_date); }
  for (const v of c.exercises) { const e = object(v); check(typeof e.id === "string" && typeof e.label === "string"); }
  if (workoutId) {
    const w = object(c.workout);
    check(w.id === workoutId && typeof w.source_hash === "string" && sha.test(w.source_hash) && typeof w.source === "string" && typeof w.editable === "boolean" && typeof w.copyable === "boolean" && (w.blocked_reason === null || typeof w.blocked_reason === "string") && typeof w.status === "string");
    if (w.goal_reference !== null) { const r = object(w.goal_reference); check(typeof r.artifact_id === "string" && /^pt-workout-goal:[a-f0-9]{64}:[a-f0-9]{32}$/.test(r.artifact_id) && typeof r.content_hash === "string" && sha.test(r.content_hash)); }
    readDraft(w.draft, false);
  } else check(c.workout === null);
  return c as ManualContext;
}

const errors: Record<string, string> = {
  ...calendarTransportMessages,
  MANUAL_WORKOUT_CHANGED: "Az edzést közben módosították. A bevitt adataid megmaradtak; az aktuális edzést újra meg kell nyitni a szerkesztéshez.",
  MANUAL_WORKOUT_PROTECTED: "Ez az edzés más forrásból származik. Másold saját edzésként egy új alkalomra.",
  MANUAL_WORKOUT_COMPLEX_BLOCKS: "Ez az edzés egymásba ágyazott szakaszokat tartalmaz; ebben a szerkesztőben még nem módosítható vagy másolható.",
  MANUAL_MESOCYCLE_DATE_MISMATCH: "Az edzés vagy valamelyik ismétlése kívül esik a kiválasztott mezocikluson. Válaszd az automatikus hozzárendelést, vagy módosítsd a dátumot.",
  MANUAL_EXERCISE_UNKNOWN: "A választott gyakorlat neve eltér a katalógustól. Válaszd újra, vagy válaszd a saját gyakorlatot.",
  MANUAL_WORKOUT_STORAGE_INVALID: "A mentési bizonylat nem ellenőrizhető. Azonos kéréssel ellenőrizheted a mentés eredményét.",
  CALENDAR_WORKOUT_NOT_FOUND: "Az edzés nem található ennél a sportolónál.",
  CALENDAR_MOVE_ALREADY_EXECUTED: "Ehhez az edzéshez már érkezett teljesítési adat, ezért a terv nem módosítható.",
  CALENDAR_MOVE_STATUS_BLOCKED: "Ez az edzés már lezárt vagy elhagyott állapotú; a terv nem módosítható.",
  CALENDAR_MOVE_APPROVED_PLAN_REVIEW_REQUIRED: "Az edzés jóváhagyott külső tervhez tartozik. Közvetlenül nem módosítható.",
  CALENDAR_MOVE_TIMEZONE_CHANGED: "Az időzóna közben megváltozott. Nyisd meg újra a szerkesztőt.",
  CALENDAR_REVISION_CONFLICT_RELOAD: "Az edzés célját közben módosították. Nyisd meg újra a szerkesztőt az aktuális célhoz.",
  CALENDAR_REQUEST_IDENTITY_CONFLICT: "Ennek a mentésnek az azonosítója már más adatokhoz tartozik. Nyisd meg újra a szerkesztőt.",
  ATHLETE_TIME_DOES_NOT_EXIST: "A kezdési idő az óraátállítás miatt nem létezik. Válassz másik időpontot.",
  ATHLETE_TIME_IS_AMBIGUOUS: "A kezdési idő az óraátállításkor kétszer fordul elő. Az óraátállítás mezőben válaszd az első vagy második előfordulást.",
};
export class ManualHTTPError extends Error {
  constructor(public status: number, public code: string, public issues: string[] = []) { super(errors[code] ?? (code === "MANUAL_INPUT_INVALID" ? "Az edzés nem menthető. Ellenőrizd az alábbi mezőket." : `A mentés nem sikerült (${status}, ${code}).`)); }
}
async function responseJSON(response: Response) {
  let value: unknown;
  try { value = await response.json(); } catch { throw new Error("A mentés válasza nem értelmezhető."); }
  if (!response.ok) {
    const detail = object(object(value).detail), issues = Array.isArray(detail.issues) ? detail.issues.map(v => {
      const i = object(v); const path = Array.isArray(i.path) ? i.path.join(" / ") : "Edzés";
      return i.type === "value_error" ? String(i.message).replace(/^Value error, /, "") : `${path}: hiányzó vagy érvénytelen érték.`;
    }) : [];
    throw new ManualHTTPError(response.status, String(detail.code ?? "UNKNOWN"), issues);
  }
  return value;
}
export async function loadManualContext(owner: string, workoutId?: string, signal?: AbortSignal) {
  check(uuid.test(owner) && (!workoutId || uuid.test(workoutId)));
  return readManualContext(await responseJSON(await calendarRead("/api/calendar/manual-workouts/" + (workoutId ?? "context"), signal)), owner, workoutId);
}
export function readManualReceipt(value: unknown, owner: string, body: ManualSave): ManualReceipt {
  const r = object(value);
  check(r.schema_version === MANUAL_SCHEMA && r.athlete_id === owner && r.request_id === body.request_id && r.operation === body.operation && r.committed === true && typeof r.reused === "boolean" && r.provider_writeback === false && r.actual_training_changed === false && Array.isArray(r.workout_ids) && r.workout_ids.length === (body.operation === "create" ? (body.repeat_dates?.length ?? 0) + 1 : 1));
  check(new Set(r.workout_ids).size === r.workout_ids.length && r.workout_ids.every(v => typeof v === "string" && uuid.test(v)) && (body.workout_id == null || r.workout_ids[0] === body.workout_id));
  check(typeof r.artifact_id === "string" && /^pt-manual-workout:[a-f0-9]{64}:[a-f0-9]{32}$/.test(r.artifact_id) && typeof r.content_hash === "string" && sha.test(r.content_hash) && Array.isArray(r.warnings));
  for (const v of r.warnings) { const w = object(v); check(w.code === "OTHER_WORKOUT_ON_DAY" && day(w.date)); }
  return r as ManualReceipt;
}
export async function saveManualWorkout(owner: string, body: string): Promise<ManualReceipt> {
  const proposal = JSON.parse(body) as ManualSave;
  const response = await fetch("/api/calendar/manual-workouts", { method: "POST", headers: { "Content-Type": "application/json" }, body });
  return readManualReceipt(await responseJSON(response), owner, proposal);
}
export const manualPendingKey = (owner: string) => `paddletrainer.manual-workout.pending.v1:${owner}`;
export function weeklyDates(first: string, occurrences: number): string[] {
  check(day(first) && int(occurrences, 1, 24));
  const dates: string[] = [];
  for (let i = 1; i < occurrences; i++) { const d = new Date(first); d.setUTCDate(d.getUTCDate() + 7 * i); const next = d.toISOString().slice(0, 10); check(day(next)); dates.push(next); }
  return dates;
}
