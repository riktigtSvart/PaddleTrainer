import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-11-calibrated-calendar.json.gz',import.meta.url))));
const previous=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-10-workout-instructions.json.gz',import.meta.url))));
const {readFeed,eventsFrom}=load('src/lib/calendar/contracts.ts');
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {deriveInstructions,readProjectedInstructions}=load('src/lib/planning-cycles/workout-instructions.ts');
const {strengthPresentation}=load('src/lib/planning-cycles/strength-assessment.ts');
const {default:Instructions}=load('src/components/planning-cycles/workout-instructions.tsx');
const {default:EventDetail}=load('src/components/calendar/event-detail.tsx');
const html=(C,props)=>renderToStaticMarkup(React.createElement(C,props));

for(const [name,v] of Object.entries(data))test(`real accepted API ${name}: unknown future RIR retains the valid measured reserve`,async()=>{
  await readTrainingReview(v.review,{owner:v.review.athlete_id,reference:v.review.program_reference,zone:v.review.timezone_name});
  const feed=readFeed(v.feed),rows=feed.planned.filter(p=>p.sport==='STRENGTH');assert(rows.length);
  for(const p of rows){
    const instruction=p.planning_context.instructions;assert(instruction);
    assert.equal(p.planning_context.instructions_issue,undefined);
    assert.deepEqual(readProjectedInstructions(instruction,p),instruction);
    const dose=instruction.main.strength;assert.equal(dose.minimum_rir,3);assert.equal(dose.rest_seconds,180);
    assert(dose.movements.every(m=>m.sets.length===1&&m.sets[0].repetitions===6&&m.sets[0].rir==='unknown'));
    assert(dose.calibration_derivations.every(d=>d.source_rir===name.at(-1)&&d.source_repetitions===8));
  }
  assert.deepEqual(v.feed.planned,feed.planned);assert.equal(eventsFrom(feed).filter(e=>e.kind==='planned').length,feed.planned.length);
});
test('the calibrated table separates measured reserve from the new prescribed minimum',()=>{
  const feed=readFeed(data.current_rir_2.feed),p=feed.planned.find(p=>p.sport==='STRENGTH'),v=p.planning_context.instructions;
  const rendered=html(Instructions,{value:v});
  for(const phrase of ['6','2 ismétlés','00:03:00','legalább 3','tényleges tartaléka még nincs megmérve','12,5 kg'])assert(rendered.includes(phrase),phrase);
  assert(!rendered.includes('unknown'));assert(!rendered.includes('Nincs mérve ismétlés'));
  const event=eventsFrom(feed).find(e=>e.entityId===p.id);
  const modal=html(EventDetail,{event,feed,onClose(){}});assert(modal.includes('Edzés lépésről lépésre'));assert(modal.includes('felmérésből levezetett'));
});

function changedInstruction(change){
  const p=structuredClone(data.current_rir_2.feed.planned.find(p=>p.sport==='STRENGTH'));
  const dose=p.planning_context.instructions.main.strength;change(dose);
  // Even coherent rewritten presentation cannot excuse a broken derivation.
  const presentation=strengthPresentation(dose,p.duration_sec);p.title=presentation.title;p.description=presentation.description;
  p.planning_context.instructions=deriveInstructions({sport:p.sport,duration_sec:p.duration_sec,description:p.description,blocks:[{duration_sec:300},{duration_sec:p.duration_sec-600},{duration_sec:300}]},{strength:dose});
  return p;
}
for(const [name,change] of [
  ['missing source proof',d=>delete d.calibration_derivations],
  ['duplicate proof',d=>d.calibration_derivations.push(structuredClone(d.calibration_derivations[0]))],
  ['orphan source entry',d=>d.calibration_derivations[0].entry_id=crypto.randomUUID()],
  ['different observation',d=>d.calibration_derivations[0].observation_id=crypto.randomUUID()],
  ['too few measured reps',d=>d.calibration_derivations[0].source_repetitions=3],
  ['wrong reduction',d=>{d.calibration_derivations[0].planned_repetitions=7;d.movements[0].sets[0].repetitions=7;}],
  ['lower reserve',d=>d.calibration_derivations[0].planned_minimum_rir=2],
  ['false measured reserve',d=>d.movements[0].sets[0].rir='3'],
  ['failure reference',d=>d.calibration_derivations[0].source_rir='0'],
  ['shortened rest',d=>d.rest_seconds=120],
  ['capacity claim',d=>d.calibration_derivations[0].personal_capacity_estimated=true],
  ['bad source hash',d=>d.calibration_derivations[0].guided_reference.content_hash='broken'],
])test(`calibrated instructions still reject ${name}`,()=>{
  const row=changedInstruction(change);assert.throws(()=>readProjectedInstructions(row.planning_context.instructions,row));
});
test('unknown reserve in an ordinary reference cannot masquerade as a calibrated starter',()=>{
  const p=structuredClone(previous.accepted_feed.planned.find(p=>p.sport==='STRENGTH'));
  p.planning_context.instructions.main.strength.movements[0].sets[0].rir='unknown';
  assert.throws(()=>readProjectedInstructions(p.planning_context.instructions,p));
});
test('one rejected optional panel preserves every valid event, date, purpose and original description',()=>{
  const raw=structuredClone(data.current_rir_2.feed),target=raw.planned.find(p=>p.sport==='STRENGTH');
  target.planning_context.instructions.main.strength.minimum_rir=0;
  const before=JSON.stringify(raw),safe=readFeed(raw),row=safe.planned.find(p=>p.id===target.id);
  assert.equal(JSON.stringify(raw),before,'Reader must not alter the source response');
  assert.equal(row.planning_context.instructions,undefined);assert.equal(row.planning_context.instructions_issue,'not_verified');
  assert.equal(row.description,target.description);assert.equal(row.planning_context.primary_goal,target.planning_context.primary_goal);
  assert.equal(safe.local_today,raw.local_today);assert.equal(safe.planned.length,raw.planned.length);
  assert.equal(eventsFrom(safe).filter(e=>e.kind==='planned').length,raw.planned.length);
  assert(safe.planned.filter(p=>p.id!==target.id&&p.planning_context?.instructions).length);
  const event=eventsFrom(safe).find(e=>e.entityId===target.id),rendered=html(EventDetail,{event,feed:safe,onClose(){}});
  assert(rendered.includes('eredeti edzésleírás fent látható'));assert(!rendered.includes('<table'));
});
for(const value of [null,{},'unknown library',{schema_version:'future'}])test(`an unreadable optional panel is isolated: ${JSON.stringify(value)}`,()=>{
  const raw=structuredClone(data.current_rir_2.feed),target=raw.planned.find(p=>p.sport==='STRENGTH');target.planning_context.instructions=value;
  const safe=readFeed(raw);assert.equal(safe.planned.find(p=>p.id===target.id).planning_context.instructions_issue,'not_verified');
});
test('a forged upstream warning is discarded when the instruction actually verifies',()=>{
  const raw=structuredClone(data.current_rir_2.feed);raw.planned[0].planning_context.instructions_issue='not_verified';
  const safe=readFeed(raw);assert.equal(safe.planned[0].planning_context.instructions_issue,undefined);assert(safe.planned[0].planning_context.instructions);
});
for(const [name,change] of [
  ['unrecognized owner',f=>f.athlete_id='not-an-owner'],
  ['invalid goal source',f=>f.planned[0].planning_context.source_kind='invented'],
  ['wrong mesocycle',f=>f.planned[0].planning_context.mesocycle_id=crypto.randomUUID()],
  ['invalid event date',f=>f.planned[0].date='2026-02-30'],
])test(`optional-panel isolation does not bypass core calendar checks: ${name}`,()=>{
  const raw=structuredClone(data.current_rir_2.feed);change(raw);assert.throws(()=>readFeed(raw));
});
