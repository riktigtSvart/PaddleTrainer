import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/calendar-duration.json',import.meta.url)));
const c=load('src/lib/calendar/contracts.ts'),d=load('src/lib/calendar/duration-estimate.ts');
const constraints=load('src/lib/calendar/constraints.ts'),grid=load('src/components/calendar/time-grid.tsx');
const Summary=load('src/components/calendar/conflict-summary.tsx').default,Details=load('src/components/calendar/duration-details.tsx').default;
const plan=fixture.feed.planned.find((p)=>p.title==='6km paddling'),estimate=plan.duration_estimate;
const clone=(v)=>structuredClone(v);
const impact=(code,severity='review')=>({plan_id:plan.id,plan_title:plan.title,occurrence_key:'test',constraint_title:'Munka',date:plan.date,code,severity});
test('real backend estimate belongs to exact owner/plan and removes the 08:00 false alarm',async()=>{
 assert.equal(c.readFeed(fixture.feed).planned[0].duration_sec,null);
 assert.equal(d.readDurationEstimate(estimate,plan.id,fixture.feed.athlete_id).duration_sec,2000);
 const ctx=await constraints.readScheduleContext(fixture.context);
 assert.deepEqual(ctx.duration_estimates[plan.id],estimate);assert(!ctx.conflicts.some((x)=>x.plan_id===plan.id));
});
for(const [name,change] of [
 ['foreign athlete',e=>{e.athlete_id=crypto.randomUUID();}],['foreign plan',e=>{e.plan_id=crypto.randomUUID();}],
 ['wrong method',e=>{e.method='title-guess';}],['calibrated claim',e=>{e.range_is_calibrated=true;}],
 ['inverted bounds',e=>{e.lower_sec=3000;}],['unknown upper',e=>{e.upper_sec=null;}],['boolean count',e=>{e.sample_count=true;}],
 ['future source',e=>{e.samples[0].ended_at='2026-11-20T06:00:00Z';}],['wrong scale',e=>{e.samples[0].projected_sec=1;}],
 ['empty census',e=>{e.samples=[];}],['duplicate source',e=>{e.samples.push(clone(e.samples[0]));e.sample_count++;}],
])test('rejects '+name,()=>{const e=clone(estimate);change(e);assert.throws(()=>d.readDurationEstimate(e,plan.id,fixture.feed.athlete_id));});
test('known and zero duration never become a historical estimate',()=>{
 for(const seconds of [0,3600]){const f=clone(fixture.feed);f.planned.find(p=>p.id===plan.id).duration_sec=seconds;assert.throws(()=>c.readFeed(f));}
});
test('estimated event has a 06:33 end while the source duration stays null',()=>{
 const f=c.readFeed(clone(fixture.feed)),e=c.eventsFrom(f).find(e=>e.entityId===plan.id);
 assert.equal(e.end,'2026-10-29T05:33:20.000Z');assert.equal(e.duration,2000);assert.equal(e.endEstimated,true);
 assert.equal(f.planned.find(p=>p.id===plan.id).duration_sec,null);
 assert(c.eventsFrom(f).filter(e=>e.kind==='session').every(e=>!e.durationEstimate));
});
test('card and tooltip show approximately 33 minutes and the transparent range',()=>{
 const events=c.eventsFrom(c.readFeed(fixture.feed)),e=events.find(e=>e.entityId===plan.id);
 assert.equal(d.estimateLabel(e.durationEstimate),'~33 p');assert.match(grid.eventLabel(e,fixture.feed.timezone_name),/06:00–~06:33/);
 assert.match(grid.eventLabel(e,fixture.feed.timezone_name),/30–37 p/);
 const html=renderToStaticMarkup(React.createElement(grid.default,{feed:fixture.feed,events,days:c.dayList(fixture.feed.start_date,fixture.feed.end_date),fullDay:false,open(){},selectDay(){},expandHours(){}}));
 assert.match(html,/~33 p/);assert.match(html,/pt-event-true-end/);
});
test('missing time is neutral information rather than an actual-conflict warning',()=>{
 const html=renderToStaticMarkup(React.createElement(Summary,{conflicts:[impact('PLAN_END_UNKNOWN')]}));
 assert.match(html,/is-data-gap/);assert.match(html,/Hiányzó időadat/);assert(!html.includes('edzésterv időpontja egyeztetendő'));
 assert.equal(constraints.conflictKind(impact('PLAN_END_UNKNOWN')),'unknown');
});
test('estimated and declared overlap retain separate labels',()=>{
 const html=renderToStaticMarkup(React.createElement(Summary,{conflicts:[impact('ESTIMATED_OVERLAP_POSSIBLE'),impact('WORKOUT_OVERLAP','fixed')],estimates:{[plan.id]:estimate}}));
 assert.match(html,/becslés alapján átfedés lehetséges/);assert.match(html,/edzésterv időpontja egyeztetendő/);
 assert.equal(constraints.conflictKind(impact('ESTIMATED_WORKOUT_OVERLAP')),'estimate');
});
test('details expose measured-source links and the elapsed-time basis',()=>{
 const html=renderToStaticMarkup(React.createElement(Details,{estimate,zone:fixture.feed.timezone_name}));
 assert.match(html,/1 saját/);assert.match(html,/30–37 p/);assert.match(html,/eltelt idő/);assert(html.includes('/sessions/'+estimate.samples[0].session_id));
});
test('old feed without estimate preserves missing and zero',()=>{
 const f=clone(fixture.feed),p=f.planned.find(p=>p.id===plan.id);delete p.duration_estimate;
 let e=c.eventsFrom(c.readFeed(f)).find(e=>e.entityId===p.id);assert.equal(e.duration,null);assert.equal(e.end,null);
 p.duration_sec=0;e=c.eventsFrom(c.readFeed(f)).find(e=>e.entityId===p.id);assert.equal(e.duration,0);assert.equal(e.end,new Date(e.start).toISOString());
});
