import {canonical, object} from "./contracts";
import {readReceipt} from "@/lib/athlete-setup/contracts";
export function assessmentProfileContent(raw: unknown) {
  const ignored = new Set(["sport_history", "sport_history_status", "competition_category", "target_sport", "typical_days_per_week", "typical_minutes_per_week", "last_training_date"]);
  return Object.fromEntries(Object.entries(object(raw)).filter(([key])=>!ignored.has(key)));
}
const currentOnlyFields=new Set(["resources","duration_doubling_slowdown_pct","manual_observations","source_window","source_selections"]);
export function strengthProfileContent(raw:unknown) {
  return Object.fromEntries(Object.entries(assessmentProfileContent(raw)).filter(([key])=>!currentOnlyFields.has(key)));
}
export type ProfileComparison={schema_version:"strength-profile-comparison-v0.1";changed_fields:string[];blocking_fields:string[];source_reference_changed:boolean;reference_reusable:boolean};
export const profileFieldLabels:Record<string,string>={
  profile_presence:"A kiinduló személyes profil megléte",birth_date:"Születési dátum",sex_reference:"Nemre vonatkozó referencia",competition_category:"Versenyzési kategória",target_sport:"Célzott sportág",sport_history_status:"Sportelőélet megadottsága",sport_history:"Sportelőélet és sporteredmények",constraint_status:"Mozgási vagy egészségi korlátozás megadottsága",constraints:"Mozgási és egészségi korlátozások",participation:"Sportolásban való részvétel állapota",interruption:"Kihagyás utáni visszatérés",last_training_date:"Utolsó edzés dátuma",typical_days_per_week:"Heti rendelkezésre álló napok",typical_minutes_per_week:"Heti rendelkezésre álló idő",resources:"Általános eszközlista",duration_doubling_slowdown_pct:"Időtartam és iram összefüggésének beállítása",accessibility_needs:"Hozzáférési és alkalmazkodási igények",recovery_notes:"Regenerációs és állapotra vonatkozó megjegyzések",manual_observations:"Profilban rögzített mérési adatok",source_window:"Adatforrások vizsgált időszaka",source_selections:"Kiválasztott adatforrások",body_mass_kg:"Testtömeg",height_cm:"Testmagasság",body_measurements_recorded_on:"Testméretek mérési dátuma",body_mass_recorded_on:"Testtömeg mérési dátuma",
};
const check=(v:unknown)=>{if(!v)throw Error("A profilváltozás és az erőfelmérés forrása nem ellenőrizhető.");};
const artifact=(raw:unknown)=>raw?object(object(raw).artifact):null;
export function compareStrengthProfile(context:Record<string,unknown>):ProfileComparison {
  const saved=artifact(context.receipt);
  const empty:ProfileComparison={schema_version:"strength-profile-comparison-v0.1",changed_fields:[],blocking_fields:[],source_reference_changed:false,reference_reusable:false};
  if(!saved)return empty;
  const snapshot=object(saved.snapshot),old=artifact(snapshot.profile_receipt),current=artifact(context.current_profile_receipt);
  const before=old?object(object(old.proposal).data):null,after=current?object(object(current.proposal).data):null;
  const changed=before&&after?[...new Set([...Object.keys(before),...Object.keys(after)])].filter(k=>canonical(before[k]??null)!==canonical(after[k]??null)).sort():before===after?[]:["profile_presence"];
  const relevant=before&&after?new Set([...Object.keys(strengthProfileContent(before)),...Object.keys(strengthProfileContent(after))]):new Set(changed);
  const blocking=changed.filter(k=>relevant.has(k)),referenceChanged=canonical(snapshot.profile_reference)!==canonical(object(context.source_body).profile_reference);
  return {...empty,changed_fields:changed,blocking_fields:blocking,source_reference_changed:referenceChanged,reference_reusable:!!(before&&after&&!blocking.length&&!referenceChanged)};
}
export function readProfileComparison(raw:unknown):ProfileComparison {
  const v=object(raw);check(v.schema_version==="strength-profile-comparison-v0.1"&&Array.isArray(v.changed_fields)&&Array.isArray(v.blocking_fields)&&typeof v.source_reference_changed==="boolean"&&typeof v.reference_reusable==="boolean");
  for(const fields of [v.changed_fields as unknown[],v.blocking_fields as unknown[]])check(fields.every(k=>typeof k==="string"&&Object.hasOwn(profileFieldLabels,k))&&canonical([...new Set(fields)].sort())===canonical(fields));
  check((v.blocking_fields as string[]).every(k=>(v.changed_fields as string[]).includes(k))&&(!v.reference_reusable||(!v.source_reference_changed&&!(v.blocking_fields as string[]).length)));
  return v as ProfileComparison;
}
async function verifyStrengthProfile(inputs:Record<string,unknown>,body:Record<string,unknown>,context:Record<string,unknown>,owner:string) {
  const cutoff=Date.parse(String(inputs.captured_at)),p=inputs.profile?object(inputs.profile):null,saved=artifact(context.receipt);
  check(Number.isFinite(cutoff));
  const read=async(raw:unknown)=>{const r=await readReceipt(raw);check(r.artifact.kind==="profile"&&r.artifact.athlete_id===owner&&Date.parse(r.durable_available_at)<=cutoff&&Date.parse(r.artifact.created_at)<=cutoff);return r;};
  const ref=(a:{artifact_id:unknown;content_hash:unknown})=>({artifact_id:a.artifact_id,content_hash:a.content_hash});
  if(p) {
    const current=await read(context.current_profile_receipt),sourceRaw=context.profile_source_receipt??(saved?object(saved.snapshot).profile_receipt:context.current_profile_receipt);
    const source=await read(sourceRaw);
    check(canonical(ref(current.artifact))===canonical(ref(object(p.reference) as {artifact_id:unknown;content_hash:unknown}))&&canonical(current.artifact.proposal.data)===canonical(p.data)&&
      canonical(ref(source.artifact))===canonical(body.profile_reference)&&Number(source.artifact.revision)<=Number(current.artifact.revision)&&Date.parse(source.artifact.created_at)<=Date.parse(current.artifact.created_at)&&
      canonical(strengthProfileContent(source.artifact.proposal.data))===canonical(strengthProfileContent(p.data)));
  } else check(body.profile_reference===null&&!context.current_profile_receipt&&!context.profile_source_receipt);
  const expected=compareStrengthProfile(context);readProfileComparison(context.profile_comparison);
  check(canonical(expected)===canonical(context.profile_comparison));
}
export async function verifyAssessmentProfile(inputs:Record<string,unknown>,body:Record<string,unknown>,context:Record<string,unknown>,owner:string) {
  if(context.profile_comparison!==undefined)return verifyStrengthProfile(inputs,body,context,owner);
  const p=inputs.profile===null?null:object(inputs.profile),reference=p?object(p.reference):null;
  const expected=reference?{artifact_id:reference.artifact_id,content_hash:reference.content_hash}:null;
  if(canonical(body.profile_reference)===canonical(expected))return;
  const saved=object(object(context.receipt).artifact),source=await readReceipt(object(saved.snapshot).profile_receipt),current=await readReceipt(context.current_profile_receipt);
  const ref=(r:typeof source)=>({artifact_id:r.artifact.artifact_id,content_hash:r.artifact.content_hash});
  const cutoff=Date.parse(String(inputs.captured_at));
  if(!p||!Number.isFinite(cutoff)||[source,current].some(r=>r.artifact.kind!=="profile"||r.artifact.athlete_id!==owner||Date.parse(r.durable_available_at)>cutoff)||
    canonical(ref(source))!==canonical(body.profile_reference)||canonical(ref(current))!==canonical(expected)||
    !Number.isSafeInteger(source.artifact.revision)||!Number.isSafeInteger(current.artifact.revision)||Number(source.artifact.revision)>Number(current.artifact.revision)||Date.parse(source.artifact.created_at)>Date.parse(current.artifact.created_at)||
    canonical(current.artifact.proposal.data)!==canonical(p.data)||
    canonical(assessmentProfileContent(source.artifact.proposal.data))!==canonical(assessmentProfileContent(p.data)))
    throw Error("A felmérés egészségi vagy mozgást érintő profiladatai megváltoztak.");
}
