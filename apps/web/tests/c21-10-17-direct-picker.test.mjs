import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-17-direct-picker.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {loadWorkoutAlternatives,prepareDaySelection,selectionRequest,assertDaySelection,AlternativesChanged}=load('src/lib/calendar/alternative-selection.ts');
const {readFeed,eventsFrom}=load('src/lib/calendar/contracts.ts');
const {default:EventDetail}=load('src/components/calendar/event-detail.tsx');
const {canonical,sha}=load('src/lib/planning-cycles/contracts.ts');
const expected={owner:data.initial.athlete_id,reference:data.initial.program_reference,zone:data.initial.timezone_name};
const target={...data.target.planning_context,id:data.target.id};
const check=r=>readTrainingReview(r,{owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name});
const chosenKey=data.choice.result.alternatives[0].selected_candidate_key;
const clicked=data.initial.result.alternatives[0].candidates.find(c=>c.candidate_key===chosenKey)??data.initial.result.alternatives[0].candidates.find(c=>c.sport==='STRENGTH');
for(const name of ['initial','choice','after_expiry','future'])test(`real API ${name}: automatic offering has exact day/owner/source bounds without a personal assertion`,async()=>{
 const r=data[name],before=canonical(r);await check(r);assert.equal(canonical(r),before);
 assert(r.alternatives_for);assert(!('same_day_replacement' in r));assert.equal(r.calibration_review,null);
 assert.equal(r.start_date,r.end_date);assert(r.plan_snapshots.filter(p=>p.replaceable).every(p=>p.workout.id===r.alternatives_for.workout_id));
});
test('legacy daily-review helper requests one scoped review without loading global history or accepting anything',async()=>{
 const old=globalThis.fetch,sent=[];
 globalThis.fetch=async(url,init)=>{sent.push({url,method:init.method,body:JSON.parse(init.body)});return Response.json({review:data.initial});};
 try{await loadWorkoutAlternatives(expected,target);assert.equal(sent.length,1);assert(sent[0].url.endsWith('/review'));
  assert.deepEqual(sent[0].body,{start_date:target.date,end_date:target.date,alternatives_for:{schema_version:'workout-alternatives-request-v0.1',workout_id:target.id,expected_workout_hash:target.workout_hash}});
  assert(!JSON.stringify(sent).includes('confirmed_not_started'));
 }finally{globalThis.fetch=old;}
});
test('a card click rechecks the same physical workout and prepares only the clicked day for saving',async()=>{
 const oldFetch=globalThis.fetch,oldNow=Date.now,sent=[];Date.now=()=>Date.parse(data.initial.created_at);
 globalThis.fetch=async(url,init)=>{sent.push({url,body:JSON.parse(init.body)});return Response.json({review:url.endsWith('/review')?data.initial:data.choice});};
 try{const chosen=await prepareDaySelection(expected,target,data.initial,clicked);assertDaySelection(chosen,target);
  assert.deepEqual(sent.map(s=>s.url.split('/').at(-1)),['review','choose']);
  const request=selectionRequest(expected,target,chosen),body=JSON.parse(request.body);
  assert.equal(request.operation,'accept');assert.equal(body.acknowledge_reviewed_plan,true);assert.deepEqual(body.review_reference,{artifact_id:chosen.artifact_id,content_hash:chosen.content_hash});
  assert.deepEqual(chosen.result.cancel,[target.id]);assert(chosen.result.create.every(c=>c.date===target.date));
 }finally{globalThis.fetch=oldFetch;Date.now=oldNow;}
});
test('a changed or expired dose cannot be silently substituted while processing a click',async()=>{
 const oldFetch=globalThis.fetch,oldNow=Date.now,sent=[];Date.now=()=>Date.parse(data.after_expiry.created_at);
 const original=data.initial.result.alternatives[0].candidates.reduce((a,b)=>a.duration_sec>b.duration_sec?a:b);
 globalThis.fetch=async(url)=>{sent.push(url);assert(url.endsWith('/review'));return Response.json({review:data.after_expiry});};
 try{await assert.rejects(()=>prepareDaySelection(expected,target,data.initial,original),e=>e instanceof AlternativesChanged&&e.review.artifact_id===data.after_expiry.artifact_id);assert.equal(sent.length,1);}
 finally{globalThis.fetch=oldFetch;Date.now=oldNow;}
});
for(const field of ['another_workout','wrong_hash','missing_input_scope','another_day','another_editable_row','two_scopes'])test(`rehashed picker proof rejects ${field}`,async()=>{
 const r=structuredClone(data.initial);
 if(field==='another_workout')r.alternatives_for.workout_id='00000000-0000-0000-0000-000000000001';
 if(field==='wrong_hash')r.alternatives_for.expected_workout_hash='f'.repeat(64);
 if(field==='missing_input_scope')delete r.inputs.alternatives_for;
 if(field==='another_day')r.end_date='2026-10-27';
 if(field==='another_editable_row')r.plan_snapshots.find(p=>p.workout.id!==target.id).replaceable=true;
 if(field==='two_scopes')r.same_day_replacement={schema_version:'same-day-training-replacement-v0.1',workout_id:target.id,confirmed_not_started:true};
 const inputs=structuredClone(r.inputs);delete inputs.content_hash;r.inputs.content_hash=await sha(inputs);
 const body=structuredClone(r);delete body.content_hash;r.content_hash=await sha(body);
 await assert.rejects(()=>check(r));
});
for(const field of ['another_cancelled_day','another_created_day','wrong_target'])test(`direct click cannot commit ${field}`,()=>{
 const r=structuredClone(data.choice);
 if(field==='another_cancelled_day')r.result.cancel.push('00000000-0000-0000-0000-000000000001');
 if(field==='another_created_day')r.result.create[0].date='2026-10-27';
 if(field==='wrong_target')r.alternatives_for.workout_id='00000000-0000-0000-0000-000000000001';
 assert.throws(()=>selectionRequest(expected,target,r),/adott nap/);
});
test('one calendar click renders the picker before the collapsed workout details, without checkboxes or an alternatives toggle',()=>{
 const feed=readFeed(data.initial_feed),event=eventsFrom(feed).find(e=>e.entityId===target.id);assert(event);
 const html=renderToStaticMarkup(React.createElement(EventDetail,{event,feed,onClose(){}}));
 assert(html.includes('Az adott nap alternatívái'));assert(html.indexOf('data-alternatives-date')<html.indexOf('A naptárban lévő edzés részletei'));
 assert(!html.includes('type="checkbox"'));assert(!html.includes('Változatok összecsukása'));assert(!html.includes('nem kezdtem el'));
});
