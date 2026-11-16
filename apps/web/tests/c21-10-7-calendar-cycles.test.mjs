import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-7-calendar-cycles.json.gz',import.meta.url))));
const {readCycleContext,cycleData,cycleLoad}=load('src/lib/calendar/cycle-context.ts');
const {readFeed,addDays}=load('src/lib/calendar/contracts.ts');
const {cycleCoverage,actualGoal,plannedGoal}=load('src/lib/calendar/cycle-coverage.ts');
const {calendarCycles}=load('src/lib/calendar/cycles.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {CycleDayMarkers}=load('src/components/calendar/cycle-markers.tsx');
const {CycleDetailContent,CycleLoadLegend}=load('src/components/calendar/cycle-detail.tsx');
const {default:TimeGrid}=load('src/components/calendar/time-grid.tsx');
const {default:PeriodGrid}=load('src/components/calendar/period-grid.tsx');
const {default:OverviewCalendar}=load('src/components/calendar/overview-calendar.tsx');
const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const visibility=load('src/lib/calendar/visibility.ts');
const expected=v=>({owner:v.athlete_id,zone:v.timezone_name,start:v.start_date,end:v.end_date});
const rehash=async v=>{const body={...v};delete body.content_hash;v.content_hash=await sha(body);};
const html=(C,props)=>renderToStaticMarkup(React.createElement(C,props));
const accepted=f.accepted,period=accepted.context.cycles[0].period;

for(const [name,v] of Object.entries(f))test(`actual read-only API cycle context is valid: ${name}`,async()=>{
  await readCycleContext(v.context,expected(v.context));if(v.feed)readFeed(v.feed);
});
test('saved goals and a numeric source reference exist before any wave is accepted',()=>{
  assert(f.unaccepted.context.cycles.some(c=>c.goals.some(g=>g.capability_key==='MAX_STRENGTH'&&g.role==='primary_development')));
  assert(f.unaccepted.context.cycles.every(c=>c.blocks.length===0&&c.wave_source===null));
});
test('accepted civil-date waves use green/yellow/red/blue for 80/90/100/70 percent',()=>{
  const c=accepted.context,p=c.cycles[0].period;
  assert.deepEqual([0,7,14,21].map(n=>cycleLoad(c,accepted.feed,addDays(p.start_date,n))?.tone),['green','yellow','red','blue']);
  assert.equal(cycleLoad(c,accepted.feed,'2026-10-25').tone,'green');
  assert.match(cycleLoad(c,accepted.feed,addDays(p.start_date,14)).label,/100%/);
});
test('a preview changes no accepted colours or source receipt',()=>{
  for(const c of f.preview_only.context.cycles){
    const old=f.preview_only.previous_context.cycles.find(r=>r.period.id===c.period.id);assert(old);
    assert.deepEqual(c.blocks,old.blocks);assert.deepEqual(c.wave_source,old.wave_source);
  }
});
test('unaccepted, changed-date, absent and overlapping cycles never get a guessed colour',()=>{
  assert.equal(cycleLoad(null,accepted.feed,period.start_date),null);
  assert.equal(cycleLoad(f.unaccepted.context,accepted.feed,period.start_date),null);
  const changed=f.changed_dates.context.cycles.find(c=>c.period.id===period.id);
  assert.equal(changed.wave_status,'dates_changed');assert.equal(changed.blocks.length,0);
  assert.equal(cycleData(f.changed_dates.context,period),null);
  const duplicate=structuredClone(accepted.feed);duplicate.periods.push({...period,id:crypto.randomUUID()});
  assert.equal(cycleLoad(accepted.context,duplicate,period.start_date),null);
});
test('cycle details count actual sessions once and keep unlabelled strength separate',()=>{
  const {feed,context}=f.recorded,p=context.cycles[0].period,v=cycleCoverage(feed,p);
  assert.equal(v.completed.count,2);assert.equal(v.byGoal.MAX_STRENGTH.actual.count,1);assert.equal(v.unassigned,1);
  assert.equal(v.bySport.STRENGTH.count,2);assert.equal(v.reportedOnly,0);
  const linked=feed.sessions.find(s=>s.planned_workout_id);assert.equal(actualGoal(linked,feed),'MAX_STRENGTH');
  assert.equal(v.upcoming.count,feed.planned.filter(p=>['PLANNED','DRAFT','SCHEDULED'].includes(p.status)&&Date.parse(p.planned_start_time)>Date.parse(feed.retrieved_at)).length);
});
test('unknown durations, future actual records and reported-only plans remain distinct',()=>{
  const feed=structuredClone(f.recorded.feed),p=f.recorded.context.cycles[0].period;
  feed.sessions[0].duration_sec=null;let v=cycleCoverage(feed,p);assert.equal(v.completed.unknown,1);
  const future=structuredClone(feed.sessions[0]);future.id=crypto.randomUUID();future.started_at=addDays(feed.local_today,1)+'T10:00:00Z';future.ended_at=addDays(feed.local_today,1)+'T10:20:00Z';feed.sessions.push(future);
  const row=structuredClone(feed.planned[0]);row.id=crypto.randomUUID();row.status='COMPLETED';feed.planned.push(row);
  v=cycleCoverage(feed,p);assert.equal(v.completed.count,2);assert.equal(v.reportedOnly,1);
});
test('a cleared manual goal is respected and sport/title never invent a purpose',()=>{
  const feed=structuredClone(f.recorded.feed),s=feed.sessions.find(s=>s.planned_workout_id),p=feed.planned.find(p=>p.id===s.planned_workout_id);
  p.goal_tag={artifact_id:'explicit-clear',content_hash:'f'.repeat(64),primary_goal:null};assert.equal(plannedGoal(p),null);assert.equal(actualGoal(s,feed),null);
  s.name='Maximális erő';s.sport='STRENGTH';s.planned_workout_id=null;assert.equal(actualGoal(s,feed),null);
});
test('the popup states current goals, actual representation and accepted microcycle ceilings',()=>{
  const v=f.recorded,rendered=html(CycleDetailContent,{feed:v.feed,context:v.context,period:v.context.cycles[0].period});
  for(const text of ['Kezdés','Tervezett befejezés','Fő fejlesztési cél','Maximális erő','Mikrociklusok','Igazolt befejezett teljesítések','nincs hozzárendelt fő cél','nem igazolja a képesség javulását','/planning-goals','/training-periods/'])assert(rendered.includes(text),text);
  assert(!rendered.includes('Fejlődés: 100%'));
});
test('boundary labels become real buttons and retain start/end meaning',()=>{
  const cycles=calendarCycles([period]);
  for(const date of [period.start_date,period.end_date]){
    const s=html(CycleDayMarkers,{cycles,date,onOpenCycle(){}});assert.match(s,/<button/);assert.match(s,/részletei/);assert.match(s,date===period.start_date?/Mezociklus kezdete/:/Mezociklus vége/);
  }
});
test('day/week, four-week and scrolling overview use the optional accepted colour layer',()=>{
  const feed=accepted.feed,props={feed,events:[],days:[period.start_date],selected:period.start_date,overview:false,fullDay:false,open(){},selectDay(){},expandHours(){},showCycles:true,onOpenCycle(){},cycleContext:accepted.context};
  for(const C of [TimeGrid,PeriodGrid]){
    assert.match(html(C,{...props,showCycleLoad:true}),/data-cycle-load="green"/);
    assert.doesNotMatch(html(C,{...props,showCycleLoad:false}),/data-cycle-load=/);
  }
  const overview=html(OverviewCalendar,{feed,context:null,layers:{training:true,availability:false,commitments:false},selectDay(){},showCycles:true,showCycleLoad:true,cycleContext:accepted.context,onOpenCycle(){}});
  assert.match(overview,/data-cycle-load="green"/);assert.match(overview,/Mezociklus kezdete/);
  const legend=html(CycleLoadLegend,{});assert.match(legend,/nem személyes határterhelés/);
});
test('the colour switch persists separately per view while old preferences remain readable',()=>{
  const owner=accepted.feed.athlete_id;
  for(const [i,span] of [1,7,28,168].entries()){
    const p=visibility.defaultVisibility();p.cycleLoad=i%2===0;p.layers.availability=false;
    assert.equal(visibility.readVisibility(visibility.writeVisibility(owner,span,p),owner,span).cycleLoad,i%2===0);
    const old=JSON.parse(visibility.writeVisibility(owner,span,p));delete old.cycleLoad;
    const read=visibility.readVisibility(JSON.stringify(old),owner,span);assert.equal(read.cycleLoad,false);assert.equal(read.layers.availability,false);
    old.cycleLoad='true';assert.throws(()=>visibility.readVisibility(JSON.stringify(old),owner,span));
  }
});
for(const [name,change] of [
  ['foreign owner',v=>v.athlete_id=crypto.randomUUID()],['wrong range',v=>v.start_date='2026-01-01'],
  ['invented adaptation',v=>v.adaptation_measured=true],['write authority',v=>v.planning_authorized=true],
  ['truncated results',v=>v.has_more=true],['unknown schema',v=>v.schema_version='future'],
  ['duplicate cycle',v=>v.cycles.push(structuredClone(v.cycles[0]))],
  ['invented percentage',v=>v.cycles[0].blocks[0].volume_percent=110],
  ['string percentage',v=>v.cycles[0].blocks[1].volume_percent='90'],
  ['shifted civil boundary',v=>v.cycles[0].blocks[0].start_date='2026-10-24'],
  ['string ordinal',v=>v.cycles[0].blocks[0].ordinal='1'],
  ['unaccepted coloured block',v=>v.cycles[0].wave_status='not_accepted'],
  ['future acceptance',v=>v.cycles[0].wave_source.accepted_at='2030-01-01T00:00:00Z'],
  ['invented goal',v=>v.cycles[0].goals[0].capability_key='RUN_FAST'],
  ['missing goal reference',v=>v.cycles[0].goal_reference=null],
  ['negative report count',v=>v.cycles[0].latest_review.goal_coverage[0].planned_sessions=-1],
])test(`cycle context rejects ${name} after an outer rehash`,async()=>{
  const v=structuredClone(accepted.context);change(v);await rehash(v);await assert.rejects(()=>readCycleContext(v,expected(accepted.context)));
});
test('the cycle endpoint proxy permits only owned GET ranges',async()=>{
  let calls=0;const send=async()=>{calls++;return Response.json({ok:true});};
  assert.equal((await forwardCalendar(new Request('https://paddle.test/api/calendar/cycles?start_date=2026-10-23&end_date=2026-11-19'),['cycles'],'http://backend.test',send)).status,200);
  assert.equal((await forwardCalendar(new Request('https://paddle.test/api/calendar/cycles',{method:'POST'}),['cycles'],'http://backend.test',send)).status,405);
  assert.equal((await forwardCalendar(new Request('https://paddle.test/api/calendar/cycles?owner=other'),['cycles'],'http://backend.test',send)).status,422);
  assert.equal(calls,1);
});
