import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const values=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-10-workout-instructions.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readFeed,eventsFrom,viewRange,dayList,addDays}=load('src/lib/calendar/contracts.ts');
const {deriveInstructions,readProjectedInstructions}=load('src/lib/planning-cycles/workout-instructions.ts');
const {calendarWeekStart}=load('src/lib/calendar/cycles.ts');
const {initialOverview,adjacentOverview}=load('src/lib/calendar/overview.ts');
const visibility=load('src/lib/calendar/visibility.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {default:Instructions}=load('src/components/planning-cycles/workout-instructions.tsx');
const {PrescriptionDetails}=load('src/components/planning-cycles/plan-output.tsx');
const {default:EventDetail}=load('src/components/calendar/event-detail.tsx');
const {default:PeriodGrid}=load('src/components/calendar/period-grid.tsx');
const {default:TimeGrid}=load('src/components/calendar/time-grid.tsx');
const html=(C,props)=>renderToStaticMarkup(React.createElement(C,props));
const review=values.mixed_review,feed=values.accepted_feed;
const read=v=>readTrainingReview(v,{owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});
async function resign(v){const body={...v};delete body.content_hash;v.content_hash=await sha(body);}

test('the actual v0.14 mixed API review and new/legacy accepted feeds verify',async()=>{
  await read(review);
  for(const name of ['accepted_feed','legacy_feed']){
    const f=readFeed(values[name]);
    assert.deepEqual(new Set(f.planned.map(p=>p.sport)),new Set(['STRENGTH','SWIMMING','RUNNING','KAYAK']));
    assert(f.planned.every(p=>p.planning_context.instructions));
  }
});
test('concrete warmups and optional stretches retain the exact accepted time budget',()=>{
  for(const candidate of review.result.proposals){
    const routine=review.result.instruction_context.by_candidate[candidate.candidate_key];
    assert.deepEqual(routine,deriveInstructions(candidate,review.result.prescription_context.by_candidate[candidate.candidate_key]));
    assert.equal(routine.warmup.steps.reduce((n,s)=>n+s.duration_sec,0),routine.warmup.duration_sec);
    assert.equal(routine.warmup.duration_sec+routine.main.duration_sec+routine.finish.duration_sec,candidate.duration_sec);
    assert.equal(routine.finish.easy_duration_sec+routine.finish.stretches.reduce((n,s)=>n+s.duration_sec,0),routine.finish.duration_sec);
    assert.equal(routine.finish.stretching_optional,true);
    assert.equal(routine.recovery_effect_claimed,false);
    assert.equal(routine.external_load_increased,false);assert.equal(routine.sets_added,false);
  }
});
test('the strength table displays the exact own load, reps, sets, rest and reserve',()=>{
  const c=review.result.proposals.find(c=>c.sport==='STRENGTH'),v=review.result.instruction_context.by_candidate[c.candidate_key];
  assert.deepEqual(v.main.strength,c.strength_prescription);
  const rendered=html(Instructions,{value:v});
  for(const phrase of ['Bemelegítés és gimnasztika','Főrész','Gyakorlat','Sorozat','Terhelés','Ismétlés','Tartalék','Pihenő','12,5 kg','kézenként','2 perc','legalább 3','ne dolgozz kifáradásig','Választható nyújtó gyakorlatsor','2 perc a levezetésen belül','/strength-assessment'])assert(rendered.includes(phrase),phrase);
  for(const m of v.main.strength.movements)assert(rendered.includes(m.label));
  assert.match(rendered,/<table/);assert.match(rendered,/<details/);
});
test('each supported sport receives its own explicit preparatory movements',()=>{
  for(const [sport,phrase] of [['RUNNING','Bokabillentés'],['KAYAK','törzsgimnasztika'],['STRENGTH','csípőátmozgatás'],['SWIMMING','mozgás a vízben']]){
    const p=feed.planned.find(p=>p.sport===sport);
    assert(html(Instructions,{value:p.planning_context.instructions}).includes(phrase),sport);
  }
});
test('calendar event details and selected/unselected plan alternatives show the same instructions',()=>{
  const row=feed.planned.find(p=>p.sport==='STRENGTH'),event=eventsFrom(readFeed(feed)).find(e=>e.entityId===row.id);
  assert(html(EventDetail,{event,feed,onClose(){}}).includes('Edzés lépésről lépésre'));
  const selected=review.result.proposals[0];
  assert(html(PrescriptionDetails,{review,candidateKey:selected.candidate_key}).includes('Bemelegítés és gimnasztika'));
  const alternative=review.result.alternatives.flatMap(g=>g.candidates).find(c=>!review.result.instruction_context.by_candidate[c.candidate_key]);
  assert(alternative);
  assert(html(PrescriptionDetails,{review,candidateKey:alternative.candidate_key}).includes('Választható nyújtó gyakorlatsor'));
});
for(const [name,change] of [
  ['missing routine',v=>delete v.result.instruction_context],
  ['extra total time',v=>Object.values(v.result.instruction_context.by_candidate)[0].duration_sec+=120],
  ['extra warmup time',v=>Object.values(v.result.instruction_context.by_candidate)[0].warmup.steps[0].duration_sec+=60],
  ['invented recovery effect',v=>Object.values(v.result.instruction_context.by_candidate)[0].recovery_effect_claimed=true],
  ['new weight',v=>Object.values(v.result.instruction_context.by_candidate).find(r=>r.main.strength).main.strength.movements[0].sets[0].load_value='50.000000'],
  ['new reps',v=>Object.values(v.result.instruction_context.by_candidate).find(r=>r.main.strength).main.strength.movements[0].sets[0].repetitions=15],
  ['failure target',v=>Object.values(v.result.instruction_context.by_candidate).find(r=>r.main.strength).main.strength.minimum_rir=0],
])test(`an outer rehash cannot authorize ${name}`,async()=>{
  const v=structuredClone(review);change(v);await resign(v);await assert.rejects(()=>read(v));
});
for(const [name,change] of [
  ['time',r=>r.duration_sec+=60],['extra cooldown',r=>r.finish.duration_sec+=60],
  ['weight',r=>r.main.strength.movements[0].sets[0].load_value='99.000000'],
  ['reserve',r=>r.main.strength.minimum_rir=0],['added sets',r=>r.sets_added=true],
])test(`accepted feed cannot display changed ${name} as the saved instruction`,()=>{
  const v=structuredClone(feed),p=v.planned.find(p=>p.sport==='STRENGTH');change(p.planning_context.instructions);
  assert.throws(()=>readProjectedInstructions(p.planning_context.instructions,p));
  const safe=readFeed(v).planned.find(row=>row.id===p.id);
  assert.equal(safe.planning_context.instructions,undefined);
  assert.equal(safe.planning_context.instructions_issue,'not_verified');
});

const friday={id:'00000000-0000-0000-0000-000000001110',period_type:'MESOCYCLE',title:'Pénteki ciklus',start_date:'2026-11-20',end_date:'2026-12-17'};
test('Monday and microcycle mode align weeks by saved cycle boundaries, independently of colours',()=>{
  assert.deepEqual(calendarWeekStart('2026-11-23',[friday],'monday'),{weekday:1,matched:true});
  assert.deepEqual(calendarWeekStart('2026-11-23',[friday],'microcycle'),{weekday:5,matched:true});
  for(const span of [7,28,168]){
    assert.equal(viewRange('2026-11-23',span,1).start,'2026-11-23');
    const range=viewRange('2026-11-23',span,5);assert.equal(range.start,'2026-11-20');assert.equal(dayList(range.start,range.end).length,span);
  }
  assert.deepEqual(viewRange('2026-11-23',1,5),{start:'2026-11-23',end:'2026-11-23'});
  for(const first of [0,1,2,3,4,5,6]){
    const range=viewRange('2026-10-25',28,first);
    assert.equal(new Date(range.start+'T12:00Z').getUTCDay(),first);assert.equal(dayList(range.start,range.end).length,28);
  }
  assert.throws(()=>viewRange('2026-11-23',7,7));assert.throws(()=>viewRange('2026-11-23',7,1.5));
});
test('missing or overlapping cycles fall back to Monday without modifying the saved preference',()=>{
  for(const periods of [[],[friday,{...friday,id:crypto.randomUUID()}]])assert.deepEqual(calendarWeekStart('2026-11-23',periods,'microcycle'),{weekday:1,matched:false});
  assert.deepEqual(calendarWeekStart('2026-12-18',[friday],'microcycle'),{weekday:1,matched:false});
  const shortened={...friday,end_date:'2026-11-29'};
  assert.equal(calendarWeekStart('2026-11-29',[shortened],'microcycle').weekday,5);
});
test('headers follow the rotated dates in week, four-week and contiguous overview chunks',()=>{
  const days=dayList('2026-11-20','2026-12-17'),props={feed,events:[],days,selected:days[0],overview:false,fullDay:false,open(){},selectDay(){},expandHours(){}};
  const four=html(PeriodGrid,props),headers=[...four.matchAll(/class="pt-month-heading">(.*?)<\/div>/g)].map(m=>m[1]);
  assert.deepEqual(headers,['P','Szo','V','H','K','Sze','Cs']);
  const week=html(TimeGrid,{...props,days:days.slice(0,7)});
  assert(week.indexOf('nov. 20.')<week.indexOf('nov. 21.'));
  const chunks=initialOverview('2026-11-23',5);assert.equal(chunks.length,6);assert.equal(chunks[0].start,'2026-11-20');
  chunks.forEach((c,i)=>{assert.equal(new Date(c.start+'T12:00Z').getUTCDay(),5);if(i)assert.equal(c.start,addDays(chunks[i-1].end,1));});
  assert.equal(adjacentOverview(chunks,1).start,addDays(chunks.at(-1).end,1));
});
test('week alignment is owner/view-scoped and backward-compatible with all previous visibility fields',()=>{
  const owner=feed.athlete_id,keys=new Set();
  for(const [i,span] of [1,7,28,168].entries()){
    keys.add(visibility.visibilityKey(owner,span));const p=visibility.defaultVisibility();p.weekStart=i%2?'microcycle':'monday';p.cycleLoad=true;p.layers.availability=false;
    assert.deepEqual(visibility.readVisibility(visibility.writeVisibility(owner,span,p),owner,span),p);
    const old=JSON.parse(visibility.writeVisibility(owner,span,p));delete old.weekStart;
    const read=visibility.readVisibility(JSON.stringify(old),owner,span);assert.equal(read.weekStart,undefined);assert.equal(read.cycleLoad,true);assert.equal(read.layers.availability,false);
    old.weekStart='sunday';assert.throws(()=>visibility.readVisibility(JSON.stringify(old),owner,span));
  }
  assert.equal(keys.size,4);assert.notEqual(visibility.visibilityKey(owner,7),visibility.visibilityKey(crypto.randomUUID(),7));
});
