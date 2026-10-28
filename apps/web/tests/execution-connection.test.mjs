import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';
const c=load('src/lib/session-analysis/execution-connection.ts'),{forwardCalendar}=load('src/lib/calendar/proxy.ts');
const sample=JSON.parse(readFileSync(new URL('./fixtures/execution-connection.json',import.meta.url),'utf8'));
const owner=sample.preview.athlete_id,session=sample.preview.session_id;
const pending={owner,session,body:JSON.stringify(sample.proposal)};
test('Python preview and committed receipt verify in JavaScript',async()=>{
 const v=await c.readExecutionPreview(sample.preview,owner,session);assert.equal(v.plan_adoption_required,true);
 assert.equal((await c.readConnectionReceipt(sample.receipt,pending)).committed,true);
 assert.equal(sample.receipt.artifact.phase_alignment_verified,false);
});
test('pending metadata is owner/session bound and preserves exact proposal bytes',()=>{
 assert.deepEqual(c.readConnectionPending(JSON.stringify(pending),owner,session),pending);
 assert.throws(()=>c.readConnectionPending(JSON.stringify(pending),'other',session));
 assert.throws(()=>c.readConnectionPending(JSON.stringify({...pending,body:'{}'}),owner,session));
});
for(const [name,change] of [['owner',a=>a.athlete_id='other'],['content',a=>a.plan_title='changed'],['phase authority',a=>a.phase_alignment_verified=true],['history claim',a=>a.plan_content_at_execution_status='verified']])
 test(`preview refuses altered ${name}`,async()=>{const v=structuredClone(sample.preview);change(v);await assert.rejects(c.readExecutionPreview(v,owner,session));});
for(const [name,change] of [['uncommitted',x=>x.committed=false],['phase claim',x=>x.artifact.phase_alignment_verified=true],['other session',x=>x.artifact.session_id='other'],['other proposal',x=>x.artifact.proposal.request_id=crypto.randomUUID()]])
 test(`receipt refuses ${name}`,async()=>{const x=structuredClone(sample.receipt);change(x);await assert.rejects(c.readConnectionReceipt(x,pending));});
test('transport retries send identical reviewed bytes and no editable source data',async()=>{
 const old=globalThis.fetch,calls=[];globalThis.fetch=async(url,options)=>{calls.push([url,options]);return Response.json(sample.receipt);};
 try{await c.sendExecutionConnection(pending);await c.sendExecutionConnection(pending);assert.ok(calls.every(x=>x[1].body===pending.body));assert.equal(Object.keys(JSON.parse(pending.body)).length,4);}finally{globalThis.fetch=old;}
});
for(const method of ['GET','POST'])test(`closed proxy admits execution connection ${method}`,async()=>{
 const route=`sessions/${session}/execution-connection`;let calls=0;
 const reply=await forwardCalendar(new Request('http://localhost:3000/api/calendar/'+route,{method,headers:{Origin:'http://localhost:3000','Content-Type':'application/json'},...(method==='POST'?{body:pending.body}:{})}),route.split('/'),'http://127.0.0.1:8000',async()=>{calls++;return Response.json({});});
 assert.equal(reply.status,200);assert.equal(calls,1);
});
test('proxy rejects unsupported execution routes, methods, query and forged origin',async()=>{
 const route=`sessions/${session}/execution-connection`,send=()=>{throw Error('must not send');};
 for(const [url,path,options,status] of [
  ['http://localhost:3000/api/calendar/'+route+'/extra',(route+'/extra').split('/'),{},404],
  ['http://localhost:3000/api/calendar/'+route,route.split('/'),{method:'DELETE'},405],
  ['http://localhost:3000/api/calendar/'+route+'?plan=other',route.split('/'),{},422],
  ['http://localhost:3000/api/calendar/'+route,route.split('/'),{method:'POST',headers:{Origin:'http://evil.test','Content-Type':'application/json'},body:pending.body},403],
 ])assert.equal((await forwardCalendar(new Request(url,options),path,'http://api',send)).status,status);
});
