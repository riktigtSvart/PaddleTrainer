import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-9-2-running-start.json',import.meta.url)));
const receipt=JSON.parse(readFileSync(new URL('./fixtures/c21-9-2-history-backfill.json',import.meta.url)));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {validatePrescriptionContext}=load('src/lib/planning-cycles/prescription-context.ts');
const {runningReference}=load('src/lib/planning-cycles/running-prescription.ts');
const {sha,canonical}=load('src/lib/planning-cycles/contracts.ts');
const {newHistory,historyPending,readHistory,advanceHistory}=load('src/lib/data-connections/history-backfill.ts');
const {readBody,readReceipt}=load('src/lib/data-connections/contracts.ts');
const {PrescriptionDetails}=load('src/components/planning-cycles/plan-output.tsx');
const expected=v=>({owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});
async function rehash(v){delete v.content_hash;v.content_hash=await sha(v);return v;}

test('real HTTP reviews support empty, short, historical and personal-best running evidence',async()=>{
  assert.equal(Object.keys(f).length,5);
  for(const v of Object.values(f))await readTrainingReview(v,expected(v));
  assert.equal(runningReference(f.empty.inputs).running.mode,'run_walk_start');
  assert.equal(runningReference(f.personal_best.inputs).running.mode,'experience_start');
  assert.equal(runningReference(f.historical.inputs).cap,null);
  assert.equal(runningReference(f.short_test.inputs).cap,1800);
  assert.equal(runningReference(f.current_evidence.inputs).cap,2100);
  assert(f.current_evidence.calibration_review);
});
for(const [name,edit]of[
  ['invented current capacity',v=>{Object.values(v.result.prescription_context.by_candidate)[0].running.current_capacity_inferred=true;}],
  ['invented historical source',v=>{Object.values(v.result.prescription_context.by_candidate)[0].running.historical_session_ids.push('foreign');}],
  ['larger product default',v=>{Object.values(v.result.prescription_context.by_candidate)[0].reference_cap_seconds=3600;}],
  ['wrong starting mode',v=>{Object.values(v.result.prescription_context.by_candidate)[0].running.mode='recent_duration';}],
  ['future historical record',v=>{v.inputs.running_background.sessions[0].ended_at='2027-01-01T00:00:00+00:00';}],
  ['reference from another sport',v=>{v.inputs.running_background.sessions[0].sport='KAYAK';}],
])test(`running provenance rejects ${name} after outer rehash`,async()=>{
  const v=structuredClone(f.historical);edit(v);await rehash(v);await assert.rejects(()=>readTrainingReview(v,expected(v)));
  await assert.rejects(()=>validatePrescriptionContext(v));
});
test('the verified instruction cannot silently turn walk-run intervals into a hard workout',async()=>{
  const v=structuredClone(f.empty);
  for(const c of v.result.proposals)c.description='20 perc maximális futás';
  await assert.rejects(()=>validatePrescriptionContext(v));
});
test('older immutable reviews retain their original prescription rules',async()=>{
  const old=JSON.parse(readFileSync(new URL('./fixtures/c21-9-1-calendar-endurance.json',import.meta.url))).review;
  await readTrainingReview(old,expected(old));
});
test('the visible prescription distinguishes a product start from current running records',()=>{
  for(const [name,pattern]of[['empty',/kezdő futás–séta/],['personal_best',/mai terhelhetőséget/],['short_test',/rövid tesztek nem szabnak felső korlátot/]]){
    const v=f[name],html=renderToStaticMarkup(React.createElement(PrescriptionDetails,{review:v,candidateKey:v.result.proposals[0].candidate_key}));
    assert.match(html,pattern);
    assert.doesNotMatch(html,/legfeljebb 30 perces kezdőváltozat/);
  }
});
test('invalid whole-period dates are rejected before preparing the first import',()=>{
  assert.throws(()=>newHistory(receipt.athlete_id,'2021-02-30','2026-11-13'));
  assert.throws(()=>newHistory(receipt.athlete_id,'2021-12-01','2026-13-01'));
});
test('backfill partitions years into exact, non-overlapping ninety-day batches',()=>{
  let s=newHistory(receipt.athlete_id,'2021-12-01','2026-11-13'),batches=0,days=0;
  while(s.cursor>s.first_date){
    const p=historyPending(s,crypto.randomUUID()),b=readBody(JSON.parse(p.body)),range=b.history_range;
    assert.equal(range.to_exclusive,s.cursor);
    const length=(Date.parse(range.to_exclusive)-Date.parse(range.from_date))/86400000;
    assert(length>=1&&length<=90);days+=length;batches++;s={...s,cursor:range.from_date};
  }
  assert.equal(days,(Date.parse('2026-11-13')-Date.parse('2021-12-01'))/86400000);
  assert.equal(batches,21);
});
test('a historical receipt advances only the exact retained owner, body and range',async()=>{
  let s=newHistory(receipt.athlete_id,'2021-12-01','2022-03-01');
  s={...s,pending:historyPending(s,receipt.start.proposal.request_id)};
  await readReceipt(receipt,s.pending);
  const next=await advanceHistory(s,receipt);
  assert.equal(next.cursor,'2021-12-01');assert.equal(next.imported,1);assert.equal(next.checked_batches,1);assert.equal(next.pending,null);
  assert.deepEqual(readHistory(JSON.stringify(s),s.owner),s);
  assert.throws(()=>readHistory(JSON.stringify(s),crypto.randomUUID()));
  const other={...s,pending:{...s.pending,body:canonical({...JSON.parse(s.pending.body),history_range:{from_date:'2021-12-02',to_exclusive:'2022-03-01'}})}};
  await assert.rejects(()=>advanceHistory(other,receipt));
});
for(const range of [
  {from_date:'2021-12-01',to_exclusive:'2022-03-02'},
  {from_date:'2021-02-30',to_exclusive:'2021-03-01'},
  {from_date:'2021-12-01',to_exclusive:'2021-12-01'},
])test(`invalid historical range is rejected: ${JSON.stringify(range)}`,()=>{
  assert.throws(()=>readBody({...receipt.start.proposal,history_range:range}));
});
test('history requests cannot add target or sample imports',()=>{
  assert.throws(()=>readBody({...receipt.start.proposal,datasets:['sessions','targets']}));
  assert.throws(()=>readBody({...receipt.start.proposal,datasets:['session_details']}));
});
