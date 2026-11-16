import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-15-today-variants.json.gz',import.meta.url))));
const {readTrainingReview,reviewTraining}=load('src/lib/planning-cycles/training-plan.ts');
const {readFeed,eventsFrom}=load('src/lib/calendar/contracts.ts');
const {workoutVariant,groupAlternatives}=load('src/lib/calendar/alternative-variants.ts');
const {canonical,sha}=load('src/lib/planning-cycles/contracts.ts');
const {alternativeLabel}=load('src/lib/calendar/training-alternatives.ts');
const {default:Badge}=load('src/components/calendar/alternative-badge.tsx');
const {default:EventDetail}=load('src/components/calendar/event-detail.tsx');
const check=r=>readTrainingReview(r,{owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name});
for(const [name,r] of [['today',data.today.review],['choice',data.today.choice],['no time',data.no_time],['ordinary',data.future]])test(`real owned ${name} preserves explicit current-day scope and all source checks`,async()=>{const before=canonical(r);await check(r);assert.equal(canonical(r),before);});
test('both kinds of real calendar count are informational and retain current prescription',()=>{
 const f=readFeed(data.today.after),events=eventsFrom(f);
 for(const p of f.planned){
  assert(p.planning_context.alternative_kinds);const k=p.planning_context.alternative_kinds;
  assert.equal(k.workout_variant.sport,p.sport);
  if(k.different_workouts_count!==null&&p.planning_context.replaceable){
   const label=alternativeLabel(p.planning_context);assert.match(label,/Más edzések/);assert.match(label,/időpontjai/);
   const event=events.find(e=>e.entityId===p.id&&e.kind==='planned');assert(event);
   assert.match(renderToStaticMarkup(React.createElement(Badge,{event})),/◷/);
   const detail=renderToStaticMarkup(React.createElement(EventDetail,{event,feed:f,onClose:()=>{}}));
   assert.match(detail,/Más edzések:/);assert.match(detail,/időpontjai\/helyszínei:/);
   assert(!detail.includes(`Alternatív edzések (${p.planning_context.alternatives_count})`));
  }
 }
});
test('time/place/source identities do not inflate the distinct-workout count',()=>{
 const x=data.grouping;assert.equal(canonical(workoutVariant(x.candidate,x.metadata)),canonical(workoutVariant(x.moved,x.metadata)));assert.notEqual(canonical(workoutVariant(x.changed,x.metadata)),canonical(workoutVariant(x.candidate,x.metadata)));
 const fake={result:{prescription_context:{by_candidate:{[x.candidate.candidate_key]:x.metadata,other:x.metadata}},alternatives:[]}},target={candidate_key:x.candidate.candidate_key,date:x.candidate.date,alternative_kinds:x.summary};
 const groups=groupAlternatives(fake,target,[x.candidate,x.moved,x.moved,x.changed]);assert.equal(groups.filter(g=>g.sameWorkout).length,1);assert.equal(groups.find(g=>g.sameWorkout).candidates.length,2);assert.equal(groups.filter(g=>!g.sameWorkout).length,1);
});
for(const change of ['unconfirmed','wrong_day','another_workout','scope_mismatch','missing_scope'])test(`current-day scope rejects ${change} after outer rehash`,async()=>{
 const r=structuredClone(data.today.review);
 if(change==='unconfirmed')r.same_day_replacement.confirmed_not_started=false;
 if(change==='wrong_day')r.plan_snapshots.find(p=>p.workout.id===r.same_day_replacement.workout_id).workout.date='2026-10-25';
 if(change==='another_workout')r.same_day_replacement.workout_id='00000000-0000-0000-0000-000000000001';
 if(change==='scope_mismatch')delete r.inputs.same_day_replacement;
 if(change==='missing_scope'){delete r.same_day_replacement;delete r.inputs.same_day_replacement;}
 const inputs=structuredClone(r.inputs);delete inputs.content_hash;r.inputs.content_hash=await sha(inputs);const body=structuredClone(r);delete body.content_hash;r.content_hash=await sha(body);
 await assert.rejects(()=>check(r),/mai edzés|tartalom|ellenőrizhető/);
});
test('explicit today preview carries the exact declaration and sends no automatic acceptance',async()=>{
 const r=data.today.review,expected={owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name},sent=[];const old=globalThis.fetch;
 globalThis.fetch=async(url,init)=>{sent.push({url,body:JSON.parse(init.body)});return Response.json({review:r});};
 try{await reviewTraining(expected,r.start_date,r.end_date,undefined,undefined,r.same_day_replacement);assert.equal(sent.length,1);assert.deepEqual(sent[0].body.same_day_replacement,r.same_day_replacement);assert(sent[0].url.endsWith('/review'));}finally{globalThis.fetch=old;}
});
