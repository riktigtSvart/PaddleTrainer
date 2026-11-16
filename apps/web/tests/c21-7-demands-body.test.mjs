import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-7-demands-body.json',import.meta.url)));
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const b=load('src/lib/athlete-setup/body-mass.ts');
const {demandSuggestion,autoEventProfile}=load('src/lib/planning-cycles/event-demands.ts');
const {checkedSuggestion}=load('src/lib/planning-cycles/goal-suggestions.ts');
const {readPlanningInputs}=load('src/lib/planning-cycles/inputs.ts');
const {default:EventProfile}=load('src/components/planning-cycles/event-profile-editor.tsx');
const {forwardGoals}=load('src/lib/planning-goals/proxy.ts');
const {editingProfile}=load('src/lib/planning-data/profile-state.ts');
const capture=f.capture,m=capture.goal_suggestions.macrocycles[0],period=capture.periods.find(p=>p.id===m.macrocycle_period_id),children=capture.periods.filter(p=>p.parent_id===period.id);
const check=v=>checkedSuggestion(v,period,children,Object.keys(capture.competitions[0].profile.capability_weights),m.base_reference?{reference:m.base_reference,revision:m.base_revision}:undefined);
const rehash=async v=>{delete v.content_hash;v.content_hash=await sha(v);return v;};
test('actual 10 km HTTP capture verifies all demand priorities and shared mass without a write claim',async()=>{
 await readPlanningInputs(capture,{owner:f.owner,reference:capture.program_reference,zone:capture.timezone_name,first:capture.start_date,last:capture.end_date});
 assert.equal(check(capture).rows.length,13);assert.equal(capture.body_mass.current.value_kg,'116.900');
 const p=capture.competitions[0].profile;assert.deepEqual(demandSuggestion(p,'Kajak').weights,p.capability_weights);
 const legacy={...p,capability_basis:'unassessed',capability_keys:[]};delete legacy.capability_weights;
 assert.deepEqual(autoEventProfile(legacy,'Kajak'),p);
 assert.equal(autoEventProfile({...legacy,distance_value:'10000',distance_unit:'m'},'Kajak').capability_weights.MUSCULAR_ENDURANCE,5);
 const html=renderToStaticMarkup(React.createElement(EventProfile,{value:legacy,index:0,sport:'Kajak',change(){}}));
 assert.match(html,/automatikus|Automatikus/);assert.match(html,/1–5/);assert.match(html,/1766347/);
});
for(const [name,change] of [['foreign event priority',v=>v.goal_suggestions.macrocycles[0].rows[0].demand_priority=1],['training percentage claim',v=>v.goal_suggestions.strategy.demand_priorities.training_percentages=true],['unknown weight rules',v=>v.goal_suggestions.strategy.demand_priorities.version='future'],['missing competition evidence',v=>v.competitions=[]]])test('weighted review rejects '+name,()=>{const v=structuredClone(capture);change(v);assert.throws(()=>check(v));});
test('manual priorities survive automatic suggestions and unrelated sport gets no paddling default',()=>{
 const p={...capture.competitions[0].profile,capability_basis:'coach_declared'};assert.deepEqual(autoEventProfile(p,'Kajak'),p);assert.equal(demandSuggestion({...p,discipline:'Országút'},'Futás'),null);
});
test('real body state and goal receipt retain all exact observations and independent target',async()=>{
 assert.deepEqual(await b.readBodyState(f.state,f.owner),f.state);assert.deepEqual(await b.readBodyState(f.after,f.owner),f.after);
 assert.equal(f.after.nutrition_goal.proposal.target_kg,'110.00');assert.equal(f.after.current.value_kg,'116.900');assert.deepEqual(f.after.items,f.state.items);
 const profile=editingProfile({profile:{artifact:{proposal:{data:{body_mass_kg:'118',body_mass_recorded_on:'2026-10-19'}}}},body_mass:capture.body_mass});
 assert.equal(profile.body_mass_kg,'116.900');assert.equal(profile.body_mass_recorded_on,'2026-10-21');
});
for(const [name,change] of [['foreign owner',v=>v.athlete_id='00000000-0000-4000-8000-000000000000'],['truncated history',v=>v.items.pop()],['duplicate history',v=>v.items[1]=v.items[0]],['future measurement',v=>v.items[1].recorded_on='2099-01-01'],['invented zero',v=>v.current.value_kg='0'],['goal as actual measurement',v=>v.nutrition_goal=f.mass_receipt.artifact]])test('body reader rejects rehashed '+name,async()=>{const v=structuredClone(f.after);change(v);await rehash(v);await assert.rejects(b.readBodyState(v,f.owner));});
test('pending survives byte for byte; receipt from another operation or request cannot resolve it',async()=>{
 const pending={version:'body-pending-v0.1',owner:f.owner,operation:'body-mass',body:JSON.stringify(f.mass_receipt.artifact.proposal,null,2)};
 assert.equal(b.readBodyPending(JSON.stringify(pending),f.owner).body,pending.body);assert.throws(()=>b.readBodyPending(JSON.stringify(pending),'other'));
 const old=globalThis.fetch;const sent=[];
 try{
  globalThis.fetch=async(url,init)=>{sent.push(init.body);return Response.json(f.goal_receipt);};await assert.rejects(b.sendBody(pending));
  globalThis.fetch=async(url,init)=>{sent.push(init.body);return Response.json(f.mass_receipt);};await b.sendBody(pending);await b.sendBody(pending);assert(sent.every(v=>v===pending.body));
  const altered={...pending,body:JSON.stringify({...JSON.parse(pending.body),value_kg:'117'})};await assert.rejects(b.sendBody(altered));
 }finally{globalThis.fetch=old;}
});
for(const [method,path,query,status] of [['GET','body-mass','?limit=100&offset=0',200],['POST','body-mass','',200],['POST','nutrition-goal','',200],['GET','nutrition-goal','',405],['DELETE','body-mass','',405],['GET','body-mass','?owner=evil',422],['GET','body-mass','?limit=1&limit=2',422],['POST','nutrition-goal','?url=evil',422]])test('closed body boundary '+method+' '+path+query,async()=>{
 let called=0;const headers=method==='POST'?{'Content-Type':'application/json',Origin:'https://paddle.test'}:{};
 const response=await forwardGoals(new Request('https://paddle.test/api/goal-workflow/athlete/'+path+query,{method,headers,body:method==='POST'?'{}':undefined}),['athlete',path],'http://backend.test',async(url,init)=>{called++;assert.equal(init.headers.Authorization,undefined);return Response.json({ok:true});});
 assert.equal(response.status,status);assert.equal(called,status===200?1:0);
});
