import {canonical, object, sha} from '@/lib/planning-cycles/contracts';
import {readTrainingReview} from '@/lib/planning-cycles/training-plan';
import type {Candidate, TrainingReview} from '@/lib/planning-cycles/training-plan';
import {readProjectedInstructions} from '@/lib/planning-cycles/workout-instructions';
import type {WorkoutInstructions} from '@/lib/planning-cycles/workout-instructions';
import type {AlternativeTiming} from '@/lib/planning-cycles/alternative-availability';
import {workoutVariant} from './alternative-variants';
import type {WorkoutVariant} from './alternative-variants';
import type {FocusWorkout} from './training-alternatives';
import type {PickerIdentity} from './alternative-selection';
import {CalendarHTTPError} from './client';
import {calendarRead} from './read-request';
import {goalLabels, validInstant} from './contracts';

export type SavedOption={candidate:Candidate;timing:AlternativeTiming;instructions:WorkoutInstructions|null;workout_variant:WorkoutVariant;is_current:boolean};
export type SavedOptions={schema_version:'calendar-saved-options-v0.1';athlete_id:string;workout_id:string;workout_hash:string;date:string;timezone_name:string;
 retrieved_at:string;status:'ready'|'unavailable';source_review_reference:{artifact_id:string;content_hash:string}|null;program_reference:{artifact_id:string;content_hash:string}|null;
 prepared_at:string|null;candidates:SavedOption[];recommended_candidate_key:string|null;content_hash:string};
const cache=new Map<string,SavedOptions>();
const key=(owner:string,target:FocusWorkout)=>`${owner}:${target.id}:${target.workout_hash}`;
export const cachedSavedOptions=(owner:string,target:FocusWorkout)=>cache.get(key(owner,target))??null;
export const clearSavedOptions=()=>cache.clear();
const check=(v:unknown)=>{if(!v)throw Error('A mentett edzésalternatívák adatai nem ellenőrizhetők.');};
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
async function json(response:Response) {
 const value=await response.json();
 if(!response.ok)throw new CalendarHTTPError(response.status,String(object(object(value).detail).code??'UNKNOWN'));
 return value;
}
export async function readSavedOptions(raw:unknown,expected:PickerIdentity,target:FocusWorkout):Promise<SavedOptions>{
 const v=object(raw),body={...v};delete body.content_hash;
 check(v.schema_version==='calendar-saved-options-v0.1'&&v.athlete_id===expected.owner&&v.workout_id===target.id&&hash(v.workout_hash)&&(v.status==='unavailable'||v.workout_hash===target.workout_hash&&v.date===target.date)&&v.timezone_name===expected.zone&&validInstant(v.retrieved_at)&&v.planning_authorized===false&&v.workouts_changed===false&&await sha(body)===v.content_hash);
 check(['ready','unavailable'].includes(String(v.status))&&Array.isArray(v.candidates)&&v.candidates.length<=500);
 if(v.status==='unavailable'){check((v.candidates as unknown[]).length===0&&v.recommended_candidate_key===null);return v as SavedOptions;}
 const source=object(v.source_review_reference),program=object(v.program_reference);
 check(typeof source.artifact_id==='string'&&/^pt-training-plan:[a-f0-9]{64}$/.test(source.artifact_id)&&hash(source.content_hash)&&canonical(program)===canonical(expected.reference)&&validInstant(v.prepared_at));
 const seen=new Set<string>();
 for(const raw of v.candidates as unknown[]){const row=object(raw),c=object(row.candidate),t=object(row.timing),variant=object(row.workout_variant);
  check(hash(c.candidate_key)&&!seen.has(String(c.candidate_key)));seen.add(String(c.candidate_key));
  check(c.date===target.date&&c.training_period_id===target.mesocycle_id&&['KAYAK','RUNNING','SWIMMING','STRENGTH'].includes(String(c.sport))&&typeof c.title==='string'&&typeof c.description==='string'&&typeof c.location==='string'&&Number.isSafeInteger(c.duration_sec)&&Number(c.duration_sec)>0&&Number(c.duration_sec)<=86400&&validInstant(c.start_at)&&validInstant(c.end_at)&&Date.parse(String(c.end_at))-Date.parse(String(c.start_at))===Number(c.duration_sec)*1000&&Array.isArray(c.blocks)&&Object.hasOwn(goalLabels,String(c.capability_key))&&['primary_development','secondary_development','maintenance'].includes(String(c.role))&&typeof row.is_current==='boolean');
  check(validInstant(t.expires_at)&&validInstant(t.window_start_at)&&validInstant(t.window_end_at)&&validInstant(t.day_end_at)&&t.duration_sec===c.duration_sec&&t.goal_key===c.capability_key&&t.goal_role===c.role&&t.goal_rank===['primary_development','secondary_development','maintenance'].indexOf(String(c.role))&&typeof t.expires_inclusive==='boolean'&&Array.isArray(t.limiting_factors));
  const last=Date.parse(String(t.window_end_at))-Number(c.duration_sec)*1000,dayEnd=Date.parse(String(t.day_end_at));
  check(Date.parse(String(t.expires_at))===Math.min(last,dayEnd)&&t.expires_inclusive===(last<dayEnd)&&Date.parse(String(c.start_at))>=Date.parse(String(t.window_start_at))&&Date.parse(String(c.end_at))<=Date.parse(String(t.window_end_at)));
  if(row.instructions!==null)readProjectedInstructions(row.instructions,c);
  check(variant.schema_version==='training-workout-variant-v0.1'&&variant.sport===c.sport&&variant.primary_goal===c.capability_key&&variant.duration_sec===c.duration_sec);
 }
 check(v.recommended_candidate_key===null||seen.has(String(v.recommended_candidate_key)));
 return v as SavedOptions;
}
export async function loadSavedOptions(expected:PickerIdentity,target:FocusWorkout,signal?:AbortSignal){
 const value=await readSavedOptions(await json(await calendarRead(`/api/calendar/workouts/${target.id}/alternatives`,signal)),expected,target);
 if(!signal?.aborted){if(cache.size>=100)cache.delete(cache.keys().next().value!);cache.set(key(expected.owner,target),value);}
 return value;
}
export async function chooseSavedOption(expected:PickerIdentity,target:FocusWorkout,options:SavedOptions,clicked:SavedOption):Promise<TrainingReview>{
 if(!options.source_review_reference)throw Error('A mentett alternatíva forrása már nem érhető el.');
 const value=await json(await fetch(`/api/calendar/workouts/${target.id}/alternatives/choose`,{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_workout_hash:target.workout_hash,source_review_reference:options.source_review_reference,candidate_key:clicked.candidate.candidate_key})}));
 const reviewed=await readTrainingReview(object(value).review,expected),c=reviewed.result.create[0];
 const meta=reviewed.result.prescription_context?.by_candidate[c?.candidate_key];
 check(reviewed.alternatives_for?.workout_id===target.id&&reviewed.result.cancel.length===1&&reviewed.result.cancel[0]===target.id&&reviewed.result.create.length===1&&c.opportunity_key===clicked.candidate.opportunity_key&&canonical(workoutVariant(c as unknown as Record<string,unknown>,(meta??{}) as unknown as Record<string,unknown>))===canonical(clicked.workout_variant));
 return reviewed;
}
export function liveSavedOptions(value:SavedOptions,now:number){return value.candidates.filter(row=>row.timing.expires_inclusive?now<=Date.parse(row.timing.expires_at):now<Date.parse(row.timing.expires_at));}
