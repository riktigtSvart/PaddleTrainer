import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/training-options.json',import.meta.url)));
const d=load('src/lib/training-options/schedule-draft.ts');
const v=load('src/lib/training-options/slot-validation.ts');
const {scheduleContent}=load('src/lib/training-options/synchronization.ts');
const {readOptionsData}=load('src/lib/training-options/contracts.ts');
const SlotFields=load('src/components/training-options/slot-fields.tsx').default;
const owner=f.context.athlete_id,zone=f.context.timezone_name,data=f.context.data,today=f.context.local_today;
const details={...structuredClone(data.weekly_slots[0].details),start_time:'18:30',end_time:'20:00',max_minutes:120};

test('the exact Thursday failure identifies 120 minutes in a 90 minute window',()=>{
  assert.equal(v.slotWindowMinutes(details),90);
  const text=v.slotProblem(details,data.locations);
  for(const value of ['18:30','20:00','90','120'])assert(text.includes(value));
  assert.equal(v.slotProblem({...details,max_minutes:90},data.locations),null);
  assert.equal(v.slotProblem({...details,start_time:'05:15',end_time:'06:15',max_minutes:57},data.locations),null);
});
test('slot validation retains overnight and repeated-hour rules',()=>{
  assert.equal(v.slotWindowMinutes({...details,start_time:'23:00',end_time:'01:00',ends_next_day:true}),120);
  assert.equal(v.slotWindowMinutes({...details,start_time:'23:00',end_time:'01:00',ends_next_day:false}),null);
  assert.equal(v.slotWindowMinutes({...details,start_time:'02:45',end_time:'02:15',start_fold:0,end_fold:1}),30);
  assert.equal(v.slotWindowMinutes({...details,start_time:'',end_time:'20:00'}),null);
  assert(v.slotProblem({...details,max_minutes:90,location_ids:[]},data.locations).includes('helyszínt'));
});
test('the actual form exposes a specific correction and the native 90 minute maximum',()=>{
  const html=renderToStaticMarkup(React.createElement(SlotFields,{value:details,locations:data.locations,onChange(){}}));
  assert(html.includes('max="90"'));assert(html.includes('aria-invalid="true"'));
  assert(html.includes('Edzéskeret igazítása 90 percre'));
  assert(html.includes('A megadott 120 perc nem fér bele'));
});
function unfinished(){
  const state=d.initialScheduleDraft(data,today);
  state.draft.weekly_slots[0].details.max_minutes=30;
  state.editing={...structuredClone(state.draft.weekly_slots[0]),id:crypto.randomUUID(),weekdays:[3],details:structuredClone(details)};
  return state;
}
test('adopted earlier work and the invalid unfinished Thursday editor round-trip exactly',()=>{
  const state=unfinished(),copy=structuredClone(state),raw=d.writeScheduleDraft(state,owner,zone);
  const restored=d.readScheduleDraft(raw,owner,zone);
  assert.deepEqual(restored,state);assert.deepEqual(state,copy);
  assert(d.scheduleDraftDirty(restored));
  assert.equal(restored.editing.details.max_minutes,120);
  assert.equal(restored.editing.weekdays[0],3);
  assert.throws(()=>readOptionsData({...data,...restored.draft,weekly_slots:[...restored.draft.weekly_slots,restored.editing]}));
});
test('new location metadata does not reset the recovered general schedule',()=>{
  const state=unfinished(),current=structuredClone(data);
  current.locations.push({...structuredClone(data.locations[0]),id:crypto.randomUUID(),name:'Új helyszín'});
  assert.deepEqual(d.reconcileScheduleDraft(state,current,today),state);
  const changed=structuredClone(current);changed.weekly_slots[0].details.notes='Másik órarendváltozat';
  assert.deepEqual(d.reconcileScheduleDraft(state,changed,today),state,'Conflicting draft must remain available');
});
test('verified saved data retires adopted work while preserving a newer open editor',()=>{
  const state=unfinished(),current={...data,...structuredClone(state.draft)};
  const restored=d.reconcileScheduleDraft(state,current,today);
  assert(!d.scheduleDraftDirty(restored));assert.deepEqual(restored.editing,state.editing);
  assert.deepEqual(restored.source,scheduleContent(current));
  const complete=d.reconcileScheduleDraft({...state,editing:null},current,today);
  assert(!d.scheduleDraftDirty(complete));assert.equal(complete.editing,null);
});
for(const [name,change] of [
  ['foreign owner',x=>x.owner=crypto.randomUUID()],
  ['other timezone',x=>x.timezone_name='UTC'],
  ['unknown schema',x=>x.schema_version='future'],
  ['hidden location changes',x=>x.draft.locations=[]],
  ['boolean minute budget',x=>x.editing.details.max_minutes=true],
  ['duplicate slots',x=>x.draft.weekly_slots.push(structuredClone(x.draft.weekly_slots[0]))],
  ['bad slot identity',x=>x.editing.id='not-an-id'],
])test('local draft rejects '+name,()=>{
  const raw=JSON.parse(d.writeScheduleDraft(unfinished(),owner,zone));change(raw);
  assert.throws(()=>d.readScheduleDraft(JSON.stringify(raw),owner,zone));
});
test('draft preservation permits incomplete input without treating it as a valid proposal',()=>{
  const state=unfinished();state.editing.details.start_time='';state.editing.details.max_minutes=0;state.editing.details.location_ids=[];
  const restored=d.readScheduleDraft(d.writeScheduleDraft(state,owner,zone),owner,zone);
  assert.equal(restored.editing.details.start_time,'');assert.equal(restored.editing.details.max_minutes,0);
  assert(v.slotProblem(restored.editing.details,data.locations));
  assert.notEqual(d.scheduleDraftKey(owner,zone),d.scheduleDraftKey(crypto.randomUUID(),zone));
  assert.equal(d.scheduleDraftKey(undefined,zone),null);
});
