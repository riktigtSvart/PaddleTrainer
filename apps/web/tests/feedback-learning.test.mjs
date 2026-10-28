import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const learning=load('src/lib/session-analysis/learning.ts'),{forwardCalendar}=load('src/lib/calendar/proxy.ts');
const data=JSON.parse(readFileSync(new URL('./fixtures/feedback-learning.json',import.meta.url),'utf8'));
const {athlete_id:owner,session_id:session}=data;

test('Python learning selection verifies in JS with source revision, delay and zero/null',async()=>{
 const x=await learning.readLearning(data,owner,session);assert.equal(x.items[0].revision,1);
 const m=Object.fromEntries(x.items[0].measurements.map(x=>[x.metric_key,x]));
 assert.equal(m.self_reported_fatigue_score.value,0);assert.equal(m.self_reported_soreness_score.value,null);
 assert.equal(x.model_updated,false);
});
for(const [name,change] of [
 ['foreign owner',x=>x.athlete_id='other'],['future schema',x=>x.schema_version='future'],
 ['changed score',x=>x.items[0].measurements[0].value=9],['planning permission',x=>x.planning_authorized=true],
 ['model update claim',x=>x.model_updated=true],['duplicate timing',x=>x.items.push(x.items[0])],
 ['false ready receipt',x=>x.items[0].state='ready'],['unknown state',x=>x.items[0].state='trained'],
])test(`reject ${name}`,async()=>{const x=structuredClone(data);change(x);await assert.rejects(learning.readLearning(x,owner,session));});
test('explicit learning refresh uses identical empty POST and validates the response',async()=>{
 const original=globalThis.fetch,calls=[];globalThis.fetch=async(url,options)=>{calls.push([url,options]);return Response.json(data);};
 try {await learning.loadLearning(owner,session,true);await learning.loadLearning(owner,session,true);assert.ok(calls.every(x=>x[1].body==='{}' && x[1].method==='POST'));}
 finally{globalThis.fetch=original;}
});
for(const method of ['GET','POST'])test(`learning ${method} passes only the exact owned route`,async()=>{
 const route=`sessions/${session}/learning`;let call;
 const reply=await forwardCalendar(new Request('http://localhost:3000/api/calendar/'+route,{method,headers:{Origin:'http://localhost:3000','Content-Type':'application/json'},...(method==='POST'?{body:'{}'}:{})}),route.split('/'),'http://127.0.0.1:8000',async(url,options)=>{call={url,options};return Response.json(data);});
 assert.equal(reply.status,200);assert.equal(call.url.pathname,'/api/v1/planning/calendar/'+route);
});
test('learning inputs route is read-only and allows only unique date bounds',async()=>{
 let calls=0;const send=async()=>{calls++;return Response.json({});};
 assert.equal((await forwardCalendar(new Request('http://local/api/calendar/learning-inputs?start_date=2026-10-01&end_date=2026-10-28'),['learning-inputs'],'http://api',send)).status,200);
 assert.equal((await forwardCalendar(new Request('http://local/api/calendar/learning-inputs',{method:'POST'}),['learning-inputs'],'http://api',send)).status,405);
 assert.equal((await forwardCalendar(new Request('http://local/api/calendar/learning-inputs?start_date=x&start_date=y'),['learning-inputs'],'http://api',send)).status,422);assert.equal(calls,1);
});
test('learning panel renders a stable accessible summary',()=>{
 const {LearningStatus}=load('src/components/session-analysis/learning-status.tsx');
 const html=renderToStaticMarkup(React.createElement(LearningStatus,{owner,session,revisionKey:'empty'}));
 assert.match(html,/Tanulási kapcsolat/);assert.match(html,/Kapcsolat ellenőrzése/);assert.doesNotMatch(html,/Bekötve a személyes/);
});
