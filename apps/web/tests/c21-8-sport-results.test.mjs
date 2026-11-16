import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(readFileSync(new URL('./fixtures/c21-8-sport-results.json',import.meta.url)));
const history=load('src/lib/athlete-setup/sport-history.ts'),athlete=load('src/lib/athlete-setup/contracts.ts');
const {profileChanges}=load('src/lib/planning-data/profile-state.ts');
const Fields=load('src/components/athlete-setup/performance-fields.tsx').default;
const results=f.request.data.sport_history[0].performances, today=f.context.local_today;
const render=row=>renderToStaticMarkup(React.createElement(Fields,{value:row,change(){}}));
test('real Python receipt retains old distance results, Cooper, 1RM and both repetition formats exactly',async()=>{
 await athlete.readReceipt(f.receipt,{schema_version:'athlete-pending-v0.1',operation:'profiles',body:JSON.stringify(f.request)});
 await athlete.readContext(f.context);
 const raw=f.receipt.artifact.proposal.data;
 assert.deepEqual(athlete.normalizeProfile(raw,today),raw);
 assert.deepEqual(raw.sport_history[0].performances,results);
 assert.equal(results[2].load_kg,'100.500');assert.equal(results[3].repetitions,0);
 assert.equal(results[0].protocol,undefined);
});
test('Cooper has fixed read-only 12:00 and a distance result field',()=>{
 const html=render(results[1]);assert.match(html,/Cooper-teszt időtartama/);assert.match(html,/readOnly=""[^>]*value="12:00"|value="12:00"[^>]*readOnly/);assert.match(html,/12 perc alatt megtett táv/);
 assert.throws(()=>history.normalizePerformance({...results[1],time:'11:59'},today));
});
test('strength maximum has kilograms and one repetition while bodyweight repeats require no weight choice',()=>{
 const max=render(results[2]),body=render(results[3]);
 assert.match(max,/Teljesített maximális súly \(kg\)/);assert.match(max,/rögzített 1RM/);assert.doesNotMatch(max,/label="Időeredmény|Táv \(méter\)|>Időeredmény \(/);
 assert.match(body,/hozzáadott külső súly nélkül/);assert.match(body,/value="0"/);assert.doesNotMatch(body,/A próbában használt külső súly \(kg\)/);
});
test('timed repetition result preserves clock, count and added load as different fields',()=>{
 const row={...results[4],time:' 1:20,500 ',repetitions:23,load_kind:'external_kg',load_kg:'10,750',load_basis:'additional_to_bodyweight'};
 const out=history.normalizePerformance(row,today);assert.equal(out.time,'1:20.500');assert.equal(out.repetitions,23);assert.equal(out.load_kg,'10.750');assert.equal(out.load_basis,'additional_to_bodyweight');
 assert.match(render(out),/Próba időtartama/);assert.equal(out.distance_m,undefined);
});
for(const [name,row] of [['unknown repetitions',{...results[3],repetitions:undefined}],['boolean repetitions',{...results[3],repetitions:true}],['fractional repetitions',{...results[3],repetitions:2.5}],['invented time on 1RM',{...results[2],time:'1:00'}],['two-rep 1RM',{...results[2],repetitions:2}],['missing exercise',{...results[3],exercise:''}],['invented bodyweight zero kilograms',{...results[3],load_kg:'0'}]])test('result rejects '+name,()=>assert.throws(()=>history.normalizePerformance(row,today)));
test('protocol switches retain identity and historical date and remove fields belonging to the old result kind',()=>{
 const changed=history.changePerformanceProtocol(results[1],'strength_1rm');assert.equal(changed.result_id,results[1].result_id);assert.equal(changed.year,2000);assert.equal(changed.recorded_on,null);assert.equal(changed.time,undefined);assert.equal(changed.distance_m,undefined);assert.equal(changed.repetitions,1);
 const back=history.changePerformanceProtocol(results[2],'cooper_12min');assert.equal(back.time,'12:00');assert.equal(back.exercise,undefined);assert.equal(back.load_kg,undefined);
});
test('a profile with different JSON key order does not claim an unsaved personal or sports change',()=>{
 const p=f.receipt.artifact.proposal.data, reordered=Object.fromEntries(Object.entries(p).reverse());
 assert.notEqual(JSON.stringify(p),JSON.stringify(reordered));assert.deepEqual(profileChanges(p,reordered),{personal:false,sports:false,history:false});
 const changed=structuredClone(p);changed.sport_history[0].performances[3].repetitions=12;
 assert.deepEqual(profileChanges(changed,p),{personal:false,sports:true,history:false});
});
const {mergeAssessmentAnswers}=load('src/lib/initial-assessment/draft-sync.ts');
const initial=JSON.parse(readFileSync(new URL('./fixtures/initial-assessment.json',import.meta.url))).request.data;
test('refreshing saved assessment results retains unfinished answers and independent new result sets',()=>{
 const base=structuredClone(initial),draft=structuredClone(initial),saved=structuredClone(initial);
 draft.state_notes='Saját még mentetlen megjegyzés';draft.exercises[0].notes='Eltérő fogás';
 const oldSet=structuredClone(saved.exercises[0].sets[0]);oldSet.id=crypto.randomUUID();oldSet.load_value='13.500';saved.exercises[0].sets.push(oldSet);
 saved.exercises[1].performed_on='2026-10-21';
 const result=mergeAssessmentAnswers(base,draft,saved);
 assert.equal(result.state_notes,draft.state_notes);assert.equal(result.exercises[0].notes,draft.exercises[0].notes);
 assert.equal(result.exercises[0].sets.length,base.exercises[0].sets.length+1);assert.equal(result.exercises[1].performed_on,'2026-10-21');
 assert.equal(base.exercises[0].sets.length,initial.exercises[0].sets.length);
});
test('an explicit fresh-source rebase can retain independent local and newly saved set IDs together',()=>{
 const base=structuredClone(initial),draft=structuredClone(initial),saved=structuredClone(initial);
 const own=structuredClone(draft.exercises[0].sets[0]);own.id=crypto.randomUUID();own.repetitions=10;draft.exercises[0].sets.push(own);
 const external=structuredClone(saved.exercises[0].sets[0]);external.id=crypto.randomUUID();external.repetitions=7;saved.exercises[0].sets.push(external);
 const result=mergeAssessmentAnswers(base,draft,saved);
 assert(result.exercises[0].sets.some(v=>v.id===own.id));assert(result.exercises[0].sets.some(v=>v.id===external.id));
 assert.equal(new Set(result.exercises[0].sets.map(v=>v.id)).size,result.exercises[0].sets.length);
});
test('rebasing later saved assessment results retains the newer review date and every original measurement day',()=>{
 const old=structuredClone(initial),draft=structuredClone(initial),saved=structuredClone(initial);
 old.assessment_date='2026-10-22';draft.assessment_date='2026-10-23';old.last_strength_date='2026-10-22';draft.last_strength_date='2026-10-22';
 for(const x of [...old.exercises,...draft.exercises])if(x.performed_on)x.performed_on='2026-10-22';
 for(const x of [...old.sport_references,...draft.sport_references])if(x.performed_on)x.performed_on='2026-10-22';
 draft.state_notes='Saját még mentetlen megjegyzés';
 saved.assessment_date='2026-11-11';saved.last_strength_date='2026-11-11';saved.exercises[0].performed_on='2026-11-11';
 const merged=mergeAssessmentAnswers(old,draft,saved);
 assert.equal(merged.assessment_date,'2026-11-11');assert.equal(merged.exercises[0].performed_on,'2026-11-11');assert.equal(merged.state_notes,draft.state_notes);
 assert.equal(old.assessment_date,'2026-10-22');assert.equal(saved.exercises[0].performed_on,'2026-11-11');
 assert.doesNotThrow(()=>load('src/lib/initial-assessment/contracts.ts').normalizeData(merged));
});
const {assessmentSaveData,AssessmentSaveInputError}=load('src/lib/initial-assessment/save-validation.ts');
for (const date of ['', '2026-02-30','2026-11-12']) test('an invalid or future review date points to step 1 before any request: '+date,()=>{
 const value={...structuredClone(initial),assessment_date:date};
 assert.throws(()=>assessmentSaveData(value,'2026-11-11'),e=>e instanceof AssessmentSaveInputError && e.step===0);
});
test('an outdated review date explains both real dates without rewriting observations',()=>{
 const value=structuredClone(initial);value.assessment_date='2026-10-23';value.exercises[0].performed_on='2026-11-11';
 const before=JSON.stringify(value);
 assert.throws(()=>assessmentSaveData(value,'2026-11-11'),e=>e instanceof AssessmentSaveInputError && e.step===0 && /2026-10-23/.test(e.message) && /2026-11-11/.test(e.message));
 assert.equal(JSON.stringify(value),before);
});
test('a later user-entered review date survives rebasing while precise reference values remain unchanged',()=>{
 const old=structuredClone(initial),local=structuredClone(initial),saved=structuredClone(initial);
 local.assessment_date='2026-11-11';saved.assessment_date='2026-11-10';
 const merged=mergeAssessmentAnswers(old,local,saved),normalized=assessmentSaveData(merged,'2026-11-11');
 assert.equal(normalized.assessment_date,'2026-11-11');assert.equal(normalized.exercises[0].sets[0].load_value,initial.exercises[0].sets[0].load_value);
});
const {restoreAssessmentDraft}=load('src/lib/initial-assessment/draft-sync.ts');
function oldConflictingDraft(){
 const saved=structuredClone(initial);saved.assessment_date='2026-11-11';saved.exercises[0].performed_on='2026-11-11';
 const data={...structuredClone(saved),assessment_date:'2026-10-24',state_notes:'Megőrzendő saját válasz'};
 const draft={version:'initial-assessment-draft-v0.1',owner:f.context.athlete_id,data,source_hash:'a'.repeat(64),previous_reference:null,open:5};
 return {saved,draft};
}
test('an already persisted C21.8 date conflict can reopen with its results intact',()=>{
 const {saved,draft}=oldConflictingDraft(),raw=JSON.stringify(draft);
 const result=restoreAssessmentDraft(raw,draft.owner,saved);
 assert.equal(result.recovered,true);assert.equal(result.draft.data.assessment_date,'2026-11-11');
 assert.equal(result.draft.data.exercises[0].performed_on,'2026-11-11');assert.equal(result.draft.data.state_notes,'Megőrzendő saját válasz');
 assert.equal(result.draft.source_hash,draft.source_hash);assert.deepEqual(result.draft.data.exercises,draft.data.exercises);
 assert.equal(JSON.stringify(draft),raw);
});
test('date recovery still rejects another owner, malformed observations or missing saved evidence',()=>{
 const {saved,draft}=oldConflictingDraft();
 assert.throws(()=>restoreAssessmentDraft(JSON.stringify(draft),crypto.randomUUID(),saved));
 assert.throws(()=>restoreAssessmentDraft(JSON.stringify(draft),draft.owner,null));
 draft.data.exercises[0].sets[0].repetitions=true;
 assert.throws(()=>restoreAssessmentDraft(JSON.stringify(draft),draft.owner,saved));
});
test('a valid older draft opens unchanged and is only rebased through the explicit source action',()=>{
 const {saved,draft}=oldConflictingDraft();draft.data=structuredClone(initial);
 const raw=JSON.stringify(draft),result=restoreAssessmentDraft(raw,draft.owner,saved);
 assert.equal(result.recovered,false);assert.deepEqual(result.draft.data,draft.data);assert.equal(JSON.stringify(draft),raw);
});
