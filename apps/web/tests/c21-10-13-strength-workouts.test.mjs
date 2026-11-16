import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const fixture=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-13-strength-workouts.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readFeed}=load('src/lib/calendar/contracts.ts');
const {canonical,sha}=load('src/lib/planning-cycles/contracts.ts');
const {default:Details}=load('src/components/planning-cycles/workout-instructions.tsx');
const logs=load('src/lib/session-analysis/strength-log.ts');
const check=r=>readTrainingReview(r,{owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name});
for(const name of ['default_review','logged_review','feedback_review','accessory_review'])test(`actual new ${name} verifies every independent volume source and retains immutable bytes`,async()=>{
 const r=fixture[name],before=canonical(r);await check(r);assert.equal(canonical(r),before);
 const strength=r.result.proposals.filter(c=>c.sport==='STRENGTH');assert(strength.length);
 for(const c of strength){const v=r.result.instruction_context.by_candidate[c.candidate_key],html=renderToStaticMarkup(React.createElement(Details,{value:v}));assert.match(html,/Előírt munkasorozatok/);assert.match(html,/külön tervezett adag/);assert.match(html,/Legalább 3 szabályos ismétlés/);}
});
test('accepted calendar displays the independently calculated dose without hiding the table',()=>{
 const before=canonical(fixture.logged_feed),feed=readFeed(fixture.logged_feed);
 for(const p of feed.planned.filter(p=>p.sport==='STRENGTH')){assert.equal(p.planning_context.instructions_issue,undefined);assert.equal(p.planning_context.instructions.main.strength.schema_version,'strength-workout-dose-v0.1');}
 assert.equal(canonical(fixture.logged_feed),before);
});
async function rehash(r){const body=structuredClone(r);delete body.content_hash;r.content_hash=await sha(body);}
for(const kind of ['extra_set','weight','reference_set','duration','feedback','future_log','other_owner','wrong_pattern','assessment_as_training'])test(`tampering ${kind} is rejected even if the outer review is rehashed`,async()=>{
 const r=structuredClone(fixture.feedback_review),c=r.result.proposals.find(c=>c.sport==='STRENGTH'),d=c.strength_prescription,source=r.inputs.strength_workout_context.logs[0];
 if(kind==='extra_set')d.movements[0].work_sets++;
 if(kind==='weight')d.movements[0].target.load_value='999';
 if(kind==='reference_set')d.movements[0].reference.set_id='invented';
 if(kind==='duration')d.duration_sec+=300;
 if(kind==='feedback')source.feedback[0].artifact.proposal.fatigue=0;
 if(kind==='future_log'){source.log.durable_available_at='2099-01-01T00:00:00+00:00';}
 if(kind==='other_owner')source.log.artifact.athlete_id='00000000-0000-0000-0000-000000000001';
 if(kind==='wrong_pattern')source.log.artifact.proposal.exercises[0].pattern='core';
 if(kind==='assessment_as_training')source.log.artifact.proposal.purpose='assessment';
 await rehash(r.inputs);await rehash(r);await assert.rejects(()=>check(r));
});
test('actual log receipt retains exact decimal values and unknown reserve',async()=>{
 const r=fixture.log_context.current,read=await logs.receipt(r,r.artifact.athlete_id);assert.deepEqual(read,r);
 const p=structuredClone(r.artifact.proposal);p.exercises[0].sets[0].rir='unknown';assert.equal(logs.proposal(p).exercises[0].sets[0].rir,'unknown');
 assert.throws(()=>logs.proposal({...p,confirmed_actual:false}));p.exercises[0].sets[0].repetitions=null;assert.throws(()=>logs.proposal(p));
});

test('accessory without formal assessment has its own logged load and shares the pattern volume limit',async()=>{
 const r=fixture.accessory_review;await check(r);const doses=r.result.alternatives.flatMap(g=>g.candidates).filter(c=>c.sport==='STRENGTH').map(c=>c.strength_prescription);
 const rows=doses.flatMap(d=>d.movements).filter(m=>m.role==='accessory'&&m.reference.kind==='workout_log');assert(rows.some(m=>m.exercise_id==='db_overhead_press'&&m.target.load_value==='10.500000'));
 for(const d of doses)for(const pattern of new Set(d.movements.map(m=>m.pattern)))assert(d.movements.filter(m=>m.pattern===pattern).reduce((s,m)=>s+m.work_sets,0)<=7);
});
