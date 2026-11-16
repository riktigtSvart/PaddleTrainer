import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';
const {withConnectionDeadline}=load('src/lib/data-connections/deadline.ts');
const {loadStatus,sendSync,findSync,ConnectionError,errorText}=load('src/lib/data-connections/client.ts');
const {forwardConnections}=load('src/lib/data-connections/proxy.ts');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/data-sync-receipt.json',import.meta.url)));
const pending={version:'data-sync-pending-v0.1',owner:fixture.receipt.athlete_id,body:JSON.stringify(fixture.receipt.start.proposal,null,2)};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const timeout=e=>e instanceof ConnectionError&&e.status===504&&e.code==='DATA_SYNC_API_TIMEOUT';

test('deadline rejects even when the transport ignores abort, and a late response cannot finish the expired wait',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let signal,reply;
  const waiting=withConnectionDeadline(s=>{signal=s;return new Promise(r=>reply=r);},100);
  const rejected=assert.rejects(waiting,e=>e.name==='TimeoutError');
  await flush();t.mock.timers.tick(101);await rejected;
  assert.equal(signal.aborted,true);reply('late success');await flush();
});
test('successful exchange clears its deadline without aborting a finished response',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});let signal;
  assert.equal(await withConnectionDeadline(async s=>{signal=s;return 'finished';},100),'finished');
  t.mock.timers.tick(200);assert.equal(signal.aborted,false);
});
test('parent cancellation stops a background wait without claiming a timeout',async()=>{
  const parent=new AbortController();let child;
  const waiting=withConnectionDeadline(s=>{child=s;return new Promise(()=>{});},1000,parent.signal);
  const rejected=assert.rejects(waiting,e=>e.name==='AbortError');await flush();parent.abort();await rejected;
  assert.equal(child.aborted,true);
});
test('already-cancelled background work never calls its transport',async()=>{
  const parent=new AbortController();parent.abort();let calls=0;
  await assert.rejects(()=>withConnectionDeadline(async()=>{calls++;},1000,parent.signal),e=>e.name==='AbortError');assert.equal(calls,0);
});
for(const operation of ['status','receipt'])test(`${operation} has a bounded browser-side read with one request`,async t=>{
  t.mock.timers.enable({apis:['setTimeout']});const original=globalThis.fetch;let calls=0,signal;
  globalThis.fetch=async(_url,init)=>{calls++;signal=init.signal;return new Promise(()=>{});};
  try {
    const waiting=operation==='status'?loadStatus():findSync(pending);
    const rejected=assert.rejects(waiting,timeout);await flush();t.mock.timers.tick(35001);await rejected;
    assert.equal(calls,1);assert.equal(signal.aborted,true);
  } finally {globalThis.fetch=original;}
});
test('a stalled JSON body after successful headers is covered by the same deadline',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response(new ReadableStream({start(){}}),{headers:{'Content-Type':'application/json'}});
  try {
    const waiting=loadStatus(),rejected=assert.rejects(waiting,timeout);await flush();t.mock.timers.tick(35001);await rejected;
  } finally {globalThis.fetch=original;}
});
test('expired sync preserves the exact original request and never resends the POST automatically',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});const original=globalThis.fetch,copy=structuredClone(pending);let calls=0,sent;
  globalThis.fetch=async(_url,init)=>{calls++;sent=init;return new Promise(()=>{});};
  try {
    const waiting=sendSync(pending),rejected=assert.rejects(waiting,timeout);await flush();t.mock.timers.tick(220001);await rejected;
    assert.equal(calls,1);assert.equal(sent.body,copy.body);assert.deepEqual(pending,copy);assert.equal(sent.signal.aborted,true);
  } finally {globalThis.fetch=original;}
});
test('a verified receipt read can cancel the original POST wait without another import',async()=>{
  const original=globalThis.fetch,parent=new AbortController();let posts=0,reads=0;
  globalThis.fetch=async(_url,init)=>{
    if(init.method==='POST'){posts++;return new Promise(()=>{});}
    reads++;return Response.json(fixture.receipt);
  };
  try {
    const waiting=sendSync(pending,parent.signal),stopped=assert.rejects(waiting,e=>e.name==='AbortError');
    await flush();assert.equal((await findSync(pending)).run.state,'succeeded');parent.abort();await stopped;
    assert.equal(posts,1);assert.equal(reads,1);
  } finally {globalThis.fetch=original;}
});

const request=()=>new Request('https://app.invalid/api/data-connections/status');
for(const stage of ['headers','body'])test(`proxy deadline includes upstream ${stage} and returns a distinct 504`,async t=>{
  t.mock.timers.enable({apis:['setTimeout']});let calls=0,signal;
  const waiting=forwardConnections(request(),['status'],'http://api.invalid',async(_url,init)=>{
    calls++;signal=init.signal;
    return stage==='headers'?new Promise(()=>{}):new Response(new ReadableStream({start(){}}),{headers:{'Content-Type':'application/json'}});
  });
  await flush();t.mock.timers.tick(30001);
  const response=await waiting;assert.equal(response.status,504);assert.equal((await response.json()).detail.code,'DATA_SYNC_API_TIMEOUT');
  assert.equal(calls,1);assert.equal(signal.aborted,true);
});
test('proxy keeps unavailable server separate from timeout and never exposes its exception text',async()=>{
  const response=await forwardConnections(request(),['status'],'http://api.invalid',async()=>{throw Error('private backend path');});
  assert.equal(response.status,502);assert.equal((await response.json()).detail.code,'DATA_SYNC_API_UNAVAILABLE');
  assert.match(errorText('DATA_SYNC_API_TIMEOUT'),/mentett kérés/);
  assert.match(errorText('DATA_SYNC_API_UNAVAILABLE'),/nem érhető el/);
});
