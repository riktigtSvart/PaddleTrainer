import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';
const f=load('src/lib/session-analysis/feedback.ts');
const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const sample=JSON.parse(readFileSync(new URL('./fixtures/session-feedback.json',import.meta.url),'utf8'));
const {owner,session}=sample;
const copy=x=>structuredClone(x);

test('Python durable artifacts verify in the browser, including decimals, zero, null and Unicode',async()=>{
 const c=await f.readContext(sample.context,owner,session);
 assert.equal(c.current.IMMEDIATE.proposal.fatigue,0);
 assert.equal(c.current.IMMEDIATE.proposal.soreness,null);
 assert.equal(c.current.IMMEDIATE.proposal.rpe,5.5);
 assert.equal(c.current.NEXT_MORNING.revision,1);
});
test('score entry keeps unanswered distinct from zero',()=>{
 for(const [input,value] of [['',null],['0',0],['0,5',.5],['10',10],['5.5',5.5]])assert.equal(f.score(input),value);
 for(const input of ['NaN','Infinity','-1','11','1e0','1.23','  '])assert.throws(()=>f.score(input));
});
test('pending request restores identical bytes, bound to owner and session',()=>{
 const p={owner,session,body:JSON.stringify(sample.receipt.artifact.proposal)};
 assert.deepEqual(f.readPending(JSON.stringify(p),owner,session),p);
 assert.throws(()=>f.readPending(JSON.stringify(p),'other',session));
 assert.throws(()=>f.readPending(JSON.stringify(p),owner,'other'));
});
test('altered, foreign, unknown-schema and broken-chain replies are rejected',async()=>{
 for(const mutate of [a=>{a.athlete_id='other';},a=>{a.schema_version='future';},a=>{a.proposal.rpe=9;},a=>{a.planning_authorized=true;}]) {
  const a=copy(sample.receipt.artifact);mutate(a);await assert.rejects(f.artifact(a,owner,session));
 }
 const c=copy(sample.context);c.history=[];await assert.rejects(f.readContext(c,owner,session));
});
test('a matching committed receipt alone resolves the POST; retries preserve exact bytes',async()=>{
 const original=globalThis.fetch, calls=[];
 const p={owner,session,body:JSON.stringify(sample.receipt.artifact.proposal)};
 globalThis.fetch=async(url,options)=>{calls.push([url,options]);return Response.json(sample.receipt);};
 try {
  await f.sendFeedback(p);await f.sendFeedback(p);
  assert.equal(calls.length,2);assert.ok(calls.every(x=>x[1].body===p.body));
  globalThis.fetch=async()=>Response.json({...sample.receipt,committed:false});await assert.rejects(f.sendFeedback(p));
  globalThis.fetch=async()=>Response.json(sample.next_receipt);await assert.rejects(f.sendFeedback(p));
 }finally{globalThis.fetch=original;}
});
for(const method of ['GET','POST'])test(`closed calendar proxy allows owned feedback ${method} without credentials`,async()=>{
 const path=`sessions/${session}/feedback`, body=JSON.stringify(sample.receipt.artifact.proposal);
 let call;
 const r=await forwardCalendar(new Request('http://localhost:3000/api/calendar/'+path,{method,headers:{Origin:'http://localhost:3000','Content-Type':'application/json',Cookie:'never-forward'},...(method==='POST'?{body}:{})}),path.split('/'),'http://127.0.0.1:8000',async(url,options)=>{call={url,options};return Response.json({ok:true});});
 assert.equal(r.status,200);assert.equal(call.options.headers.Cookie,undefined);
 assert.equal(call.url.pathname,'/api/v1/planning/calendar/'+path);
 if(method==='POST')assert.equal(call.options.body,body);
});
for(const [suffix,method,status] of [['/extra','GET',404],['?x=1','GET',422],['','DELETE',405]])test(`feedback proxy rejects ${method} ${suffix}`,async()=>{
 const route=`sessions/${session}/feedback${suffix.startsWith('/')?suffix:''}`;
 const r=await forwardCalendar(new Request('http://localhost:3000/api/calendar/'+route+(suffix.startsWith('?')?suffix:''),{method}),route.split('/'),'http://127.0.0.1:8000',()=>{throw Error('must not send');});
 assert.equal(r.status,status);
});
