import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const {readAnalysis}=load('src/lib/session-analysis/contracts.ts');
const {alignDistancePhases,planBoundaries}=load('src/lib/session-analysis/plan-boundaries.ts');
const {Charts}=load('src/components/session-analysis/charts.tsx');
const data=JSON.parse(readFileSync(new URL('./fixtures/session-mixed-phase-goals.json',import.meta.url)));
const part=data.plan_timeline.parts[0],source=data.samples.series;
const clone=x=>structuredClone(x);
const clock=[0,1000000,1720000,1840000,2560000,2680000,3400000,3520000,4240000,4360000];

test('owned API distance goal and nested repeats pass the frontend contract without inventing stored durations',()=>{
 assert.deepEqual(readAnalysis(data,data.session.id),data);
 assert.equal(part.phases.length,9);assert.equal(part.phases[0].distance_m,2600);assert.equal(part.phases[0].duration_ms,null);
 assert.equal(part.phases[1].from_ms,null);
});
for(const value of [true,null,-1,Infinity,'2600'])test('contract rejects invalid distance goal '+String(value),()=>{
 const d=clone(data);d.plan_timeline.parts[0].phases[0].distance_m=value;
 assert.throws(()=>readAnalysis(d,d.session.id));
});
test('distance cannot silently coexist with a different duration prescription',()=>{
 const d=clone(data);d.plan_timeline.parts[0].phases[1].distance_m=100;
 assert.throws(()=>readAnalysis(d,d.session.id));
});
test('two repeat groups produce nine consecutive phases from measured 2600m followed by their declared times',()=>{
 const before=clone({part,source}),r=alignDistancePhases(part,source);
 assert.equal(r.distanceUsed,true);assert.equal(r.source.id,source[0].id);assert.deepEqual(r.reasons,[]);
 assert.deepEqual(planBoundaries(r.part).map(b=>b.ms),clock);
 assert.equal(r.part.phases[0].duration_ms,null);assert.deepEqual(r.part.issues,[]);
 assert.deepEqual({part,source},before);
});
test('crossing uses the first recorded sample reaching the goal and never a fractional guessed transition',()=>{
 const p=clone(part);p.phases[0].distance_m=2601;
 const r=alignDistancePhases(p,source);assert.equal(r.part.phases[0].to_ms,1001000);
 assert.equal(r.part.phases[1].from_ms,1001000);
});
test('the distance series declared interval determines the threshold clock rather than a one-second assumption',()=>{
 const s=clone(source);s[0].interval_ms=500;
 const r=alignDistancePhases(part,s);assert.equal(r.part.phases[0].to_ms,500000);
 assert.equal(r.part.phases[1].to_ms,1220000);
});
test('a stationary distance plateau uses its first threshold sample and preserves later time prescriptions',()=>{
 const s=clone(source);for(let i=1000;i<1100;i++)s[0].values[i]=2600;
 const r=alignDistancePhases(part,s);assert.equal(r.part.phases[0].to_ms,1000000);
 assert.equal(r.part.phases[1].to_ms,1720000);
});
test('a positive distance below floating-point resolution cannot move the next phase backwards',()=>{
 const p=clone(part);p.phases[0]={...p.phases[0],duration_ms:1000,distance_m:undefined};p.phases[1]={...p.phases[1],duration_ms:null,distance_m:1};
 const s=clone(source);s[0].values=s[0].values.map((_,i)=>i===0?0:1e30);
 const r=alignDistancePhases(p,s);assert.equal(r.part.phases[1].to_ms,null);
 assert.deepEqual(r.reasons,['DISTANCE_CLOCK_INVALID']);
});
test('a later distance phase starts with the measured distance at its own start, not at workout zero',()=>{
 const p={index:0,issues:['PLAN_DURATION_UNKNOWN'],total_ms:null,phases:[
  {id:'warm',label:'Timed warmup',source_block_id:null,from_ms:0,to_ms:100000,duration_ms:100000},
  {id:'distance',label:'Distance',source_block_id:null,from_ms:100000,to_ms:null,duration_ms:null,distance_m:2600},
  {id:'timed',label:'Timed work',source_block_id:null,from_ms:null,to_ms:null,duration_ms:720000},
 ]};
 const r=alignDistancePhases(p,source);
 assert.equal(r.part.phases[1].to_ms,1100000);assert.equal(r.part.phases[2].to_ms,1820000);
});
test('a missing distance sample at the crossing leaves that boundary and all later positions unknown',()=>{
 const s=clone(source);s[0].values[999]=null;
 const r=alignDistancePhases(part,s);
 assert.deepEqual(planBoundaries(r.part).map(b=>b.ms),[0]);
 assert.deepEqual(r.reasons,['DISTANCE_CROSSING_GAP']);
});
test('a hole well before the crossing is preserved and does not move a later fully bracketed crossing',()=>{
 const s=clone(source);s[0].values[10]=null;
 const r=alignDistancePhases(part,s);assert.deepEqual(planBoundaries(r.part).map(b=>b.ms),clock);
 assert.equal(s[0].values[10],null);
});
for(const [name,change,reason] of [
 ['missing distance',s=>s.splice(0,1),'DISTANCE_SOURCE_MISSING'],
 ['two competing distance series',s=>s.push({...clone(s[0]),id:'another'}),'DISTANCE_SOURCE_AMBIGUOUS'],
 ['mixed exercise clocks',s=>{s[1].exercise_index=1;},'DISTANCE_SOURCE_AMBIGUOUS'],
 ['unknown interval',s=>{s[0].interval_ms=null;},'DISTANCE_CLOCK_INVALID'],
 ['distance reset',s=>{s[0].values[50]=0;},'DISTANCE_CLOCK_INVALID'],
 ['unknown initial distance',s=>{s[0].values[0]=null;},'DISTANCE_START_UNKNOWN'],
 ['nonzero initial distance',s=>{s[0].values=s[0].values.map(v=>v+10);},'DISTANCE_START_UNKNOWN'],
 ['goal beyond stored distance',s=>{s[0].values=s[0].values.slice(0,200);},'DISTANCE_GOAL_NOT_REACHED'],
])test('uncertain source refuses automatic placement: '+name,()=>{
 const s=clone(source);change(s);const r=alignDistancePhases(part,s);
 assert.equal(r.distanceUsed,false);assert.equal(r.part.total_ms,null);
 assert.deepEqual(planBoundaries(r.part).map(b=>b.ms),[0]);assert.deepEqual(r.reasons,[reason]);
});
test('zero distance is explicit zero even without a distance source',()=>{
 const p=clone(part);p.phases[0].distance_m=0;
 const r=alignDistancePhases(p,[]);assert.equal(r.part.phases[0].to_ms,0);assert.equal(r.part.phases[1].to_ms,720000);
});
test('unknown manual transitions are not resolved using distance or intensity curves',()=>{
 const p=clone(part);delete p.phases[0].distance_m;
 const r=alignDistancePhases(p,source);assert.equal(r.part.phases[1].from_ms,null);
 assert.deepEqual(r.reasons,['PLAN_DURATION_UNKNOWN']);
});
test('planned final recovery remains the prescribed length when recording ends earlier',()=>{
 const s=clone(source).map(s=>({...s,values:s.values.slice(0,4301)}));
 const r=alignDistancePhases(part,s);assert.equal(r.part.total_ms,4360000);
 assert.equal(r.part.phases.at(-1).duration_ms,120000);assert.equal(r.part.phases.at(-1).to_ms,4360000);
});
test('fractional start with no exact matching distance sample stays unknown instead of interpolating measured values',()=>{
 const p=clone(part);p.phases.unshift({id:'fraction',label:'Fraction',source_block_id:null,from_ms:0,to_ms:500,duration_ms:500});
 const r=alignDistancePhases(p,source);assert.equal(r.part.phases[1].from_ms,500);assert.equal(r.part.phases[1].to_ms,null);
 assert.deepEqual(r.reasons,['DISTANCE_START_UNKNOWN']);
});
for(const unit of ['km/h','m/s','knots'])test('all charts render the same visible calculated phase lines with speed in '+unit,()=>{
 const html=renderToStaticMarkup(React.createElement(Charts,{source,timeline:data.plan_timeline,singleExercise:true,speedUnit:unit}));
 assert.match(html,/Számított tervhatárok · mért távsor alapján/);
 assert.match(html,/Tervezett határidőpontok · 9 szakasz/);assert.match(html,/távmintákból/);
 assert.equal((html.match(/data-boundary-ms=/g)||[]).length,20);
 assert.equal((html.match(/data-boundary-ms="1000000"/g)||[]).length,2);
 assert.match(html,/Számított tervhatár · mért távsor/);assert.doesNotMatch(html,/NaN|Infinity/);
});
