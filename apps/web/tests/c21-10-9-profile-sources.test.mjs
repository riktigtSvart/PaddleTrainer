import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const values=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-9-profile-sources.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readCycleContext}=load('src/lib/calendar/cycle-context.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {compareStrengthProfile,readProfileComparison,profileFieldLabels}=load('src/lib/planning-cycles/assessment-profile.ts');
const {StrengthAssessmentPanel}=load('src/components/planning-cycles/strength-assessment.tsx');
const {default:ProfileChanges}=load('src/components/planning-cycles/profile-changes.tsx');
const read=v=>readTrainingReview(v,{owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});
const c=v=>v.inputs.strength_assessment;
async function resign(v) {for(const raw of [v.inputs,v].filter(Boolean)){const body={...raw};delete body.content_hash;raw.content_hash=await sha(body);}}
for(const [name,v] of Object.entries(values))test(`actual C21.10.9 API profile evidence verifies: ${name}`,async()=>{
  if(v.schema_version==='calendar-cycle-context-v0.1')await readCycleContext(v,{owner:v.athlete_id,zone:v.timezone_name,start:v.start_date,end:v.end_date});
  else await read(v);
});
test('live source and equipment updates retain original observations with current profile receipts',()=>{
  for(const name of ['resources','duration_doubling_slowdown_pct','manual_observations','source_window','selected_sources_and_pool']) {
    const v=values[name],context=c(v);
    assert.deepEqual(compareStrengthProfile(context),context.profile_comparison);
    assert(context.profile_comparison.reference_reusable);
    assert.deepEqual(context.profile_comparison.blocking_fields,[]);
    assert(v.result.proposals.some(p=>p.sport==='STRENGTH'&&p.capability_key==='MAX_STRENGTH'));
    assert.notEqual(context.current_profile_receipt.artifact.content_hash,context.receipt.artifact.snapshot.profile_reference.content_hash);
  }
  assert.equal(values.repeated.result.create.length,0);assert.equal(values.repeated.result.cancel.length,0);
});
test('true state/body changes stay blocked and the exact fields are available',()=>{
  for(const [name,v] of Object.entries(values).filter(([name])=>name.startsWith('changed_'))) {
    assert(c(v).profile_comparison.blocking_fields.length,name);
    assert.equal(c(v).profile_comparison.reference_reusable,false);
    assert(!v.result.proposals.some(p=>p.sport==='STRENGTH'));
  }
  assert.deepEqual(c(values.changed_recovery_notes).profile_comparison.blocking_fields,['recovery_notes']);
  assert(c(values.changed_body_mass_kg).profile_comparison.blocking_fields.includes('body_mass_kg'));
});
for(const [name,change] of [
  ['missing profile comparison',v=>delete c(v).profile_comparison],
  ['fake blocking field',v=>c(v).profile_comparison.blocking_fields=['resources']],
  ['hidden changed fields',v=>c(v).profile_comparison.changed_fields=[]],
  ['reusability flag without proof',v=>c(v).profile_comparison.reference_reusable=false],
  ['missing current profile receipt',v=>delete c(v).current_profile_receipt],
  ['profile data under another receipt',v=>v.inputs.profile.data.participation='paused'],
  ['receipt belonging to another owner',v=>c(v).current_profile_receipt.artifact.athlete_id='00000000-0000-0000-0000-000000000999'],
  ['receipt after capture cutoff',v=>c(v).current_profile_receipt.durable_available_at='2027-01-01T00:00:00+00:00'],
])test(`rehashing the envelope cannot hide ${name}`,async()=>{const v=structuredClone(values.resources);change(v);await resign(v);await assert.rejects(read(v));});
test('a real health change cannot be relabelled as a harmless profile refresh',async()=>{
  const v=structuredClone(values.changed_recovery_notes);
  c(v).profile_comparison.blocking_fields=[];c(v).profile_comparison.reference_reusable=true;
  await resign(v);await assert.rejects(read(v));
});
test('the changed profile source must match the declared source reference',async()=>{
  const v=structuredClone(values.changed_recovery_notes);delete c(v).profile_source_receipt;
  await resign(v);await assert.rejects(read(v));
});
test('an intermediate state change remains visible after current values are equal again',()=>{
  const v=values.reverted_profile,comparison=c(v).profile_comparison;
  assert.deepEqual(comparison.changed_fields,[]);assert(comparison.source_reference_changed);assert(!comparison.reference_reusable);
  const markup=renderToStaticMarkup(React.createElement(ProfileChanges,{value:comparison}));
  assert(markup.includes('változási előzménye'));
  assert(markup.includes('/strength-assessment'));
});
test('field names are shown without copying private profile values to the cycle context',()=>{
  const v=values.changed_recovery_notes,markup=renderToStaticMarkup(React.createElement(StrengthAssessmentPanel,{review:v}));
  assert(markup.includes('Felülvizsgálandó profiladatok'));
  assert(markup.includes(profileFieldLabels.recovery_notes));
  assert(!markup.includes(v.inputs.profile.data.recovery_notes));
  assert(!JSON.stringify(values.calendar_blocked).includes(v.inputs.profile.data.recovery_notes));
});
test('the changed profile can be explicitly reviewed while preserving existing sets',()=>{
  const v=values.reviewed_profile;
  assert(v.result.proposals.some(p=>p.sport==='STRENGTH'));
  assert(c(v).profile_comparison.reference_reusable);
});
test('unknown field labels and contradictory diagnostic flags are rejected',()=>{
  for(const change of [v=>v.changed_fields.push('unknown_private_field'),v=>v.blocking_fields=['recovery_notes'],v=>v.source_reference_changed=true]) {
    const v=structuredClone(c(values.resources).profile_comparison);change(v);assert.throws(()=>readProfileComparison(v));
  }
});
