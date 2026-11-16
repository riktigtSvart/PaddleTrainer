import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-6-references.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {declaredSwimming}=load('src/lib/planning-cycles/declared-swimming.ts');
const {validateSwimmingCandidate}=load('src/lib/planning-cycles/swimming-prescription.ts');
const {validateStarterCandidate}=load('src/lib/planning-cycles/strength-starter.ts');
const {PrescriptionDetails}=load('src/components/planning-cycles/plan-output.tsx');
const {default:SportAvailability}=load('src/components/planning-data/sport-availability.tsx');
const read=v=>readTrainingReview(v,{owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});
const candidates=v=>v.result.alternatives.flatMap(g=>g.candidates);
const firstSwim=v=>candidates(v).find(c=>c.sport==='SWIMMING');
const firstStarter=v=>candidates(v).find(c=>c.template_version==='v0.4'&&c.sport==='STRENGTH');
const rehash=async v=>{const body={...v};delete body.content_hash;v.content_hash=await sha(body);};
for(const [name,v] of Object.entries(f)) test(`real C21.10.6 API review verifies unchanged receipts and prescription evidence: ${name}`,async()=>{await read(v);});

test('rescheduling keeps exact source observations and uses the current slot',()=>{
  const v=f.rescheduled,ctx=v.inputs.strength_assessment;
  assert.equal(ctx.receipt.artifact.proposal.source_hash,ctx.source_hash);
  assert(candidates(v).some(c=>c.strength_prescription&&c.start_at.slice(11,16)==='18:00'));
});
test('sport-history skill enables self-paced swimming without inventing a stroke or capacity',()=>{
  const v=f.profile_swimming,d=declaredSwimming(v.inputs),c=firstSwim(v),dose=v.result.prescription_context.by_candidate[c.candidate_key].swimming;
  assert.equal(d.skill.independent,true);assert.equal(d.skill.preferred_stroke,'self_selected');
  assert.deepEqual(d.skill.strokes,[]);assert.equal(dose.continuous_distance_limit_m,null);
  assert.equal(dose.declared_cap_seconds,null);assert.equal(dose.mode,'self_paced');
});
for(const [name,change] of [
  ['learning',r=>r.planning.proficiency='learning'],['unknown skill',r=>r.planning.proficiency='unknown'],
  ['recreational role',r=>r.role='recreation'],['paused role',r=>r.role='paused'],['inactive',r=>r.current=false],
  ['other supported sport',r=>r.planning.supported_sports=['Futás']],
])test(`swimming independence is not inferred from ${name}`,()=>{
  const inputs=structuredClone(f.profile_swimming.inputs),row=inputs.profile.data.sport_history.find(r=>r.sport==='Úszás');change(row);
  assert.equal(declaredSwimming(inputs),null);
});
test('a known stroke is used; a generic mixed discipline stays self-selected',()=>{
  assert.equal(declaredSwimming(f.swimming_without_length.inputs).skill.preferred_stroke,'breaststroke');
  assert.equal(declaredSwimming(f.profile_swimming.inputs).skill.preferred_stroke,'self_selected');
});
for(const [name,change] of [
  ['forged continuous capacity',(_v,_c,m)=>m.swimming.continuous_distance_limit_m=2000],
  ['guessed freestyle',(_v,_c,m)=>m.swimming.stroke='freestyle'],
  ['pace claim',(_v,_c,m)=>m.swimming.pace_estimated=true],
  ['foreign skill source',(_v,_c,m)=>m.swimming.ability_basis.profile_reference.content_hash='f'.repeat(64)],
  ['different pool',(_v,c)=>c.location_id=crypto.randomUUID()],
])test(`profile swimming rejects ${name}`,async()=>{
  const v=structuredClone(f.profile_swimming),c=firstSwim(v),m=v.result.prescription_context.by_candidate[c.candidate_key];change(v,c,m);
  await assert.rejects(()=>validateSwimmingCandidate(v,c,m));
});
for(const [name,change] of [
  ['missing current profile receipt',v=>delete v.inputs.strength_assessment.current_profile_receipt],
  ['profile data changed under the same receipt',v=>v.inputs.profile.data.typical_days_per_week=1],
  ['health change hidden as a biography change',v=>v.inputs.profile.data.participation='professional_review'],
  ['foreign receipt owner',v=>v.inputs.strength_assessment.current_profile_receipt.artifact.athlete_id=crypto.randomUUID()],
  ['receipt after cutoff',v=>v.inputs.strength_assessment.current_profile_receipt.durable_available_at='2030-01-01T00:00:00Z'],
])test(`reference reuse rejects ${name} even if the outer review is rehashed`,async()=>{
  const v=structuredClone(f.profile_swimming);change(v);await rehash(v);await assert.rejects(()=>read(v));
});
for(const [name,change] of [
  ['external weight',m=>m.introductory_strength.external_load_prescribed=true],
  ['invented maximum',m=>m.introductory_strength.one_rm_estimated=true],
  ['added sets',m=>m.introductory_strength.sets_per_movement=3],
  ['invented reference',m=>m.reference_session_ids=[crypto.randomUUID()]],
  ['development claim',m=>m.introductory_strength.full_development_claim=true],
])test(`introductory default rejects ${name}`,async()=>{
  const v=structuredClone(f.introductory_strength),c=firstStarter(v),m=v.result.prescription_context.by_candidate[c.candidate_key];change(m);
  await assert.rejects(()=>validateStarterCandidate(v,c,m,v.inputs.strength_assessment));
});
test('new prescription details show concrete preparation and never print null length or rest',()=>{
  const intro=f.introductory_strength,c=firstStarter(intro);
  const h=renderToStaticMarkup(React.createElement(PrescriptionDetails,{review:intro,candidateKey:c.candidate_key}));
  assert.match(h,/legfeljebb 5/);assert.match(h,/külső teher nélkül/);assert.match(h,/előkészítő alkalom/);
  const swim=f.swimming_without_length,s=firstSwim(swim),html=renderToStaticMarkup(React.createElement(PrescriptionDetails,{review:swim,candidateKey:s.candidate_key}));
  assert.match(html,/saját szakaszokkal/);assert.doesNotMatch(html,/null|undefined|hosszanként/);
});
test('introductory default cannot enlarge a known recent 15-minute strength duration',async()=>{
  const v=structuredClone(f.introductory_strength),c=firstStarter(v),end=Date.parse(v.inputs.captured_at)-86400000;
  v.inputs.recent_sessions.unshift({id:crypto.randomUUID(),sport:'STRENGTH',duration_sec:900,started_at:new Date(end-900000).toISOString(),ended_at:new Date(end).toISOString(),reference_occasion:false});
  await assert.rejects(()=>validateStarterCandidate(v,c,v.result.prescription_context.by_candidate[c.candidate_key],v.inputs.strength_assessment));
});
test('detailed planning reasons remain collapsed until opened',()=>{
  const html=renderToStaticMarkup(React.createElement(SportAvailability,{value:f.profile_swimming.result.preparation.sport_availability}));
  assert.match(html,/^<details class="pt-auto-sport-availability"><summary>Miért ezek az edzések\?/);
  assert.doesNotMatch(html,/^<details[^>]*\bopen/);
});
