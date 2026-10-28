import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const {alignDistancePhases}=load('src/lib/session-analysis/plan-boundaries.ts');
const {transitionCandidates,candidateReceipt,readSavedTransitions,reviseTransition,pickedCandidateTime,motionPolicy}=load('src/lib/session-analysis/phase-candidates.ts');
const {phaseResults}=load('src/lib/session-analysis/phase-statistics.ts');
const {PhaseCandidateControls}=load('src/components/session-analysis/phase-candidates.tsx');
const {PhaseWindows}=load('src/components/session-analysis/phase-windows.tsx');
const clone=x=>structuredClone(x);

function scenario(dt=1000){
 const phase=(id,duration,advance='AUTOMATIC',distance)=>({id,label:id,source_block_id:null,from_ms:null,to_ms:null,duration_ms:duration,advance,...(distance===undefined?{}:{distance_m:distance})});
 const part={index:0,total_ms:null,issues:[],phases:[phase('warm',20000,'MANUAL'),phase('start-1',10000),phase('work-1',null,'AUTOMATIC',20),phase('rest-1',5000,'MANUAL'),phase('start-2',10000),phase('work-2',null,'AUTOMATIC',20),phase('rest-2',5000,'MANUAL')]};
 const speed=Array.from({length:Math.floor(100000/dt)+1},(_,i)=>i*dt<20000?6:i*dt<35000?0:i*dt<47000?8:i*dt<70000?0:8);
 const distance=[0];for(let i=1;i<speed.length;i++)distance.push(distance[i-1]+speed[i-1]*dt/3600);
 const mk=(type,key,unit,values)=>({id:type,exercise_index:0,source_path:'synthetic.'+type,source_type:type,metric_key:key,unit,interval_ms:dt,values,slot_count:values.length,valid_sample_count:values.length,missing_sample_count:0,issues:[]});
 return {part,series:[mk('SPEED','speed_kmh','km/h',speed),mk('DISTANCE','distance_m','m',distance),mk('HEART_RATE','heart_rate_bpm','bpm',speed.map((_,i)=>100+i))]};
}
function candidates(s,starts={},issues=[]){const alignment=alignDistancePhases(s.part,s.series,starts,issues);return transitionCandidates(s.part,s.series,alignment,issues);}

test('manual waits are proposed without changing source samples, references or unresolved statistics',()=>{
 const s=scenario(),before=clone(s),a=alignDistancePhases(s.part,s.series),c=candidates(s);
 assert.equal(c.options[0].start_ms,25000);assert.equal(c.options[0].lead_ms,10000);assert.equal(c.options[0].moving_ms,35000);
 assert.deepEqual([c.options[0].from_ms,c.options[0].to_ms],[20000,30000]);
 assert.ok(c.options.some(c=>c.start_ms===35000&&c.lead_ms===0));
 assert.equal(a.part.phases[1].from_ms,null);
 assert.equal(phaseResults(a.part,a.gaps,s.series,null,{heart_rate:null,speed:null,power:null}).find(r=>r.id==='work-1').observed_ms,null);
 assert.deepEqual(s,before);
});
test('the next manual transition becomes eligible only after the first is explicitly resolved',()=>{
 const s=scenario(),first=candidates(s).options[0],refs={[first.transition_id]:first.start_ms};
 const next=candidates(s,refs);assert.equal(next.options[0].transition_id,'rest-1');assert.equal(next.options[0].start_ms,60000);
 const a=alignDistancePhases(s.part,s.series,{...refs,'rest-1':60000});
 assert.equal(candidates(s,{...refs,'rest-1':60000}).options.length,0);
 assert.deepEqual(a.gaps.filter(g=>g.kind==='wait').map(g=>[g.from_ms,g.to_ms]),[[20000,25000],[50000,60000]]);
 const rows=phaseResults(a.part,a.gaps,s.series,null,{heart_rate:null,speed:null,power:null});
 assert.equal(rows.reduce((sum,r)=>sum+(r.observed_ms??0),0),100000);
 assert.ok(rows.filter(r=>r.kind==='wait').every(r=>r.target===null&&r.goal_time===null&&r.speed.value===0));
});
for(const dt of [500,2000,5000])test('source interval drives detection and the following distance grid: '+dt,()=>{
 const s=scenario(dt),c=candidates(s);assert.ok(c.options.length>0);
 const option=c.options.find(c=>c.lead_ms===10000);assert.equal((option.start_ms+option.lead_ms)%dt,0);
 assert.equal(option.interval_ms,dt);assert.equal(option.moving_ms-option.start_ms,10000);
});
test('the original prescribed short duration is retained, including fractional seconds',()=>{
 const s=scenario();s.part.phases[1].duration_ms=1500;
 const c=candidates(s).options[0];assert.equal(c.start_ms,33500);assert.equal(c.lead_ms,1500);
 const a=alignDistancePhases(s.part,s.series,{warm:c.start_ms});assert.equal(a.part.phases[2].from_ms,35000);
});
test('movement hypotheses never inspect heart-rate outcomes or displayed units',()=>{
 const s=scenario(),before=candidates(s);s.series[2].values.fill(999);
 assert.deepEqual(candidates(s),before);s.series.pop();assert.deepEqual(candidates(s),before);
});
for(const [name,change,reason] of [
 ['duplicate speed',s=>s.series.push(clone(s.series[0])),'MOTION_SOURCE_AMBIGUOUS_OR_MISSING'],
 ['missing distance',s=>s.series.splice(1,1),'MOTION_SOURCE_AMBIGUOUS_OR_MISSING'],
 ['mixed exercise',s=>s.series[2].exercise_index=1,'MOTION_SOURCE_AMBIGUOUS_OR_MISSING'],
 ['wrong plan clock',s=>s.part.index=1,'PLAN_EXERCISE_CLOCK_MISMATCH'],
 ['unknown interval',s=>s.series[0].interval_ms=null,'MOTION_GRID_UNSUITABLE'],
 ['different interval',s=>s.series[1].interval_ms=2000,'MOTION_GRID_UNSUITABLE'],
 ['unsupported unit',s=>s.series[0].unit='m/s','MOTION_GRID_UNSUITABLE'],
 ['reset counter',s=>s.series[1].values[80]=0,'DISTANCE_COUNTER_INVALID'],
 ['unknown advance',s=>s.part.phases[0].advance='UNKNOWN','ADVANCE_MODE_UNKNOWN'],
])test('unsafe interpretation is withheld: '+name,()=>{
 const s=scenario();change(s);const c=candidates(s);assert.equal(c.options.length,0);assert.ok(c.reasons.includes(reason));
});
test('an interior recording pause withholds motion suggestions rather than becoming a wait',()=>{
 const s=scenario(),c=candidates(s,{},['INTERIOR_RECORDING_PAUSE_REQUIRES_CLOCK_ALIGNMENT']);
 assert.equal(c.options.length,0);assert.deepEqual(c.reasons,['RECORDING_CLOCK_UNRESOLVED']);
});
test('missing motion samples are not bridged into a candidate',()=>{
 const s=scenario();s.series[0].values[35]=null;s.series[1].values[36]=null;
 const c=candidates(s);assert.ok(c.options.every(c=>c.moving_ms!==35000));
});
test('a stationary counter does not validate stale high-speed readings',()=>{
 const s=scenario();s.series[1].values.fill(0);assert.equal(candidates(s).options.length,0);
});
test('continuous movement does not become a fabricated zero-wait confirmation',()=>{
 const s=scenario();s.series[0].values.fill(8);assert.equal(candidates(s).options.length,0);
});
test('a manual flag on the last phase does not label the recording suffix as another wait',()=>{
 const s=scenario(),a=alignDistancePhases(s.part,s.series,{warm:25000,'rest-1':60000});
 assert.equal(a.transitions.length,2);assert.equal(a.gaps.at(-1).kind,'unassigned');
});
test('short goals are not inferred from labels and a long phase is not subtracted from movement time',()=>{
 const s=scenario();s.part.phases[1].label='Countdown 10 seconds';s.part.phases[1].duration_ms=45000;
 assert.ok(candidates(s).options.every(c=>c.lead_ms===0));
});
test('submissions retain the selected proposal and allow an explicitly corrected point outside its inspection window',()=>{
 const s=scenario(),o=candidates(s).options[0],receipt=candidateReceipt(o,31000);
 const saved=reviseTransition(s.part,alignDistancePhases(s.part,s.series),{},{},'warm',31000,receipt);
 const read=readSavedTransitions(saved,s.part);assert.equal(read.starts.warm,31000);
 assert.equal(read.receipts.warm.suggested_ms,25000);assert.equal(read.receipts.warm.start_ms,31000);
 assert.deepEqual(readSavedTransitions({version:'phase-transitions-v0.1',part_index:0,starts:{warm:25000}},s.part),{starts:{warm:25000},receipts:{}});
});
test('editing or deleting an earlier start invalidates dependent later references and receipts',()=>{
 const s=scenario(),starts={warm:25000,'rest-1':60000},a=alignDistancePhases(s.part,s.series,starts);
 const edited=reviseTransition(s.part,a,starts,{},'warm',26000);assert.deepEqual(edited.starts,{warm:26000});
 const removed=reviseTransition(s.part,a,starts,{},'warm',null);assert.deepEqual(removed.starts,{});
 const same=reviseTransition(s.part,a,starts,{},'warm',25000);assert.deepEqual(same.starts,starts);
 assert.throws(()=>reviseTransition(s.part,a,starts,{},'work-1',35000));
 assert.throws(()=>reviseTransition(s.part,a,starts,{},'warm',19000));
});
for(const [name,change]of[
 ['other point',v=>v.starts.warm=26000],['other rules',v=>v.motion_receipts.warm.rules='future'],
 ['wrong candidate',v=>v.motion_receipts.warm.candidate_id='unrelated'],['nonfinite clock',v=>v.motion_receipts.warm.start_ms=Infinity],
])test('stored estimate metadata is rejected when inconsistent: '+name,()=>{
 const s=scenario(),o=candidates(s).options[0],saved=reviseTransition(s.part,alignDistancePhases(s.part,s.series),{},{},'warm',o.start_ms,candidateReceipt(o));
 change(saved);assert.throws(()=>readSavedTransitions(saved,s.part));
});
test('chart correction preserves an exact following distance sample rather than interpolating',()=>{
 const o=candidates(scenario()).options[0];assert.equal(pickedCandidateTime(o,26740),27000);
 assert.equal(pickedCandidateTime({...o,lead_ms:1500},26740),26500);
});
test('proposal IDs depend on the occurrence, goal and source motion rather than render time',()=>{
 const s=scenario(),a=candidates(s).options[0];assert.equal(candidates(s).options[0].id,a.id);
 s.part.phases[0].duration_ms=21000;assert.notEqual(candidates(s).options[0].id,a.id);
});
test('candidate count is bounded without implying an exhaustive or unique explanation',()=>{
 const s=scenario();s.part.phases[0].duration_ms=0;
 s.series[0].values=s.series[0].values.map((_,i)=>i%12<5?0:8);
 const c=candidates(s);assert.equal(c.options.length,motionPolicy.max_options);assert.equal(c.truncated,true);
});
test('rendered proposals remain escaped, tentative and separate from actual phase boundaries',()=>{
 const s=scenario();s.part.phases[0].label='<script>private-label</script>';
 const a=alignDistancePhases(s.part,s.series),c=transitionCandidates(s.part,s.series,a);
 const view={manual:null,alignment:a,candidates:c};
 const html=renderToStaticMarkup(React.createElement(PhaseCandidateControls,{view,onPreview:()=>{},pickedMs:null,onCancel:()=>{}}));
 assert.match(html,/Elfogadásig/);assert.match(html,/Becsült kezdés elfogadása/);assert.match(html,/Most nem tudom/);
 assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
 const overlay=renderToStaticMarkup(React.createElement(PhaseWindows,{gaps:[],selected:{from:20000,to:30000,proposal:true},from:15000,to:40000}));
 assert.match(overlay,/data-proposal-window="true"/);assert.match(overlay,/nem igazolt szakaszhatár/);
});
