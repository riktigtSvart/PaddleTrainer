import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-10-planning.json',import.meta.url)));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {readDaylightPreview}=load('src/lib/training-options/daylight.ts');
const {minimumAreaAltitude,areaLightIntervals}=load('src/lib/training-options/area-daylight.ts');
const {readOptionsContext,readOptionsReceipt}=load('src/lib/training-options/contracts.ts');
const {readPrescriptionSettings}=load('src/lib/training-options/prescription-settings.ts');
const {validateLoadBudget,spacingHours}=load('src/lib/planning-cycles/training-load.ts');
const {validateSwimmingCandidate}=load('src/lib/planning-cycles/swimming-prescription.ts');
const {validateSportAvailability}=load('src/lib/planning-cycles/sport-availability.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const {mapPixel,mapCoordinate}=load('src/lib/training-options/location-map.ts');
const {default:Settings}=load('src/components/training-options/prescription-settings.tsx');
const {default:Details}=load('src/components/planning-data/sport-availability.tsx');
const {PrescriptionDetails}=load('src/components/planning-cycles/plan-output.tsx');
const owner=f.mixed_review.athlete_id;
const read=v=>readTrainingReview(v,{owner:v.athlete_id,reference:v.program_reference,zone:v.timezone_name});

for(const name of ['mixed_review','swim_recent_review','swim_repeats_review','observed_review','area_review'])
  test(`real API ${name} independently verifies ownership, sources and prescriptions`,async()=>{await read(f[name]);});
test('the shared weekly envelope produces endurance and strength with a scarce daylight-safe kayak option',()=>{
  const v=f.mixed_review,sports=new Set(v.result.proposals.map(c=>c.sport));
  for(const s of ['KAYAK','SWIMMING','RUNNING','STRENGTH'])assert(sports.has(s));
  assert.equal(v.result.prescription_context.starting_budget.mode,'declared_current_training');
  assert.equal(v.result.preparation.max_sessions_per_7_days,6);
  assert.equal(v.result.preparation.max_minutes_per_7_days,450);
  const data=v.inputs.daylight_context.options_receipt.artifact.proposal.data;
  for(const c of v.result.proposals.filter(c=>c.sport==='KAYAK')) {
    const site=data.locations.find(l=>l.id===c.location_id),rule=data.daylight_rules.find(r=>r.sport==='KAYAK');
    assert(areaLightIntervals(Date.parse(c.start_at)/1000,Date.parse(c.end_at)/1000,site.area,rule).some(([a,b])=>a<=Date.parse(c.start_at)/1000&&b>=Date.parse(c.end_at)/1000));
  }
});
for(const [name,v] of Object.entries(f).filter(([k])=>k.startsWith('minimum_')))
  test(`independent JavaScript whole-area minimum matches Python ${name}`,()=>assert(Math.abs(minimumAreaAltitude(v.at,v.area)-v.minimum)<1e-8));
test('region preview replays complete intervals and refuses rehashed forged boundaries',async()=>{
  const v=f.area_preview;await readDaylightPreview(v,v.athlete_id,v.request);
  const forged=structuredClone(v);forged.result.daylight.intervals[0].start_at=forged.result.day_start_at;
  delete forged.content_hash;forged.content_hash=await sha(forged);
  await assert.rejects(()=>readDaylightPreview(forged,forged.athlete_id,forged.request));
  await assert.rejects(()=>readDaylightPreview(v,crypto.randomUUID(),v.request));
});
test('region geometry, pool length and planning settings round-trip in owned options',async()=>{
  await readOptionsReceipt(f.area_options,owner);
  await readOptionsContext(f.mixed_options,owner);
});
for(const [name,edit] of [
  ['invented weekly count',v=>v.result.prescription_context.starting_budget.max_sessions_per_7_days++],
  ['availability used as fitness',v=>v.result.prescription_context.starting_budget.current_baseline=null],
  ['wrong baseline source',v=>v.result.prescription_context.starting_budget.source_reference.content_hash='0'.repeat(64)],
  ['missing current census',v=>v.result.prescription_context.starting_budget.weeks.pop()],
])test(`weekly budget rejects ${name}`,async()=>{const v=structuredClone(f.mixed_review);edit(v);await assert.rejects(()=>validateLoadBudget(v));});

function firstSwim(v){return v.result.alternatives.flatMap(g=>g.candidates).find(c=>c.sport==='SWIMMING');}
for(const [name,edit] of [
  ['wrong pool',(_v,_c,m)=>m.swimming.pool_length_m='25'],
  ['invented pace',(_v,_c,m)=>m.swimming.pace_estimated=true],
  ['changed mode',(_v,_c,m)=>m.swimming.mode='length_repeats'],
  ['borrowed venue',(_v,c)=>c.location_id=crypto.randomUUID()],
  ['changed instructions',(_v,c)=>c.description+=' Ússz maximálisan.'],
  ['omitted rest evidence',(_v,_c,m)=>delete m.swimming.rest_seconds],
  ['unmeasured capacity claim',(_v,_c,m)=>m.swimming.current_capacity_measured=true],
])test(`swimming rejects ${name}`,async()=>{
  const v=structuredClone(f.swim_recent_review),c=firstSwim(v),m=v.result.prescription_context.by_candidate[c.candidate_key];edit(v,c,m);
  await assert.rejects(()=>validateSwimmingCandidate(v,c,m));
});
test('the shorter continuous report uses whole lengths with explicit rest',()=>{
  const c=firstSwim(f.swim_repeats_review),m=f.swim_repeats_review.result.prescription_context.by_candidate[c.candidate_key];
  assert.equal(m.swimming.mode,'length_repeats');assert.equal(m.swimming.lengths_per_repeat,2);assert.equal(m.swimming.rest_seconds,30);
  assert.match(c.blocks[1].name,/2 medencehossz/);assert.equal(c.duration_sec,1200);
});
test('sport summary verifies its weekly basis against the actual shared budget',()=>{
  validateSportAvailability(f.mixed_review.result);
  const r=structuredClone(f.mixed_review.result);r.preparation.sport_availability.weekly_budget.max_minutes_per_7_days++;
  assert.throws(()=>validateSportAvailability(r));
});
test('settings and swimming details provide the actual next action and source',()=>{
  const data=f.mixed_options.data,html=renderToStaticMarkup(React.createElement(Settings,{data,today:'2026-10-23',disabled:false,save:async()=>true}));
  assert.match(html,/Terhelési és úszási adatok mentése/);assert.match(html,/szokásos edzésszám/);assert.match(html,/medence pontos hosszát/);
  const c=firstSwim(f.swim_recent_review),details=renderToStaticMarkup(React.createElement(PrescriptionDetails,{review:f.swim_recent_review,candidateKey:c.candidate_key}));
  assert.match(details,/33.333333 méteres medence/);assert.match(details,/nem mért aktuális/);
  const summary=renderToStaticMarkup(React.createElement(Details,{value:f.mixed_review.result.preparation.sport_availability}));
  assert.match(summary,/6 edzés, 450 perc/);assert.match(summary,/most megadott szokásos/);assert.match(summary,/athlete-setup#sports/);
});
for(const change of [s=>s.current_baseline.weekly_sessions=true,s=>s.swimming.preferred_stroke='unknown',s=>s.current_baseline.from_date='2026-10-22'])
  test('invalid or ambiguous self-report fails before sending',()=>{
    const settings=structuredClone(f.mixed_options.data.prescription_settings);change(settings);assert.throws(()=>readPrescriptionSettings(settings));
  });
test('map projection round-trips user-selected coordinates without inventing a location',()=>{
  for(const [lat,lon,z] of [[47.8,17.6,7],[-33.86,151.2,10],[0,0,4]]){
    const [x,y]=mapPixel(lat,lon,z),[a,b]=mapCoordinate(x,y,z);
    assert(Math.abs(a-lat)<1e-6&&Math.abs(b-lon)<1e-6);
  }
});
test('spacing distinguishes strength, upper-body water sports and unknown intensity',()=>{
  assert.equal(spacingHours('STRENGTH','STRENGTH',true),48);
  assert.equal(spacingHours('SWIMMING','KAYAK',true),24);
  assert.equal(spacingHours('RUNNING','SWIMMING',true),12);
  assert.equal(spacingHours('RUNNING','SWIMMING',false),36);
});
