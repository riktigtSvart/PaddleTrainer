import {canonical,object,sha} from "./contracts";
import {globalIssues} from "./strength-assessment";
import type {StrengthEvidence} from "./strength-assessment";
type Row=Record<string,unknown>;
const check=(v:unknown)=>{if(!v)throw Error("A bevezető erőnléti minta forrása vagy tartalma nem ellenőrizhető.");};
export const starterMovements=[
  {key:"shallow_squat",label:"Kényelmes részleges guggolás",instruction:"Csak kényelmes mélységig ereszkedj, majd állj fel; a térd kövesse a lábfej irányát."},
  {key:"unloaded_hip_hinge",label:"Csípőhajlítás állva, külső teher nélkül",instruction:"Enyhén hajlított térddel told hátra a csípőt, tartsd kényelmesen a hátad, majd egyenesedj fel."},
  {key:"standing_scapular_control",label:"Lapockazárás állva",instruction:"Külső teher nélkül közelítsd finoman a lapockákat, a vállakat ne húzd a füledhez, majd lazíts."},
];
export async function validateStarterCandidate(review:Row,c:Row,metadata:unknown,context:StrengthEvidence|null) {
  const inputs=object(review.inputs),result=object(review.result),profile=object(inputs.profile),p=object(profile.data),reference=object(profile.reference);
  check(context&&["training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version))&&object(result.entry_review).global_entry_gate==="OPEN"&&
    p.participation==="unrestricted"&&p.constraint_status==="none_known"&&Array.isArray(p.constraints)&&p.constraints.length===0&&p.interruption!=="returning");
  check(globalIssues(context!,inputs).every(code=>["STRENGTH_ASSESSMENT_MISSING","STRENGTH_ASSESSMENT_HISTORY_REVIEW"].includes(code)));
  const value=context!.receipt?.artifact.proposal.data;
  check(value?.supervision!=="needed"&&(value?.usual_strength_minutes===undefined||value.usual_strength_minutes===null||value.usual_strength_minutes>=20));
  check(!(value?.exercises??[]).some(e=>["symptoms","avoid","uncertain"].includes(e.comfort)||e.sets.some(s=>["pain","discomfort"].includes(s.symptoms))));
  const cutoff=Date.parse(String(inputs.captured_at));
  const recent=((inputs.recent_sessions??[]) as Row[]).filter(s=>s.sport==="STRENGTH"&&s.reference_occasion!==true&&Number.isSafeInteger(s.duration_sec)&&Number(s.duration_sec)>0&&s.ended_at!==null&&Date.parse(String(s.started_at))<=Date.parse(String(s.ended_at))&&Date.parse(String(s.ended_at))<=cutoff&&Number(s.duration_sec)*1000<=Date.parse(String(s.ended_at))-Date.parse(String(s.started_at))).sort((a,b)=>String(b.started_at).localeCompare(String(a.started_at))||String(b.id).localeCompare(String(a.id))).slice(0,3);
  check(recent.every(s=>Number(s.duration_sec)>=1200));
  check(c.template_key==="STRENGTH_REFERENCE_AND_DEVELOPMENT"&&c.template_version==="v0.4"&&c.sport==="STRENGTH"&&["MAX_STRENGTH","MUSCULOSKELETAL_ROBUSTNESS"].includes(String(c.capability_key))&&c.duration_sec===1200&&c.duration_reference_session_id===null&&c.strength_prescription===undefined);
  const d=(inputs.days as unknown[]).map(object).find(d=>d.date===c.date),g=((d?.opportunities??[]) as unknown[]).map(object).find(g=>g.key===c.opportunity_key),constraints=object(g?.constraints);
  check(g&&g.known===true&&typeof c.location_id==="string"&&constraints.location_id===c.location_id&&constraints.location===c.location&&["any","moderate","easy"].includes(String(constraints.effort_cap))&&
    (constraints.sport_scope==="any"||(constraints.sport_scope==="specified"&&((constraints.sports??[]) as string[]).some(s=>["strength","erőnlét","erőedzés","erősítés","kondi"].includes(s.trim().toLocaleLowerCase("hu"))))));
  const work=starterMovements.map(m=>m.label).join(" / "),description='Erőfejlesztést előkészítő, könnyű technikai alkalom, számszerű erőreferencia nélkül. 5 perc könnyű séta és kényelmes ízületi átmozgatás. A főrészben gyakorlatonként egy sorozat, legfeljebb 5 lassú, könnyű ismétlés: '+starterMovements.map(m=>m.label+': '+m.instruction).join(' | ')+' A gyakorlatok között 1–2 perc nyugodt pihenő. Maradj RPE 2–3/10 erőfeszítésnél; külső súlyt ne használj. Az ismeretlen, bizonytalan vagy panaszt okozó mozdulatot hagyd ki; ilyenkor maradj könnyű sétánál vagy fejezd be. 5 perc levezetés. A 20 perc felső időkeret, a pihenőkkel együtt; nem kell kitölteni. Ez bevezető gyakorlás, nem maximáliserő-teszt vagy mért kapacitásból számított fejlesztési dózis.';
  check(c.title==='Bevezető erőnléti gyakorlás · 20 perces időkeret'&&c.description===description);
  const dose={schema_version:"introductory-strength-v0.1",rules_version:"introductory-strength-v0.1",source_kind:"literature_and_product_default",profile_reference:{artifact_id:reference.artifact_id,content_hash:reference.content_hash},assessment_reference:context!.receipt?{artifact_id:context!.receipt.artifact.artifact_id,content_hash:context!.receipt.artifact.content_hash}:null,movements:starterMovements,sets_per_movement:1,max_repetitions:5,rest_seconds:{min:60,max:120},external_load_prescribed:false,one_rm_estimated:false,progression_applied:false,preparatory_only:true,full_development_claim:false,source_url:"https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/"};
  const expected={schema_version:"training-prescription-v0.5",family_key:"STRENGTH_REFERENCE_AND_DEVELOPMENT",duration_sec:1200,minimum_seconds:1200,maximum_seconds:1200,reference_session_ids:[],reference_cap_seconds:null,product_default_used:true,soft_duration_reduced:false,progression_applied:false,personal_response_model_applied:false,intensity_basis:"introductory_product_default",rpe:{min:2,max:3},introductory_strength:dose};
  check(await sha(metadata)===await sha(expected));
  const blocks=(c.blocks as unknown[]).map(object);check(blocks.length===3);
  blocks.forEach((b,i)=>check(b.position===i+1&&b.block_type===["WARMUP","WORK","COOLDOWN"][i]&&b.name===["Könnyű séta és átmozgatás",work+' · 1 sorozat, legfeljebb 5 könnyű ismétlés',"Könnyű levezetés"][i]&&b.duration_sec===[300,600,300][i]&&["distance_m","intensity_type","intensity_min","intensity_max","repeat_count","parent_block_id"].every(k=>b[k]===null)));
  check(canonical(dose.movements)===canonical(starterMovements));
}
