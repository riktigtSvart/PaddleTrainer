import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';

const m = load('src/lib/nutrition/journal.ts'), { sha } = load('src/lib/planning-cycles/contracts.ts');
const fixture = JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-12-journal.json.gz', import.meta.url))));
const owner = fixture.current.athlete_id, catalog = fixture.catalog;
async function hash(v) { delete v.content_hash; v.content_hash = await sha(v); }

test('actual owned API journal validates in JS with source receipts, exact personal serving and immutable recovery', async () => {
  for (const c of [fixture.initial, fixture.current]) assert.equal((await m.readJournal(c, owner, catalog)).athlete_id, owner);
  const c = fixture.current;
  assert.equal(c.saved.result.entries[0].recipe_portions, '0.75');
  const r = m.projectJournal(c.saved.proposal.data, c.sources, c.saved.created_at, c.saved.timezone, catalog);
  assert.equal(Number(r.entries[0].recipe_portions), 0.75);
  assert.equal(Date.parse(r.entries[0].instant), Date.parse(c.saved.result.entries[0].instant));
  assert.equal(r.nutrient_totals, null); assert.equal(r.nutrient_adequacy, 'not_evaluated');
  assert.deepEqual(m.readJournalWrite(fixture.body), fixture.body);
  await assert.rejects(m.readJournal(c, '00000000-0000-0000-0000-000000000001', catalog));
});

for (const [name, mutation] of [
  ['foreign owner', v => v.saved.athlete_id = '00000000-0000-0000-0000-000000000001'],
  ['another source hash', v => v.saved.proposal.data.entries[0].source.reference.content_hash = 'f'.repeat(64)],
  ['household dose as personal serving', v => v.saved.result.entries[0].recipe_portions = '8'],
  ['invented energy total', v => v.saved.result.nutrient_totals = { energy: 2000 }],
  ['invented nutrient adequacy', v => v.saved.result.nutrient_adequacy = 'adequate'],
  ['lab converted to a dose', v => v.saved.lab_based_dose_generated = true],
  ['workout mutation', v => v.saved.workouts_changed = true],
  ['invented learned timing', v => v.saved.result.suggested_times.breakfast = '04:00:00'],
  ['different source recipe', v => v.saved.proposal.data.entries[0].recipe_id = 'chicken_rice'],
  ['missing backing menu', v => v.sources = []],
  ['duplicate backing menu', v => v.sources.push(structuredClone(v.sources[0]))],
  ['unexpected calorie prescription', v => v.saved.proposal.data.personal_energy_kcal = 2000],
]) test('rehashed journal still rejects ' + name, async () => {
  const v = structuredClone(fixture.current); mutation(v); await hash(v.saved); v.reference.content_hash = v.saved.content_hash; await hash(v);
  await assert.rejects(m.readJournal(v, owner, catalog));
});

test('DST gap and both autumn folds are handled as real instants, independently of machine timezone', () => {
  const e = structuredClone(fixture.body.data.entries[0]); e.date = '2026-03-29'; e.time = '02:30:00';
  assert.throws(() => m.entryInstant(e), /nem létezik/);
  e.date = '2026-10-25'; assert.throws(() => m.entryInstant(e), /előfordulást/);
  e.fold = 0; const first = m.entryInstant(e); e.fold = 1; const second = m.entryInstant(e);
  assert.equal(Date.parse(second) - Date.parse(first), 3600000);
  e.date = '2026-11-15'; assert.throws(() => m.entryInstant(e), /nem ismétlődő/);
});

test('general guidance remains available with no assessment and a lab value does not create an intake target', () => {
  const d = m.blankJournal();
  d.observations.push({ id: '00000000-0000-0000-0000-000000000001', analyte: 'Szintetikus ferritin', value: '12.350', qualifier: 'less_than', unit: 'µg/l', sampled_on: '2026-11-15', source_name: 'Tesztlabor', reference_low: '10', reference_high: '100', interpretation: '', note: '' });
  const r = m.projectJournal(d, [], fixture.current.now, fixture.current.timezone, catalog);
  assert.equal(r.assessment_mode, 'general_guidance'); assert.equal(r.nutrient_totals, null); assert.equal(d.targets.length, 0);
  assert.equal(m.readData(d).observations[0].value, '12.350');
});

test('a daily intake target uses its own unit and source, not a laboratory concentration', () => {
  const d = m.blankJournal();
  const t = { id: '00000000-0000-0000-0000-000000000002', nutrient: 'protein', minimum: '100.125', maximum: '120', unit: 'g', scope: 'total_intake', source_name: 'Teszt dietetikai értékelés', assessed_on: '2026-11-01', valid_until: '2026-12-01', observation_ids: [], note: '' };
  d.targets = [t]; assert.equal(m.readData(d).targets[0].minimum, '100.125');
  for (const edit of [t => t.unit = 'mg', t => t.minimum = true, t => t.minimum = '121', t => t.valid_until = '2026-10-01', t => t.observation_ids = ['00000000-0000-0000-0000-000000000003']]) {
    const changed = structuredClone(d); edit(changed.targets[0]); assert.throws(() => m.readData(changed));
  }
});

test('an explicit per-day time override can also clear a default without changing the recipe or dose', () => {
  const d = m.blankJournal(); d.default_times.breakfast = '07:30:15';
  assert.equal(m.plannedTime(d, '2026-11-15', 'breakfast'), '07:30:15');
  d.timings.push({ date: '2026-11-15', slot: 'breakfast', time: null });
  assert.equal(m.plannedTime(d, '2026-11-15', 'breakfast'), null);
  assert.equal(m.plannedTime(d, '2026-11-16', 'breakfast'), '07:30:15');
  assert.equal(d.entries.length, 0);
});

test('a planned meal has one personal report even if a later menu has a different source identity', () => {
  const d = structuredClone(fixture.body.data); const e = structuredClone(d.entries[0]); e.id = '00000000-0000-0000-0000-000000000004'; e.source.reference.artifact_id = 'pt-meals:' + 'f'.repeat(64); d.entries.push(e);
  assert.throws(() => m.readData(d));
});

test('actual food ratings can refine a menu while preserving individual amounts and all exclusions', () => {
  const { blankNutritionData, generatePlan, projectNutrition } = load('src/lib/nutrition/contracts.ts');
  const d = blankNutritionData(); d.preferences.allergens_reviewed = true;
  const plan = generatePlan(catalog, d, '2026-11-15', 3, 8);
  plan.plan.meals[0].portion_factor = '1.5';
  const e = structuredClone(fixture.body.data.entries[0]); e.status = 'eaten'; e.satisfaction = 5;
  const adjusted = m.applyFoodFeedback(plan, catalog, [e]);
  assert.equal(adjusted.plan.meals[0].portion_factor, '1.5'); assert.equal(adjusted.plan.people, 8);
  assert.equal(adjusted.plan.meals[0].recipe_id, e.recipe_id);
  assert(projectNutrition(adjusted, catalog));
  const avoided = structuredClone(plan); avoided.preferences.excluded_foods = [catalog.recipes.find(r => r.id === e.recipe_id).ingredients[0].food_id];
  const safe = m.applyFoodFeedback(avoided, catalog, [e]);
  assert(safe.plan.meals.every(meal => meal.recipe_id !== e.recipe_id));
  projectNutrition(safe, catalog);
  e.satisfaction = null; assert.deepEqual(m.applyFoodFeedback(plan, catalog, [e]), plan);
});

test('journal read uses one bounded GET; a save is not automatically accepted or replayed', async () => {
  const original = globalThis.fetch, calls = [];
  try {
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return Response.json(fixture.current); };
    await m.loadJournal(owner, catalog); assert.equal(calls.length, 1); assert.equal(calls[0].options.method, 'GET');
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return Response.json(fixture.receipt); };
    await m.saveJournal(owner, catalog, JSON.stringify(fixture.body)); assert.equal(calls.length, 2); assert.equal(calls[1].options.body, JSON.stringify(fixture.body));
    globalThis.fetch = async () => { throw Error('network'); };
    await assert.rejects(m.saveJournal(owner, catalog, JSON.stringify(fixture.body)), /network/);
  } finally { globalThis.fetch = original; }
});

test('closed proxy exposes only the exact journal path and retains origin/query protections', async () => {
  const { forwardGoals } = load('src/lib/planning-goals/proxy.ts'); const calls = [];
  const send = async (url, options) => { calls.push({ url: String(url), options }); return Response.json({ ok: true }); };
  for (const method of ['GET', 'POST']) {
    const r = await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition/journal', { method, body: method === 'POST' ? '{"same":"bytes"}' : undefined, headers: { origin: 'https://paddle.test', 'content-type': 'application/json', cookie: 'private' } }), ['nutrition', 'journal'], 'http://api.internal', send);
    assert.equal(r.status, 200); assert.equal(calls.at(-1).url, 'http://api.internal/api/v1/planning/nutrition/journal'); assert(!calls.at(-1).options.headers.cookie);
  }
  for (const [path, method, query, expected] of [[['nutrition', 'journal'], 'DELETE', '', 405], [['nutrition', 'journal', 'other'], 'GET', '', 404], [['nutrition', 'journal'], 'GET', '?owner=x', 422]]) {
    assert.equal((await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition/journal' + query, { method }), path, 'http://api.internal', send)).status, expected);
  }
  assert.equal(calls.length, 2);
});

test('the journal panel explains unknown intake and separates assessment from laboratory-derived dosing', () => {
  const { JournalWorkspace } = load('src/components/nutrition/journal-workspace.tsx');
  const store = { context: fixture.current, data: fixture.body.data, menu: { catalog }, preview: fixture.current.saved.result, locked: false, dirty: false, error: '', notice: '', save() {}, edit() {}, refresh() {} };
  const html = renderToStaticMarkup(React.createElement(JournalWorkspace, { store }));
  for (const text of ['Étkezés hozzáadása', 'ismeretlen bevitel', 'laborérték', 'személyes', 'nincs teljes, ellenőrzött tápanyag']) assert(html.includes(text));
  assert(html.includes('07:30:15')); assert(!html.includes('minden szükségleted teljesült'));
});
