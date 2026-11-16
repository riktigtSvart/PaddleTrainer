import {addDays,object,sha} from "./contracts";
import {localDay} from "./plan-view";
import {readDaylightContext} from "@/lib/training-options/daylight";
type Row=Record<string,unknown>;
const check=(v:unknown)=>{if(!v)throw Error("A heti terhelés forrása nem ellenőrizhető.");};
const at=(v:unknown)=>{check(typeof v==="string"&&/(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v)));return Date.parse(String(v));};
const weekday=(d:string)=>(new Date(d+"T12:00:00Z").getUTCDay()+6)%7;
function midnight(day:string,zone:string) {
  const target=Date.parse(day+"T00:00:00Z"),format=new Intl.DateTimeFormat("sv-SE",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"});
  let value=target;
  for(let i=0;i<4;i++){const p=Object.fromEntries(format.formatToParts(value).map(v=>[v.type,v.value])),shown=Date.parse(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}Z`);if(shown===target)return value;value+=target-shown;}
  throw Error("A helyi nap kezdete nem ellenőrizhető.");
}
function valid(s:Row,cutoff:number) {return Number.isSafeInteger(s.duration_sec)&&Number(s.duration_sec)>=0&&s.ended_at!==null&&at(s.started_at)<=at(s.ended_at)&&at(s.ended_at)<=cutoff&&Number(s.duration_sec)*1000<=at(s.ended_at)-at(s.started_at);}
const sportCode=(v:unknown)=>Object.entries({KAYAK:["kajak","kayak","kayaking","kayak_flatwater"],RUNNING:["futás","futas","run","running"],STRENGTH:["erőnlét","erőedzés","erősítés","strength","kondi"],SWIMMING:["úszás","uszas","swimming","swim"]}).find(([,names])=>names.includes(String(v).trim().toLocaleLowerCase("hu")))?.[0];
const median=(values:number[])=>{const a=[...values].sort((a,b)=>a-b),m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;};

export async function validateLoadBudget(review:Row) {
  const inputs=object(review.inputs),result=object(review.result),context=object(result.prescription_context),actual=object(context.starting_budget),zone=String(review.timezone_name),cutoff=at(inputs.captured_at),window=object(inputs.recent_window);
  const policy=object(result.policy);
  check(["training-plan-policy-v0.9","training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(policy.version))&&policy.spacing_rules_version==="training-start-spacing-v0.1"&&policy.minimum_gap_hours===12&&policy.unknown_effort_gap_hours===36&&policy.strength_gap_hours===48);
  const today=localDay(zone,new Date(cutoff)),low=localDay(zone,new Date(at(window.start_at)));
  check(at(window.end_at)===cutoff&&at(window.start_at)===midnight(addDays(today,-56),zone));
  const sessions=(inputs.recent_sessions as unknown[]).map(object),seen=new Set();
  sessions.forEach(s=>{check(typeof s.id==="string"&&!seen.has(s.id)&&at(s.started_at)>=at(window.start_at)&&at(s.started_at)<=cutoff);seen.add(s.id);});
  const sources=(object(result.execution_reconciliation).sync_windows as unknown[]).map(object),weeks:Row[]=[];
  const actualWeeks=actual.weeks as unknown[];
  for(let d=addDays(low,(7-weekday(low))%7);d<addDays(today,-weekday(today));d=addDays(d,7)){
    const first=midnight(d,zone),last=midnight(addDays(d,7),zone),source=sources.find(s=>at(s.from_at)<=first&&last<=at(s.to_exclusive_at)&&last<=at(s.started_at));
    const recorded=sessions.filter(s=>first<=at(s.started_at)&&at(s.started_at)<last),positive=recorded.filter(s=>valid(s,cutoff)&&Number(s.duration_sec)>0),complete=!!source&&recorded.every(s=>valid(s,cutoff));
    const w=object(actualWeeks?.[weeks.length]);check(at(w.from_at)===first&&at(w.to_exclusive_at)===last);
    weeks.push({start_date:d,end_date:addDays(d,6),from_at:w.from_at,to_exclusive_at:w.to_exclusive_at,source_reference:source?.result_reference??null,
      status:complete?"covered":source?"incomplete_records":"coverage_missing",session_ids:positive.map(s=>s.id),sessions:positive.length,
      duration_sec:complete?positive.reduce((sum,s)=>sum+Number(s.duration_sec),0):null,main_sport_present:positive.some(s=>s.sport===sportCode(inputs.program_sport))});
  }
  const data=await readDaylightContext(inputs,String(review.athlete_id)),baseline=data?.prescription_settings?.current_baseline??null;
  const fresh=!!baseline&&addDays(today,-14)<=baseline.to_date&&baseline.to_date<=today;
  const covered:Row[]=[];for(const w of [...weeks.slice(-4)].reverse()){if(w.status!=="covered")break;covered.unshift(w);}
  const observed=covered.length>=2&&covered.slice(-2).every(w=>Number(w.sessions)>0);
  const mode=fresh?"declared_current_training":observed?"observed_covered_weeks":"declared_and_product_defaults";
  let count=fresh?baseline!.weekly_sessions:observed?Math.floor(median(covered.map(w=>Number(w.sessions)))):3;
  let minutes=fresh?baseline!.weekly_minutes:observed?Math.floor(median(covered.map(w=>Number(w.duration_sec)))/60):180;
  const profile=inputs.profile?object(object(inputs.profile).data):{};
  count=Math.min(7,count,Number(profile.typical_days_per_week??(mode!=="declared_and_product_defaults"?count:2)));
  minutes=Math.min(10080,minutes,Number(profile.typical_minutes_per_week??(mode!=="declared_and_product_defaults"?minutes:90)));
  const expected={schema_version:"training-starting-budget-v0.2",history_days:56,mode,weeks,used_week_starts:fresh?[]:observed?covered.map(w=>w.start_date):[],
    max_sessions_per_7_days:count,max_minutes_per_7_days:minutes,baseline_status:fresh?"used":baseline?"stale":"not_provided",current_baseline:baseline,
    source_reference:baseline?inputs.training_options_reference??null:null,personal_response_model_applied:false,historical_records_are_current_capacity:false};
  check(await sha(actual)===await sha(expected));
  const prep=object(result.preparation);check(prep.max_sessions_per_7_days===count&&prep.max_minutes_per_7_days===minutes&&prep.available_days_per_week===(profile.typical_days_per_week??null)&&prep.available_minutes_per_week===(profile.typical_minutes_per_week??null));
}

export function spacingHours(first:unknown,second:unknown,known=false,rpe:unknown=null) {
  if(first==="STRENGTH"&&second==="STRENGTH")return 48;
  if(!known&&!(typeof rpe==="number"&&rpe>0&&rpe<=3))return 36;
  if(first==="STRENGTH"||second==="STRENGTH")return 24;
  if(first===second||[first,second].every(s=>s==="KAYAK"||s==="SWIMMING"))return 24;
  return 12;
}
