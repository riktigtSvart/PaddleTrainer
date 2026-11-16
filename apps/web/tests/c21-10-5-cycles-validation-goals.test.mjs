import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const {calendarCycles,cycleBoundaries,cycleProgress}=load('src/lib/calendar/cycles.ts');
const {readSportAvailability,validateSportAvailability}=load('src/lib/planning-cycles/sport-availability.ts');
const {default:Progress,CycleDayMarkers}=load('src/components/calendar/cycle-markers.tsx');
const {default:TimeGrid}=load('src/components/calendar/time-grid.tsx');
const {default:PeriodGrid}=load('src/components/calendar/period-grid.tsx');
const {default:SportDetails}=load('src/components/planning-data/sport-availability.tsx');
const {controlProblem}=load('src/lib/forms/validation.ts');
const {scheduleDateProblem}=load('src/lib/training-options/slot-validation.ts');
const mesos=[{id:crypto.randomUUID(),title:'Alapozó mezociklus',period_type:'MESOCYCLE',start_date:'2026-10-22',end_date:'2026-11-19'}];
const feed={periods:mesos,local_today:'2026-10-25',timezone_name:'Europe/Budapest',availability:{days:[]}};

test('calendar microcycles follow saved mesocycle civil dates across DST, not Mondays',()=>{
  const cycles=calendarCycles(mesos),micros=cycles.filter(c=>c.kind==='micro');
  assert.deepEqual(micros.map(c=>[c.start_date,c.end_date]),[['2026-10-22','2026-10-28'],['2026-10-29','2026-11-04'],['2026-11-05','2026-11-11'],['2026-11-12','2026-11-18'],['2026-11-19','2026-11-19']]);
  assert.deepEqual(cycleProgress(micros[0],'2026-10-25'),{day:4,total:7});
  assert.deepEqual(cycleProgress(micros.at(-1),'2026-11-19'),{day:1,total:1});
  assert.equal(cycleBoundaries(cycles,'2026-11-19').length,3);
  assert.equal(cycleBoundaries(cycles,'2026-10-26').length,0);
  assert.equal(calendarCycles([{...mesos[0],period_type:'MACROCYCLE'}]).length,0);
});
test('cycle progress names the selected date, saved bounds and current position',()=>{
  const html=renderToStaticMarkup(React.createElement(Progress,{feed,date:feed.local_today}));
  for(const s of ['Ma','Alapozó mezociklus','4/29. nap','1. mikrociklus','4/7. nap',mesos[0].id])assert(html.includes(s),s);
  const outside=renderToStaticMarkup(React.createElement(Progress,{feed,date:'2027-01-01'}));
  assert(outside.includes('nincs mentett mezociklus'));
});
test('one-day final microcycle can display both its start and its end',()=>{
  const html=renderToStaticMarkup(React.createElement(CycleDayMarkers,{cycles:calendarCycles(mesos),date:'2026-11-19'}));
  assert(html.includes('Mezociklus vége'));assert(html.includes('5. mikrociklus kezdete'));assert(html.includes('5. mikrociklus vége'));
});
test('day/week and four-week grids mark bounds without introducing fake activities',()=>{
  for(const Component of [TimeGrid,PeriodGrid]){
    const props={feed,events:[],days:['2026-10-22'],selected:'2026-10-22',overview:false,fullDay:false,open(){},selectDay(){},expandHours(){}};
    const marked=renderToStaticMarkup(React.createElement(Component,{...props,showCycles:true}));
    assert(marked.includes('Mezociklus kezdete'));assert(marked.includes('1. mikrociklus kezdete'));
    assert(!marked.includes('data-calendar-event='));
    const hidden=renderToStaticMarkup(React.createElement(Component,{...props,showCycles:false}));
    assert(!hidden.includes('Mezociklus kezdete'));
  }
});
test('native validation explains missing values and limits with the field label',()=>{
  const control={getAttribute(){return null;},labels:[{childNodes:[{nodeType:3,textContent:'Edzéskeret'}]}],validity:{rangeOverflow:true},max:'90',validationMessage:'native'};
  assert.equal(controlProblem(control),'Edzéskeret: Legfeljebb 90 adható meg.');
  control.validity={valueMissing:true};assert(controlProblem(control).includes('Ezt a mezőt töltsd ki'));
  control.validity={rangeUnderflow:true};control.min='1';assert(controlProblem(control).includes('Legalább 1 szükséges'));
});
test('programmatic timetable save explains missing, malformed and reversed validity dates',()=>{
  assert(scheduleDateProblem('',null).includes('kezdődátumát'));
  assert(scheduleDateProblem('2026-11-13','2026-11-01').includes('nem előzheti meg'));
  assert(scheduleDateProblem('2026-11-13','2026-02-30').includes('érvényes dátum'));
  assert.equal(scheduleDateProblem('2026-11-13',null),null);
});

const fixtures=JSON.parse(readFileSync(new URL('./fixtures/c21-10-5-goal-coverage.json',import.meta.url)));
for(const [name,v] of Object.entries(fixtures))test('actual API goal summary agrees with source days and candidates: '+name,()=>{
  validateSportAvailability(v.result,v.inputs);
});
test('omitted strength stays inspectable inside collapsed planning details',()=>{
  const report=fixtures.changed_timetable.result.preparation.sport_availability;
  const html=renderToStaticMarkup(React.createElement(SportDetails,{value:report}));
  assert(html.includes('A terv nem képvisel minden'));
  assert(html.includes('Maximális erő'));assert(html.includes('/initial-assessment'));
  assert(html.indexOf('Miért ezek az edzések?')<html.indexOf('A terv nem képvisel minden'));
  assert(html.startsWith('<details class="pt-auto-sport-availability">'));
});
for(const [name,mutate] of [
  ['invented fulfilled goal',v=>{const r=v.result.preparation.sport_availability.goal_coverage.find(r=>r.status!=='represented');r.status='represented';r.planned_sessions=1;r.reasons=[];}],
  ['missing goal',v=>v.result.preparation.sport_availability.goal_coverage.pop()],
  ['foreign mesocycle',v=>v.result.preparation.sport_availability.goal_coverage[0].mesocycle_id=crypto.randomUUID()],
  ['invented swimming alternative',v=>v.result.preparation.sport_availability.goal_coverage[0].candidate_days++],
  ['unsupported version',v=>v.result.preparation.sport_availability.schema_version='future'],
  ['missing modern coverage',v=>delete v.result.preparation.sport_availability.goal_coverage],
])test('goal summary rejects '+name,()=>{
  const v=structuredClone(fixtures.changed_timetable);mutate(v);
  assert.throws(()=>validateSportAvailability(v.result,v.inputs));
});
test('older stored sport reports stay readable without pretending they checked goals',()=>{
  const v=structuredClone(fixtures.mixed.result.preparation.sport_availability);
  v.schema_version='training-sport-availability-v0.2';delete v.goal_coverage;
  assert.equal(readSportAvailability(v).goal_coverage,undefined);
});
