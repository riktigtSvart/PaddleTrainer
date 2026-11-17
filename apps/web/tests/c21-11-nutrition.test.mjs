import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';

const m = load('src/lib/nutrition/contracts.ts');
const { sha } = load('src/lib/planning-cycles/contracts.ts');
const { forwardGoals } = load('src/lib/planning-goals/proxy.ts');
const fixture = JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-11-nutrition.json.gz', import.meta.url))));
const bank = fixture.current.catalog, owner = fixture.current.athlete_id;
async function rehash(v) { delete v.content_hash; v.content_hash = await sha(v); return v; }

test('real HTTP initial, saved and idempotent receipts cross the Python/JS boundary exactly', async () => {
  for (const value of [fixture.initial, fixture.current]) assert.equal((await m.readNutritionContext(value, owner)).athlete_id, owner);
  for (const tag of ['first', 'second']) {
    const r = await m.readNutritionReceipt(fixture[tag + '_receipt'], owner, JSON.stringify(fixture[tag + '_body']), bank);
    assert.deepEqual(m.projectNutrition(r.artifact.proposal.data, bank), r.artifact.result);
  }
  assert.deepEqual(m.readPending(JSON.stringify(fixture.second_body), bank), fixture.second_body);
});

test('a multi-day plan has complete civil-date coverage, stable recipes and independent shared shopping totals', () => {
  const d = m.blankNutritionData(); d.preferences.allergens_reviewed = true;
  const generated = m.generatePlan(bank, d, '2026-10-23', 14, 8), result = m.projectNutrition(generated, bank);
  assert.equal(result.days.length, 14); assert.equal(result.meal_count, 56); assert.equal(result.days[2].date, '2026-10-25'); assert.equal(result.days.at(-1).date, '2026-11-05');
  assert.deepEqual(m.generatePlan(bank, d, '2026-10-23', 14, 8), generated);
  const sums = new Map();
  for (const day of result.days) for (const meal of day.meals) for (const i of meal.ingredients) sums.set(i.food_id, (sums.get(i.food_id) ?? 0) + Number(i.quantity));
  for (const row of result.shopping) assert.equal(Number(row.required), sums.get(row.food_id));
  assert.equal(new Set(result.shopping.map(r => r.food_id)).size, result.shopping.length);
  assert.equal(d.plan, null); assert.equal(d.preferences.allergens_reviewed, true);
});

for (const diet of Object.keys(m.diets)) for (const time of [15, 30, 45, 60]) test(`real catalog ${diet}/${time}: exclusions are never relaxed to produce a plan`, () => {
  const d = m.blankNutritionData(); Object.assign(d.preferences, { diet, max_prep_minutes: time, allergens_reviewed: true, excluded_allergens: Object.keys(bank.allergens) });
  const result = m.projectNutrition(m.generatePlan(bank, d, '2026-11-16', 7, 1), bank);
  for (const row of result.shopping) { const f = bank.foods.find(f => f.id === row.food_id); assert.equal(f.allergens.length, 0); if (diet === 'vegan') assert.equal(f.animal_source, 'none'); }
});

test('hand-calculated shared portions retain decimal stock, zero remaining stock and unit identities', () => {
  const d = m.blankNutritionData(); Object.assign(d.preferences, { diet: 'vegan', allergens_reviewed: true, meals_per_day: 3 });
  d.plan = { start_date: '2026-11-16', day_count: 1, people: 2, meals: [
    { date: '2026-11-16', slot: 'breakfast', recipe_id: 'banana_oats', portion_factor: '1.5' },
    { date: '2026-11-16', slot: 'lunch', recipe_id: 'chickpea_seed_salad', portion_factor: '0.5' },
    { date: '2026-11-16', slot: 'dinner', recipe_id: 'chickpea_seed_salad', portion_factor: '1' }] };
  d.pantry = { chickpeas: '50.5', olive_oil: '10.25', oats: '1000' };
  const rows = Object.fromEntries(m.projectNutrition(d, bank).shopping.map(r => [r.food_id, r]));
  assert.equal(rows.chickpeas.required, '750'); assert.equal(rows.chickpeas.to_buy, '699.5'); assert.equal(rows.olive_oil.to_buy, '19.75'); assert.equal(rows.oats.to_buy, '0'); assert.equal(rows.pumpkin_seeds.required, '150'); assert.equal(rows.banana.required, '450');
});

test('unknown allergy review and impossible exclusions produce no invented fallback', () => {
  const d = m.blankNutritionData(); assert.throws(() => m.generatePlan(bank, d, '2026-11-16', 7, 1), /allergén/);
  d.preferences.allergens_reviewed = true; d.preferences.excluded_foods = bank.foods.map(f => f.id);
  assert.throws(() => m.generatePlan(bank, d, '2026-11-16', 7, 1), /nincs megfelelő recept/);
  for (const [days, people] of [[15, 1], [0, 1], [1, 0], [1, 9], [true, 1]]) assert.throws(() => m.generatePlan(bank, d, '2026-11-16', days, people));
});

for (const [name, edit] of [
  ['foreign owner', v => v.saved.athlete_id = '00000000-0000-0000-0000-000000000001'],
  ['wrong recipe', v => v.saved.proposal.data.plan.meals[0].recipe_id = 'chicken_rice'],
  ['wrong total', v => v.saved.result.shopping[0].required = '999999'],
  ['wrong remaining', v => v.saved.result.shopping[0].to_buy = '999999'],
  ['wrong meal portion', v => v.saved.result.days[0].meals[0].ingredients[0].quantity = '999999'],
  ['meal omitted', v => v.saved.proposal.data.plan.meals.pop()],
  ['missing allergy review', v => v.saved.proposal.data.preferences.allergens_reviewed = false],
  ['invented energy prescription', v => v.saved.personal_energy_prescribed = true],
  ['different catalog quantity', v => v.catalog.recipes[0].ingredients[0].quantity = '999'],
  ['different catalog allergen', v => v.catalog.foods[0].allergens = ['milk']],
  ['changed pantry unit', v => v.catalog.foods[0].unit = 'db'],
]) test('a rehashed response rejects ' + name, async () => {
  const v = structuredClone(fixture.current); edit(v); await rehash(v.catalog); await rehash(v.saved); v.reference.content_hash = v.saved.content_hash; await rehash(v);
  await assert.rejects(m.readNutritionContext(v, owner));
});

test('wrong expected owner or save body cannot validate another context or receipt', async () => {
  await assert.rejects(m.readNutritionContext(fixture.current, '00000000-0000-0000-0000-000000000001'));
  const body = structuredClone(fixture.second_body); body.request_id = '00000000-0000-0000-0000-000000000001';
  await assert.rejects(m.readNutritionReceipt(fixture.second_receipt, owner, JSON.stringify(body), bank));
});

test('shopping export is ingredient-based and zero-stock rows stay out of the purchase list', () => {
  const d = structuredClone(fixture.second_body.data); const result = m.projectNutrition(d, bank); const text = m.shoppingText(result, bank);
  assert(text.includes('[x]')); assert(text.includes('ml')); assert.equal(text.split('\n').length, result.shopping.filter(r => r.to_buy !== '0').length);
  for (const value of ['', '0', '0.125', '999999']) assert(m.validPantryQuantity(value));
  for (const value of ['0.', '-1', 'NaN', '1.0001', '999999.999']) assert(!m.validPantryQuantity(value));
});

test('nutrition and shopping have real UI entry points and the cart is enabled', () => {
  const { navigation } = load('src/lib/ui/navigation.ts'); const n = navigation.find(n => n.href === '/nutrition');
  assert(n.children.some(v => v.href === '/shopping')); assert(n.children.some(v => v.href === '/nutrition'));
  const page = load('src/app/nutrition/page.tsx').default;
  const html = renderToStaticMarkup(React.createElement(page)); assert(html.includes('Étrend és táplálkozás')); assert(!html.includes('Az étrendtervezés későbbi modul'));
});

test('closed proxy forwards only exact nutrition GET/POST without credentials or arbitrary query fields', async () => {
  const calls = [], send = async (target, init) => { calls.push({ target: String(target), ...init }); return Response.json({ ok: true }); };
  for (const method of ['GET', 'POST']) {
    const r = await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition', { method, headers: { origin: 'https://paddle.test', 'content-type': 'application/json', cookie: 'private' }, body: method === 'POST' ? '{"exact":"body"}' : undefined }), ['nutrition'], 'http://api.internal', send);
    assert.equal(r.status, 200); assert.equal(calls.at(-1).target, 'http://api.internal/api/v1/planning/nutrition'); assert(!calls.at(-1).headers.cookie);
  }
  const before = calls.length;
  for (const [path, method, query, status] of [[['nutrition'], 'DELETE', '', 405], [['nutrition', 'other'], 'GET', '', 404], [['nutrition'], 'GET', '?owner=other', 422]]) {
    assert.equal((await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition' + query, { method }), path, 'http://api.internal', send)).status, status);
  }
  assert.equal(calls.length, before);
});
