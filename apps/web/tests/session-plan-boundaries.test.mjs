import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const {readAnalysis}=load('src/lib/session-analysis/contracts.ts');
const b=load('src/lib/session-analysis/plan-boundaries.ts');
const {SampleChart}=load('src/components/session-analysis/charts.tsx');
const d=JSON.parse(readFileSync(new URL('./fixtures/session-plan-timeline.json',import.meta.url)));
const prior=JSON.parse(readFileSync(new URL('./fixtures/session-sections-targets.json',import.meta.url)));
const clone=x=>structuredClone(x),part=d.plan_timeline.parts[0];
const render=(s,props={})=>renderToStaticMarkup(React.createElement(SampleChart,{series:s,from:0,to:4560000,cursor:0,setCursor:()=>{},boundaries:b.planBoundaries(part),...props}));

test('real owned source projection restores an exact clock while the stored block list stays empty',()=>{
 assert.deepEqual(readAnalysis(d,d.session.id),d);assert.equal(d.plan.blocks.length,0);
 assert.equal(d.plan_timeline.source,'stored_polar_target');assert.equal(part.phases[1].from_ms,1200000);
});
for(const [name,change] of [
 ['wrong plan',a=>{a.plan_timeline.plan_id='00000000-0000-0000-0000-000000000001';}],
 ['fabricated boundary',a=>{a.plan_timeline.parts[0].phases[1].to_ms++;}],
 ['missing predecessor duration',a=>{a.plan_timeline.parts[0].phases[0].duration_ms=null;}],
 ['different total',a=>{a.plan_timeline.parts[0].total_ms++;}],
 ['duplicate phase',a=>{a.plan_timeline.parts[0].phases[1].id=a.plan_timeline.parts[0].phases[0].id;}],
 ['wrong source reference',a=>{a.plan_timeline.parts[0].phases[0].source_block_id='00000000-0000-0000-0000-000000000002';}],
 ['missing fingerprint',a=>{delete a.plan_timeline.content_hash;}],
 ['boolean duration',a=>{a.plan_timeline.parts[0].phases[0].duration_ms=true;}],
 ['unavailable with precise phases',a=>{a.plan_timeline.source='unavailable';}],
])test('planned time read rejects '+name,()=>{const a=clone(d);change(a);assert.throws(()=>readAnalysis(a,a.session.id));});
test('older workout reads remain accepted without a phase projection',()=>{
 const a=clone(d);delete a.plan_timeline;assert.deepEqual(readAnalysis(a,a.session.id),a);
});
test('vertical source boundaries match explicit warmup/work/recovery times and merge shared endpoints',()=>{
 const markers=b.planBoundaries(part);
 assert.deepEqual(markers.map(m=>m.ms),[0,1200000,1920000,2040000,2760000,2880000,3600000,3720000,4440000,4560000]);
 assert.equal(markers[1].labels.length,2);assert.match(markers[1].labels.join(' '),/Bemelegítés vége/);
});
test('all metrics receive the same exact vertical positions independently of unit and observed curve',()=>{
 const before=clone(prior.samples.series);
 for(const s of prior.samples.series.filter(s=>['heart_rate_bpm','speed_kmh','left_power_w'].includes(s.metric_key))){
  for(const speedUnit of ['km/h','m/s','knots']){
   const html=render({...s,values:[0,0,0,0]},{speedUnit});
   assert.equal((html.match(/data-boundary-ms=/g)||[]).length,10);assert.match(html,/data-boundary-ms="1200000"/);
   assert.match(html,/Terv szerinti határ/);assert.doesNotMatch(html,/NaN|Infinity/);
  }
 }
 assert.deepEqual(prior.samples.series,before);
});
test('zoom clips boundaries without moving or snapping their true planned instants',()=>{
 const markers=b.planBoundaries(part),visible=b.visibleBoundaries(markers,1200001,2040000);
 assert.deepEqual(visible.map(b=>b.ms),[1920000,2040000]);
 const positions=b.positionedBoundaries(markers,1200000,1920000);
 assert.equal(positions[0].x,76);assert.equal(positions.at(-1).x,870);
});
test('crowded labels are reduced while every vertical boundary is retained',()=>{
 const markers=Array.from({length:100},(_,i)=>({ms:i,labels:['x']})),positions=b.positionedBoundaries(markers,0,100);
 assert.equal(positions.length,100);assert.ok(positions.filter(p=>p.showLabel).length<20);
});
test('unknown durations stop later boundary placement instead of being treated as zero',()=>{
 const a=clone(part);a.phases[1].to_ms=null;a.phases[1].duration_ms=null;
 for(const p of a.phases.slice(2)){p.from_ms=null;p.to_ms=null;}
 a.total_ms=null;
 const markers=b.planBoundaries(a);assert.deepEqual(markers.map(m=>m.ms),[0,1200000]);
});
for(const [text,expected] of [['20:00',1200000],['0:00',0],['12:00',720000],['1:20:00',4800000],['0:01,125',1125],['0:00.001',1]])test('declared clock parses exactly '+text,()=>assert.equal(b.readClock(text),expected));
for(const text of ['', '20','12:60','-1:00','1e2:00','0:00.0001','1:99:00'])test('ambiguous or invalid clock is rejected '+text,()=>assert.throws(()=>b.readClock(text)));
function reference(changes={}){return {version:'manual-plan-reference-v0.1',first_ms:1200000,work_ms:720000,recovery_ms:120000,count:4,...changes};}
test('declared four-by-twelve uses exactly three between-work recoveries and retains explicit offset',()=>{
 const p=b.manualPart(reference());assert.equal(p.total_ms,4440000);
 assert.deepEqual(p.phases.filter(p=>p.label.endsWith('munka')).map(p=>p.from_ms),[1200000,2040000,2880000,3720000]);
 assert.equal(p.phases.filter(p=>p.label.endsWith('pihenő')).length,3);
});
test('explicit zero recovery keeps adjacent work starts with no fabricated pause',()=>{
 const p=b.manualPart(reference({first_ms:0,recovery_ms:0}));assert.equal(p.phases.length,4);assert.equal(p.total_ms,2880000);
 assert.deepEqual(b.planBoundaries(p).map(p=>p.ms),[0,720000,1440000,2160000,2880000]);
});
for(const [name,change] of [
 ['unknown first time',{first_ms:null}],['unknown recovery',{recovery_ms:null}],['boolean work',{work_ms:true}],['zero work',{work_ms:0}],['negative gap',{recovery_ms:-1}],['fractional repeat',{count:4.5}],['too many repeats',{count:100}],['future format',{version:'unknown'}]
])test('manual reference refuses '+name,()=>assert.throws(()=>b.manualPart(reference(change))));
test('manual labels remain explicit and do not claim a recorded phase switch',()=>{
 const html=render(prior.samples.series[0],{boundaries:b.planBoundaries(b.manualPart(reference())),manualBoundaries:true});
 assert.match(html,/Kézi tervjelölés/);assert.match(html,/is-manual/);assert.doesNotMatch(html,/Rögzített szakaszhatár/);
});
