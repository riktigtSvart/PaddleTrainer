import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';

const f=JSON.parse(readFileSync(new URL('./fixtures/c21-8-3-assessment-recovery.json',import.meta.url)));
const {recoverAssessment}=load('src/lib/initial-assessment/recovery.ts');
const {restoreAssessmentDraft}=load('src/lib/initial-assessment/draft-sync.ts');
const {preserveAssessmentRecovery,preserveLocalRecovery}=load('src/lib/initial-assessment/recovery-backup.ts');
const {readContext,readPending,summarize,normalizeData}=load('src/lib/initial-assessment/contracts.ts');
const c=f.context, owner=c.athlete_id;
const rawDraft=(data=f.local_data)=>JSON.stringify({version:'initial-assessment-draft-v0.1',owner,
  data,source_hash:c.sources.source_hash,previous_reference:c.reference,open:4});
const rawPending=(data=f.local_data)=>JSON.stringify({version:'initial-assessment-pending-v0.1',owner,
  body:JSON.stringify({request_id:crypto.randomUUID(),source_hash:c.sources.source_hash,previous_reference:c.reference,data})});
const references=result=>summarize(result.data,c.sources,c.local_today).recorded_reference_count;

test('real owned API context has zero usable old references while four newer answers exist only locally',async()=>{
  await readContext(c);assert.equal(c.summary.recorded_reference_count,0);
  assert.equal(f.local_data.exercises.filter(e=>e.performed_on==='2026-11-11').length,4);
  assert.equal(f.local_data.assessment_date,c.data.assessment_date);
});

test('an old review date recovers newer local observations even when the server has no newer assessment',()=>{
  const raw=rawDraft(),result=restoreAssessmentDraft(raw,owner,c.data,c.local_today);
  assert.equal(result.recovered,true);assert.equal(result.draft.data.assessment_date,'2026-11-11');
  assert.deepEqual(result.draft.data.exercises,f.local_data.exercises);
  assert.equal(rawDraft(),raw);assert.doesNotThrow(()=>normalizeData(result.draft.data));
});

for(const date of ['', '2026-02-30']) test('a broken review day can be reopened using today while real observation dates stay intact: '+date,()=>{
  const data={...structuredClone(f.local_data),assessment_date:date};
  const result=restoreAssessmentDraft(rawDraft(data),owner,c.data,c.local_today);
  assert.equal(result.recovered,true);assert.equal(result.draft.data.assessment_date,c.local_today);
  assert.deepEqual(result.draft.data.exercises,data.exercises);
});

test('invalid pending chronology cannot hide four recoverable local results',async()=>{
  const draft=rawDraft(),pending=rawPending();
  assert.throws(()=>readPending(pending,owner));
  const result=await recoverAssessment(c,draft,pending,async()=>{throw Error('No invalid write should be read or sent');});
  assert.equal(result.recoveryRequired,true);assert.equal(result.pending,null);assert.equal(result.committed,null);
  assert.equal(references(result),4);assert.equal(result.data.reviewed,false);
  assert.deepEqual(result.data.exercises,f.local_data.exercises);
  assert.equal(draft,rawDraft());assert.doesNotThrow(()=>normalizeData(result.data));
});

test('the newest results can be recovered from an invalid frozen request even if the old draft was not updated',async()=>{
  const result=await recoverAssessment(c,rawDraft(c.data),rawPending(),async()=>null);
  assert.equal(result.recoveryRequired,true);assert.equal(references(result),4);
  assert.deepEqual(result.data.exercises,f.local_data.exercises);
});

test('edits made while an invalid pending request awaits recovery survive another reopening',async()=>{
  const pending=rawPending(),first=await recoverAssessment(c,rawDraft(),pending,async()=>null);
  const working=JSON.parse(rawDraft(first.data));working.pending_request_id=first.draftPendingId;
  working.data.exercises[0].sets[0].repetitions=17;
  const reopened=await recoverAssessment(c,JSON.stringify(working),pending,async()=>null);
  assert.equal(reopened.data.exercises[0].sets[0].repetitions,17);
  assert.equal(references(reopened),4);assert.equal(reopened.recoveryRequired,true);
});

test('a valid older pending request cannot replace a newer unlinked legacy draft',async()=>{
  const pending=rawPending(c.data),body=JSON.parse(pending).body;
  const result=await recoverAssessment(c,rawDraft(),pending,async()=>null);
  assert.equal(result.recoveryRequired,true);assert.equal(result.pending.body,body);
  assert.equal(references(result),4);assert.equal(result.data.reviewed,false);
});

for(const malformed of ['not JSON',JSON.stringify({version:'future',owner}),rawPending({...f.local_data,experience:'future'})])
  test('a malformed pending envelope does not prevent an independent valid draft from opening: '+malformed.slice(0,28),async()=>{
    const result=await recoverAssessment(c,rawDraft(),malformed,async()=>null);
    assert.equal(result.recoveryRequired,true);assert.equal(references(result),4);
  });

test('a foreign draft and foreign pending body never populate the current athletes editor',async()=>{
  const draft=JSON.parse(rawDraft()),pending=JSON.parse(rawPending());draft.owner=crypto.randomUUID();pending.owner=draft.owner;
  const result=await recoverAssessment(c,JSON.stringify(draft),JSON.stringify(pending),async()=>null);
  assert.equal(result.recoveryRequired,true);assert.deepEqual(result.data.exercises,c.data.exercises);
  assert.equal(references(result),0);
});

test('a future observation is retained outside the working editor rather than silently redated into the past',async()=>{
  const local=structuredClone(f.local_data);local.exercises[0].performed_on='2027-01-01';
  assert.throws(()=>restoreAssessmentDraft(rawDraft(local),owner,c.data,c.local_today));
  const result=await recoverAssessment(c,rawDraft(local),null,async()=>null);
  assert.equal(result.recoveryRequired,true);assert.deepEqual(result.data.exercises,c.data.exercises);
  assert.equal(local.exercises[0].performed_on,'2027-01-01');
});

test('backup stores original draft and frozen pending strings exactly and never overwrites their normal keys',async()=>{
  const writes=[],map=new Map(),storage={getItem:k=>map.get(k)??null,setItem:(k,v)=>{writes.push(k);map.set(k,v);}};
  const inputs={draft:rawDraft(),pending:rawPending()};
  const first=await preserveAssessmentRecovery(storage,owner,inputs),second=await preserveAssessmentRecovery(storage,owner,inputs);
  assert.deepEqual(first,second);assert.equal(writes.length,1);assert.match(first.key,/:recovery:/);
  assert.equal(JSON.parse(first.payload).draft,inputs.draft);assert.equal(JSON.parse(first.payload).pending,inputs.pending);
});

test('a full or unreadable local store cannot be reported as a preserved recovery copy',async()=>{
  await assert.rejects(()=>preserveAssessmentRecovery({getItem:()=>null,setItem:()=>{throw Error('full');}},owner,{draft:rawDraft(),pending:null}));
  await assert.rejects(()=>preserveAssessmentRecovery({getItem:()=>null,setItem(){}},owner,{draft:rawDraft(),pending:null}));
});

test('guided-operation recovery copies are separate from questionnaire recovery copies',async()=>{
  const map=new Map(),storage={getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)};
  const inputs={draft:'exact draft bytes',pending:'exact pending bytes'};
  const initial=await preserveAssessmentRecovery(storage,owner,inputs);
  const guided=await preserveLocalRecovery(storage,owner,inputs,'guided-strength');
  assert.notEqual(initial.key,guided.key);assert.equal(map.size,2);
  assert.equal(JSON.parse(guided.payload).pending,inputs.pending);
});
