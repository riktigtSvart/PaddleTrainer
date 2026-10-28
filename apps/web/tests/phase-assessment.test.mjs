import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const {readAnalysis}=load('src/lib/session-analysis/contracts.ts');
const {alignDistancePhases,readTransitions,planBoundaries}=load('src/lib/session-analysis/plan-boundaries.ts');
const {phaseResults,windowMean,windowDistance,phaseTarget}=load('src/lib/session-analysis/phase-statistics.ts');
const {withPace}=load('src/lib/session-analysis/chart-data.ts');
const {Charts}=load('src/components/session-analysis/charts.tsx');
const {PhaseWindows}=load('src/components/session-analysis/phase-windows.tsx');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/phase-assessment.json',import.meta.url)));
const part=fixture.plan_timeline.parts[0],source=fixture.samples.series,series=withPace(source),exercise=fixture.samples.exercises[0];
const zones={heart_rate:exercise.heart_rate_zones,speed:exercise.speed_zones,power:exercise.power_zones};
const clone=x=>structuredClone(x),work1=part.phases[1].id,work2=part.phases[3].id;
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} differs from ${b}`);
const starts={[work1]:19000,[work2]:32000};
function resolved(refs=starts){return alignDistancePhases(part,source,refs);}
function rows(refs=starts){const a=resolved(refs);return phaseResults(a.part,a.gaps,series,fixture.plan,zones);}
test('real owned C10 API payload passes all frontend checks with its source-bound manual metadata',()=>{
 assert.deepEqual(readAnalysis(fixture,fixture.session.id),fixture);
 assert.deepEqual(part.phases.map(p=>p.advance),['AUTOMATIC','MANUAL','AUTOMATIC','MANUAL','AUTOMATIC']);
});
for(const [label,change] of [
 ['bad advance',a=>{a.plan_timeline.parts[0].phases[1].advance='AUTO';}],
 ['bad source pointer',a=>{a.plan_timeline.parts[0].phases[1].source_pointer='https://untrusted.invalid';}],
 ['reversed target',a=>{a.plan_timeline.parts[0].phases[1].target.low=6;}],
 ['boolean target',a=>{a.plan_timeline.parts[0].phases[1].target.low=true;}],
 ['invalid sample hash',a=>{a.samples.content_hash='wrong';}],
 ['invalid clock reasons',a=>{a.samples.exercises[0].clock_issues=[1];}],
])test('the read contract rejects '+label,()=>{const a=clone(fixture);change(a);assert.throws(()=>readAnalysis(a,a.session.id));});
test('a manual advance keeps the goal end and withholds subsequent boundaries until its next start is known',()=>{
 const a=resolved({});assert.deepEqual(planBoundaries(a.part).map(b=>b.ms),[0,10000,16000]);
 assert.equal(a.part.phases[2].from_ms,null);assert.equal(a.transitions[0].next_ms,null);
 assert.ok(a.reasons.includes('MANUAL_ADVANCE_TIME_UNKNOWN'));
 assert.deepEqual(a.gaps,[{id:'unassigned',from_ms:16000,to_ms:36000,kind:'unassigned'}]);
});
test('two manual references create separate waits and retain the recording after the plan',()=>{
 const a=resolved();assert.deepEqual(a.part.phases.map(p=>[p.from_ms,p.to_ms]),[[0,10000],[10000,16000],[19000,21000],[21000,27000],[32000,34000]]);
 assert.deepEqual(a.gaps.map(g=>[g.kind,g.from_ms,g.to_ms]),[['wait',16000,19000],['wait',27000,32000],['unassigned',34000,36000]]);
 assert.equal(a.part.total_ms,34000);assert.equal(a.transitions.length,2);
});
test('zero waiting time is explicitly supported without introducing a gap',()=>{
 const a=resolved({[work1]:16000,[work2]:24000});assert.equal(a.gaps.filter(g=>g.kind==='wait').length,0);
 assert.equal(a.part.phases[2].from_ms,16000);
});
for(const value of [-1,15000,36001,Infinity,true,'19000'])test('invalid next start does not create a precise boundary: '+String(value),()=>{
 const a=resolved({[work1]:value});assert.equal(a.part.phases[2].from_ms,null);
});
test('a later absolute reference that conflicts with an edited earlier reference remains unresolved',()=>{
 const a=resolved({[work1]:26000,[work2]:32000});assert.equal(a.part.phases[3].to_ms,34000);
 assert.equal(a.part.phases[4].from_ms,null);
});
test('unknown advance mode is withheld and can be localized only with an explicit user start',()=>{
 const p=clone(part);p.phases[0].advance='UNKNOWN';const a=alignDistancePhases(p,source,{});
 assert.equal(a.part.phases[1].from_ms,null);assert.ok(a.reasons.includes('ADVANCE_MODE_UNKNOWN'));
 assert.equal(alignDistancePhases(p,source,{[p.phases[0].id]:10000}).part.phases[1].from_ms,10000);
});
test('an interior recording pause blocks automatic goal clocks rather than becoming a fabricated waiting interval',()=>{
 const a=alignDistancePhases(part,source,starts,['INTERIOR_RECORDING_PAUSE_REQUIRES_CLOCK_ALIGNMENT']);
 assert.ok(a.part.phases.every(p=>p.from_ms===null&&p.to_ms===null));assert.equal(a.gaps[0].kind,'unassigned');
});
test('reference validation is bound to exact occurrence IDs and part rather than repeated block IDs',()=>{
 const v={version:'phase-transitions-v0.1',part_index:0,starts};assert.deepEqual(readTransitions(v,part),starts);
 assert.throws(()=>readTransitions({...v,part_index:1},part));
 assert.throws(()=>readTransitions({...v,starts:{[part.phases[1].source_block_id]:19000}},part));
 assert.throws(()=>readTransitions({...v,starts:{[part.phases[0].id]:19000}},part));
});
test('statistics retain all observed intervals exactly once across work, rests, waits and unassigned suffix',()=>{
 const before=clone(fixture),r=rows();assert.equal(r.length,8);
 assert.equal(r.reduce((n,r)=>n+r.observed_ms,0),36000);
 assert.equal(r.reduce((n,r)=>n+(r.distance_m??0),0),108);
 assert.deepEqual(fixture,before);
});
test('each manual wait retains measured physiology and distance without an active prescribed target',()=>{
 const r=rows().find(r=>r.kind==='wait');assert.equal(r.observed_ms,3000);assert.equal(r.distance_m,9);
 near(r.heart_rate.value,117);near(r.speed.value,10);near(r.power.value,110);
 assert.equal(r.target,null);assert.equal(r.goal_time,null);
});
test('work means and target times use only the work window rather than its following manual wait',()=>{
 const r=rows().find(r=>r.id===work1);assert.equal(r.observed_ms,6000);assert.equal(r.distance_m,18);
 near(r.heart_rate.value,112.5);near(r.speed.value,10);near(r.power.value,110);
 assert.deepEqual(r.goal_time,{below_ms:2000,inside_ms:2000,above_ms:2000,known_ms:6000,missing_ms:0});
});
test('missing samples reduce known target time and never become failures, successes or zero workload',()=>{
 const s=clone(series);const speed=s.find(s=>s.metric_key==='speed_kmh');speed.values[12]=null;
 const a=resolved();const r=phaseResults(a.part,a.gaps,s,fixture.plan,zones).find(r=>r.id===work1);
 assert.equal(r.goal_time.known_ms,4000);assert.equal(r.goal_time.missing_ms,2000);
 assert.equal(r.speed.known_ms,4000);assert.equal(r.distance_m,18);
});
test('recording end truncates only observed coverage while preserving the original planned last recovery',()=>{
 const s=clone(series).map(s=>({...s,values:s.values.slice(0,34)}));const a=alignDistancePhases(part,s,starts);
 const r=phaseResults(a.part,a.gaps,s,fixture.plan,zones).find(r=>r.id===part.phases[4].id);
 assert.equal(r.to_ms,34000);assert.equal(r.observed_ms,1000);assert.equal(r.partial,true);
 assert.equal(part.phases[4].duration_ms,2000);
});
test('unlocated phases contain no invented averages or zero target percentages',()=>{
 const r=rows({}).find(r=>r.id===part.phases[2].id);assert.equal(r.observed_ms,null);
 assert.equal(r.heart_rate.value,null);assert.equal(r.goal_time,null);
});
function channel(values,interval_ms=1000){return {...source[1],values,interval_ms};}
test('means are time-weighted with half-open boundaries and fractional windows',()=>{
 const s=channel([0,10,20,30]);assert.equal(windowMean(s,500,2500).mean.value,10);
 assert.equal(windowMean(s,0,1000).mean.value,0);assert.equal(windowMean(s,1000,2000).mean.value,10);
 assert.equal(windowMean(channel([5,10,15],2000),0,4000).mean.value,7.5);
});
test('no values or declared intervals are extrapolated beyond the last recorded point',()=>{
 assert.equal(windowMean(channel([5,10,15]),0,5000).mean.known_ms,2000);
 assert.equal(windowMean(channel([5]),0,1000).mean.value,null);
 assert.equal(windowMean(channel([5,10],null),0,1000).mean.value,null);
});
test('distance requires continuous valid counter observations at exact endpoints and preserves zero',()=>{
 assert.equal(windowDistance(channel([0,3,6,9]),0,3000),9);
 assert.equal(windowDistance(channel([0,0,0]),0,2000),0);
 assert.equal(windowDistance(channel([0,null,6,9]),0,3000),null);
 assert.equal(windowDistance(channel([0,6,3,9]),0,3000),null);
 assert.equal(windowDistance(channel([0,3,6,9]),500,3000),null);
});
test('duplicate competing channels and one-sided power do not produce arbitrary totals',()=>{
 const a=resolved();const only=series.filter(s=>!['right_power_w','power_w'].includes(s.metric_key));
 let r=phaseResults(a.part,a.gaps,only,fixture.plan,zones).find(r=>r.id===work1);assert.equal(r.power.value,null);
 r=phaseResults(a.part,a.gaps,[...series,{...series.find(s=>s.metric_key==='speed_kmh'),id:'duplicate'}],fixture.plan,zones).find(r=>r.id===work1);
 assert.equal(r.speed.value,null);assert.equal(r.goal_time.known_ms,0);
});
test('separate exercise clocks cannot be mixed into one phase result',()=>{
 assert.deepEqual(phaseResults(resolved().part,[],[...series,{...series[0],exercise_index:1}],fixture.plan,zones),[]);
});
test('large finite sample values keep a finite average rather than overflowing a raw sum',()=>{
 const r=windowMean(channel([1e308,1e308,1e308]),0,2000);assert.equal(r.mean.value,1e308);
});
test('pace and m/s prescriptions share the canonical speed criterion; unavailable zones withhold the criterion',()=>{
 const p={...part.phases[1],target:{type:'PACE_SEC_KM',low:300,high:360}};
 assert.deepEqual([phaseTarget(p,null,zones).low,phaseTarget(p,null,zones).high],[10,12]);
 p.target={type:'SPEED_MPS',low:1,high:2};assert.equal(phaseTarget(p,null,zones).low,3.6);
 assert.equal(phaseTarget(part.phases[1],null,{...zones,speed:null}).low,null);
});
for(const unit of ['km/h','m/s','knots'])test('C10 renders escaped labels, coverage and manual controls with speed in '+unit,()=>{
 const html=renderToStaticMarkup(React.createElement(Charts,{source,timeline:fixture.plan_timeline,plan:fixture.plan,zones:exercise.heart_rate_zones,speedZones:exercise.speed_zones,speedUnit:unit}));
 assert.match(html,/Szakaszonkénti értékelés/);assert.match(html,/Kézi szakaszkezdések/);assert.match(html,/Bizonytalan időablak/);
 assert.match(html,/data-gap-kind="unassigned"/);assert.match(html,/&lt;script&gt;literal&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>|NaN|Infinity/);
});
test('neutral waiting bands clip to the visible chart range while preserving their original bounds',()=>{
 const html=renderToStaticMarkup(React.createElement('svg',null,React.createElement(PhaseWindows,{gaps:resolved().gaps,from:17000,to:18000,selected:null})));
 assert.match(html,/data-gap-kind="wait"/);assert.match(html,/x="76"/);assert.match(html,/width="794"/);
 assert.match(html,/0:16–0:19/);
});
