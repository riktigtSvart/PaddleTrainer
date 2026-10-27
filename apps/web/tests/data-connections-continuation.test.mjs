import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {load} from './load-goal-modules.mjs';
const c=load('src/lib/data-connections/contracts.ts'),{runMessages}=load('src/lib/data-connections/client.ts');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/session-details-sync.json',import.meta.url)));
function status(){
 const s=structuredClone(fixture.status),r=s.providers[0].last_run;r.state='partial';r.error_code='DATA_SYNC_PROTECTED_PLANS_SKIPPED';
 Object.assign(r.datasets[1],{skipped:1,skip_reasons:{protected_plan:1},error_code:'DATA_SYNC_PROTECTED_PLANS_SKIPPED'});
 Object.assign(r.datasets[2],{imported:0,updated:1,skipped:2,skip_reasons:{details_batch_pending:2},error_code:'DATA_SYNC_DETAILS_PENDING',
  details:{requested_sessions:5,already_complete:2,fetched_sessions:1,with_samples:1,without_samples:0,pending_sessions:2,processed_days:1,pending_days:2}});
 return s;
}
test('a complete reported pending batch with preserved plans is resumable without rewriting its partial receipt',()=>{
 const s=status(),before=structuredClone(s),p=c.readStatus(s).providers[0];
 assert.equal(c.continuationOnly(p.last_run),true);assert.equal(c.attention(p),false);assert.equal(c.providerState(p),'Átvétel folytatható');
 assert.match(runMessages(p.last_run).join(' '),/még 2 edzés, 2 napon/);assert.deepEqual(s,before);assert.equal(p.last_run.state,'partial');
});
for(const [name,change] of [
 ['source conflict',r=>{r.datasets[2].error_code='DATA_SYNC_DETAILS_SOURCE_CONFLICT';r.datasets[2].skip_reasons={details_source_conflict:2};}],
 ['omitted source',r=>{r.datasets[2].error_code='DATA_SYNC_DETAILS_NOT_RETURNED';r.datasets[2].skip_reasons={details_not_returned:2};}],
 ['mixed omissions',r=>{r.datasets[2].skip_reasons={details_batch_pending:1,details_not_returned:1};}],
 ['timeout',r=>{r.datasets[2].error_code='DATA_SYNC_TIMEOUT';}],
 ['failed dataset',r=>{r.datasets[2].state='failed';}],
 ['missing dataset',r=>{r.datasets.pop();}],
 ['duplicate dataset',r=>{r.datasets[2]=structuredClone(r.datasets[1]);}],
 ['unknown outcome',r=>{r.error_code='FUTURE_ERROR';}],
 ['unknown counts',r=>{r.datasets[0].updated=null;}],
 ['unknown reason census',r=>{delete r.datasets[2].skip_reasons;}],
 ['no detail census',r=>{delete r.datasets[2].details;}],
 ['no end timestamp',r=>{r.finished_at=null;}],
 ['pairing conflict',r=>{r.datasets[2].pairing={linked:0,already_linked:0,unmatched:0,missing_reference:0,conflicts:1,ambiguous:0};}],
])test('resumable display never masks '+name,()=>{
 const s=status();change(s.providers[0].last_run);const p=c.readStatus(s).providers[0];
 assert.equal(c.continuationOnly(p.last_run),false);assert.equal(c.attention(p),true);
});
test('the actual dataset failure is prominent even when the first overall code only describes preserved plans',()=>{
 const s=status(),r=s.providers[0].last_run;r.datasets[2].error_code='DATA_SYNC_DETAILS_SOURCE_CONFLICT';r.datasets[2].skip_reasons={details_source_conflict:2};
 const lines=runMessages(c.readStatus(s).providers[0].last_run);assert.match(lines[0],/Részletes edzésadatok.*DATA_SYNC_DETAILS_SOURCE_CONFLICT/);
 assert.match(lines.join(' '),/védett vagy kézi/);
});
for(const code of ['DATA_SYNC_RECONNECT_REQUIRED','DATA_SYNC_PERMISSION_MISSING'])test('a dataset authorization problem is visible even behind preserved-plan overall status: '+code,()=>{
 const s=status(),p=s.providers[0];p.last_run.datasets[2].error_code=code;
 const verified=c.readStatus(s).providers[0];assert.equal(c.connectionAttention(verified),true);
 assert.equal(c.providerState(verified),code==='DATA_SYNC_RECONNECT_REQUIRED'?'Újracsatlakozás szükséges':'Hiányzó adathozzáférés');
});
test('a real backend-produced pending receipt verifies with its original partial result and stable bytes',async()=>{
 const f=JSON.parse(readFileSync(new URL('./fixtures/sync-details-continuation.json',import.meta.url))),before=structuredClone(f);
 const receipt=await c.readReceipt(f.receipt,{version:'data-sync-pending-v0.1',owner:f.receipt.athlete_id,body:JSON.stringify(f.body)});
 assert.equal(receipt.run.state,'partial');assert.equal(c.continuationOnly(receipt.run),true);
 assert.equal(c.attention(c.readStatus(f.status).providers[0]),false);assert.deepEqual(f,before);
});
