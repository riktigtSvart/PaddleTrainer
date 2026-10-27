import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';
const contracts=load('src/lib/data-connections/contracts.ts');
const client=load('src/lib/data-connections/client.ts');
const analysis=load('src/lib/session-analysis/contracts.ts');
const {SessionDetails}=load('src/components/session-analysis/workspace.tsx');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/session-details-sync.json',import.meta.url)));
const clone=x=>structuredClone(x);
const pending={version:'data-sync-pending-v0.1',owner:fixture.receipt.athlete_id,body:JSON.stringify(fixture.body)};

test('actual full sync receipt and status support three explicit provider datasets',async()=>{
 assert.deepEqual(contracts.readBody(fixture.body).datasets,['sessions','targets','session_details']);
 assert.deepEqual(contracts.readStatus(fixture.status),fixture.status);
 assert.deepEqual(await contracts.readReceipt(fixture.receipt,pending),fixture.receipt);
});
test('the same sync operation turns a source without charts into real stored sample series',()=>{
 const before=analysis.readAnalysis(fixture.before,fixture.before.session.id);
 const after=analysis.readAnalysis(fixture.after,fixture.after.session.id);
 assert.equal(before.samples.series.length,0);assert.equal(after.samples.series.length,2);
 const oldHTML=renderToStaticMarkup(React.createElement(SessionDetails,{data:before}));
 const newHTML=renderToStaticMarkup(React.createElement(SessionDetails,{data:after}));
 assert.doesNotMatch(oldHTML,/<svg/);assert.match(newHTML,/<svg/);
 assert.match(newHTML,/Pulzus/);assert.match(newHTML,/Sebesség/);
 assert.equal(after.session.avg_power,0);
});
test('new status capabilities do not append datasets to a stored older pending request',()=>{
 const old=clone(fixture.body);old.datasets=['sessions','targets'];
 const body=JSON.stringify(old),envelope={...pending,body};
 assert.equal(contracts.readPending(JSON.stringify(envelope)).body,body);
 assert.deepEqual(contracts.readBody(JSON.parse(body)).datasets,['sessions','targets']);
});
test('source detail counts report actual sample presence separately from completed fetches',()=>{
 const d=fixture.receipt.run.datasets.find(d=>d.dataset==='session_details');
 assert.match(client.resultCounts(d),/Lekért részletek: 1/);
 assert.match(client.resultDetails(d).join(' '),/mintasorral: 1 · mintasor nélkül: 0/);
 const missing={...clone(d),details:{...d.details,with_samples:0,without_samples:1}};
 assert.match(client.resultDetails(missing).join(' '),/mintasorral: 0 · mintasor nélkül: 1/);
});
for(const [name,mutate]of[
 ['inconsistent pending total',d=>{d.details.pending_sessions++;}],
 ['fabricated sample availability',d=>{d.details.with_samples++;}],
 ['boolean count',d=>{d.details.fetched_sessions=true;}],
 ['negative count',d=>{d.details.processed_days=-1;}],
 ['unknown omission',d=>{delete d.details.without_samples;}],
])test('source report rejects '+name,()=>{
 const status=clone(fixture.status);const d=status.providers[0].last_run.datasets.find(d=>d.dataset==='session_details');mutate(d);
 assert.throws(()=>contracts.readStatus(status));
});
test('a pending batch remains a warning and explains how to continue',()=>{
 const run=clone(fixture.receipt.run),d=run.datasets.find(d=>d.dataset==='session_details');
 d.skipped=2;d.error_code='DATA_SYNC_DETAILS_PENDING';d.skip_reasons={details_batch_pending:2};
 d.details.pending_sessions=2;d.details.pending_days=2;d.details.requested_sessions+=2;
 run.state='partial';run.error_code=d.error_code;
 assert.equal(contracts.preservedPlansOnly(run),false);
 assert.match(client.errorText(run.error_code),/Újabb szinkronizálással folytatható/);
 assert.match(client.resultDetails(d).join(' '),/További átvételre vár: 2/);
});
test('source conflicts and omitted provider records have distinct explanations',()=>{
 assert.match(client.errorText('DATA_SYNC_DETAILS_SOURCE_CONFLICT'),/eltér/);
 assert.match(client.errorText('DATA_SYNC_DETAILS_NOT_RETURNED'),/nem adta vissza/);
});
