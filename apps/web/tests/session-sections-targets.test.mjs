import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const c=load('src/lib/session-analysis/contracts.ts');
const {graphTargets,targetOnChart,zonesOnChart}=load('src/lib/session-analysis/presentation.ts');
const {withPace}=load('src/lib/session-analysis/chart-data.ts');
const {SessionSections}=load('src/components/session-analysis/sections.tsx');
const {Charts}=load('src/components/session-analysis/charts.tsx');
const d=JSON.parse(readFileSync(new URL('./fixtures/session-sections-targets.json',import.meta.url)));
const clone=x=>structuredClone(x), html=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const e=d.samples.exercises[0],defs={heart_rate:e.heart_rate_zones,speed:e.speed_zones,power:e.power_zones};

test('the real owned read validates ordered laps and separate speed/power definitions',()=>{
 assert.deepEqual(c.readAnalysis(d,d.session.id),d);
 assert.deepEqual(d.sections.groups[1].rows.map(r=>r.avg_hr),[110,125,135]);
 assert.equal(d.sections.groups[2].rows[0].avg_speed,null);
});
for(const [name,mutate] of [
 ['row census',a=>{a.sections.row_count++;}],
 ['foreign exercise',a=>{a.sections.groups[1].rows[0].exercise_index=99;}],
 ['different lap source',a=>{a.sections.groups[1].rows[0].id='exercises[3].laps.laps[0]';}],
 ['duplicate group',a=>{a.sections.groups.push(clone(a.sections.groups[1]));}],
 ['duplicate position',a=>{a.sections.groups[1].rows[1].position=0;}],
 ['boolean average',a=>{a.sections.groups[1].rows[0].avg_hr=true;}],
 ['missing field',a=>{delete a.sections.groups[1].rows[0].avg_speed;}],
 ['negative duration',a=>{a.sections.groups[1].rows[0].duration_sec=-2;}],
 ['incorrect speed unit',a=>{a.samples.exercises[0].speed_zones.unit='m/s';}],
 ['overlapping power limits',a=>{a.samples.exercises[0].power_zones.zones[1].low=50;}],
]) test('new read rejects '+name,()=>{const a=clone(d);mutate(a);assert.throws(()=>c.readAnalysis(a,a.session.id));});
test('old read contracts remain valid without optional sections or non-HR zones',()=>{
 const a=clone(d);delete a.sections;delete a.samples.exercises[0].speed_zones;delete a.samples.exercises[0].power_zones;
 assert.deepEqual(c.readAnalysis(a,a.session.id),a);
});
for(const [unit,expected] of [['km/h','9 km/h'],['m/s','2,5 m/s'],['knots','4,86 knots']])test('lap table preserves provider means and converts speed: '+unit,()=>{
 const before=clone(d.sections),markup=html(SessionSections,{source:d.sections,plan:d.plan,speedUnit:unit});
 assert.ok(markup.includes(expected));assert.match(markup,/110 bpm/);assert.match(markup,/125 bpm/);assert.match(markup,/135 bpm/);
 assert.match(markup,/2:00/);assert.match(markup,/5:00/);assert.match(markup,/10:00/);assert.match(markup,/0,3 km/);
 assert.deepEqual(d.sections,before);
});
test('a missing duration makes the cumulative time unknown rather than skipping a gap',()=>{
 const a=clone(d.sections);a.groups[1].rows[1].duration_sec=null;
 const markup=html(SessionSections,{source:a,plan:null,speedUnit:'km/h'});
 assert.match(markup,/Nincs adat/);assert.doesNotMatch(markup,/10:00/);
});
test('unknown section means are never filled with whole-session averages and planned names stay escaped',()=>{
 const a=clone(d.sections);for(const r of a.groups[1].rows){r.avg_hr=null;r.avg_speed=null;}
 const markup=html(SessionSections,{source:a,plan:d.plan,speedUnit:'m/s'});
 assert.doesNotMatch(markup,/124 bpm|10,8 km\/h/);assert.match(markup,/&lt;script&gt;x&lt;\/script&gt;/);assert.doesNotMatch(markup,/<script>/);
});
test('speed targets use the same exact range in km/h, m/s, knots and reciprocal pace',()=>{
 const target=graphTargets(d.plan,defs).find(t=>t.family==='speed');
 assert.deepEqual([target.low,target.high],[2,6]);
 assert.deepEqual([targetOnChart(target,'speed_kmh','m/s').low,targetOnChart(target,'speed_kmh','m/s').high],[2/3.6,6/3.6]);
 assert.equal(targetOnChart(target,'speed_kmh','knots').high,6/1.852);
 assert.deepEqual([targetOnChart(target,'pace_sec_km','knots').low,targetOnChart(target,'pace_sec_km','knots').high],[600,1800]);
 assert.equal(targetOnChart(target,'heart_rate_bpm','km/h'),null);
});
test('explicit pace and m/s prescriptions convert once into canonical speed',()=>{
 const plan=clone(d.plan);plan.blocks=[{...plan.blocks[0],intensity_type:'PACE_SEC_KM',intensity_min:300,intensity_max:360}];
 let target=graphTargets(plan,defs)[0];assert.deepEqual([target.low,target.high],[10,12]);
 assert.equal(targetOnChart(target,'pace_sec_km','knots').low,300);
 Object.assign(plan.blocks[0],{intensity_type:'SPEED_MPS',intensity_min:3,intensity_max:4});
 target=graphTargets(plan,defs)[0];assert.deepEqual([target.low,target.high],[10.8,14.4]);
});
test('zone power uses watts and never overlays an overall target on a single crank trace',()=>{
 const plan=clone(d.plan);plan.blocks=[{...plan.blocks[0],intensity_type:'POWER_ZONES',intensity_min:2,intensity_max:3}];
 const target=graphTargets(plan,defs)[0];assert.deepEqual([target.low,target.high],[100,300]);
 assert.equal(targetOnChart(target,'power_w','km/h').low,100);
 assert.equal(targetOnChart(target,'left_power_w','km/h'),null);assert.equal(targetOnChart(target,'right_power_w','km/h'),null);
});
test('zero speed keeps its band while reciprocal pace has no invented finite upper limit',()=>{
 const plan=clone(d.plan);plan.blocks=[{...plan.blocks[0],intensity_type:'SPEED_KMH',intensity_min:0,intensity_max:12}];
 const target=graphTargets(plan,defs)[0];assert.equal(targetOnChart(target,'speed_kmh','m/s').low,0);
 assert.equal(targetOnChart(target,'pace_sec_km','m/s'),null);
 assert.equal(zonesOnChart(e.speed_zones,'pace_sec_km','knots').zones.length,4);
});
test('missing zone definitions retain named intent without numerical invention',()=>{
 const targets=graphTargets(d.plan,{...defs,speed:null});const target=targets.find(t=>t.family==='speed');
 assert.equal(target.zoneLabel,'Z2–Z3');assert.equal(target.low,null);assert.equal(targetOnChart(target,'speed_kmh','m/s'),null);
});
test('displayed constraints do not mutate stored limits, source samples or provider records',()=>{
 const before=clone(d),targets=graphTargets(d.plan,defs);
 for(const unit of ['km/h','m/s','knots'])for(const target of targets)for(const metric of ['speed_kmh','pace_sec_km','power_w','left_power_w'])targetOnChart(target,metric,unit);
 assert.deepEqual(d,before);
});
test('aligned two-sided power yields an explicit total and retains every missing observation',()=>{
 const channels=d.samples.series.filter(s=>['left_power_w','right_power_w'].includes(s.metric_key));
 const a=clone(channels);a[0].values=[90,null,0];a[1].values=[95,100,0];a.forEach(s=>{s.slot_count=3;});
 const total=withPace(a).find(s=>s.metric_key==='power_w');assert.deepEqual(total.values,[185,null,0]);assert.equal(total.derived,true);
 assert.deepEqual(a[0].values,[90,null,0]);
});
for(const [name,change] of [
 ['only one side',a=>a.pop()],['different cadence',a=>{a[1].interval_ms=2000;}],['different length',a=>a[1].values.push(100)],['other exercise',a=>{a[1].exercise_index=1;}],['duplicate channel',a=>a.push(clone(a[0]))]
])test('overall power is not invented for '+name,()=>{
 const a=clone(d.samples.series.filter(s=>['left_power_w','right_power_w'].includes(s.metric_key)));change(a);
 assert.ok(!withPace(a).some(s=>s.metric_key==='power_w'));
});
test('all chart target families render with a visible local unit selector',()=>{
 const markup=html(Charts,{source:d.samples.series,plan:d.plan,zones:e.heart_rate_zones,speedZones:e.speed_zones,powerZones:e.power_zones,speedUnit:'m/s',onSpeedUnitChange:()=>{}});
 assert.match(markup,/Sebesség egysége/);assert.match(markup,/Sebesség\/iram célja/);assert.match(markup,/Teljesítménycél a grafikonon/);
 assert.match(markup,/180 W/);assert.match(markup,/220 W/);assert.match(markup,/0,56 m\/s/);
 assert.doesNotMatch(markup,/NaN|Infinity/);
});
test('a power prescription remains visible as a clearly labeled reference when no total power samples exist',()=>{
 const markup=html(Charts,{source:d.samples.series.filter(s=>s.metric_key==='left_power_w'),plan:d.plan,powerZones:e.power_zones,speedZones:e.speed_zones});
 assert.match(markup,/Csak tervcél · W/);assert.match(markup,/Ehhez nincs teljes, megjeleníthető mért mintasor/);
 assert.match(markup,/180 W/);assert.match(markup,/220 W/);
});
test('multisport defaults to all exercise parts in sequence rather than one sport\'s lap list',()=>{
 const source=clone(d.sections),row=clone(source.groups[0].rows[0]);row.id='exerciseSamples[1]';row.exercise_index=1;row.position=1;row.avg_hr=170;row.distance_m=5000;
 source.groups[0].rows.push(row);
 const markup=html(SessionSections,{source,plan:null,speedUnit:'km/h'});
 assert.match(markup,/170 bpm/);assert.match(markup,/5 km/);assert.doesNotMatch(markup,/110 bpm/);
});
test('planned child positions remain inside their repeat container rather than moving ahead of earlier root blocks',()=>{
 const plan=clone(d.plan),one=plan.blocks[0],two=plan.blocks[1];one.name='First root';one.position=0;two.name='Repeat group';two.position=1;two.repeat_count=4;
 plan.blocks.push({...one,id:'00000000-0000-0000-0000-000000000088',name:'Child work',position:0,parent_block_id:two.id});
 const markup=html(SessionSections,{source:undefined,plan,speedUnit:'km/h'});
 assert.ok(markup.indexOf('First root')<markup.indexOf('Repeat group'));assert.ok(markup.indexOf('Repeat group')<markup.indexOf('Child work'));
});
