import {object,sha} from "@/lib/planning-cycles/contracts";
import {timings} from "./feedback";
export type LearningState = "no_numeric_answers" | "waiting_for_execution" | "ready" | "ready_to_freeze";
export type LearningItem = {timing:"IMMEDIATE"|"NEXT_MORNING";revision:number;state:LearningState;
  feedback_reference:{artifact_id:string;content_hash:string};response_source_id:string;observed_at:string;
  submitted_at:string;available_at:string;reporting_delay_seconds:number;
  measurements:{metric_key:string;knowledge_status:"known"|"unknown";value:number|null;unit:null}[];
  response_reference:{artifact_id:string;content_hash:string}|null};
export type LearningContext = {schema_version:string;athlete_id:string;session_id:string;information_cutoff_at:string;
  items:LearningItem[];content_hash:string;planning_authorized:false;model_updated:false;provider_writeback:false};
export const learningLabels:Record<LearningState,string>={
  no_numeric_answers:"Megőrzött megjegyzés · nincs számszerű válasz",
  waiting_for_execution:"Állapotadatként elérhető · az elemzési bekötés edzésbizonyítékra vár",
  ready_to_freeze:"Állapotadatként elérhető · beköthető a személyes elemzésbe",
  ready:"Bekötve a személyes elemzés adatfolyamába",
};
function requireValue(ok:unknown):asserts ok {if(!ok)throw Error("A tanulási kapcsolat válasza nem ellenőrizhető.");}
const instant=(x:unknown)=>typeof x==="string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(x) && Number.isFinite(Date.parse(x));
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
function reference(x:unknown){const r=object(x);requireValue(typeof r.artifact_id==="string" && r.artifact_id.length>0 && typeof r.content_hash==="string" && /^[a-f0-9]{64}$/.test(r.content_hash));}
export async function readLearning(value:unknown,owner:string,session:string):Promise<LearningContext>{
 const x=object(value);
 requireValue(x.schema_version==="feedback-learning-v0.1" && x.athlete_id===owner && x.session_id===session &&
  x.selection_policy==="latest_known_revision_per_session_and_timing" && instant(x.information_cutoff_at) &&
  x.planning_authorized===false && x.model_updated===false && x.provider_writeback===false && Array.isArray(x.items) && x.items.length<=2);
 const seen=new Set();
 for(const raw of x.items){const a=object(raw);
  requireValue(timings.includes(a.timing as "IMMEDIATE"|"NEXT_MORNING") && !seen.has(a.timing));seen.add(a.timing);
  requireValue(Number.isSafeInteger(a.revision) && Number(a.revision)>0 && typeof a.state==="string" && Object.hasOwn(learningLabels,a.state));
  requireValue(typeof a.response_source_id==="string" && uuid.test(a.response_source_id));reference(a.feedback_reference);
  requireValue(instant(a.observed_at) && instant(a.submitted_at) && instant(a.available_at));
  requireValue(Date.parse(String(a.available_at))>=Math.max(Date.parse(String(a.observed_at)),Date.parse(String(a.submitted_at))) && Date.parse(String(a.available_at))<=Date.parse(String(x.information_cutoff_at)));
  requireValue(Number.isSafeInteger(a.reporting_delay_seconds) && Number(a.reporting_delay_seconds)>=0);
  requireValue(Array.isArray(a.measurements) && a.measurements.length===5);
  const keys=new Set();for(const raw of a.measurements){const m=object(raw);requireValue(typeof m.metric_key==="string" && /^self_reported_(rpe|fatigue|soreness|recovery|energy)_score$/.test(m.metric_key) && !keys.has(m.metric_key));keys.add(m.metric_key);
   requireValue(m.unit===null && (m.knowledge_status==="unknown" ? m.value===null : m.knowledge_status==="known" && typeof m.value==="number" && Number.isFinite(m.value) && m.value>=0 && m.value<=10));}
  requireValue(a.state==="no_numeric_answers" ? a.measurements.every(v=>object(v).knowledge_status==="unknown") : a.measurements.some(v=>object(v).knowledge_status==="known"));
  if(a.state==="ready")reference(a.response_reference);else requireValue(a.response_reference===null);
 }
 const {content_hash,...raw}=x;requireValue(content_hash===await sha(raw));return x as LearningContext;
}
export async function loadLearning(owner:string,session:string,refresh=false,signal?:AbortSignal){
 requireValue(uuid.test(owner) && uuid.test(session));
 const response=await fetch(`/api/calendar/sessions/${session}/learning`,{method:refresh?"POST":"GET",body:refresh?"{}":undefined,
  cache:"no-store",signal,headers:{Accept:"application/json",...(refresh?{"Content-Type":"application/json"}:{})}});
 if(!response.ok)throw Error("A tanulási kapcsolat nem frissíthető. A saját visszajelzésed mentését ez nem törli; az ellenőrzés megismételhető.");
 return readLearning(await response.json(),owner,session);
}
