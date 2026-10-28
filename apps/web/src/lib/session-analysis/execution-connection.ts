import {object,canonical,sha} from "@/lib/planning-cycles/contracts";
export const CONNECTION_SCHEMA="execution-connection-v0.1";
type Ref={artifact_id:string;content_hash:string};
export type ExecutionPreview={schema_version:string;athlete_id:string;session_id:string;review_hash:string;
 state:"ready_for_review"|"blocked"|"already_frozen";blockers:string[];session_title:string;session_started_at:string;timezone_name:string;
 plan_id:string|null;plan_title:string|null;plan_date:string|null;link_basis:"exact_provider_id"|"manual_confirmed"|null;
 provider_target_id:string|null;plan_adoption_required:boolean;plan_reference:Ref|null;execution_reference:Ref|null;
 source_workout_content_hash:string|null;session_source_content_hash:string|null};
export type ConnectionProposal={request_id:string;review_hash:string;acknowledge_current_state_baseline_only:true;acknowledge_session_identity_only:true};
export type ConnectionPending={owner:string;session:string;body:string};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash=(x:unknown):x is string=>typeof x==="string" && /^[a-f0-9]{64}$/.test(x);
function requireValue(ok:unknown):asserts ok {if(!ok)throw Error("A végrehajtási kapcsolat válasza nem ellenőrizhető. Bizonytalan mentésnél ugyanazt a kérést próbáld újra.");}
function reference(x:unknown,prefix:string){const r=object(x);requireValue(typeof r.artifact_id==="string" && r.artifact_id.startsWith(prefix) && hash(r.content_hash));return r as Ref;}
function flags(x:Record<string,unknown>){requireValue(x.history_claim==="current_state_baseline_only" && x.plan_content_at_execution_status==="unverified"
 && x.phase_alignment_verified===false && x.clock_alignment_verified===false && x.provider_event_verified===false
 && x.training_dose_changed===false && x.planning_authorized===false && x.provider_writeback===false);}
export async function readExecutionPreview(value:unknown,owner:string,session:string):Promise<ExecutionPreview>{
 const x=object(value);requireValue(x.schema_version===CONNECTION_SCHEMA && x.athlete_id===owner && x.session_id===session);flags(x);
 requireValue(["ready_for_review","blocked","already_frozen"].includes(String(x.state)) && Array.isArray(x.blockers) && x.blockers.length<=30 && x.blockers.every(v=>typeof v==="string" && v.length<=1024));
 requireValue(typeof x.session_title==="string" && typeof x.session_started_at==="string" && Number.isFinite(Date.parse(x.session_started_at)) && typeof x.timezone_name==="string" && typeof x.plan_adoption_required==="boolean");
 try{new Intl.DateTimeFormat("hu-HU",{timeZone:x.timezone_name as string});}catch{requireValue(false);}
 if(x.state==="ready_for_review"){
  requireValue(typeof x.plan_id==="string" && uuid.test(x.plan_id) && typeof x.plan_title==="string" && typeof x.plan_date==="string" && /^\d{4}-\d{2}-\d{2}$/.test(x.plan_date)
   && ["exact_provider_id","manual_confirmed"].includes(String(x.link_basis)) && x.blockers.length===0 && hash(x.source_workout_content_hash) && hash(x.session_source_content_hash));
  if(x.link_basis==="exact_provider_id")requireValue(typeof x.provider_target_id==="string" && x.provider_target_id.length>0);
  if(x.plan_adoption_required)requireValue(x.plan_reference===null);else reference(x.plan_reference,"pt-plan-rev:");
 }
 if(x.state==="already_frozen")requireValue(reference(x.execution_reference,"pt-executed-training-evidence:session:").artifact_id==="pt-executed-training-evidence:session:"+session);
 else requireValue(x.execution_reference===null);
 const {review_hash,...raw}=x;requireValue(review_hash===await sha(raw));return x as ExecutionPreview;
}
function proposal(value:unknown):ConnectionProposal{
 const p=object(value);requireValue(typeof p.request_id==="string" && uuid.test(p.request_id) && hash(p.review_hash)
  && p.acknowledge_current_state_baseline_only===true && p.acknowledge_session_identity_only===true
  && Object.keys(p).sort().join()==="acknowledge_current_state_baseline_only,acknowledge_session_identity_only,request_id,review_hash");return p as ConnectionProposal;
}
export const connectionStorageKey=(owner:string,session:string)=>`paddletrainer:execution-connection:v1:${owner}:${session}`;
export function readConnectionPending(raw:string,owner:string,session:string):ConnectionPending{
 const x=object(JSON.parse(raw));requireValue(x.owner===owner && x.session===session && typeof x.body==="string");proposal(JSON.parse(x.body));return x as ConnectionPending;
}
export async function readConnectionReceipt(value:unknown,pending:ConnectionPending){
 const x=object(value),a=object(x.artifact),p=proposal(a.proposal);flags(a);
 requireValue(x.committed===true && typeof x.reused==="boolean" && typeof x.durable_available_at==="string" && Number.isFinite(Date.parse(x.durable_available_at))
  && a.schema_version===CONNECTION_SCHEMA && a.athlete_id===pending.owner && a.session_id===pending.session && typeof a.created_at==="string" && Number.isFinite(Date.parse(a.created_at))
  && typeof a.plan_adopted==="boolean" && hash(a.source_workout_content_hash) && hash(a.session_source_content_hash));
 requireValue(a.artifact_id==="pt-execution-connection:"+await sha({athlete_id:pending.owner,request_id:p.request_id}) && canonical(p)===canonical(proposal(JSON.parse(pending.body))));
 requireValue(reference(a.execution_reference,"pt-executed-training-evidence:session:").artifact_id==="pt-executed-training-evidence:session:"+pending.session);
 reference(a.plan_reference,"pt-plan-rev:");reference(a.link_reference,"pt-exec-link:");
 const {content_hash,...raw}=a;requireValue(content_hash===await sha(raw));return x;
}
const messages:Record<string,string>={
 CALENDAR_EXECUTION_REVIEW_CHANGED:"Az előnézet óta változtak az adatok. Készíts új előnézetet, és ellenőrizd újra a kapcsolatot.",
 CALENDAR_EXECUTION_NOT_ELIGIBLE:"Ez a kapcsolat jelenleg nem rögzíthető. Ellenőrizd az előnézet jelzéseit.",
 CALENDAR_EXECUTION_REQUEST_CONFLICT:"A kérésazonosító már másik rögzítéshez tartozik.",
};
export const blockerLabels:Record<string,string>={
 EXECUTION_OWNED_PLAN_REQUIRED:"A teljesítéshez még nincs ebben a fiókban elérhető tervkapcsolat.",
 EXECUTION_EXACT_IDENTITY_REQUIRED:"A naptári párosítás még nem igazolt azonosítóegyezés vagy korábban kézzel megerősített kapcsolat.",
 EXECUTION_SOURCE_CHANGED_AFTER_LINK:"A korábban rögzített kapcsolat óta változott a forrás. Külön felülvizsgálat szükséges.",
};
export class ConnectionError extends Error {constructor(public status:number,code:string){super(messages[code]??`A kapcsolat nem rögzíthető (${code||status}).`);}}
async function request(session:string,body?:string,signal?:AbortSignal){
 requireValue(uuid.test(session));const response=await fetch(`/api/calendar/sessions/${session}/execution-connection`,{method:body?"POST":"GET",body,signal,cache:"no-store",headers:{Accept:"application/json",...(body?{"Content-Type":"application/json"}:{})}});
 let data:unknown;try{data=await response.json();}catch{throw Error("A válasz nem olvasható; a rögzítés eredménye még nem ismert.");}
 if(!response.ok){let code="";try{code=String(object(object(data).detail).code??"");}catch{}throw new ConnectionError(response.status,code);}return data;
}
export async function loadExecutionPreview(owner:string,session:string,signal?:AbortSignal){return readExecutionPreview(await request(session,undefined,signal),owner,session);}
export async function sendExecutionConnection(pending:ConnectionPending){return readConnectionReceipt(await request(pending.session,pending.body),pending);}
