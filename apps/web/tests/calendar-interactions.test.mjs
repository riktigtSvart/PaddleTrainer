import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/calendar-interactions.json',import.meta.url)));
const c=load('src/lib/calendar/contracts.ts'),s=load('src/lib/calendar/constraints.ts');
const forms=load('src/lib/calendar/constraint-forms.ts'),drag=load('src/lib/calendar/slot-transform.ts');
const history=load('src/lib/calendar/editor-history.ts');
const Grid=load('src/components/calendar/time-grid.tsx').default;
const clone=v=>structuredClone(v),before=fixture.constraints.before,owner=before.athlete_id;
const event=forms.constraintEvents(before).find(e=>e.date==='2026-10-29');

for(const [mode,delta,days,wanted] of [
    ['move',5,0,{date:'2026-10-29',start_time:'08:05',end_time:'17:05',ends_next_day:false}],
    ['start',30,0,{date:'2026-10-29',start_time:'08:30',end_time:'17:00',ends_next_day:false}],
    ['end',-30,0,{date:'2026-10-29',start_time:'08:00',end_time:'16:30',ends_next_day:false}],
    ['move',0,1,{date:'2026-10-30',start_time:'08:00',end_time:'17:00',ends_next_day:false}],
    ['move',-600,0,{date:'2026-10-28',start_time:'22:00',end_time:'07:00',ends_next_day:true}],
])test('civil drag proposal '+mode+' '+delta+' '+days,()=>{
    const original=clone(event);assert.deepEqual(drag.transformSlot(event,delta,days,mode),wanted);assert.deepEqual(event,original);
});
test('measured DOM height controls five-minute snapping at different viewport scales',()=>{
    assert.equal(drag.minuteDelta(110,100,960,16),10);
    assert.equal(drag.minuteDelta(110,100,480,16),20);
    assert.equal(drag.minuteDelta(102,100,480,16),5);
    assert.equal(drag.minuteDelta(100,100,480,16),0);
});
test('off-grid original minutes survive dragging and overnight endpoints stay explicit',()=>{
    const e=clone(event);e.occurrence.details.start_time='23:02';e.occurrence.details.end_time='00:02';e.occurrence.details.ends_next_day=true;
    assert.deepEqual(drag.transformSlot(e,5,0,'move'),{date:e.date,start_time:'23:07',end_time:'00:07',ends_next_day:true});
});
for(const args of [[-600,0,'end'],[600,0,'start'],[1000,0,'end'],[1,0,'move'],[0,0.5,'move']])
    test('invalid interval or unsnapped delta is rejected '+args.join('/'),()=>assert.throws(()=>drag.transformSlot(event,...args)));
test('training plans and measured sessions never become draggable slots',()=>{
    for(const e of c.eventsFrom(fixture.feed).filter(e=>['planned','session'].includes(e.kind))){assert.equal(drag.canTransform(e),false);assert.throws(()=>drag.transformSlot(e,5,0,'move'));}
});
test('weekly cross-day move skips only its original occurrence and adds one dated replacement',()=>{
    const ctx=clone(before),source=clone(event),base=clone(ctx.data);
    const d=forms.draftFor(source.date,source);d.date='2026-10-30';d.details.start_time='09:00';d.details.end_time='18:00';
    const value=forms.prepareEdit(ctx,d,source,false);const data=value.proposal.data;
    assert.deepEqual(data.rules[0],base.rules[0]);
    assert(data.exceptions.some(e=>e.date===source.date&&e.rule_id===source.entityId&&e.replacement===null));
    const added=data.rules.find(r=>r.id!==source.entityId);assert.equal(added.repeat,'once');assert.equal(added.start_date,d.date);assert.equal(added.end_date,d.date);
    assert.deepEqual(ctx.data,base);
    d.scope='future';assert.throws(()=>forms.prepareEdit(ctx,d,source,false));
});
test('moving an existing weekly override retains every other exception',()=>{
    const ctx=clone(before);ctx.data.exceptions.push({rule_id:event.entityId,date:'2026-11-03',replacement:null});
    const d=forms.draftFor(event.date,event);d.date='2026-10-30';
    const data=forms.prepareEdit(ctx,d,event,false).proposal.data;
    assert(data.exceptions.some(e=>e.date==='2026-11-03'&&e.replacement===null));
});
test('legacy cross-day move preserves resources, every other day and source data; daily budgets never increase',()=>{
    const ctx=fixture.availability.before,calendar=clone(ctx.availability.artifact.proposal.data);
    const e=c.eventsFrom(fixture.feed).find(e=>e.kind==='availability'&&e.date==='2026-10-26'&&e.window.key==='morning');
    const d=forms.draftFor(e.date,e);d.date='2026-10-27';
    const changed=forms.legacyChange(calendar,e,d,false);
    assert.deepEqual(calendar,ctx.availability.artifact.proposal.data);
    assert.equal(changed.days[0].max_total_minutes,60);assert.equal(changed.days[0].windows.length,1);
    assert.deepEqual(changed.days[1].windows[0],calendar.days[0].windows[0]);assert.equal(changed.days[1].max_total_minutes,null);
    assert.deepEqual(changed.days.slice(2),calendar.days.slice(2));
    calendar.days[1].status='unavailable';assert.throws(()=>forms.legacyChange(calendar,e,d,false));
});
for(const operation of ['constraints','availability'])test('verified '+operation+' undo survives storage and creates a new CAS request',async()=>{
    const f=fixture[operation];const ctx=await s.readScheduleContext(f.after);
    const pending={version:'calendar-editor-pending-v0.1',operation,owner,body:JSON.stringify(f.receipt.artifact.proposal)};
    const recovery=await history.readRecovery(JSON.stringify(history.withHistory(pending,f.before,false)));
    assert.equal(recovery.body,pending.body);
    const u=await history.makeUndo(recovery,f.receipt),restored=await history.readUndo(JSON.stringify(u));
    assert(history.undoAvailable(restored,ctx));
    const prepared=history.prepareUndo(ctx,restored),body=JSON.parse(prepared.pending.body);
    assert.notEqual(body.request_id,f.receipt.artifact.proposal.request_id);
    assert.deepEqual(body.previous_reference,{artifact_id:f.receipt.artifact.artifact_id,content_hash:f.receipt.artifact.content_hash});
    assert.deepEqual(body.data,operation==='constraints'?f.before.data:f.before.availability.artifact.proposal.data);
    assert.equal(history.undoAvailable(restored,await s.readScheduleContext(f.undo)),false);
    assert.throws(()=>history.prepareUndo({...ctx,athlete_id:crypto.randomUUID()},restored));
    assert.equal(await history.makeUndo(history.withHistory(prepared.pending,ctx,true),f.undo_receipt),null);
});
test('first constraint save can be undone to an explicit empty declaration',async()=>{
    const receipt=before.saved;
    const u=await history.readUndo(JSON.stringify({version:'calendar-undo-v0.1',owner,operation:'constraints',before:null,after:receipt}));
    const p=history.prepareUndo(before,u);
    assert.deepEqual(JSON.parse(p.pending.body).data,{timezone_name:before.timezone_name,rules:[],exceptions:[]});
});
for(const [name,mutate] of [
    ['edited before',u=>{u.before.artifact.proposal.data.rules[0].details.title='Tampered';}],
    ['edited after',u=>{u.after.artifact.proposal.data.rules[0].details.title='Tampered';}],
    ['wrong owner',u=>{u.owner=crypto.randomUUID();}],
    ['wrong operation',u=>{u.operation='availability';}],
])test('undo rejects '+name,async()=>{
    const u={version:'calendar-undo-v0.1',owner,operation:'constraints',before:clone(before.saved),after:clone(fixture.constraints.receipt)};mutate(u);await assert.rejects(history.readUndo(JSON.stringify(u)));
});
test('old pending requests remain byte-stable and never acquire invented undo history',async()=>{
    const p={version:'calendar-editor-pending-v0.1',owner,operation:'constraints',body:JSON.stringify(fixture.constraints.receipt.artifact.proposal)};
    const restored=await history.readRecovery(JSON.stringify(p));assert.deepEqual(restored,p);assert.equal(await history.makeUndo(restored,fixture.constraints.receipt),null);
});
test('clock-grid offers separate accessible resize controls only for real civil slot edges',()=>{
    const feed=fixture.feed,events=[event,...c.eventsFrom(feed).filter(e=>e.kind==='session')];
    const html=renderToStaticMarkup(React.createElement(Grid,{feed,events,days:c.dayList(feed.start_date,feed.end_date),fullDay:false,open(){},selectDay(){},expandHours(){},onTransform(){}}));
    assert.match(html,/Kezdés szerkesztése: Munka/);assert.match(html,/Befejezés szerkesztése: Munka/);
    assert.equal((html.match(/pt-slot-shell/g)||[]).length,1);
});
