import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {load} from './load-goal-modules.mjs';
const data=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-16-alternative-deadlines.json.gz',import.meta.url))));
const {readTrainingReview}=load('src/lib/planning-cycles/training-plan.ts');
const {alternativeExpired,remainingAlternatives,goalImpact,goalRoleLabels}=load('src/lib/planning-cycles/alternative-availability.ts');
const {workoutVariant}=load('src/lib/calendar/alternative-variants.ts');
const {canonical,sha}=load('src/lib/planning-cycles/contracts.ts');
const check=r=>readTrainingReview(r,{owner:r.athlete_id,reference:r.program_reference,zone:r.timezone_name});
const candidates=r=>r.result.alternatives.find(g=>g.date==='2026-10-26').candidates;
const morning=r=>candidates(r).filter(c=>new Date(c.start_at).getUTCHours()<9);
for(const name of ['early','retimed','after_long_expiry'])test(`real API ${name}: independent deadlines and saved goal roles verify without rewriting evidence`,async()=>{
 const r=data[name],before=canonical(r);await check(r);assert.equal(canonical(r),before);
});
test('a passed suggested start is not an expired alternative',()=>{
 const r=data.early,c=morning(r).find(c=>c.sport==='STRENGTH'),timing=r.result.alternative_availability.by_candidate[c.candidate_key];
 const now=Date.parse(c.start_at)+1000;assert(now<Date.parse(timing.expires_at));assert.equal(alternativeExpired(r,c,now),false);
 assert.equal(alternativeExpired(r,c,Date.parse(timing.expires_at)),false);assert.equal(alternativeExpired(r,c,Date.parse(timing.expires_at)+1),true);
});
test('each duration expires independently and surviving options receive a new recommendation',()=>{
 const r=data.early,rows=morning(r),long=rows.reduce((a,b)=>a.duration_sec>b.duration_sec?a:b),short=rows.find(c=>c.sport==='STRENGTH');
 const now=Date.parse(r.result.alternative_availability.by_candidate[long.candidate_key].expires_at)+1;
 const result=remainingAlternatives(r,rows,long.candidate_key,long.capability_key,now);
 assert(!result.candidates.some(c=>c.candidate_key===long.candidate_key));assert(result.candidates.some(c=>c.candidate_key===short.candidate_key));
 assert.notEqual(result.recommended,long.candidate_key);assert(result.candidates.some(c=>c.candidate_key===result.recommended));
 assert(result.expiredCount>0);assert.equal(canonical(r),canonical(data.early));
});
test('a fallback ranks the saved main goal before a secondary or maintenance goal',()=>{
 const r=data.early,rows=morning(r),long=rows.reduce((a,b)=>a.duration_sec>b.duration_sec?a:b),base=rows.find(c=>c.sport==='STRENGTH');
 const main={...base,candidate_key:'main',role:'primary_development'},secondary={...base,candidate_key:'secondary',role:'secondary_development'},maintained={...base,candidate_key:'maintained',role:'maintenance'};
 const timing=r.result.alternative_availability.by_candidate[base.candidate_key],copy=structuredClone(r);
 Object.assign(copy.result.alternative_availability.by_candidate,{main:timing,secondary:timing,maintained:timing});
 const now=Date.parse(r.result.alternative_availability.by_candidate[long.candidate_key].expires_at)+1;
 assert.equal(remainingAlternatives(copy,[long,maintained,secondary,main],long.candidate_key,long.capability_key,now).recommended,'main');
});
test('goal classification explains the displaced focus and does not equate a different sport with a different priority',()=>{
 const r=data.early,c=morning(r).find(c=>c.sport==='STRENGTH'),preferred=morning(r).find(c=>c.sport==='KAYAK').capability_key;
 assert.match(goalRoleLabels.primary_development,/Fő célt/);assert.match(goalRoleLabels.secondary_development,/Alcélt/);assert.match(goalRoleLabels.maintenance,/Fenntartó/);
 const impact=goalImpact(r,c,preferred);assert.equal(impact.changed,c.capability_key!==preferred);assert(Number.isInteger(impact.otherSessionsForPreviousGoal));
 assert.equal(goalImpact(r,{...c,sport:'RUNNING'},preferred).label,impact.label);
});
test('retiming preserves every physical target, set count, load and rest',()=>{
 const a=data.early,b=data.retimed,selected=b.result.alternatives.find(g=>g.date==='2026-10-26').selected_candidate_key;
 const fresh=candidates(b).find(c=>c.candidate_key===selected),old=morning(a).find(c=>c.sport==='STRENGTH');
 assert.notEqual(fresh.start_at,old.start_at);assert.equal(fresh.duration_sec,old.duration_sec);
 assert.equal(canonical(workoutVariant(fresh,b.result.prescription_context.by_candidate[fresh.candidate_key])),canonical(workoutVariant(old,a.result.prescription_context.by_candidate[old.candidate_key])));
});
for(const change of ['extended_deadline','wrong_duration','wrong_window','wrong_day_boundary','false_daylight','wrong_role','wrong_rank','orphan','missing','weather_claim'])test(`a rehashed response still rejects ${change} in expiry/goal proof`,async()=>{
 const r=structuredClone(data.early),c=morning(r).find(c=>c.sport==='STRENGTH'),context=r.result.alternative_availability,row=context.by_candidate[c.candidate_key];
 if(change==='extended_deadline')row.expires_at=new Date(Date.parse(row.expires_at)+60000).toISOString();
 if(change==='wrong_duration')row.duration_sec+=300;
 if(change==='wrong_window')row.window_end_at=new Date(Date.parse(row.window_end_at)+60000).toISOString();
 if(change==='wrong_day_boundary')row.day_end_at=new Date(Date.parse(row.day_end_at)+3600000).toISOString();
 if(change==='false_daylight')row.limiting_factors.push('daylight_end');
 if(change==='wrong_role')row.goal_role='maintenance';
 if(change==='wrong_rank')row.goal_rank=2;
 if(change==='orphan')context.by_candidate['f'.repeat(64)]={...row};
 if(change==='missing')delete context.by_candidate[c.candidate_key];
 if(change==='weather_claim')context.weather_evaluated=true;
 const body=structuredClone(r);delete body.content_hash;r.content_hash=await sha(body);
 await assert.rejects(()=>check(r),/lejárata vagy célbesorolása/);
});
test('older immutable reviews retain unknown timing rather than a false start-time expiry',()=>{
 const r=structuredClone(data.early),c=morning(r)[0];delete r.result.alternative_availability;
 assert.equal(alternativeExpired(r,c,Date.parse(c.start_at)+1000),false);
});
