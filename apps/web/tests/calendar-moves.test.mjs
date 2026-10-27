import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const m=load('src/lib/calendar/moves.ts'),c=load('src/lib/calendar/contracts.ts'),d=load('src/lib/calendar/slot-transform.ts');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/calendar-moves.json',import.meta.url)));
const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const clone=x=>structuredClone(x),owner=fixture.context.athlete_id,pid=fixture.proposal.plan_id;
test('actual backend context, review and committed receipt share exact hashes',async()=>{
 assert.deepEqual(m.readMoveContext(fixture.context,owner,pid),fixture.context);
 assert.deepEqual(await m.readMoveReview(fixture.preview,fixture.proposal,owner),fixture.preview);
 assert.deepEqual(await m.readMoveReceipt(fixture.receipt,owner,JSON.stringify({proposal:fixture.proposal,review_hash:fixture.preview.review_hash})),fixture.receipt);
});
for(const [name,change] of [
 ['foreign owner',x=>{x.artifact.athlete_id='22222222-2222-4222-8222-222222222222';}],
 ['uncommitted',x=>{x.committed=false;}],['writeback claim',x=>{x.provider_writeback=true;}],
 ['changed time',x=>{x.artifact.after.planned_start_time='2026-10-24T09:00:00Z';}],
 ['dose claim',x=>{x.artifact.training_dose_changed=true;}],
])test('receipt rejects '+name,async()=>{const r=clone(fixture.receipt);change(r);await assert.rejects(m.readMoveReceipt(r,owner));});
test('rehashing cannot make a receipt with a different destination match its proposal',async()=>{
 const r=clone(fixture.receipt);r.artifact.after.planned_start_time='2026-10-24T09:00:00Z';delete r.artifact.content_hash;r.artifact.content_hash=await sha(r.artifact);
 await assert.rejects(m.readMoveReceipt(r,owner));
});
test('unknown response authority and altered preview conflicts are not accepted',async()=>{
 const v=clone(fixture.preview);v.conflicts.push({plan_id:pid,plan_title:'x',occurrence_key:'x',constraint_title:'x',date:'2026-10-24',severity:'fixed',code:'WORKOUT_OVERLAP'});
 await assert.rejects(m.readMoveReview(v,fixture.proposal,owner));
});
test('pending move preserves owner, exact body and explicit undo marker',()=>{
 const body=JSON.stringify({proposal:fixture.proposal,review_hash:fixture.preview.review_hash});
 const p={version:'calendar-move-pending-v0.1',owner,body,undo:false};assert.deepEqual(m.readMovePending(JSON.stringify(p)),p);
 assert.throws(()=>m.readMovePending(JSON.stringify({...p,body:JSON.stringify({proposal:fixture.proposal,review_hash:'bad'})})));
});
test('move form rejects dose fields, boolean fold and fabricated zero time',()=>{
 for(const patch of [{duration_sec:0},{start_fold:true},{start_time:'25:00'},{start_time:null,start_fold:1}])assert.throws(()=>m.readMoveProposal({...fixture.proposal,...patch}));
});
test('eligible plan body drags by civil date with seconds preserved and duration retained',()=>{
 const feed=c.readFeed(fixture.feed),e=c.eventsFrom(feed).find(e=>e.entityId===pid),original=clone(e);
 assert.equal(d.canMoveTraining(e),true);assert.equal(d.canTransform(e),false);
 const moved=d.moveTraining({...e,start:'2026-10-24T21:58:45Z',end:'2026-10-24T22:18:45Z'},5,1,'Europe/Budapest');
 assert.deepEqual(moved,{date:'2026-10-26',start_time:'00:03',end_time:'00:23',ends_next_day:false,start_seconds:45});assert.deepEqual(e,original);
});
test('actual, blocked, zero or missing duration and legacy feeds never gain plan dragging',()=>{
 const e=c.eventsFrom(c.readFeed(fixture.feed)).find(e=>e.entityId===pid);
 for(const patch of [{kind:'session'},{reschedule:undefined},{reschedule:{allowed:false}},{end:null},{end:e.start}])assert.equal(d.canMoveTraining({...e,...patch}),false);
});
test('planned draggable card keeps its lane and has no prescription resize handles',()=>{
 const feed=c.readFeed(fixture.feed),events=c.eventsFrom(feed),Grid=load('src/components/calendar/time-grid.tsx').default;
 const html=renderToStaticMarkup(React.createElement(Grid,{feed,events,days:['2026-10-24'],fullDay:true,open:()=>{},selectDay:()=>{},expandHours:()=>{},onTransform:()=>{}}));
 assert.match(html,/pt-slot-shell/);assert.doesNotMatch(html,/pt-slot-handle/);assert.match(html,/Separate plan/);
});
for(const [method,path,status] of [['GET','moves/'+pid,200],['POST','moves',200],['POST','moves/preview',200],['GET','moves',405],['GET','moves/preview',405],['POST','moves/'+pid,405],['GET','moves/evil',404],['DELETE','moves',405]])
 test('closed proxy move route '+method+' '+path,async()=>{
 let calls=0;const body=method==='POST'?'{}':undefined;
 const request=new Request('http://localhost:3000/api/calendar/'+path,{method,body,headers:{Origin:'http://localhost:3000','Content-Type':'application/json'}});
 const response=await forwardCalendar(request,path.split('/'),'http://localhost:8000',async(url,init)=>{calls++;assert.equal(new URL(url).pathname,'/api/v1/planning/calendar/'+path);if(body)assert.equal(init.body,body);return Response.json({ok:true});});
 assert.equal(response.status,status);assert.equal(calls,status===200?1:0);
 });
test('context query cannot become an arbitrary fetch target',async()=>{
 const request=new Request('http://localhost:3000/api/calendar/moves/'+pid+'?url=http://evil.invalid');
 const response=await forwardCalendar(request,['moves',pid],'http://localhost:8000',()=>{throw Error('must not fetch');});assert.equal(response.status,422);
});
