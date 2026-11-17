import { canonical, object, sha } from '@/lib/planning-cycles/contracts';
import { civilDay, eligibleRecipes, projectNutrition, readNutritionArtifact, slots } from './contracts';
import type { Artifact as Menu, Catalog, NutritionData, Reference as MenuReference } from './contracts';

export type Slot = keyof typeof slots;
export type Entry = { id: string; date: string; time: string | null; timezone: string; fold: 0 | 1 | null; status: 'eaten' | 'skipped'; title: string; amount: string; unit: 'portion' | 'g' | 'ml' | 'db'; recipe_id: string | null; source: { reference: MenuReference; date: string; slot: Slot } | null; note: string; satisfaction: number | null };
export type Observation = { id: string; analyte: string; value: string; qualifier: 'exact' | 'less_than' | 'greater_than'; unit: string; sampled_on: string; source_name: string; reference_low: string | null; reference_high: string | null; interpretation: string; note: string };
export const nutrients = { energy: ['Energia', 'kcal'], protein: ['Fehérje', 'g'], carbohydrate: ['Szénhidrát', 'g'], fat: ['Zsír', 'g'], vitamin_d: ['D-vitamin', 'µg'], b12: ['B12-vitamin', 'µg'], iron: ['Vas', 'mg'], calcium: ['Kalcium', 'mg'], magnesium: ['Magnézium', 'mg'], zinc: ['Cink', 'mg'], iodine: ['Jód', 'µg'], folate: ['Folát', 'µg'], selenium: ['Szelén', 'µg'] } as const;
export type Target = { id: string; nutrient: keyof typeof nutrients; minimum: string | null; maximum: string | null; unit: 'kcal' | 'g' | 'mg' | 'µg'; scope: 'food_only' | 'total_intake'; source_name: string; assessed_on: string; valid_until: string | null; observation_ids: string[]; note: string };
export type JournalData = { default_times: Record<Slot, string | null>; timings: { date: string; slot: Slot; time: string | null }[]; entries: Entry[]; observations: Observation[]; targets: Target[]; muscle_goal: 'unspecified' | 'maintain' | 'gain'; performance_goal: 'unspecified' | 'strength' | 'endurance' | 'wellbeing' };
type Reference = { artifact_id: string; content_hash: string };
export type Write = { request_id: string; previous_reference: Reference | null; data: JournalData };
export type Result = { entries: { id: string; instant: string | null; recipe_portions: string | null }[]; eaten_count: number; skipped_count: number; favourites: { recipe_id: string; count: number }[]; suggested_times: Partial<Record<Slot, string>>; nutrient_totals: null; nutrient_adequacy: 'not_evaluated'; assessment_mode: 'reported_targets' | 'general_guidance' };
type Artifact = { schema_version: string; kind: string; athlete_id: string; artifact_id: string; content_hash: string; created_at: string; timezone: string; proposal: Write; result: Result };
export type Journal = { schema_version: string; athlete_id: string; timezone: string; now: string; local_today: string; saved: Artifact | null; reference: Reference | null; sources: Menu[]; content_hash: string };
const SCHEMA = 'nutrition-journal-v0.1', uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/, hex = /^[a-f0-9]{64}$/;
export function ensure(v: unknown, text = 'Az étkezési napló adatai nem ellenőrizhetők.'): asserts v { if (!v) throw Error(text); }
function exact(v: Record<string, unknown>, keys: string[]) { ensure(canonical(Object.keys(v).sort()) === canonical([...keys].sort())); }
function text(v: unknown, max = 200, empty = false): asserts v is string { ensure(typeof v === 'string' && v.length <= max && (empty || v.trim().length > 0)); }
function time(v: unknown) { ensure(v === null || typeof v === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(v), 'Az időpont óra:perc:másodperc formátumú legyen.'); }
function amount(v: unknown): number { ensure(typeof v === 'string' && /^(?:0|[1-9]\d{0,5})(?:\.\d{1,3})?$/.test(v)); return Math.round(Number(v) * 1000); }
function list(v: unknown, max: number): asserts v is unknown[] { ensure(Array.isArray(v) && v.length <= max); }
function key(v: unknown) { ensure(typeof v === 'string' && uuid.test(v)); }
export function blankJournal(): JournalData { return { default_times: { breakfast: null, lunch: null, dinner: null, snack: null }, timings: [], entries: [], observations: [], targets: [], muscle_goal: 'unspecified', performance_goal: 'unspecified' }; }
export function readData(v: unknown): JournalData {
  const d = object(v); exact(d, ['default_times', 'timings', 'entries', 'observations', 'targets', 'muscle_goal', 'performance_goal']);
  const times = object(d.default_times); exact(times, Object.keys(slots)); Object.values(times).forEach(time);
  ensure(['unspecified', 'maintain', 'gain'].includes(String(d.muscle_goal)) && ['unspecified', 'strength', 'endurance', 'wellbeing'].includes(String(d.performance_goal)));
  list(d.timings, 112); const timingKeys = new Set();
  for (const raw of d.timings) { const t = object(raw); exact(t, ['date', 'slot', 'time']); text(t.date); civilDay(t.date); ensure(Object.hasOwn(slots, String(t.slot))); time(t.time); const k = `${t.date}/${t.slot}`; ensure(!timingKeys.has(k)); timingKeys.add(k); }
  list(d.entries, 500); list(d.observations, 100); list(d.targets, 50);
  for (const rows of [d.entries, d.observations, d.targets]) { const ids = rows.map(r => object(r).id); ids.forEach(key); ensure(new Set(ids).size === ids.length); }
  const planned = new Set();
  for (const raw of d.entries) {
    const e = object(raw); exact(e, ['id', 'date', 'time', 'timezone', 'fold', 'status', 'title', 'amount', 'unit', 'recipe_id', 'source', 'note', 'satisfaction']);
    text(e.date); civilDay(e.date); time(e.time); text(e.timezone); text(e.title); text(e.note, 1000, true); amount(e.amount);
    ensure(e.fold === null || e.fold === 0 || e.fold === 1); ensure(['eaten', 'skipped'].includes(String(e.status)) && ['portion', 'g', 'ml', 'db'].includes(String(e.unit)));
    ensure(e.recipe_id === null || typeof e.recipe_id === 'string' && /^[a-z][a-z0-9_]{0,59}$/.test(e.recipe_id));
    ensure(e.satisfaction === null || typeof e.satisfaction === 'number' && Number.isInteger(e.satisfaction) && e.satisfaction >= 1 && e.satisfaction <= 5);
    if (e.status === 'eaten') ensure(e.time !== null && amount(e.amount) > 0);
    else ensure(e.time === null && e.amount === '0' && e.source !== null && e.satisfaction === null);
    if (e.source !== null) { const s = object(e.source), r = object(s.reference); exact(s, ['reference', 'date', 'slot']); exact(r, ['artifact_id', 'content_hash']); ensure(/^pt-meals:[a-f0-9]{64}$/.test(String(r.artifact_id)) && hex.test(String(r.content_hash))); text(s.date); civilDay(s.date); ensure(Object.hasOwn(slots, String(s.slot)) && e.unit === 'portion' && e.recipe_id !== null); const k = `${s.date}/${s.slot}`; ensure(!planned.has(k)); planned.add(k); }
  }
  for (const raw of d.observations) { const o = object(raw); exact(o, ['id', 'analyte', 'value', 'qualifier', 'unit', 'sampled_on', 'source_name', 'reference_low', 'reference_high', 'interpretation', 'note']); text(o.analyte); amount(o.value); ensure(['exact', 'less_than', 'greater_than'].includes(String(o.qualifier))); text(o.unit, 30); text(o.sampled_on); civilDay(o.sampled_on); text(o.source_name); text(o.interpretation, 1000, true); text(o.note, 1000, true); if (o.reference_low !== null) amount(o.reference_low); if (o.reference_high !== null) amount(o.reference_high); if (o.reference_low !== null && o.reference_high !== null) ensure(amount(o.reference_low) <= amount(o.reference_high)); }
  const ids = new Set(d.observations.map(o => object(o).id));
  for (const raw of d.targets) { const t = object(raw); exact(t, ['id', 'nutrient', 'minimum', 'maximum', 'unit', 'scope', 'source_name', 'assessed_on', 'valid_until', 'observation_ids', 'note']); ensure(Object.hasOwn(nutrients, String(t.nutrient)) && t.unit === nutrients[t.nutrient as keyof typeof nutrients][1] && ['food_only', 'total_intake'].includes(String(t.scope))); ensure(t.minimum !== null || t.maximum !== null); if (t.minimum !== null) amount(t.minimum); if (t.maximum !== null) amount(t.maximum); if (t.minimum !== null && t.maximum !== null) ensure(amount(t.minimum) <= amount(t.maximum)); text(t.source_name); text(t.assessed_on); civilDay(t.assessed_on); if (t.valid_until !== null) { text(t.valid_until); civilDay(t.valid_until); ensure(t.valid_until >= t.assessed_on); } text(t.note, 1000, true); list(t.observation_ids, 20); ensure(new Set(t.observation_ids).size === t.observation_ids.length && t.observation_ids.every(id => ids.has(id))); }
  return d as unknown as JournalData;
}
const formatters = new Map<string, Intl.DateTimeFormat>(), offsets = new Map<string, number[]>();
export function localClock(instant: string, zone: string) {
  let f = formatters.get(zone); if (!f) { f = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }); formatters.set(zone, f); }
  const p = Object.fromEntries(f.formatToParts(new Date(instant)).map(p => [p.type, p.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}:${p.second}` };
}
export function entryInstant(e: Entry): string | null {
  localClock(new Date(0).toISOString(), e.timezone);
  if (e.status === 'skipped') return null;
  const wall = `${e.date}T${e.time}`, base = Date.parse(wall + 'Z'), k = `${e.timezone}/${e.date}`;
  let possible = offsets.get(k);
  if (!possible) { const found = new Set<number>(); for (let delta = -48; delta <= 48; delta += 6) { const at = base + delta * 3600000, local = localClock(new Date(at).toISOString(), e.timezone); found.add(Date.parse(`${local.date}T${local.time}Z`) - at); } possible = [...found]; offsets.set(k, possible); }
  const candidates = [...new Set(possible.map(offset => base - offset).filter(at => { const p = localClock(new Date(at).toISOString(), e.timezone); return `${p.date}T${p.time}` === wall; }))].sort((a, b) => a - b);
  ensure(candidates.length, 'Ez a helyi időpont az óraátállítás miatt nem létezik.');
  ensure(candidates.length !== 2 || e.fold !== null, 'Az ismétlődő helyi óránál válaszd az első vagy a második előfordulást.');
  ensure(candidates.length === 2 || e.fold !== 1, 'Ez az időpont nem ismétlődő óra.');
  return new Date(candidates[e.fold ?? 0]).toISOString();
}
export function plannedTime(data: JournalData, date: string, slot: Slot) { const specific = data.timings.find(t => t.date === date && t.slot === slot); return specific ? specific.time : data.default_times[slot]; }
/** Explicit local proposal: food ratings affect variety, never allergy constraints or dose. */
export function applyFoodFeedback(data: NutritionData, c: Catalog, entries: Entry[]): NutritionData {
  if (!data.plan) return data;
  const scores = new Map<string, number>();
  for (const e of entries) if (e.status === 'eaten' && e.recipe_id && e.satisfaction !== null && e.satisfaction !== 3) scores.set(e.recipe_id, (scores.get(e.recipe_id) ?? 0) + (e.satisfaction >= 4 ? 1 : -1));
  if (!scores.size) return data;
  const meals = data.plan.meals.map((meal, i) => {
    const pool = eligibleRecipes(c, data.preferences, meal.slot);
    const best = Math.max(...pool.map(r => scores.get(r.id) ?? 0));
    const preferred = pool.filter(r => (scores.get(r.id) ?? 0) === best);
    return preferred.length ? { ...meal, recipe_id: preferred[Math.floor(i / data.preferences.meals_per_day) % preferred.length].id } : meal;
  });
  const result = { ...data, plan: { ...data.plan, meals }, checked: [] };
  projectNutrition(result, c); return result;
}
export function projectJournal(raw: unknown, sources: Menu[], at: string, zone: string, c: Catalog): Result {
  const d = readData(raw), today = localClock(at, zone).date, needed = new Set<string>(), counts = new Map<string, number>(), times = new Map<Slot, number[]>();
  ensure(d.observations.every(o => o.sampled_on <= today) && d.targets.every(t => t.assessed_on <= today), 'Felmérési adatot a tényleges, már eltelt dátumával adj meg.');
  const entries = d.entries.map(e => {
    const instant = entryInstant(e); ensure(instant === null ? e.date <= localClock(at, e.timezone).date : Date.parse(instant) <= Date.parse(at), 'Jövőbeli étkezés még nem jelölhető elfogyasztottnak.');
    if (e.recipe_id) ensure(c.recipes.some(r => r.id === e.recipe_id && r.title === e.title));
    let factor: number | null = e.recipe_id && e.unit === 'portion' ? amount(e.amount) : null;
    if (e.source) { const s = e.source, saved = sources.find(a => a.artifact_id === s.reference.artifact_id && a.content_hash === s.reference.content_hash); ensure(saved); const m = saved.proposal.data.plan?.meals.find(m => m.date === s.date && m.slot === s.slot); ensure(m?.recipe_id === e.recipe_id); needed.add(saved.artifact_id); factor = amount(m.portion_factor) * amount(e.amount) / 1000; }
    if (e.status === 'eaten' && e.recipe_id) { counts.set(e.recipe_id, (counts.get(e.recipe_id) ?? 0) + 1); if (e.source) { const [h, m, s] = e.time!.split(':').map(Number), slot = e.source.slot; times.set(slot, [...(times.get(slot) ?? []), h * 3600 + m * 60 + s]); } }
    return { id: e.id, instant, recipe_portions: factor === null ? null : String(factor / 1000) };
  });
  ensure(needed.size === sources.length && sources.every(s => needed.has(s.artifact_id)));
  const suggested_times: Partial<Record<Slot, string>> = {};
  for (const [slot, values] of times) if (values.length >= 3) { values.sort((a, b) => a - b); const s = values[Math.floor(values.length / 2)]; suggested_times[slot] = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map(v => String(v).padStart(2, '0')).join(':'); }
  return { entries, eaten_count: d.entries.filter(e => e.status === 'eaten').length, skipped_count: d.entries.filter(e => e.status === 'skipped').length, favourites: [...counts].sort(([a, n], [b, m]) => m - n || (a < b ? -1 : 1)).map(([recipe_id, count]) => ({ recipe_id, count })), suggested_times, nutrient_totals: null, nutrient_adequacy: 'not_evaluated', assessment_mode: d.targets.some(t => t.assessed_on <= today && (t.valid_until === null || t.valid_until >= today)) ? 'reported_targets' : 'general_guidance' };
}
function flags(v: Record<string, unknown>) { ensure(v.workouts_changed === false && v.personal_energy_prescribed === false && v.lab_based_dose_generated === false); }
async function hashed(v: Record<string, unknown>) { const { content_hash, ...rest } = v; ensure(await sha(rest) === content_hash); }
async function readSources(raw: unknown, owner: string, c: Catalog) { list(raw, 100); const sources = await Promise.all(raw.map(a => readNutritionArtifact(a, owner, c))); ensure(new Set(sources.map(s => s.artifact_id)).size === sources.length); return sources; }
export function readJournalWrite(raw: unknown): Write { const p = object(raw); exact(p, ['request_id', 'previous_reference', 'data']); key(p.request_id); if (p.previous_reference !== null) { const r = object(p.previous_reference); exact(r, ['artifact_id', 'content_hash']); ensure(/^pt-nutrition-journal:[a-f0-9]{64}$/.test(String(r.artifact_id)) && hex.test(String(r.content_hash))); } readData(p.data); return p as unknown as Write; }
async function readArtifact(raw: unknown, owner: string, sources: Menu[], c: Catalog) { const a = object(raw); await hashed(a); flags(a); const p = readJournalWrite(a.proposal); ensure(a.schema_version === SCHEMA && a.kind === 'nutrition_journal' && a.athlete_id === owner && a.artifact_id === 'pt-nutrition-journal:' + await sha({ owner, request_id: p.request_id })); text(a.created_at); text(a.timezone); const actual = projectJournal(p.data, sources, a.created_at, a.timezone, c), expected = object(a.result); ensure(canonical(actual.favourites) === canonical(expected.favourites) && actual.eaten_count === expected.eaten_count && actual.skipped_count === expected.skipped_count && canonical(actual.suggested_times) === canonical(expected.suggested_times) && expected.nutrient_totals === null && expected.nutrient_adequacy === 'not_evaluated' && expected.assessment_mode === actual.assessment_mode); list(expected.entries, 500); ensure(expected.entries.length === actual.entries.length); actual.entries.forEach((e, i) => { const r = object((expected.entries as unknown[])[i]); ensure(r.id === e.id && (e.instant === null ? r.instant === null : Date.parse(String(r.instant)) === Date.parse(e.instant)) && (e.recipe_portions === null ? r.recipe_portions === null : typeof r.recipe_portions === 'string' && Number(r.recipe_portions) === Number(e.recipe_portions))); }); return a as unknown as Artifact; }
export async function readJournal(raw: unknown, owner: string, c: Catalog): Promise<Journal> { const v = object(raw); await hashed(v); flags(v); ensure(v.schema_version === SCHEMA && v.athlete_id === owner); text(v.now); text(v.timezone); ensure(v.local_today === localClock(v.now, v.timezone).date); const sources = await readSources(v.sources, owner, c); const saved = v.saved === null ? null : await readArtifact(v.saved, owner, sources, c); ensure(saved || sources.length === 0); ensure(canonical(v.reference) === canonical(saved ? { artifact_id: saved.artifact_id, content_hash: saved.content_hash } : null)); return v as unknown as Journal; }
const errors: Record<string, string> = { NUTRITION_JOURNAL_REVISION_CHANGED: 'A napló közben másik ablakban megváltozott. A piszkozat megmarad; vedd át a friss mentett állapotot.', NUTRITION_JOURNAL_FUTURE_INTAKE: 'Jövőbeli étkezést még nem lehet elfogyasztottnak jelölni.', NUTRITION_JOURNAL_DST_FOLD_REQUIRED: 'Az óraátállítás ismétlődő órájánál válaszd ki az előfordulást.', NUTRITION_JOURNAL_FUTURE_ASSESSMENT: 'A felmérés dátuma nem lehet jövőbeli.' };
export class JournalHTTPError extends Error { constructor(public status: number, code: string) { super(errors[code] ?? `A napló művelete nem sikerült (${code || status}).`); } }
async function request(body?: string, signal?: AbortSignal) { const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 30000), cancel = () => abort.abort(); signal?.addEventListener('abort', cancel, { once: true }); try { if (signal?.aborted) abort.abort(); const r = await fetch('/api/goal-workflow/nutrition/journal', { method: body ? 'POST' : 'GET', body, signal: abort.signal, cache: 'no-store', headers: body ? { 'Content-Type': 'application/json' } : undefined }); const v = await r.json(); if (!r.ok) throw new JournalHTTPError(r.status, String(object(object(v).detail).code ?? '')); return v; } finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel); } }
export async function loadJournal(owner: string, c: Catalog, signal?: AbortSignal) { return readJournal(await request(undefined, signal), owner, c); }
export async function saveJournal(owner: string, c: Catalog, body: string) { const p = readJournalWrite(JSON.parse(body)), v = object(await request(body)); ensure(v.committed === true && typeof v.reused === 'boolean' && Number.isFinite(Date.parse(String(v.durable_available_at)))); const sources = await readSources(v.sources, owner, c), a = await readArtifact(v.artifact, owner, sources, c); ensure(canonical(a.proposal) === canonical(p)); return { artifact: a, sources }; }
export const journalPendingKey = (owner: string) => `paddletrainer.nutrition.journal.pending.v1:${owner}`;
