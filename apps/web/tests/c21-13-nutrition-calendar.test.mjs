import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {load} from './load-goal-modules.mjs';

const m=load('src/lib/nutrition/calendar.ts'),{sha}=load('src/lib/planning-cycles/contracts.ts'),draft=load('src/lib/nutrition/draft.ts');
const fixture=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-13-nutrition-calendar.json.gz',import.meta.url))));
const owner=fixture.athlete_id,range={start:fixture.start_date,end:fixture.end_date};
async function hash(v){delete v.content_hash;v.content_hash=await sha(v);}

test('real backend calendar retains both saved periods, exact household size and no invented actual intake',async()=>{
 const v=await m.readCalendar(fixture,owner,range);
 assert.equal(v.result.days.length,6);assert.equal(v.result.meal_count,24);
 assert.equal(v.result.days[0].meals[0].people,8);assert.equal(v.result.days[3].meals[0].people,2);
 assert.equal(v.result.actual_entries.length,0);assert.equal(v.result.days[0].meals[0].planned_time,null);
 assert.equal(m.sourceContext(v,v.result.days[0].meals[0]).saved.artifact_id,v.result.days[0].meals[0].source.artifact_id);
});
for(const [name,mutate] of [
 ['owner',v=>v.athlete_id='00000000-0000-0000-0000-000000000001'],
 ['range',v=>v.start_date='2026-11-16'],
 ['invented timing',v=>v.result.days[0].meals[0].planned_time='07:00:00'],
 ['false consumption',v=>v.result.days[0].meals[0].status='eaten'],
 ['portion',v=>v.result.days[0].meals[0].portion_factor='2'],
 ['source',v=>v.result.days[0].meals[0].source.content_hash='f'.repeat(64)],
 ['truncation',v=>v.result.days.pop()],
 ['energy claim',v=>v.result.personal_energy_prescribed=true],
])test('rehashed calendar still rejects '+name,async()=>{const v=structuredClone(fixture);mutate(v);await hash(v);await assert.rejects(m.readCalendar(v,owner,range));});

test('a three-meal replacement removes the old snack for that day and preserves adjacent saved dates',()=>{
 const newer=structuredClone(fixture.sources[0]),older=fixture.sources[1],plan=newer.proposal.data.plan;
 plan.start_date='2026-11-16';plan.day_count=1;plan.meals=plan.meals.filter(m=>m.date==='2026-11-18'&&m.slot!=='snack').map(m=>({...m,date:'2026-11-16'}));
 const {blankJournal}=load('src/lib/nutrition/journal.ts');
 const days=m.projectCalendar([newer,older],blankJournal(),range.start,range.end,fixture.catalog).days;
 assert.deepEqual(days.map(d=>d.meals.length),[4,3,4]);
});

test('draft retains unfinished pantry text and rejects another owner',()=>{
 const d={schema_version:'nutrition-menu-draft-v0.1',owner,base_reference:null,data:fixture.sources[0].proposal.data,pantry_inputs:{[fixture.catalog.foods[0].id]:'1.'},start:'2026-11-18',count:3,people:2};
 assert.deepEqual(draft.readDraft(JSON.stringify(d),owner,fixture.catalog),d);
 assert.throws(()=>draft.readDraft(JSON.stringify(d),'00000000-0000-0000-0000-000000000001',fixture.catalog));
 assert(!draft.sameReference(null,fixture.result.days[0].meals[0].source));
 assert.equal(draft.readDraft(JSON.stringify({...d,start:'',count:0,people:-1}),owner,fixture.catalog).start,'');
});

test('saving shopping state retains actual status when the personal meal and dose are unchanged',()=>{
 const f=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-12-journal.json.gz',import.meta.url))));
 const original=f.current.sources[0],newer=structuredClone(original);newer.artifact_id='pt-meals:'+'e'.repeat(64);newer.content_hash='e'.repeat(64);
 let v=m.projectCalendar([newer],f.current.saved.proposal.data,'2026-11-15','2026-11-17',f.catalog,[original]);
 assert.equal(v.days[0].meals[0].status,'eaten');assert.equal(v.days[0].meals[0].different_report,false);
 newer.proposal.data.plan.meals[0].portion_factor='2';v=m.projectCalendar([newer],f.current.saved.proposal.data,'2026-11-15','2026-11-17',f.catalog,[original]);
 assert.equal(v.days[0].meals[0].status,'planned');assert.equal(v.days[0].meals[0].different_report,true);
});

test('meal visibility remains independent and old saved preference shapes still validate',()=>{
 const {defaultVisibility,readVisibility,writeVisibility}=load('src/lib/calendar/visibility.ts'),old=defaultVisibility();
 assert.deepEqual(readVisibility(writeVisibility(owner,7,old),owner,7),old);
 assert.equal(readVisibility(writeVisibility(owner,7,{...old,meals:false}),owner,7).meals,false);
 assert.throws(()=>readVisibility(writeVisibility(owner,7,{...old,meals:'yes'}),owner,7));
});

test('month buffer covers narrower day and week views across a DST boundary',()=>{
 const r=m.expandedRange('2026-10-25','2026-10-31');assert(r.start<'2026-10-01'&&r.end>'2026-10-31');assert(Date.parse(r.end)-Date.parse(r.start)<366*86400000);
});

test('calendar proxy accepts only an owned read with bounded date parameters',async()=>{
 const {forwardGoals}=load('src/lib/planning-goals/proxy.ts');let calls=0;
 const send=async(url,init)=>{calls++;assert.equal(init.method,'GET');assert(!init.headers?.authorization);assert(String(url).includes('/planning/nutrition/calendar?start_date='));return Response.json(fixture);};
 let r=await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition/calendar?start_date=2026-11-15&end_date=2026-11-23'),['nutrition','calendar'],'http://localhost:8000/api/v1',send);assert.equal(r.status,200);assert.equal(calls,1);
 for(const [method,query] of [['POST',''],['GET','?owner=x'],['GET','?start_date=a&start_date=b']]){
  r=await forwardGoals(new Request('https://paddle.test/api/goal-workflow/nutrition/calendar'+query,{method}),['nutrition','calendar'],'http://localhost:8000/api/v1',send);assert(r.status>=400);
 }
 assert.equal(calls,1);
});
