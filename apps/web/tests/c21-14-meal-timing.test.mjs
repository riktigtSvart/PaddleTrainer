import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const fixture=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-14-meal-timing.json.gz',import.meta.url))));
const c=fixture.calendar,owner=c.athlete_id,range={start:c.start_date,end:c.end_date};
const timing=load('src/lib/nutrition/timing.ts'),calendar=load('src/lib/nutrition/calendar.ts'),menus=load('src/lib/nutrition/contracts.ts'),journal=load('src/lib/nutrition/journal.ts'),{sha}=load('src/lib/planning-cycles/contracts.ts');
async function rehash(v){delete v.content_hash;v.content_hash=await sha(v);}

test('real menu and calendar APIs agree on automatic clocks and the dinner shifted after the actual owned run',async()=>{
 const v=await calendar.readCalendar(c,owner,range),m=await menus.readNutritionContext(fixture.menu_context,owner),data=journal.blankJournal();
 for(const day of v.result.days)for(const meal of day.meals)assert.equal(timing.mealTiming(m,data,meal,day.meals.map(x=>x.slot)).time,meal.planned_time);
 assert.equal(v.result.days[0].meals.find(m=>m.slot==='dinner').planned_time,'20:15:00');
 assert.equal(v.result.days[0].meals.find(m=>m.slot==='breakfast').planned_time,'07:30:00');
 assert.equal(v.result.actual_entries.length,0);assert.equal(v.journal.saved,null);
});

for(const [name,change] of [
 ['another owner',v=>v.timing_context.athlete_id='00000000-0000-0000-0000-000000000001'],
 ['another range',v=>v.timing_context.start_date='2026-11-17'],
 ['future rules',v=>v.timing_context.rules_version='future'],
 ['missing context',v=>delete v.timing_context],
 ['negative activity',v=>v.timing_context.activities[0].start_second=-1],
 ['reversed activity',v=>v.timing_context.activities[0].end_second=v.timing_context.activities[0].start_second],
 ['outside date',v=>v.timing_context.activities[0].date='2026-11-25'],
 ['duplicate activity',v=>v.timing_context.activities.push(structuredClone(v.timing_context.activities[0]))],
 ['invented clock',v=>v.result.days[0].meals[0].planned_time='01:00:00'],
 ['invented origin',v=>v.result.days[0].meals[0].timing.origin='manual'],
 ['invented eating',v=>v.result.days[0].meals[0].status='eaten'],
 ['downgraded rule proof',v=>v.schema_version='nutrition-calendar-v0.1'],
])test('rehashed automatic calendar rejects '+name,async()=>{const v=structuredClone(c);change(v);await rehash(v);await assert.rejects(calendar.readCalendar(v,owner,range));});

test('old immutable responses retain unknown clocks rather than receiving guessed evidence',async()=>{
 const old=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-13-nutrition-calendar.json.gz',import.meta.url))));
 const parsed=await calendar.readCalendar(old,old.athlete_id,{start:old.start_date,end:old.end_date});
 assert.equal(parsed.result.days[0].meals[0].planned_time,null);assert.equal(parsed.timing_context,undefined);
});

test('manual seconds and a deliberately empty clock survive workout conflicts; resetting restores the automatic suggestion',()=>{
 const d=journal.blankJournal();d.timings=[{date:'2026-11-18',slot:'dinner',time:'19:05:07'},{date:'2026-11-18',slot:'lunch',time:null}];
 const before=structuredClone(d),v=timing.daySchedule(d,'2026-11-18',['breakfast','lunch','snack','dinner'],c.timing_context);
 assert.equal(v.dinner.time,'19:05:07');assert.equal(v.dinner.origin,'manual');assert(v.dinner.conflict);assert.equal(v.lunch.time,null);assert.equal(v.lunch.origin,'unset');assert.deepEqual(d,before);
 d.timings=[];assert.equal(timing.daySchedule(d,'2026-11-18',['breakfast','lunch','snack','dinner'],c.timing_context).dinner.time,'20:15:00');
});

test('learning requires three real past reports in the current local timezone and does not rewrite preferences',()=>{
 const d=journal.blankJournal();d.entries=['07:00:00','08:00:00','07:45:00'].map(time=>({status:'eaten',source:{slot:'breakfast'},timezone:'Europe/Budapest',date:'2026-11-16',time}));
 let v=timing.daySchedule(d,'2026-11-18',['breakfast'],c.timing_context);assert.equal(v.breakfast.time,'07:45:00');assert.equal(v.breakfast.origin,'learned');assert.equal(d.default_times.breakfast,null);
 d.entries[2].date='2026-11-18';v=timing.daySchedule(d,'2026-11-18',['breakfast'],c.timing_context);assert.equal(v.breakfast.origin,'default');
 d.default_times.breakfast='09:15:20';assert.equal(timing.daySchedule(d,'2026-11-18',['breakfast'],c.timing_context).breakfast.time,'09:15:20');
});

for(const date of ['2026-03-29','2026-10-25'])test('automatic clocks avoid the DST gap/fold on '+date,()=>{
 const ctx={...c.timing_context,activities:[],uncertain_dates:[],start_date:date,end_date:date,local_today:date,now:date+'T00:00:00+00:00'},d=journal.blankJournal();d.default_times.breakfast='02:30:00';
 assert.equal(timing.daySchedule(d,date,['breakfast'],ctx).breakfast.time,'03:00:00');
});

test('there is no manufactured free slot in a full day, and no inferred actual intake',()=>{
 const ctx=structuredClone(c.timing_context);ctx.activities=[{workout_id:ctx.activities[0].workout_id,date:'2026-11-18',start_second:0,end_second:86400}];
 const d=journal.blankJournal(),v=timing.daySchedule(d,'2026-11-18',['breakfast','lunch','snack','dinner'],ctx);
 assert(Object.values(v).every(m=>m.time===null&&m.origin==='no_window'));assert.equal(d.entries.length,0);
 assert(Object.values(timing.daySchedule(d,'2026-11-16',['breakfast','lunch'],ctx)).every(m=>m.origin==='past_unknown'));
});

test('the real meal controls show the generated clock, explain its origin and allow a return from a manual override',()=>{
 const {MealJournalControls}=load('src/components/nutrition/journal-workspace.tsx'),meal=c.result.days[0].meals.find(m=>m.slot==='dinner'),menu=calendar.sourceContext(c,meal),data=journal.blankJournal();
 const store={context:c.journal,data,menu,locked:false,edit(){},save(){},dirty:false};
 let html=renderToStaticMarkup(React.createElement(MealJournalControls,{meal,store}));assert.match(html,/value="20:15:00"/);assert.match(html,/Automatikus kiinduló időpont/);assert.match(html,/naptárhoz igazítva/);
 data.timings=[{date:'2026-11-18',slot:'dinner',time:'18:12:34'}];html=renderToStaticMarkup(React.createElement(MealJournalControls,{meal,store}));
 assert.match(html,/value="18:12:34"/);assert.match(html,/Időpont mentése/);assert.match(html,/Automatikus időpont visszaállítása/);
});
