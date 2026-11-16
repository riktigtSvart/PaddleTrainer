import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {load} from './load-goal-modules.mjs';
const fixture=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-14-strength-alternatives.json.gz',import.meta.url)))).imported_history;
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readFeed}=load('src/lib/calendar/contracts.ts');
const {focusedChoices}=load('src/lib/calendar/training-alternatives.ts');
const {canonical}=load('src/lib/planning-cycles/contracts.ts');
const check=r=>readTrainingReview(r,{owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name});
for(const name of ['review','choice'])test(`actual ${name} after importing new strength history retains its frozen duration source and current eligibility`,async()=>{
 const r=fixture[name],before=canonical(r);await check(r);assert.equal(canonical(r),before);
 const originalIds=r.calibration_review.inputs.recent_sessions.map(s=>s.id);
 assert(r.inputs.recent_sessions.some(s=>s.sport==='STRENGTH'&&!originalIds.includes(s.id)));
 for(const c of r.result.alternatives.flatMap(g=>g.candidates).filter(c=>c.sport==='STRENGTH'))assert(r.result.prescription_context.by_candidate[c.candidate_key].reference_session_ids.every(id=>originalIds.includes(id)));
});
test('clicked accepted day exposes actual alternatives and a replacement to review before saving',async()=>{
 const r=await check(fixture.review),feed=readFeed(fixture.feed),row=feed.planned.find(p=>p.id===fixture.target.id),target={...row.planning_context,id:row.id},focus=focusedChoices(r,target);
 assert(focus?.group&&focus.group.candidates.length>1);assert.equal(focus.group.date,target.date);
 const chosen=await check(fixture.choice);assert(chosen.result.cancel.includes(target.id));assert.equal(chosen.result.proposals.filter(c=>c.date===target.date).length,1);
 assert.equal(chosen.result.proposals.find(c=>c.date===target.date).candidate_key,fixture.candidate.candidate_key);
});

test('using frozen history cannot hide a newly logged current strength dose',async()=>{
 const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-14-strength-alternatives.json.gz',import.meta.url)))).current_log,r=await check(data.review);
 assert.equal(r.calibration_review.inputs.strength_workout_context.logs.length,0);
 assert.equal(r.inputs.strength_workout_context.logs.length,1);
 assert(r.result.alternatives.flatMap(g=>g.candidates).filter(c=>c.sport==='STRENGTH').flatMap(c=>c.strength_prescription.movements).some(m=>m.reference.kind==='workout_log'&&m.observed_work_sets===4&&m.work_sets===4));
});

test('newly imported history cannot be substituted into a frozen duration source after outer rehash',async()=>{
 const r=structuredClone(fixture.review),originalIds=new Set(r.calibration_review.inputs.recent_sessions.map(s=>s.id)),imported=r.inputs.recent_sessions.find(s=>s.sport==='STRENGTH'&&!originalIds.has(s.id)),c=r.result.alternatives.flatMap(g=>g.candidates).find(c=>c.sport==='STRENGTH');
 assert(imported);r.result.prescription_context.by_candidate[c.candidate_key].reference_session_ids=[imported.id];
 const {sha}=load('src/lib/planning-cycles/contracts.ts'),body=structuredClone(r);delete body.content_hash;r.content_hash=await sha(body);
 await assert.rejects(()=>check(r),/erősítő munkamennyiség/);
});
