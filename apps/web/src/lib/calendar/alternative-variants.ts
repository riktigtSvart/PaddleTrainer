import {canonical,object} from '@/lib/planning-cycles/contracts';
import type {Candidate,TrainingReview} from '@/lib/planning-cycles/training-plan';
import type {PlanningContext} from './contracts';
type Row=Record<string,unknown>;
export type WorkoutVariant=Row&{schema_version:'training-workout-variant-v0.1';sport:string;primary_goal:string;duration_sec:number};
export type AlternativeKinds={schema_version:'training-alternative-kinds-v0.1';workout_variant:WorkoutVariant;original_schedule:string;different_workouts_count:number|null;same_workout_schedule_count:number|null};
const amount=(v:unknown)=>v===null||v===undefined?null:String(Number(v));
function target(s:Row){return Object.fromEntries(['repetitions','hold_seconds','load_kind','load_value','load_basis','load_note'].map(k=>[k,['hold_seconds','load_value'].includes(k)?amount(s[k]):s[k]??null]));}
export function workoutVariant(c:Row,meta:Row={}):WorkoutVariant{
 const raw=c.strength_prescription??meta.strength,strength=raw?object(raw):{},intro=meta.introductory_strength?object(meta.introductory_strength):null,swim=meta.swimming?object(meta.swimming):null;
 const movements=Array.isArray(strength.movements)?strength.movements.map(raw=>{const m=object(raw),rows=m.target?Array.from({length:Number(m.work_sets)},()=>object(m.target)):(m.sets as unknown[]).map(object);return {exercise_id:m.exercise_id,side:m.side,machine_note:m.machine_note,sets:rows.map(target),minimum_rir:m.minimum_rir??strength.minimum_rir,rest_seconds:m.rest_seconds??strength.rest_seconds};}):null;
 return {schema_version:'training-workout-variant-v0.1',sport:String(c.sport),template_key:c.template_key,primary_goal:String(c.capability_key),duration_sec:Number(c.duration_sec),
 blocks:(c.blocks as unknown[]).map(object).map(b=>Object.fromEntries(['block_type','duration_sec','distance_m','intensity_type','intensity_min','intensity_max','repeat_count','parent_block_id'].map(k=>[k,b[k]??null]))),strength:movements,rpe:meta.rpe??null,running_mode:meta.running?object(meta.running).mode??null:null,
 swimming:swim?Object.fromEntries(['mode','stroke','pool_length_m','lengths_per_repeat','rest_seconds'].map(k=>[k,k==='pool_length_m'?amount(swim[k]):swim[k]??null])):null,
 introductory:intro?{movements:(intro.movements as unknown[]).map(object).map(m=>m.key),sets:intro.sets_per_movement,max_repetitions:intro.max_repetitions}:null};
}
export const scheduleKey=(c:Row)=>canonical([Date.parse(String(c.start_at)),Date.parse(String(c.end_at)),c.location_id??null,c.location??null]);
export type ContentGroup={key:string;variant:WorkoutVariant;candidates:Candidate[];sameWorkout:boolean};
export function groupAlternatives(review:TrainingReview,target:PlanningContext,candidates:Candidate[]):ContentGroup[]{
 const base=target.alternative_kinds?.workout_variant,meta=review.result.prescription_context?.by_candidate??{},current=candidates.find(c=>c.candidate_key===target.candidate_key),baseline=base?canonical(base):current?canonical(workoutVariant(current as unknown as Row,(meta[current.candidate_key]??{}) as unknown as Row)):null;
 const result=new Map<string,ContentGroup>();
 const preferred=(c:Candidate)=>c.candidate_key===target.candidate_key?3:c.candidate_key===review.result.alternatives?.find(g=>g.date===target.date)?.selected_candidate_key?2:c.candidate_key===review.result.alternatives?.find(g=>g.date===target.date)?.recommended_candidate_key?1:0;
 for(const c of candidates){const variant=workoutVariant(c as unknown as Row,(meta[c.candidate_key]??{}) as unknown as Row),key=canonical(variant),g=result.get(key)??{key,variant,candidates:[],sameWorkout:key===baseline};
  const slot=scheduleKey(c as unknown as Row),i=g.candidates.findIndex(x=>scheduleKey(x as unknown as Row)===slot);if(i<0)g.candidates.push(c);else if(preferred(c)>preferred(g.candidates[i]))g.candidates[i]=c;result.set(key,g);
 }
 return [...result.values()];
}
