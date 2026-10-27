import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';
const { readAnalysis } = load('src/lib/session-analysis/contracts.ts');
const { speedValue, pulseTargets, timeTicks, valueAxis } = load('src/lib/session-analysis/presentation.ts');
const { displayValue, withPace } = load('src/lib/session-analysis/chart-data.ts');
const { SampleChart, Charts } = load('src/components/session-analysis/charts.tsx');
const fixture = JSON.parse(readFileSync(new URL('./fixtures/session-chart-guides.json', import.meta.url)));
const clone = x => structuredClone(x), zones = fixture.samples.exercises[0].heart_rate_zones;
const series = fixture.samples.series, speed = series.find(s => s.metric_key === 'speed_kmh');
const html = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const chart = props => html(SampleChart, { series: speed, from: 0, to: 6000, cursor: 0, setCursor: () => {}, ...props });

test('real owned read includes the exercise zone snapshot and exact plan block', () => {
  assert.deepEqual(readAnalysis(fixture, fixture.session.id), fixture);
  assert.deepEqual(pulseTargets(fixture.plan, zones).map(t => [t.zoneLabel,t.low,t.high]), [['Z2–Z3',110,150]]);
});
for (const [name, mutate] of [
  ['wrong units', z => { z.unit = '%'; }],
  ['partial list', z => { z.zones.pop(); }],
  ['reordered bands', z => { z.zones.reverse(); }],
  ['boolean limit', z => { z.zones[1].low = true; }],
  ['overlapping zones', z => { z.zones[1].low = 100; }],
  ['foreign exercise path', z => { z.source_path = 'exercises[9].zones[0]'; }],
  ['infinite limit', z => { z.zones[0].low = -Infinity; }],
]) test('zone source rejects ' + name, () => {
  const d = clone(fixture); mutate(d.samples.exercises[0].heart_rate_zones);
  assert.throws(() => readAnalysis(d, d.session.id));
});
test('older read responses and absent zones remain usable without invented thresholds', () => {
  const d = clone(fixture); delete d.samples.exercises[0].heart_rate_zones;
  assert.deepEqual(readAnalysis(d,d.session.id),d);
  const target = pulseTargets(d.plan,null)[0]; assert.equal(target.low,null); assert.equal(target.high,null);
  const markup = html(Charts,{source:series,plan:d.plan});
  assert.match(markup,/Z2–Z3/); assert.match(markup,/zónadefiníció szükséges/); assert.doesNotMatch(markup,/class="pt-chart-target"/);
});
for (const [unit, expected] of [['km/h',18.52],['m/s',18.52/3.6],['knots',10]]) test('speed converts exactly and preserves source values: ' + unit, () => {
  const copy = clone(speed);
  assert.equal(speedValue(18.52,unit),expected); assert.equal(speedValue(0,unit),0);
  assert.match(displayValue(speed,18.52,unit),new RegExp(unit.replace('/','\\/')+'$'));
  assert.equal(displayValue(speed,null,unit),'Nincs minta'); assert.deepEqual(speed,copy);
  const markup = chart({speedUnit:unit}); assert.ok(markup.includes('Sebesség · '+unit));
  assert.doesNotMatch(markup,/NaN|Infinity/);
});
test('pace is independent of the displayed speed unit and never divides by zero', () => {
  const p = withPace([speed])[1];
  for (const unit of ['km/h','m/s','knots']) {
    assert.equal(displayValue(p,300,unit),'5:00 perc/km');
    assert.equal(p.values[1],null);
    assert.match(chart({series:p,speedUnit:unit}),/5:00/);
  }
  assert.doesNotMatch(displayValue(p,Number.MAX_VALUE,'knots'),/NaN|Infinity/);
});
test('round value ticks replace arbitrary endpoints with more readable horizontal guides', () => {
  assert.deepEqual(valueAxis(90,145).ticks,[90,100,110,120,130,140,150]);
  assert.deepEqual(valueAxis(0,16.12).ticks,[0,2.5,5,7.5,10,12.5,15,17.5]);
  assert.ok(valueAxis(5*60,6*60,true).ticks.every(t => t%10===0));
  const markup=chart({series:{...series[0],values:[90,145]}});
  assert.equal((markup.match(/pt-chart-value-grid/g)||[]).length,7);
});
test('time guides are shared across all channels and retain exact zoom boundaries', () => {
  assert.deepEqual(timeTicks(0,1997000),[0,600000,1200000,1800000,1997000]);
  const ticks=timeTicks(1234,44444);assert.equal(ticks[0],1234);assert.equal(ticks.at(-1),44444);
  assert.deepEqual(timeTicks(2500,2500),[2500]);
  assert.ok(ticks.every((v,i)=>!i||v>ticks[i-1]));
});
test('target limits stay visible outside measured range and carry the exact block label', () => {
  const target=pulseTargets(fixture.plan,zones)[0];
  const markup=chart({series:series[0],zones,target});
  assert.match(markup,/pt-chart-target/);assert.match(markup,/110 bpm/);assert.match(markup,/150 bpm/);
  assert.match(markup,/&lt;script&gt;literal&lt;\/script&gt;/);assert.doesNotMatch(markup,/<script>/);
  assert.match(html(Charts,{source:series,plan:fixture.plan,zones}),/Z5/);
});
test('direct bpm targets need no zone conversion; percent or malformed zone numbers are never assumed', () => {
  const d=clone(fixture.plan),b=d.blocks[0];b.intensity_type='HR_BPM';b.intensity_min=120;b.intensity_max=140;
  assert.deepEqual(pulseTargets(d,null).map(t=>[t.low,t.high,t.zoneLabel]),[[120,140,null]]);
  for(const [type,low,high] of [['HR_PERCENT',60,70],['HR_ZONE',1.5,3],['HEART_RATE_ZONES',3,2]]) {
    Object.assign(b,{intensity_type:type,intensity_min:low,intensity_max:high}); assert.deepEqual(pulseTargets(d,zones),[]);
  }
});
test('parent repeat containers are not offered as a second independent block target', () => {
  const d=clone(fixture.plan),parent=clone(d.blocks[0]);parent.id='00000000-0000-0000-0000-000000000099';
  d.blocks[0].parent_block_id=parent.id;d.blocks.push(parent);
  assert.equal(pulseTargets(d,zones).length,1);
});
for(const [low,high] of [[-1e308,1e308],[Number.MAX_VALUE,Number.MAX_VALUE],[0,0],[1e-300,2e-300]]) test('axis remains finite for ' + low + '..' + high, () => {
  const axis=valueAxis(low,high);assert.ok(Number.isFinite(axis.low)&&Number.isFinite(axis.high));assert.ok(axis.high>axis.low);
  assert.ok(axis.ticks.every(Number.isFinite));assert.ok(axis.ticks.length<=16);
});
