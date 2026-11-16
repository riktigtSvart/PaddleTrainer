import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-12-instruction-encoding.json.gz',import.meta.url))));
const {readFeed,eventsFrom}=load('src/lib/calendar/contracts.ts');
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readProjectedInstructions}=load('src/lib/planning-cycles/workout-instructions.ts');
const {canonical}=load('src/lib/planning-cycles/contracts.ts');
const {default:Details}=load('src/components/planning-cycles/workout-instructions.tsx');
const {PrescriptionDetails}=load('src/components/planning-cycles/plan-output.tsx');
const {default:EventDetail}=load('src/components/calendar/event-detail.tsx');
const html=(C,props)=>renderToStaticMarkup(React.createElement(C,props));

for(const [encoding,value] of Object.entries(data)){
  test(`actual ${encoding} review retains its original hash and captured text`,async()=>{
    const raw=value.legacy_review,before=canonical(raw);
    const read=await readTrainingReview(raw,{owner:raw.athlete_id,reference:raw.program_reference,zone:raw.timezone_name});
    assert.equal(canonical(raw),before);assert.equal(canonical(read),before);
    const fresh=value.current_review;
    await readTrainingReview(fresh,{owner:fresh.athlete_id,reference:fresh.program_reference,zone:fresh.timezone_name});
    assert.equal(fresh.result.create.length,0);assert.equal(fresh.result.cancel.length,0);
  });
  test(`actual ${encoding} accepted feed normalizes only known library text`,()=>{
    const raw=value.legacy_feed,before=canonical(raw),safe=readFeed(raw);
    assert.equal(canonical(raw),before,'Immutable API source must remain unchanged');
    for(const p of safe.planned){
      const original=raw.planned.find(r=>r.id===p.id),expected=value.feed.planned.find(r=>r.id===p.id);
      assert(p.planning_context.instructions);assert.equal(p.planning_context.instructions_issue,undefined);
      assert.deepEqual(p.planning_context.instructions,expected.planning_context.instructions);
      assert.deepEqual(p.planning_context.instructions.main,original.planning_context.instructions.main);
      assert.equal(p.description,original.description);assert.equal(p.duration_sec,original.duration_sec);
      assert.notDeepEqual(p.planning_context.instructions,original.planning_context.instructions);
    }
    assert.equal(eventsFrom(safe).filter(e=>e.kind==='planned').length,raw.planned.length);
  });
  test(`calendar and plan details show correct Hungarian text for ${encoding} sources`,()=>{
    const feed=readFeed(value.legacy_feed),p=feed.planned.find(p=>p.sport==='STRENGTH');
    const event=eventsFrom(feed).find(e=>e.entityId===p.id);
    for(const rendered of [html(EventDetail,{event,feed,onClose(){}}),html(PrescriptionDetails,{review:value.legacy_review,candidateKey:p.planning_context.candidate_key})]){
      for(const s of ['Könnyű séta vagy helyben lépkedés','Váll-, boka- és csípőátmozgatás','Oldalanként legfeljebb 20','Előírt munkasorozatok'])assert(rendered.includes(s),s);
      assert(!rendered.includes('Ă'));assert(!rendered.includes('Ã'));
      assert(rendered.includes('1 × 8 ismétlés'));
    }
  });
}

function sample(){return structuredClone(data.cp1250.feed.planned.find(p=>p.sport==='STRENGTH').planning_context.instructions);}
test('one set of twelve is explicit for both exercises and is not an instruction to fill twenty minutes',()=>{
  const value=sample(),dose=value.main.strength;
  dose.movements.forEach((m,i)=>{m.label=i?'Fekvenyomás rúddal':'Mellhezhúzás hason fekve, rúddal';m.sets[0].repetitions=12;m.sets[0].load_kind='external_kg';m.sets[0].load_basis='total';m.sets[0].load_value='70';m.sets[0].rir='5_plus';});
  const before=canonical(value),rendered=html(Details,{value});
  assert(rendered.includes('összesen 2 sorozat'));
  assert.equal([...rendered.matchAll(/1 × 12 ismétlés/g)].length,2);
  assert.equal([...rendered.matchAll(/1\. \/ 1/g)].length,2);
  assert(rendered.includes('A megmaradó idő miatt ne adj hozzá új sorozatot'));
  assert.equal(canonical(value),before);
});
test('two recorded sets, mixed repetitions and holds remain distinct quantities',()=>{
  const value=sample(),m=value.main.strength.movements[0];
  m.sets.push({...m.sets[0],id:crypto.randomUUID()});
  let rendered=html(Details,{value});assert(rendered.includes('2 × 8 ismétlés'));assert(rendered.includes('2. / 2'));assert(rendered.includes('összesen 3 sorozat'));
  m.sets[1].repetitions=6;rendered=html(Details,{value});assert(rendered.includes('2 sorozat: 8 ismétlés; 6 ismétlés'));
  m.sets=[{...m.sets[0],repetitions:null,hold_seconds:'30'}];rendered=html(Details,{value});assert(rendered.includes('1 × 30 mp tartás'));
});

for(const [name,change] of [
  ['weight',p=>p.planning_context.instructions.main.strength.movements[0].sets[0].load_value='99'],
  ['repetitions',p=>p.planning_context.instructions.main.strength.movements[0].sets[0].repetitions=15],
  ['extra set',p=>p.planning_context.instructions.main.strength.movements[0].sets.push(structuredClone(p.planning_context.instructions.main.strength.movements[0].sets[0]))],
  ['added duration',p=>p.planning_context.instructions.duration_sec+=60],
  ['arbitrary routine edit',p=>p.planning_context.instructions.warmup.steps[1].instruction+=' Más gyakorlat.'],
  ['unrecognized library',p=>p.planning_context.instructions.library_version='training-routines-v9'],
])test(`encoding compatibility still rejects changed ${name}`,()=>{
  const raw=structuredClone(data.cp1250.legacy_feed),p=raw.planned.find(p=>p.sport==='STRENGTH');change(p);
  assert.throws(()=>readProjectedInstructions(p.planning_context.instructions,p));
  const safe=readFeed(raw).planned.find(r=>r.id===p.id);
  assert.equal(safe.planning_context.instructions,undefined);assert.equal(safe.planning_context.instructions_issue,'not_verified');
});
test('the compatibility reader never applies a blanket conversion to the athlete description',()=>{
  const p=structuredClone(data.cp1250.feed.planned.find(p=>p.sport==='STRENGTH'));
  p.description=new TextDecoder('windows-1250').decode(new TextEncoder().encode(p.description));
  p.planning_context.instructions.main.instruction=p.description;
  assert.throws(()=>readProjectedInstructions(p.planning_context.instructions,p));
});
