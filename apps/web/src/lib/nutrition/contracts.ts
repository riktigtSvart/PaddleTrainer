import { canonical, day, object, sha } from '@/lib/planning-cycles/contracts';

export const SCHEMA = 'nutrition-workspace-v0.1';
export const CATALOG_HASH = '793d79b56fbbbf2067b18c1bc086013705c74caf41138ece674dc1270d9ebda6';
export const slots = { breakfast: 'Reggeli', lunch: 'Ebéd', dinner: 'Vacsora', snack: 'Kisétkezés' };
export const diets = { omnivore: 'Vegyes étrend', pescatarian: 'Hús nélkül, hallal', vegetarian: 'Vegetáriánus', vegan: 'Vegán' };
export type Preferences = { diet: keyof typeof diets; allergens_reviewed: boolean; excluded_allergens: string[]; excluded_foods: string[]; max_prep_minutes: number; meals_per_day: number };
export type Food = { id: string; name: string; category: string; unit: 'g' | 'ml' | 'db'; allergens: string[]; animal_source: 'none' | 'milk_egg' | 'fish' | 'meat' };
export type Recipe = { id: string; title: string; slots: (keyof typeof slots)[]; prep_minutes: number; ingredients: { food_id: string; quantity: string }[]; steps: string[] };
export type Catalog = { schema_version: 'nutrition-catalog-v0.1'; version: string; content_hash: string; allergens: Record<string, string>; categories: Record<string, string>; foods: Food[]; recipes: Recipe[]; sources: { title: string; url: string }[] };
export type Meal = { date: string; slot: keyof typeof slots; recipe_id: string; portion_factor: '0.5' | '1' | '1.5' | '2' };
export type Plan = { start_date: string; day_count: number; people: number; meals: Meal[] };
export type NutritionData = { preferences: Preferences; plan: Plan | null; pantry: Record<string, string>; checked: string[] };
export type Projection = { days: { date: string; meals: (Meal & { ingredients: { food_id: string; quantity: string }[] })[] }[]; shopping: { food_id: string; required: string; in_stock: string; to_buy: string; checked: boolean }[]; meal_count: number };
export type Reference = { artifact_id: string; content_hash: string };
export type Write = { request_id: string; previous_reference: Reference | null; catalog_hash: string; data: NutritionData };
export type Artifact = { schema_version: typeof SCHEMA; kind: 'nutrition_workspace'; athlete_id: string; artifact_id: string; created_at: string; proposal: Write; result: Projection; content_hash: string; workouts_changed: false; actual_intake_changed: false; personal_energy_prescribed: false };
export type Context = { schema_version: typeof SCHEMA; athlete_id: string; local_today: string; catalog: Catalog; saved: Artifact | null; reference: Reference | null; content_hash: string };
export type Receipt = { artifact: Artifact; committed: true; reused: boolean; durable_available_at: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const digest = /^[a-f0-9]{64}$/;
const instant = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
function check(value: unknown, text = 'Az étrend adatai nem ellenőrizhetők.'): asserts value { if (!value) throw Error(text); }
function exact(value: Record<string, unknown>, keys: string[]) { check(canonical(Object.keys(value).sort()) === canonical(keys.sort())); }
export function blankNutritionData(): NutritionData { return { preferences: { diet: 'omnivore', allergens_reviewed: false, excluded_allergens: [], excluded_foods: [], max_prep_minutes: 45, meals_per_day: 4 }, plan: null, pantry: {}, checked: [] }; }
export function civilDay(value: string, increment = 0): string { const parsed = day(value); parsed.setUTCDate(parsed.getUTCDate() + increment); const result = parsed.toISOString().slice(0, 10); check(result >= '1900-01-01' && result <= '2100-12-31', 'A dátum 1900 és 2100 közé essen.'); return result; }
function unique(values: unknown, limit: number): asserts values is string[] { check(Array.isArray(values) && values.length <= limit && values.every(v => typeof v === 'string') && new Set(values).size === values.length); }
/** Fixed thousandths, never floating-point addition for shopping quantities. */
function units(value: unknown): number {
  check(typeof value === 'string' && /^(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,3})?$/.test(value), 'Pozitív vagy nulla mennyiséget adj meg, legfeljebb három tizedesjeggyel.');
  const [whole, fraction = ''] = value.split('.'); const n = Number(whole) * 1000 + Number(fraction.padEnd(3, '0'));
  check(n <= 999999000); return n;
}
function quantity(value: number): string { check(Number.isSafeInteger(value) && value >= 0); const whole = Math.floor(value / 1000), fraction = String(value % 1000).padStart(3, '0').replace(/0+$/, ''); return `${whole}${fraction ? '.' + fraction : ''}`; }
export function validPantryQuantity(value: string): boolean { if (value === '') return true; try { units(value); return true; } catch { return false; } }
export function eligibleRecipes(c: Catalog, p: Preferences, slot: keyof typeof slots): Recipe[] {
  const allowed: Record<Preferences['diet'], string[]> = { omnivore: ['none', 'milk_egg', 'fish', 'meat'], pescatarian: ['none', 'milk_egg', 'fish'], vegetarian: ['none', 'milk_egg'], vegan: ['none'] };
  return c.recipes.filter(r => r.slots.includes(slot) && r.prep_minutes <= p.max_prep_minutes && r.ingredients.every(i => {
    const f = c.foods.find(v => v.id === i.food_id)!;
    return allowed[p.diet]?.includes(f.animal_source) && !p.excluded_foods.includes(f.id) && !f.allergens.some(a => p.excluded_allergens.includes(a));
  }));
}
export function readNutritionData(value: unknown, c: Catalog): NutritionData {
  const d = object(value), p = object(d.preferences); exact(d, ['preferences', 'plan', 'pantry', 'checked']); exact(p, ['diet', 'allergens_reviewed', 'excluded_allergens', 'excluded_foods', 'max_prep_minutes', 'meals_per_day']);
  check(Object.hasOwn(diets, String(p.diet)) && typeof p.allergens_reviewed === 'boolean' && [15, 30, 45, 60].includes(Number(p.max_prep_minutes)) && typeof p.max_prep_minutes === 'number' && [3, 4].includes(Number(p.meals_per_day)) && typeof p.meals_per_day === 'number');
  unique(p.excluded_allergens, 14); unique(p.excluded_foods, 100); unique(d.checked, 100);
  const foods = new Set(c.foods.map(f => f.id)); check(p.excluded_allergens.every(a => Object.hasOwn(c.allergens, a)) && p.excluded_foods.every(f => foods.has(f)) && d.checked.every(f => foods.has(f)));
  const pantry = object(d.pantry); check(Object.keys(pantry).length <= 100); for (const [id, amount] of Object.entries(pantry)) { check(foods.has(id)); units(amount); }
  if (d.plan !== null) {
    const plan = object(d.plan); exact(plan, ['start_date', 'day_count', 'people', 'meals']);
    check(typeof plan.start_date === 'string' && Number.isInteger(plan.day_count) && Number(plan.day_count) >= 1 && Number(plan.day_count) <= 14 && Number.isInteger(plan.people) && Number(plan.people) >= 1 && Number(plan.people) <= 8 && Array.isArray(plan.meals) && plan.meals.length <= 56);
    civilDay(plan.start_date, Number(plan.day_count) - 1);
    for (const value of plan.meals) { const m = object(value); exact(m, ['date', 'slot', 'recipe_id', 'portion_factor']); check(typeof m.date === 'string' && Object.hasOwn(slots, String(m.slot)) && typeof m.recipe_id === 'string' && ['0.5', '1', '1.5', '2'].includes(String(m.portion_factor))); civilDay(m.date); }
  }
  return d as unknown as NutritionData;
}
export function projectNutrition(value: unknown, c: Catalog): Projection {
  const d = readNutritionData(value, c), plan = d.plan;
  if (!plan) { check(d.checked.length === 0); return { days: [], shopping: [], meal_count: 0 }; }
  check(d.preferences.allergens_reviewed, 'Előbb nézd át az allergéneket: jelöld a kizárandókat, vagy válaszd a „Nincs kizárandó allergén” lehetőséget.');
  const dayList = Array.from({ length: plan.day_count }, (_, i) => civilDay(plan.start_date, i)), slotList = (Object.keys(slots) as (keyof typeof slots)[]).slice(0, d.preferences.meals_per_day);
  check(plan.meals.length === dayList.length * slotList.length && new Set(plan.meals.map(m => `${m.date}/${m.slot}`)).size === plan.meals.length && plan.meals.every(m => dayList.includes(m.date) && slotList.includes(m.slot)), 'Minden nap minden étkezését pontosan egyszer add meg.');
  const totals = new Map<string, number>();
  const days = dayList.map(date => ({ date, meals: slotList.map(slot => {
    const choice = plan.meals.find(m => m.date === date && m.slot === slot)!;
    const recipe = eligibleRecipes(c, d.preferences, slot).find(r => r.id === choice.recipe_id);
    check(recipe, 'A korábbi étrend egy étele nem illik a módosított preferenciákhoz. Állíts össze új étrendet, vagy állítsd vissza a preferenciákat.');
    const ingredients = recipe.ingredients.map(i => {
      const amount = units(i.quantity) * plan.people * units(choice.portion_factor) / 1000;
      check(Number.isSafeInteger(amount)); totals.set(i.food_id, (totals.get(i.food_id) ?? 0) + amount);
      return { food_id: i.food_id, quantity: quantity(amount) };
    }); return { ...choice, ingredients };
  }) }));
  const shopping = c.foods.filter(f => totals.has(f.id)).map(f => {
    const required = totals.get(f.id)!, stock = units(d.pantry[f.id] ?? '0'), remaining = Math.max(0, required - stock), buy = f.unit === 'db' ? Math.ceil(remaining / 1000) * 1000 : remaining;
    return { food_id: f.id, required: quantity(required), in_stock: quantity(stock), to_buy: quantity(buy), checked: d.checked.includes(f.id) };
  });
  check(d.checked.every(id => shopping.some(r => r.food_id === id && r.to_buy !== '0')));
  return { days, shopping, meal_count: plan.meals.length };
}
export function generatePlan(c: Catalog, data: NutritionData, start: string, count: number, people: number): NutritionData {
  check(data.preferences.allergens_reviewed, 'Az összeállítás előtt nézd át az allergéneket.');
  check(Number.isInteger(count) && count >= 1 && count <= 14 && Number.isInteger(people) && people >= 1 && people <= 8, '1–14 napot és 1–8 főt adj meg.');
  civilDay(start, count - 1);
  const usedSlots = (Object.keys(slots) as (keyof typeof slots)[]).slice(0, data.preferences.meals_per_day);
  const meals: Meal[] = [];
  for (let index = 0; index < count; index++) for (const slot of usedSlots) {
    const pool = eligibleRecipes(c, data.preferences, slot);
    check(pool.length, `${slots[slot]}: nincs megfelelő recept. Bővítsd az elkészítési időt, vagy módosítsd a szabadon választott kizárásokat.`);
    const rank = ['lunch', 'dinner'].includes(slot) ? index * 2 + (slot === 'dinner' ? 1 : 0) : index;
    meals.push({ date: civilDay(start, index), slot, recipe_id: pool[rank % pool.length].id, portion_factor: '1' });
  }
  const result = { ...data, plan: { start_date: start, day_count: count, people, meals }, checked: [] }; projectNutrition(result, c); return result;
}
async function hashed(raw: Record<string, unknown>) { const { content_hash, ...value } = raw; check(await sha(value) === content_hash); }
function reference(value: unknown): Reference | null { if (value === null) return null; const r = object(value); exact(r, ['artifact_id', 'content_hash']); check(/^pt-meals:[a-f0-9]{64}$/.test(String(r.artifact_id)) && digest.test(String(r.content_hash))); return r as Reference; }
function flags(value: Record<string, unknown>) { check(value.workouts_changed === false && value.actual_intake_changed === false && value.personal_energy_prescribed === false); }
export function readWrite(value: unknown, c: Catalog): Write { const p = object(value); exact(p, ['request_id', 'previous_reference', 'catalog_hash', 'data']); check(typeof p.request_id === 'string' && uuid.test(p.request_id) && p.catalog_hash === c.content_hash); reference(p.previous_reference); projectNutrition(p.data, c); return p as unknown as Write; }
async function artifact(value: unknown, owner: string, c: Catalog): Promise<Artifact> {
  const a = object(value); await hashed(a); flags(a);
  const p = readWrite(a.proposal, c);
  check(a.schema_version === SCHEMA && a.kind === 'nutrition_workspace' && a.athlete_id === owner && instant(a.created_at) && a.artifact_id === 'pt-meals:' + await sha({ owner, request_id: p.request_id }) && canonical(a.result) === canonical(projectNutrition(p.data, c)));
  return a as unknown as Artifact;
}
export { artifact as readNutritionArtifact };
export async function readNutritionContext(value: unknown, expectedOwner?: string): Promise<Context> {
  const v = object(value), c = object(v.catalog); await hashed(v); await hashed(c); flags(v);
  check(v.schema_version === SCHEMA && typeof v.athlete_id === 'string' && uuid.test(v.athlete_id) && (!expectedOwner || v.athlete_id === expectedOwner) && typeof v.local_today === 'string'); civilDay(v.local_today);
  check(c.schema_version === 'nutrition-catalog-v0.1' && c.content_hash === CATALOG_HASH);
  const catalog = c as unknown as Catalog;
  const saved = v.saved === null ? null : await artifact(v.saved, v.athlete_id, catalog);
  check(canonical(reference(v.reference)) === canonical(saved ? { artifact_id: saved.artifact_id, content_hash: saved.content_hash } : null));
  return v as unknown as Context;
}
export async function readNutritionReceipt(value: unknown, owner: string, body: string, c: Catalog): Promise<Receipt> {
  const r = object(value); check(r.committed === true && typeof r.reused === 'boolean' && instant(r.durable_available_at));
  const saved = await artifact(r.artifact, owner, c); check(canonical(saved.proposal) === canonical(JSON.parse(body)));
  return r as unknown as Receipt;
}
export const pendingKey = (owner: string) => `paddletrainer.nutrition.pending.v1:${owner}`;
export function readPending(raw: string, c: Catalog): Write { check(new TextEncoder().encode(raw).length <= 100000); return readWrite(JSON.parse(raw), c); }
const labels: Record<string, string> = { NUTRITION_REVISION_CHANGED: 'Az étrend közben másik ablakban megváltozott. A piszkozatod megmaradt; olvasd újra a mentett változatot.', NUTRITION_REQUEST_CONFLICT: 'Ezzel a mentési azonosítóval már más adatot rögzítettünk.', NUTRITION_CATALOG_CHANGED: 'A receptkészlet frissült. Olvasd újra az adatokat.', NUTRITION_RECIPE_NOT_ALLOWED: 'Egy étel nem felel meg a beállított kizárásoknak.', NUTRITION_ALLERGEN_REVIEW_REQUIRED: 'Az összeállítás előtt nézd át az allergéneket.', NUTRITION_CHECKED_ITEM_INVALID: 'A bevásárlólista jelölései nem illenek az aktuális mennyiségekhez.' };
export class NutritionHTTPError extends Error { constructor(public status: number, code: string) { super(labels[code] ?? `A táplálkozási adatok nem tölthetők be vagy menthetők (${code || status}).`); } }
async function request(body?: string, signal?: AbortSignal) {
  const response = await fetch('/api/goal-workflow/nutrition', { method: body === undefined ? 'GET' : 'POST', body, signal, cache: 'no-store', headers: body === undefined ? undefined : { 'Content-Type': 'application/json' } });
  const value: unknown = await response.json(); if (!response.ok) throw new NutritionHTTPError(response.status, String(object(object(value).detail).code ?? '')); return value;
}
export async function loadNutrition(signal?: AbortSignal, owner?: string) { return readNutritionContext(await request(undefined, signal), owner); }
export async function saveNutrition(owner: string, body: string, c: Catalog) { readPending(body, c); return readNutritionReceipt(await request(body), owner, body, c); }
export function shoppingText(p: Projection, c: Catalog): string { return p.shopping.filter(r => r.to_buy !== '0').map(r => { const f = c.foods.find(f => f.id === r.food_id)!; return `${r.checked ? '[x]' : '[ ]'} ${f.name}: ${r.to_buy} ${f.unit}`; }).join('\n'); }
