import {canonical,object} from "./contracts";
import {sourceBody} from "@/lib/initial-assessment/contracts";
import {readOptionsReceipt} from "@/lib/training-options/contracts";
type Row=Record<string,unknown>;
export type SourceComparison={schema_version:"assessment-source-compatibility-v0.1";reusable:boolean;changes:string[];location_ids:string[]};
export const sourceChangeLabels:Record<string,string>={PROFILE:"A felmérést érintő személyes profil változott.",TIMEZONE:"A felmérés időzónája változott.",CATALOG:"A gyakorlatkatalógus változott.",REGISTRY:"A felmérési szabályok változtak.",PROGRAMS:"A korábban hivatkozott felkészülési adatok változtak.",PROGRAMS_ADDED:"Új célkitűzés került a listába; a korábbiak változatlanok.",OPTIONS_REFERENCED_LOCATIONS:"A felmérésben használt erősítőhelyszín elérhetősége vagy felszerelése változott.",OPTIONS_OTHER_FIELDS:"A hivatkozott erősítőhelyszínek változatlanok; az egyéb helyszínadatok frissültek.",ASSESSMENT_MISSING:"Még nincs mentett felmérés."};
export function physicalStrengthOptions(raw:unknown,ids:string[]) {
  const d=object(raw);return {timezone_name:d.timezone_name,locations:(d.locations as unknown[]).map(object).filter(p=>ids.includes(String(p.id))).map(p=>({id:p.id,archived:p.archived,strength_supported:(p.sports as string[]).includes("STRENGTH"),resources:[...new Set((p.resources as string[]).map(s=>s.trim().toLowerCase()))].sort(),confirmed_exercise_ids:((p.exercise_confirmations??[]) as unknown[]).map(object).map(v=>String(v.exercise_id)).sort()})).sort((a,b)=>String(a.id).localeCompare(String(b.id)))};
}
export function compareAssessmentSources(context:Row):SourceComparison {
  const saved=context.receipt?object(object(context.receipt).artifact):null;
  if(!saved)return {schema_version:"assessment-source-compatibility-v0.1",reusable:false,changes:["ASSESSMENT_MISSING"],location_ids:[]};
  const snapshot=object(saved.snapshot),before=sourceBody(snapshot as never),after=object(context.source_body),data=object(object(saved.proposal).data);
  const ids=[...new Set((data.exercises as unknown[]).map(object).map(e=>e.location_id).filter((v):v is string=>typeof v==="string"))].sort();
  const changes:string[]=[];let reusable=true;
  for(const [key,code] of [["timezone_name","TIMEZONE"],["profile_reference","PROFILE"],["catalog_hash","CATALOG"],["registry_hash","REGISTRY"]])if(canonical(object(before)[key])!==canonical(after[key])){changes.push(code);reusable=false;}
  if(canonical(before.programs)!==canonical(after.programs)) {const added=Array.isArray(after.programs)&&before.programs.every(p=>(after.programs as unknown[]).some(v=>canonical(v)===canonical(p)));changes.push(added?"PROGRAMS_ADDED":"PROGRAMS");reusable&&=added;}
  if(canonical(before.options_reference)!==canonical(after.options_reference)) {
    const current=context.options_source_receipt?object(object(context.options_source_receipt).artifact):null,old=snapshot.options_receipt?object(object(snapshot.options_receipt).artifact):null;
    const equivalent=!!(current&&old&&canonical({artifact_id:current.artifact_id,content_hash:current.content_hash})===canonical(after.options_reference)&&canonical(physicalStrengthOptions(object(old.proposal).data,ids))===canonical(physicalStrengthOptions(object(current.proposal).data,ids)));
    changes.push(equivalent?"OPTIONS_OTHER_FIELDS":"OPTIONS_REFERENCED_LOCATIONS");reusable&&=equivalent;
  }
  return {schema_version:"assessment-source-compatibility-v0.1",reusable,changes,location_ids:ids};
}
export async function verifySourceComparison(context:Row,inputs:Row,owner:string) {
  const expected=compareAssessmentSources(context);
  if(canonical(context.source_comparison)!==canonical(expected))throw Error("A felmérés forrásváltozásainak ellenőrzése eltér.");
  if(context.options_source_receipt) {
    const r=await readOptionsReceipt(context.options_source_receipt,owner),body=object(context.source_body);
    if(canonical({artifact_id:r.artifact.artifact_id,content_hash:r.artifact.content_hash})!==canonical(body.options_reference)||Date.parse(r.durable_available_at)>Date.parse(String(inputs.captured_at)))throw Error("A felmérés új helyszíni forrása nem ellenőrizhető.");
  }
  return expected;
}
