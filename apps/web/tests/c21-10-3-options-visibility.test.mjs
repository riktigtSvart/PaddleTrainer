import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {load} from './load-goal-modules.mjs';

const v=load('src/lib/calendar/visibility.ts');
const sync=load('src/lib/training-options/synchronization.ts');
const fixture=JSON.parse(readFileSync(new URL('./fixtures/training-options.json',import.meta.url)));
const owner=fixture.context.athlete_id;

test('four calendar views and different athletes have independent persistent keys',()=>{
  const store=new Map(),other=crypto.randomUUID();
  for(const [i,span] of [1,7,28,168].entries()){
    const value=v.defaultVisibility();value.layers.availability=i%2===0;value.layers.commitments=i>1;value.layers.preparation=i===0;value.fullDay=i===1;
    store.set(v.visibilityKey(owner,span),v.writeVisibility(owner,span,value));
  }
  assert.equal(store.size,4);
  for(const [i,span] of [1,7,28,168].entries()){
    const actual=v.readVisibility(store.get(v.visibilityKey(owner,span)),owner,span);
    assert.equal(actual.layers.availability,i%2===0);assert.equal(actual.layers.commitments,i>1);assert.equal(actual.fullDay,i===1);
    assert.deepEqual(v.readVisibility(store.get(v.visibilityKey(other,span))??null,other,span),v.defaultVisibility());
  }
  assert.equal(v.visibilityKey(null,7),null);
});
test('missing settings use fresh defaults without sharing mutable objects',()=>{
  const first=v.readVisibility(null,owner,7);first.layers.planned=false;
  assert.equal(v.readVisibility(null,owner,7).layers.planned,true);
  assert.equal(v.visibilityKey(owner,144),null);
});
for(const [name,change] of [
  ['different owner',x=>x.owner=crypto.randomUUID()],
  ['different view',x=>x.span=1],
  ['unknown schema',x=>x.schema_version='future'],
  ['missing layer',x=>delete x.layers.preparation],
  ['string checkbox',x=>x.layers.planned='false'],
  ['non-boolean hours',x=>x.fullDay=1],
])test('visibility rejects '+name,()=>{
  const raw=JSON.parse(v.writeVisibility(owner,7,v.defaultVisibility()));change(raw);
  assert.throws(()=>v.readVisibility(JSON.stringify(raw),owner,7));
});
test('a newer location changes metadata but does not replace an unsaved general timetable',()=>{
  const base=structuredClone(fixture.context.data),next=structuredClone(base);
  next.locations.push({...structuredClone(base.locations[0]),id:crypto.randomUUID(),name:'Új teszthelyszín'});
  assert.deepEqual(sync.scheduleContent(next),sync.scheduleContent(base));
  const draft=structuredClone(base);draft.weekly_slots[0].details.start_time='17:00';
  const saved={...next,...sync.scheduleContent(draft)};
  assert(saved.locations.some(l=>l.name==='Új teszthelyszín'));
  assert.equal(saved.weekly_slots[0].details.start_time,'17:00');
  assert.deepEqual(saved.restrictions,next.restrictions);
});
test('readback cannot move behind a confirmed save or substitute a same-revision fork',()=>{
  const head=sync.optionsHead(fixture.context);
  sync.requireFreshOptions(head,head);
  assert.throws(()=>sync.requireFreshOptions({...head,revision:head.revision-1},head));
  assert.throws(()=>sync.requireFreshOptions({...head,reference:{...head.reference,content_hash:'f'.repeat(64)}},head));
  sync.requireFreshOptions({...head,revision:head.revision+1},head);
  sync.requireFreshOptions({...head,owner:crypto.randomUUID(),revision:0,reference:null},head);
  assert.equal(sync.receiptHead(fixture.context.saved).revision,head.revision);
});
