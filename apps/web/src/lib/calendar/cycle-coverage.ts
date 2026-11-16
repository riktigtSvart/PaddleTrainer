import {localParts} from "./contracts";
import type {Actual, Feed, Period, Planned} from "./contracts";

export function plannedGoal(p: Planned) {return p.goal_tag!==null?p.goal_tag.primary_goal:p.planning_context?.primary_goal??null;}
export function actualGoal(s: Actual, feed: Feed) {
  if(s.goal_tag!==null)return s.goal_tag.primary_goal;
  if(s.linked_goal_tag!==null)return s.linked_goal_tag.primary_goal;
  const plan=feed.planned.find(p=>p.id===s.planned_workout_id);
  return plan?plannedGoal(plan):null;
}
export function cycleCoverage(feed: Feed, period: Period) {
  const cutoff=Date.parse(feed.retrieved_at),today=localParts(feed.retrieved_at,feed.timezone_name).date;
  const actual=feed.sessions.filter(s=>{const d=localParts(s.started_at,feed.timezone_name).date;return period.start_date<=d&&d<=period.end_date&&Date.parse(s.started_at)<=cutoff;});
  const completed=actual.filter(s=>s.ended_at!==null&&Date.parse(s.ended_at)<=cutoff);
  const linked=new Set(actual.map(s=>s.planned_workout_id).filter(Boolean));
  const plans=feed.planned.filter(p=>period.start_date<=p.date&&p.date<=period.end_date);
  const upcoming=plans.filter(p=>["PLANNED","DRAFT","SCHEDULED"].includes(p.status)&&!linked.has(p.id)&&(p.planned_start_time?Date.parse(p.planned_start_time)>cutoff:p.date>=today));
  const elapsed=plans.filter(p=>["PLANNED","DRAFT","SCHEDULED"].includes(p.status)&&!linked.has(p.id)&&(p.planned_start_time?Date.parse(p.planned_start_time)<=cutoff:p.date<today));
  const totals=(rows:{duration_sec:number|null}[])=>({count:rows.length,seconds:rows.reduce((sum,s)=>sum+(s.duration_sec??0),0),unknown:rows.filter(s=>s.duration_sec===null).length});
  const keys=new Set([...completed.map(s=>actualGoal(s,feed)),...upcoming.map(plannedGoal)].filter((v):v is string=>v!==null));
  return {completed:totals(completed),upcoming:totals(upcoming),elapsedUnconfirmed:elapsed.length,incomplete:actual.length-completed.length,
    reportedOnly:plans.filter(p=>p.status==="COMPLETED"&&!linked.has(p.id)).length,
    unassigned:completed.filter(s=>actualGoal(s,feed)===null).length,
    byGoal:Object.fromEntries([...keys].map(key=>[key,{actual:totals(completed.filter(s=>actualGoal(s,feed)===key)),planned:totals(upcoming.filter(p=>plannedGoal(p)===key))}])),
    bySport:Object.fromEntries([...new Set(completed.map(s=>s.sport))].map(sport=>[sport,totals(completed.filter(s=>s.sport===sport))]))};
}
