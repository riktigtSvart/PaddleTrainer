import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';
const contract = load('src/lib/session-analysis/contracts.ts');
const charts = load('src/lib/session-analysis/chart-data.ts');
const { SampleChart, Charts } = load('src/components/session-analysis/charts.tsx');
const { SessionDetails } = load('src/components/session-analysis/workspace.tsx');
const { forwardCalendar } = load('src/lib/calendar/proxy.ts');
const fixture = JSON.parse(readFileSync(new URL('./fixtures/session-analysis.json', import.meta.url)));
const id = fixture.session.id, clone = x => structuredClone(x);
const series = fixture.samples.series;

test('the complete backend-produced owned read contract is accepted', () => {
  assert.deepEqual(contract.readAnalysis(fixture, id), fixture);
});
for (const [name, mutate] of [
  ['wrong session', d => { d.session.id = '00000000-0000-0000-0000-000000000001'; }],
  ['authority claim', d => { d.planning_authorized = true; }],
  ['write claim', d => { d.workouts_changed = true; }],
  ['missing zero-valued summary field', d => { delete d.session.calories; }],
  ['guessed timestamp', d => { d.session.started_at = '2026-10-23T17:35:00'; }],
  ['wrong plan reference', d => { d.plan.id = '00000000-0000-0000-0000-000000000001'; }],
  ['invalid plan date', d => { d.plan.date = '2026-02-30'; }],
  ['false complete sample census', d => { d.samples.slot_count++; }],
  ['null replaced by zero without revised counts', d => { d.samples.series[0].values[2] = 0; }],
  ['wrong sample units', d => { d.samples.series[0].unit = 'W'; }],
  ['boolean interval', d => { d.samples.series[0].interval_ms = true; }],
  ['unknown raw type as known metric', d => { d.samples.series[0].source_type = 'FUTURE_SENSOR'; }],
  ['foreign exercise index', d => { d.samples.series[0].exercise_index = 99; }],
  ['duplicate series', d => { d.samples.series.push(clone(d.samples.series[0])); }],
  ['unknown time zone', d => { d.timezone_name = 'Not/AZone'; }],
]) test('rejects ' + name, () => { const d = clone(fixture); mutate(d); assert.throws(() => contract.readAnalysis(d, id)); });

test('zero summary, missing summary and negative temperature remain distinct', () => {
  const d = contract.readAnalysis(fixture, id);
  assert.equal(d.session.calories, 0); assert.equal(d.session.avg_hr, null);
  assert.deepEqual(d.samples.series.find(s => s.metric_key === 'temperature_c').values, [-4, 2]);
});
test('pace is derived only from finite positive speed, with original values untouched', () => {
  const original = clone(series), result = charts.withPace(series);
  const pace = result.find(s => s.metric_key === 'pace_sec_km');
  assert.deepEqual(pace.values, [300, null, 360, null]);
  assert.equal(pace.derived, true); assert.deepEqual(series, original);
  const tiny = charts.withPace([{ ...series[1], values: [Number.MIN_VALUE, 0], slot_count: 2 }]);
  assert.deepEqual(tiny[1].values, [null, null]);
});
test('a missing slot splits the measured line and never collapses its time', () => {
  const r = charts.segments(series[0], 0, 4000);
  assert.deepEqual(r.runs.map(run => run.map(p => p.index)), [[0, 1], [3, 4]]);
  assert.equal(r.runs[1][0].ms, 3000); assert.equal(r.runs[1][1].value, 0);
});
test('missing interval has no inferred plot geometry or cursor sample', () => {
  const s = series.find(s => s.interval_ms === null);
  assert.deepEqual(charts.segments(s, 0, 999999).runs, []);
  assert.equal(charts.atCursor(s, 0), null);
});
test('separate sampling rates use their source index times interval', () => {
  const speed = series.find(s => s.metric_key === 'speed_kmh');
  assert.equal(charts.extent([speed]), 6000);
  assert.equal(charts.atCursor(speed, 2000).value, 0);
  assert.equal(charts.atCursor(speed, 6000), null);
  assert.equal(charts.atCursor(speed, 7000), null);
});
test('min/max reduction retains peaks, original ordering and all missing breaks', () => {
  const values = Array.from({ length: 10000 }, (_, i) => i % 200 === 100 ? null : i === 3000 ? 9999 : i % 20);
  const s = { ...series[0], values, slot_count: values.length };
  const result = charts.segments(s, 0, 9999000, 100);
  assert.equal(result.reduced, true);
  assert.equal(result.runs.length, 51);
  assert.ok(result.runs.flat().some(p => p.value === 9999));
  for (const run of result.runs) for (let i = 1; i < run.length; i++) {
    assert.ok(run[i - 1].index < run[i].index);
    assert.ok(!values.slice(run[i - 1].index, run[i].index + 1).includes(null));
  }
});
test('zoom bounds do not pull neighbouring samples into the plotted window', () => {
  const result = charts.segments(series[0], 1100, 2900);
  assert.deepEqual(result.runs, []);
});
test('an isolated source sample remains a visible point and zero remains zero', () => {
  const s = { ...series[0], values: [null, 0, null] };
  const html = renderToStaticMarkup(React.createElement(SampleChart, { series: s, from: 0, to: 2000, cursor: 1000, setCursor: () => {} }));
  assert.match(html, /<circle/); assert.match(html, /0 bpm/); assert.doesNotMatch(html, /NaN|Infinity/);
});
test('empty, missing and constant traces never produce invalid SVG geometry', () => {
  for (const values of [[], [null, null], [100, 100], [0]]) {
    const html = renderToStaticMarkup(React.createElement(SampleChart, { series: { ...series[0], values }, from: 0, to: 4000, cursor: 0, setCursor: () => {} }));
    assert.doesNotMatch(html, /NaN|Infinity/);
  }
});
test('millisecond sample times retain their source precision', () => {
  assert.equal(charts.clock(1500), '0:01,5');
  assert.equal(charts.clock(3600001), '1:00:00,001');
  assert.equal(charts.clock(60000), '1:00');
});
test('pace axes use minutes per km rather than labeling seconds as minutes', () => {
  const pace = charts.withPace(series).find(s => s.metric_key === 'pace_sec_km');
  const html = renderToStaticMarkup(React.createElement(SampleChart, { series:pace, from:0, to:6000, cursor:0, setCursor:()=>{} }));
  assert.match(html, />5:00<\/text>/); assert.match(html, />6:00<\/text>/);
  assert.doesNotMatch(html, />300<\/text>|>360<\/text>/);
});
test('finite source extremes cannot overflow the plotted SVG scale', () => {
  for (const values of [[-1e308, 1e308], [Number.MAX_VALUE], [-Number.MAX_VALUE]]) {
    const html = renderToStaticMarkup(React.createElement(SampleChart, { series: { ...series[0], metric_key:'altitude_m', values }, from:0, to:4000, cursor:0, setCursor:()=>{} }));
    assert.doesNotMatch(html, /NaN|Infinity/);
  }
});
test('controls expose independent source channels and accessible numeric sample inspection', () => {
  const html = renderToStaticMarkup(React.createElement(Charts, { source: series }));
  assert.match(html, /type="checkbox"/); assert.match(html, /Vizsgált mintavételi idő/);
  assert.match(html, /Legközelebbi forrásminták/); assert.match(html, /Bal oldali teljesítmény/);
  assert.match(html, /Jobb oldali teljesítmény/); assert.match(html, /Iram/);
});
test('real details compare planned and reported time without treating elapsed as active time', () => {
  const html = renderToStaticMarkup(React.createElement(SessionDetails, { data: fixture }));
  assert.match(html, /Terv és teljesítés/); assert.match(html, /45:00/); assert.match(html, /50:00/);
  assert.match(html, /0 kcal/); assert.match(html, /Nincs adat/);
  assert.match(html, /&lt;script&gt;literal&lt;\/script&gt;/); assert.doesNotMatch(html, /<script>/);
});
test('unavailable samples never invent a graph from summary averages', () => {
  const d = clone(fixture); d.samples.series = []; d.samples.slot_count = 0; d.samples.valid_sample_count = 0;
  const html = renderToStaticMarkup(React.createElement(SessionDetails, { data: contract.readAnalysis(d, id) }));
  assert.match(html, /nincs megjeleníthető tárolt mintasor/); assert.doesNotMatch(html, /<svg/);
});
for (const [method, path, query, status] of [
  ['GET', 'sessions/' + id, '', 200], ['POST', 'sessions/' + id, '', 405],
  ['GET', 'sessions', '', 404], ['GET', 'sessions/evil', '', 404],
  ['GET', 'sessions/' + id, '?include_raw=1', 422], ['GET', 'sessions/' + id, '?url=http://evil.invalid', 422],
]) test(`closed session projection proxy ${method} ${path}${query}`, async () => {
  let calls = 0;
  const response = await forwardCalendar(new Request('http://localhost:3000/api/calendar/' + path + query, { method }),
    path.split('/'), 'http://localhost:8000', async (url, init) => {
      calls++; assert.equal(new URL(url).pathname, '/api/v1/planning/calendar/' + path);
      assert.deepEqual(init.headers, { Accept: 'application/json' }); assert.equal(init.cache, 'no-store');
      assert.equal(init.redirect, 'error'); return Response.json(fixture);
    });
  assert.equal(response.status, status); assert.equal(calls, status === 200 ? 1 : 0);
});
