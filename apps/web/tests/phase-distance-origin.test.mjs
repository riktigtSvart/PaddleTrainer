import assert from 'node:assert/strict';
import test from 'node:test';
import {load} from './load-goal-modules.mjs';
const {alignDistancePhases}=load('src/lib/session-analysis/plan-boundaries.ts');
const {transitionCandidates}=load('src/lib/session-analysis/phase-candidates.ts');
const {phaseResults}=load('src/lib/session-analysis/phase-statistics.ts');
const clone=x=>structuredClone(x);
function scenario(offset=0.5,dt=1000){
 const phases=[{id:'warm',label:'Warm',source_block_id:null,from_ms:0,to_ms:null,duration_ms:null,distance_m:10,advance:'MANUAL'},
  {id:'start',label:'Short declared start',source_block_id:null,from_ms:null,to_ms:null,duration_ms:2000,advance:'AUTOMATIC'},
  {id:'work',label:'Work',source_block_id:null,from_ms:null,to_ms:null,duration_ms:null,distance_m:10,advance:'AUTOMATIC'}];
 const values=Array.from({length:31},(_,i)=>offset+(i<=10?i:i<=20?10:10+(i-20)*2));
 const series=[{id:'d',exercise_index:0,source_path:'synthetic.distance',source_type:'DISTANCE',metric_key:'distance_m',unit:'m',interval_ms:dt,values,slot_count:values.length,valid_sample_count:values.length,missing_sample_count:0,issues:[]},
  {id:'s',exercise_index:0,source_path:'synthetic.speed',source_type:'SPEED',metric_key:'speed_kmh',unit:'km/h',interval_ms:dt,values:values.map((_,i)=>i<=10?3.6:i<=20?0:7.2),slot_count:values.length,valid_sample_count:values.length,missing_sample_count:0,issues:[]}];
 return {part:{index:0,phases,total_ms:null,issues:[]},series};
}
test('a half-metre first observation no longer blocks the first manual transition',()=>{
 const s=scenario(),a=alignDistancePhases(s.part,s.series);
 assert.equal(a.part.phases[0].to_ms,10000);assert.equal(a.transitions.length,1);
 assert.equal(a.transitions[0].next_ms,null);assert.equal(a.part.phases[1].from_ms,null);
 assert.ok(a.reasons.includes('DISTANCE_INITIAL_OFFSET'));
 assert.ok(transitionCandidates(s.part,s.series,a).options.length>0);
});
test('the initial offset is not silently treated as distance already completed inside the observed window',()=>{
 const s=scenario();s.series[0].values=[0.5,5.5,10.25,10.5,15.5];s.series[1].values=[5,5,5,5,5];
 const a=alignDistancePhases(s.part,s.series);assert.equal(a.part.phases[0].to_ms,3000);
 assert.equal(s.series[0].values[0],0.5);
});
test('adding a fixed native counter offset leaves nominal windows and motion options invariant',()=>{
 const zero=scenario(0),shifted=scenario(12345),a=alignDistancePhases(zero.part,zero.series),b=alignDistancePhases(shifted.part,shifted.series);
 assert.deepEqual(a.part,b.part);
 assert.deepEqual(transitionCandidates(zero.part,zero.series,a),transitionCandidates(shifted.part,shifted.series,b));
 assert.ok(!a.reasons.includes('DISTANCE_INITIAL_OFFSET'));assert.ok(b.reasons.includes('DISTANCE_INITIAL_OFFSET'));
});
test('known start values preserve source sampling intervals other than one second',()=>{
 const s=scenario(0.5,2000),a=alignDistancePhases(s.part,s.series);
 assert.equal(a.part.phases[0].to_ms,20000);assert.equal(a.source.interval_ms,2000);
});
test('missing first distance stays unknown and is not replaced with zero or the next sample',()=>{
 const s=scenario();s.series[0].values[0]=null;const a=alignDistancePhases(s.part,s.series);
 assert.equal(a.part.phases[0].to_ms,null);assert.ok(a.reasons.includes('DISTANCE_START_UNKNOWN'));
 assert.equal(a.transitions.length,0);
});
test('a missing crossing sample or a reset still withholds an offset-source boundary',()=>{
 const gap=scenario();gap.series[0].values[9]=null;assert.ok(alignDistancePhases(gap.part,gap.series).reasons.includes('DISTANCE_CROSSING_GAP'));
 const reset=scenario();reset.series[0].values[25]=0;assert.ok(alignDistancePhases(reset.part,reset.series).reasons.includes('DISTANCE_CLOCK_INVALID'));
});
test('known starting offsets do not authorize interpolation at a fractional later distance start',()=>{
 const s=scenario();const a=alignDistancePhases(s.part,s.series,{warm:18500});
 assert.equal(a.part.phases[2].from_ms,20500);assert.equal(a.part.phases[2].to_ms,null);
 assert.ok(a.reasons.includes('DISTANCE_START_UNKNOWN'));
});
test('after explicit review, waits and phases partition measured time without discarding the native first value',()=>{
 const s=scenario(),before=clone(s),a=alignDistancePhases(s.part,s.series,{warm:19000});
 const rows=phaseResults(a.part,a.gaps,s.series,null,{heart_rate:null,speed:null,power:null});
 assert.equal(rows.reduce((n,r)=>n+(r.observed_ms??0),0),30000);
 assert.equal(rows.reduce((n,r)=>n+(r.distance_m??0),0),s.series[0].values.at(-1)-0.5);
 assert.equal(rows.find(r=>r.kind==='wait').target,null);assert.deepEqual(s,before);
});
test('overflow and below-resolution goals do not become zero-length observed phases',()=>{
 const s=scenario();s.series[0].values=s.series[0].values.map(()=>1e308);
 const a=alignDistancePhases(s.part,s.series);assert.equal(a.part.phases[0].to_ms,null);
 assert.ok(a.reasons.includes('DISTANCE_CLOCK_INVALID'));
});
