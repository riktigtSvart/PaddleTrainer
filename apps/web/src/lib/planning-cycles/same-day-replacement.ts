import {canonical,object} from './contracts';
import {localDay} from './plan-view';
type Row=Record<string,unknown>;
export type SameDayReplacement={schema_version:'same-day-training-replacement-v0.1';workout_id:string;confirmed_not_started:true};
export type AlternativesFor={schema_version:'workout-alternatives-request-v0.1';workout_id:string;expected_workout_hash:string};
export function validateSameDayReplacement(review:Row){
 const scope=review.same_day_replacement,inputs=object(review.inputs),plans=(review.plan_snapshots as unknown[]).map(object),now=Date.parse(String(review.created_at));
 const check=(v:unknown)=>{if(!v)throw Error('A mai edzés cseréjének megerősítése vagy forrása nem ellenőrizhető.');};
 const picker=review.alternatives_for;
 if(picker===undefined)check(inputs.alternatives_for===undefined);
 else {
  const s=object(picker),p=plans.find(p=>object(p.workout).id===s.workout_id),w=object(p?.workout),today=localDay(String(review.timezone_name),new Date(now)),r=object(review.result);
  check(scope===undefined&&inputs.alternatives_for!==undefined&&canonical(picker)===canonical(inputs.alternatives_for)&&canonical(Object.keys(s).sort())===canonical(['schema_version','workout_id','expected_workout_hash'].sort())&&s.schema_version==='workout-alternatives-request-v0.1'&&typeof s.workout_id==='string'&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(s.workout_id)&&typeof s.expected_workout_hash==='string'&&/^[a-f0-9]{64}$/.test(s.expected_workout_hash));
  check(p&&p.owned_sample===true&&p.linked===false&&p.replaceable===true&&p.workout_hash===s.expected_workout_hash&&String(w.date)>=today&&review.start_date===w.date&&review.end_date===w.date&&review.calibration_review===null&&['PLANNED','DRAFT','SCHEDULED'].includes(String(w.status)));
  check(plans.every(p=>p.replaceable!==true||object(p.workout).id===s.workout_id)&&(r.cancel as unknown[]).every(id=>id===s.workout_id)&&(r.proposals as unknown[]).length<=1&&(r.create as unknown[]).every(c=>object(c).date===w.date));
 }
 if(scope===undefined){check(inputs.same_day_replacement===undefined);}else{
  const s=object(scope);check(canonical(Object.keys(s).sort())===canonical(['schema_version','workout_id','confirmed_not_started'].sort())&&s.schema_version==='same-day-training-replacement-v0.1'&&s.confirmed_not_started===true&&typeof s.workout_id==='string'&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(s.workout_id)&&inputs.same_day_replacement!==undefined&&canonical(scope)===canonical(inputs.same_day_replacement));
  const p=plans.find(p=>object(p.workout).id===s.workout_id),w=object(p?.workout),today=localDay(String(review.timezone_name),new Date(now));
  check(p&&p.owned_sample===true&&p.linked===false&&p.replaceable===true&&w.date===today&&String(review.start_date)<=today&&today<=String(review.end_date)&&['PLANNED','DRAFT','SCHEDULED'].includes(String(w.status))&&typeof w.planned_start_time==='string');
 }
 for(const p of plans){const w=object(p.workout);if(p.replaceable===true&&w.planned_start_time&&Date.parse(String(w.planned_start_time))<=now)check((scope&&object(scope).workout_id===w.id)||(picker&&object(picker).workout_id===w.id));}
}
