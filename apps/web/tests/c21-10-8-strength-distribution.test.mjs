import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-8-strength-distribution.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {compareAssessmentSources,physicalStrengthOptions,sourceChangeLabels}=load('src/lib/planning-cycles/assessment-source-changes.ts');
const {StrengthAssessmentPanel}=load('src/components/planning-cycles/strength-assessment.tsx');
const {default:PlanOutput}=load('src/components/planning-cycles/plan-output.tsx');
const read=v=>readTrainingReview(v,{owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});
async function resign(v) {for(const raw of [v.inputs,v]) {const body={...raw};delete body.content_hash;raw.content_hash=await sha(body);}}

for(const [name,value] of Object.entries(f))test(`C21.10.8 actual API review passes independent browser verification: ${name}`,async()=>{await read(value);});

test('adding an unrelated pool preserves the exact assessment and assigned strength purpose',()=>{
  const v=f.added_pool,c=v.inputs.strength_assessment;
  assert(c.receipt.artifact.proposal.source_hash!==c.source_hash);
  assert.deepEqual(compareAssessmentSources(c),c.source_comparison);
  assert(c.source_comparison.reusable);
  assert(v.result.proposals.some(p=>p.sport==='STRENGTH'&&p.capability_key==='MAX_STRENGTH'));
  assert(f.repeated.result.create.length===0&&f.repeated.result.cancel.length===0);
});
test('venue identity uses only measured venues, sorted equipment, and strength availability',()=>{
  const c=f.cosmetic.inputs.strength_assessment,ids=c.source_comparison.location_ids;
  assert.deepEqual(physicalStrengthOptions(c.receipt.artifact.snapshot.options_receipt.artifact.proposal.data,ids),physicalStrengthOptions(c.options_source_receipt.artifact.proposal.data,ids));
  assert(!f.material_equipment.inputs.strength_assessment.source_comparison.reusable);
});
test('three weekly sessions are spaced across Friday-started microcycles with strength included',()=>{
  const v=f.three_per_week,d=v.result.distribution;
  assert.equal(d.before.adjacent_training_day_pairs,8);
  assert.equal(d.after.adjacent_training_day_pairs,0);
  assert.equal(d.before.longest_training_free_span_days,4);
  assert(d.after.longest_training_free_span_days<=2);
  for(const block of v.result.mesocycle_coordination.blocks) {
    const rows=v.result.proposals.filter(c=>block.start_date<=c.date&&c.date<=block.end_date);
    assert(rows.length===3&&rows.some(c=>c.sport==='STRENGTH'));
  }
});
for(const [name,change] of [
  ['unverified reuse flag',v=>v.inputs.strength_assessment.source_comparison.reusable=false],
  ['shrunk venue scope',v=>v.inputs.strength_assessment.source_comparison.location_ids=[]],
  ['missing comparison',v=>delete v.inputs.strength_assessment.source_comparison],
  ['receipt after input cutoff',v=>v.inputs.strength_assessment.options_source_receipt.durable_available_at='2027-01-01T00:00:00+00:00'],
  ['different owner',v=>v.inputs.strength_assessment.options_source_receipt.artifact.athlete_id='00000000-0000-0000-0000-000000000999'],
  ['returning status changed under same profile reference',v=>v.inputs.profile.data.interruption='returning'],
  ['missing distribution proof',v=>delete v.result.distribution],
  ['inflated rhythm claim',v=>v.result.distribution.after.adjacent_training_day_pairs++],
  ['inflated rest gap claim',v=>v.result.distribution.before.longest_training_free_span_days++],
  ['duplicate seed reference',v=>v.result.distribution.baseline_candidate_keys.push(v.result.distribution.baseline_candidate_keys[0])],
  ['invented capacity increase',v=>v.result.distribution.capacity_increased=true],
  ['unbounded search claim',v=>v.result.distribution.optimization_passes=33],
])test(`rehashed API envelope cannot hide ${name}`,async()=>{
  const v=structuredClone(f.added_pool);change(v);await resign(v);await assert.rejects(read(v));
});
test('a material equipment change cannot be reclassified as harmless',async()=>{
  const v=structuredClone(f.material_equipment);v.inputs.strength_assessment.source_comparison.reusable=true;
  v.inputs.strength_assessment.source_comparison.changes=['OPTIONS_OTHER_FIELDS'];await resign(v);await assert.rejects(read(v));
});
test('the user sees the specific source category and a placement explanation',()=>{
  const panel=renderToStaticMarkup(React.createElement(StrengthAssessmentPanel,{review:f.material_equipment}));
  assert(panel.includes(sourceChangeLabels.OPTIONS_REFERENCED_LOCATIONS));
  const output=renderToStaticMarkup(React.createElement(PlanOutput,{review:f.three_per_week,disabled:false,onChoose(){}}));
  assert(output.includes('pihenőnapokkal tagoltabb ritmust'));
  assert(output.includes('edzésszáma és összideje nem nő'));
});
