import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-9-1-calendar-endurance.json',import.meta.url)));
const {readFeed,eventsFrom}=load('src/lib/calendar/contracts.ts');
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readAutomaticContext,runAutomatic,AutomaticError}=load('src/lib/planning-data/automation.ts');
const {readSportAvailability,validateSportAvailability}=load('src/lib/planning-cycles/sport-availability.ts');
const {forwardGoals}=load('src/lib/planning-goals/proxy.ts');
const {default:Details}=load('src/components/planning-data/sport-availability.tsx');
const {verifyAssessmentOptions}=load('src/lib/planning-cycles/assessment-options.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const owner=f.review.athlete_id;

test('real accepted refresh exposes daylight-safe endurance and excludes archived cancellations from the calendar',async()=>{
  await readTrainingReview(f.review,{owner,reference:f.review.program_reference,zone:f.review.timezone_name});
  const feed=readFeed(f.feed),events=eventsFrom(feed).filter(e=>e.kind==='planned');
  assert(events.some(e=>e.sport==='KAYAK'));assert(events.some(e=>e.sport==='RUNNING'));
  assert(!events.some(e=>f.cancelled_ids.includes(e.entityId)));
  await readAutomaticContext(f.automatic.context,owner);
});
test('a stale calendar response cannot draw cancelled plans while retaining active workouts and actual sessions',()=>{
  const feed=structuredClone(f.feed),original=feed.planned[0],cancelled=crypto.randomUUID();
  feed.planned.push({...original,id:cancelled,status:'CANCELLED'});
  const events=eventsFrom(feed);
  assert(!events.some(e=>e.entityId===cancelled));
  assert(events.some(e=>e.entityId===original.id));
  assert.equal(events.filter(e=>e.kind==='session').length,feed.sessions.length);
});
test('sport summary replays counts from actual proposals and alternatives',()=>{
  validateSportAvailability(f.review.result);
  const value=structuredClone(f.review.result),row=value.preparation.sport_availability.sports.find(r=>r.planned_sessions>0);
  row.planned_sessions--;
  assert.throws(()=>validateSportAvailability(value));
});
for(const [name,edit] of [
  ['boolean count',v=>v.sports[0].candidate_days=true],
  ['negative count',v=>v.sports[0].planned_sessions=-1],
  ['unknown sport',v=>v.sports[0].sport='OTHER'],
  ['duplicate sport',v=>v.sports.push(structuredClone(v.sports[0]))],
  ['invented swimming support',v=>v.sports.find(r=>r.sport==='SWIMMING').supported=true],
])test(`sport explanation rejects ${name}`,()=>{
  const v=structuredClone(f.missing_report);edit(v);assert.throws(()=>readSportAvailability(v));
});
test('missing running reference and unavailable swimming template have visible distinct explanations',()=>{
  const html=renderToStaticMarkup(React.createElement(Details,{value:readSportAvailability(f.missing_report)}));
  assert.match(html,/Futás/);assert.match(html,/kezdő futás már előzmény nélkül is tervezhető/);assert.match(html,/Úszás/);assert.match(html,/még nincs automatikus edzésminta/);
});
test('automatic planning timeout has a separate status and a longer bounded deadline without retrying a write',async()=>{
  const url='https://paddle.test/api/goal-workflow/automation/run';
  const request=()=>new Request(url,{method:'POST',headers:{Origin:'https://paddle.test','Content-Type':'application/json'},body:'{}'});
  const original=AbortSignal.timeout,deadlines=[];let calls=0;
  AbortSignal.timeout=ms=>{deadlines.push(ms);return new AbortController().signal;};
  try {
    const r=await forwardGoals(request(),['automation','run'],'http://backend.test',async()=>{calls++;throw new DOMException('Timed out','TimeoutError');});
    assert.equal(r.status,504);assert.equal((await r.json()).detail.code,'GOAL_API_TIMEOUT');
    assert.deepEqual(deadlines,[180000]);assert.equal(calls,1);
    const network=await forwardGoals(request(),['automation','run'],'http://backend.test',async()=>{throw new TypeError('Disconnected');});
    assert.equal(network.status,502);assert.equal((await network.json()).detail.code,'GOAL_API_UNAVAILABLE');
  } finally {AbortSignal.timeout=original;}
});
test('timeout message preserves the uncertainty and never automatically resends the mutation',async()=>{
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>{calls++;return Response.json({detail:{code:'GOAL_API_TIMEOUT'}},{status:504});};
  try {await assert.rejects(()=>runAutomatic(owner),e=>e instanceof AutomaticError&&e.code==='GOAL_API_TIMEOUT'&&e.status===504&&e.message.includes('még dolgozhat'));assert.equal(calls,1);}
  finally {globalThis.fetch=original;}
});

test('coordinate-only options update remains readable without an active daylight rule',async()=>{
  const value=f.geo_only_review;
  assert(value&&!value.inputs.daylight_context);
  await readTrainingReview(value,{owner,reference:value.program_reference,zone:value.timezone_name});
});
for(const [name,edit] of [
  ['changed equipment',r=>r.artifact.proposal.data.locations[0].resources.push('Másik felszerelés')],
  ['foreign owner',r=>r.artifact.athlete_id='00000000-0000-0000-0000-000000000001'],
])test(`assessment rebinding rejects ${name} even with an updated receipt hash`,async()=>{
  const value=structuredClone(f.geo_only_review),inputs=value.inputs,context=inputs.strength_assessment,current=context.current_options_receipt;
  edit(current);delete current.artifact.content_hash;current.artifact.content_hash=await sha(current.artifact);
  inputs.training_options_reference={artifact_id:current.artifact.artifact_id,content_hash:current.artifact.content_hash};
  await assert.rejects(()=>verifyAssessmentOptions(inputs,context.source_body,context,owner));
});
test('assessment observations survive a verified timetable-only revision',async()=>{
  const value=structuredClone(f.geo_only_review),inputs=value.inputs,context=inputs.strength_assessment,current=context.current_options_receipt;
  current.artifact.proposal.data.weekly_slots[0].details.max_minutes--;
  delete current.artifact.content_hash;current.artifact.content_hash=await sha(current.artifact);
  inputs.training_options_reference={artifact_id:current.artifact.artifact_id,content_hash:current.artifact.content_hash};
  await verifyAssessmentOptions(inputs,context.source_body,context,owner);
});
