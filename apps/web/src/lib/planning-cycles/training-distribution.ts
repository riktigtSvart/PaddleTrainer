import {addDays,canonical,object} from "./contracts";
import {localDay} from "./plan-view";
type Row=Record<string,unknown>;
type Rhythm={adjacent_training_day_pairs:number;longest_training_free_span_days:number;squared_training_free_spans:number};
export type Distribution={schema_version:"training-distribution-v0.1";placement_preference:"saved_goals_then_spaced_civil_days";baseline_candidate_keys:string[];before:Rhythm;after:Rhythm;optimization_passes:number;max_passes:32;capacity_increased:false;personal_response_model_applied:false};
const check=(v:unknown)=>{if(!v)throw Error("Az edzések elosztása vagy változatlan terhelési kerete nem ellenőrizhető.");};
const distance=(a:string,b:string)=>(Date.parse(b+"T12:00:00Z")-Date.parse(a+"T12:00:00Z"))/86400000;
function fixedDays(review:Row) {
  const result=object(review.result),inputs=object(review.inputs),first=String(review.start_date),last=String(review.end_date);
  const absent=new Set((result.events as unknown[]).map(object).filter(e=>e.kind==="not_recorded_after_sync").map(e=>e.workout_id));
  const days=(inputs.recent_sessions as unknown[]).map(object).map(s=>localDay(String(review.timezone_name),new Date(String(s.started_at))));
  for(const raw of review.plan_snapshots as unknown[]) {
    const p=object(raw),w=object(p.workout);
    if(w.status==="CANCELLED"||p.linked===true||w.status==="SKIPPED"||absent.has(w.id)||(p.replaceable===true&&first<=String(w.date)&&String(w.date)<=last))continue;
    days.push(String(w.date));
  }
  return days.filter(d=>addDays(first,-6)<=d&&d<=addDays(last,6));
}
function rhythm(rows:Row[],fixed:string[],first:string,last:string):Rhythm {
  const days=[...new Set([...rows.map(c=>String(c.date)),...fixed])].sort();
  const adjacent=days.slice(1).filter((d,i)=>distance(days[i],d)===1&&((first<=days[i]&&days[i]<=last)||(first<=d&&d<=last))).length;
  const inside=days.filter(d=>first<=d&&d<=last),left=days.filter(d=>d<first).at(-1)??addDays(first,-1),right=days.find(d=>d>last)??addDays(last,1);
  const edges=[left,...inside,right],gaps=edges.slice(1).map((d,i)=>distance(edges[i],d)-1);
  return {adjacent_training_day_pairs:adjacent,longest_training_free_span_days:Math.max(0,...gaps),squared_training_free_spans:gaps.reduce((sum,n)=>sum+n*n,0)};
}
export function validateDistribution(review:Row) {
  const result=object(review.result);
  if(!["training-plan-policy-v0.12","training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version))) {check(result.distribution===undefined);return;}
  const d=object(result.distribution);
  check(d.schema_version==="training-distribution-v0.1"&&d.placement_preference==="saved_goals_then_spaced_civil_days"&&d.max_passes===32&&Number.isInteger(d.optimization_passes)&&Number(d.optimization_passes)>=0&&Number(d.optimization_passes)<=32&&d.capacity_increased===false&&d.personal_response_model_applied===false&&Array.isArray(d.baseline_candidate_keys));
  const pool=(result.alternatives as unknown[]).map(object).flatMap(a=>(a.candidates as unknown[]).map(object));
  const keys=d.baseline_candidate_keys as string[];
  check(new Set(keys).size===keys.length&&keys.every(k=>pool.some(c=>c.candidate_key===k)));
  const before=keys.map(k=>pool.find(c=>c.candidate_key===k)!),after=(result.proposals as unknown[]).map(object);
  const blocks=(object(result.mesocycle_coordination).blocks as unknown[]).map(object);
  const totals=(rows:Row[])=>{
    const sums:Record<string,[number,number]>={};
    for(const c of rows) {const block=blocks.find(b=>String(b.start_date)<=String(c.date)&&String(c.date)<=String(b.end_date)),key=String(block?.key??c.training_period_id),sum=sums[key]??=[0,0];sum[0]++;sum[1]+=Number(c.duration_sec);}
    return sums;
  };
  const a=totals(before),b=totals(after);
  check(canonical(Object.keys(a).sort())===canonical(Object.keys(b).sort())&&Object.keys(a).every(k=>a[k][0]===b[k][0]&&b[k][1]<=a[k][1]));
  const fixed=fixedDays(review),first=String(review.start_date),last=String(review.end_date);
  check(canonical(d.before)===canonical(rhythm(before,fixed,first,last))&&canonical(d.after)===canonical(rhythm(after,fixed,first,last)));
}
