import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { load } from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-9-daylight.json',import.meta.url)));
const { readDaylightPreview, readDaylightContext, validateDaylightReview }=load('src/lib/training-options/daylight.ts');
const { readCoordinates, readDaylightRules, decimalCoordinate }=load('src/lib/training-options/daylight-rules.ts');
const { lightIntervals }=load('src/lib/training-options/solar.ts');
const { readOptionsContext, readOptionsReceipt, readPending }=load('src/lib/training-options/contracts.ts');
const { readTrainingReview }=load('src/lib/planning-cycles/training-plan.ts');
const { sha }=load('src/lib/planning-cycles/contracts.ts');
const { forwardGoals }=load('src/lib/planning-goals/proxy.ts');
const owner=f.context.athlete_id, point=f.preview.request.coordinates;

test('real durable geographic receipt, context and pending retry retain exact coordinates and light rules',async()=>{
  await readOptionsReceipt(f.receipt,owner,JSON.stringify(f.receipt.artifact.proposal));
  const c=await readOptionsContext(f.context);assert.deepEqual(c.data.locations[0].coordinates,point);
  const pending={version:'training-options-pending-v0.1',owner,body:JSON.stringify({...f.receipt.artifact.proposal,request_id:crypto.randomUUID(),previous_reference:c.reference,data:c.data})};assert.equal(readPending(JSON.stringify(pending)).body,pending.body);
  assert.equal(JSON.parse(pending.body).data.locations[0].coordinates.latitude,'47.5');
});
for(const sample of [{...f.preview.request,result:f.preview},...f.solar_cases])test(`Python and browser solar calculation agree for ${sample.date}, ${sample.coordinates.timezone_name}, ${sample.coordinates.latitude}`,async()=>{
  const r=await readDaylightPreview(sample.result,owner,{date:sample.date,coordinates:sample.coordinates});
  assert.equal(r.method,'noaa-meeus-light-v1');
});
for(const [name,edit]of[
  ['other owner',v=>v.athlete_id='00000000-0000-0000-0000-000000000001'],
  ['edited solar time',v=>v.result.daylight.sets_at[0]='2026-11-12T20:00:00+00:00'],
  ['future method',v=>v.result.method='future'],
  ['false polar day',v=>v.result.daylight.state='all_day'],
  ['expanded allowed interval',v=>v.result.daylight.intervals[0].end_at='2026-11-12T21:00:00+00:00'],
  ['wrong local date',v=>v.result.day_start_at='2026-11-12T23:00:00+00:00'],
])test(`a rehashed solar preview cannot conceal ${name}`,async()=>{
  const v=structuredClone(f.preview);edit(v);delete v.content_hash;v.content_hash=await sha(v);
  await assert.rejects(()=>readDaylightPreview(v,owner,f.preview.request));
});
test('body and source ownership stay exact; an unknown coordinate never becomes zero',async()=>{
  await assert.rejects(()=>readDaylightPreview(f.preview,owner,{...f.preview.request,coordinates:{...point,latitude:'0'}}));
  assert.equal(readCoordinates({...point,latitude:'0',longitude:'0'}).latitude,'0');
  for(const latitude of [0,true,'','90.01','NaN','1e1'])assert.throws(()=>readCoordinates({...point,latitude}));
  assert.equal(decimalCoordinate(' -33,8688 '),'-33.8688');
  assert.throws(()=>readDaylightRules([f.context.data.daylight_rules[0],f.context.data.daylight_rules[0]]));
  assert.throws(()=>readDaylightRules([{...f.context.data.daylight_rules[0],start_buffer_minutes:true}]));
  await assert.rejects(()=>readDaylightContext(f.day_review.inputs,'00000000-0000-0000-0000-000000000001'));
});
test('actual daytime and excluded-night training reviews remain readable with independently replayed light limits',async()=>{
  for(const review of [f.day_review,f.night_review])await readTrainingReview(review,{owner,reference:review.program_reference,zone:review.timezone_name});
  assert(f.day_review.result.proposals.length);assert.equal(f.night_review.result.proposals.length,0);
});
test('a session starting in daylight but ending after the permitted boundary is rejected',async()=>{
  const v=structuredClone(f.day_review), c=v.result.proposals[0];
  c.start_at='2026-10-24T14:00:00+00:00';c.end_at='2026-10-24T20:00:00+00:00';
  await assert.rejects(()=>validateDaylightReview(v));
  const rule=f.context.data.daylight_rules[0],a=Date.parse('2026-11-12T14:00:00Z')/1000,b=Date.parse('2026-11-12T15:30:00Z')/1000;
  assert(!lightIntervals(a,b,point,rule).some(([x,y])=>x<=a&&y>=b));
});
test('preview proxy accepts only the exact POST path, no query, same-origin request',async()=>{
  let calls=0;const send=async(url,init)=>{calls++;assert.equal(new URL(url).pathname,'/api/v1/planning/training-options/daylight/preview');assert.equal(init.method,'POST');return Response.json(f.preview);};
  const headers={'Content-Type':'application/json',Origin:'https://paddle.test'};
  const path=['training-options','daylight','preview'],url='https://paddle.test/api/goal-workflow/'+path.join('/');
  assert.equal((await forwardGoals(new Request(url,{method:'POST',headers,body:JSON.stringify(f.preview.request)}),path,'http://backend.test',send)).status,200);
  assert.equal((await forwardGoals(new Request(url),path,'http://backend.test',send)).status,405);
  assert.equal((await forwardGoals(new Request(url+'?coordinates=0',{method:'POST',headers,body:'{}'}),path,'http://backend.test',send)).status,422);
  assert.equal((await forwardGoals(new Request(url,{method:'POST',headers:{...headers,Origin:'https://other.test'},body:'{}'}),path,'http://backend.test',send)).status,403);
  assert.equal(calls,1);
});
test('venue form exposes labelled geographic fields, solar preview and per-sport override controls',()=>{
  const {CoordinatesEditor,RuleFields}=load('src/components/training-options/daylight-settings.tsx');
  const html=renderToStaticMarkup(React.createElement(CoordinatesEditor,{value:point,defaultZone:point.timezone_name,owner,today:'2026-11-12',disabled:false,onChange(){},rules:[]}));
  assert.match(html,/Földrajzi szélesség/);assert.match(html,/Földrajzi hosszúság/);assert.match(html,/Helyszín időzónája/);assert.match(html,/Napfényidők ellenőrzése/);
  const rules=renderToStaticMarkup(React.createElement(RuleFields,{rules:[],sports:['KAYAK','STRENGTH'],defaults:[],disabled:false,onChange(){}}));
  assert.match(rules,/Sportági alapbeállítás/);assert.match(rules,/Kondi · napfény/);
});
