import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';

function fixture(name) {
  return JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/' + name + '.json.gz', import.meta.url))));
}

const needs = fixture('c21-15-nutrition-requirements');
const { readRequirements } = load('src/lib/nutrition/requirements.ts');
const { sha } = load('src/lib/planning-cycles/contracts.ts');
const { NutritionCalendarProvider } = load('src/components/nutrition/calendar-layer.tsx');
const TimeGrid = load('src/components/calendar/time-grid.tsx').default;
const day = '2026-11-18';

test('real API preserves sport-adjusted energy, verified planned amounts and unknown actual intake', async () => {
  const result = await readRequirements(needs, needs.athlete_id, needs.start_date, needs.end_date);
  assert.deepEqual(result.days[3].maintenance_kcal, ['3080', '3290']);
  assert.deepEqual(result.days[2].workouts.extra_kcal, ['105', '210']);
  assert(result.days[2].planned.amounts.energy.amount);
  assert.equal(result.days[2].logged.amounts.energy.amount, null);
  assert.equal(result.days[4].maintenance_kcal, null);
});

for (const [name, alter] of [
  ['foreign owner', x => x.athlete_id = 'foreign'],
  ['a skipped day', x => x.days[2].date = '2026-11-18'],
  ['negative amounts', x => x.days[0].planned.amounts.iron.amount = '-8'],
  ['reversed range', x => x.days[0].maintenance_kcal = ['3', '2']],
  ['false total', x => x.days[4].maintenance_kcal = ['2050', '2300']],
  ['pretend zero intake', x => x.days[2].logged.amounts.energy.amount = '0'],
]) test('validated requirements reject ' + name, async () => {
  const result = structuredClone(needs);
  alter(result);
  delete result.content_hash;
  result.content_hash = await sha(result);
  await assert.rejects(readRequirements(result, needs.athlete_id, needs.start_date, needs.end_date));
});

test('nutrition requirements proxy allows only a dated read', async () => {
  const { forwardGoals } = load('src/lib/planning-goals/proxy.ts');
  const path = ['nutrition', 'requirements'];
  const url = 'https://paddle.test/api/goal-workflow/nutrition/requirements';
  let calls = 0;
  const send = async target => {
    calls++;
    assert.equal(String(target), 'http://127.0.0.1:8000/api/v1/planning/nutrition/requirements?start_date=2026-11-15&end_date=2026-11-19');
    return Response.json(needs);
  };
  assert.equal((await forwardGoals(new Request(url + '?start_date=2026-11-15&end_date=2026-11-19'), path, 'http://127.0.0.1:8000', send)).status, 200);
  assert.equal((await forwardGoals(new Request(url + '?owner=other'), path, 'http://127.0.0.1:8000', send)).status, 422);
  assert.equal((await forwardGoals(new Request(url, { method: 'POST' }), path, 'http://127.0.0.1:8000', send)).status, 405);
  assert.equal(calls, 1);
});

function renderGrid(fullDay, length = 1) {
  const packet = fixture('c21-13-nutrition-calendar');
  const meals = packet.result.days.find(d => d.date === day).meals;
  const times = { breakfast: '07:30:00', lunch: '12:30:00', dinner: '20:15:30', snack: '23:00:00' };
  for (const meal of meals) meal.planned_time = times[meal.slot];
  const feed = { periods: [], local_today: day, timezone_name: packet.timezone, availability: { days: [] } };
  const events = [{ key: 'planned/1', kind: 'planned', date: day, sport: 'RUNNING', title: 'Könnyű futás',
    start: day + 'T12:30:00+01:00', end: day + 'T13:15:00+01:00', duration: 2700, goal: null }];
  const options = { feed, events, days: Array.from({ length }, (_, i) => '2026-11-' + (18 + i)), fullDay,
    open() {}, selectDay() {}, expandHours() {} };
  const useState = React.useState;
  let seed = true;
  const injection = mock.method(React, 'useState', initial => {
    if (!seed) return useState(initial);
    // Render the same first state used once the provider has fetched a saved meal packet.
    seed = false;
    assert.deepEqual(initial, []);
    return useState([packet]);
  });
  try {
    return renderToStaticMarkup(React.createElement(NutritionCalendarProvider, {
      owner: packet.athlete_id, zone: packet.timezone, start: day, end: day, enabled: true,
    }, React.createElement(TimeGrid, options)));
  } finally {
    injection.mock.restore();
  }
}

test('day grid positions clock times once and shares lanes with a simultaneous workout', () => {
  const [header, grid] = renderGrid(false).split('class="pt-grid-body"');
  assert.doesNotMatch(header, /2026-11-18\/(breakfast|lunch|dinner)/);
  const breakfast = grid.match(/<button[^>]*data-nutrition-meal="2026-11-18\/breakfast"[^>]*>/)?.[0];
  const lunch = grid.match(/<button[^>]*data-nutrition-meal="2026-11-18\/lunch"[^>]*>/)?.[0];
  const workout = grid.match(/<button[^>]*data-calendar-event="planned\/1"[^>]*>/)?.[0];
  const dinner = grid.match(/<button[^>]*data-nutrition-meal="2026-11-18\/dinner"[^>]*>/)?.[0];
  assert.match(breakfast, /top:9\.375%;height:32px/);
  assert.match(lunch, /top:40\.625%;height:32px;left:50%;width:calc\(50% - 6px\)/);
  assert.match(workout, /left:0%;width:calc\(50% - 6px\)/);
  const exact = Number(dinner.match(/top:([\d.]+)%/)[1]);
  assert(Math.abs(exact - (14 * 60 + 15.5) / (16 * 60) * 100) < 1e-10);
  assert.match(dinner, /20:15:30/);
});

test('week grid preserves no-time meals and expands to show out-of-hours meals', () => {
  const [header, grid] = renderGrid(false, 7).split('class="pt-grid-body"');
  assert.match(header, /Teljes nap mutatása/);
  assert.match(header, /2026-11-18\/snack/);
  assert.match(header, /2026-11-19\/breakfast/);
  assert.doesNotMatch(grid, /2026-11-18\/snack|2026-11-19\/breakfast/);
  const [expandedHeader, expanded] = renderGrid(true, 7).split('class="pt-grid-body"');
  assert.doesNotMatch(expandedHeader, /2026-11-18\/snack/);
  assert.match(expanded, /data-nutrition-meal="2026-11-18\/snack"[^>]*top:95\.8333/);
});
