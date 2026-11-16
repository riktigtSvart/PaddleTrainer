import {canonical,object,sha} from "./contracts";
import {localDay} from "./plan-view";
import {readDaylightContext} from "@/lib/training-options/daylight";
import {swimStrokes} from "@/lib/training-options/prescription-settings";
import type {SwimmingAbility} from "@/lib/training-options/prescription-settings";
import {declaredSwimming} from "./declared-swimming";
type Row=Record<string,unknown>;
const check=(v:unknown)=>{if(!v)throw Error("Az úszóedzés forrása vagy adagja nem ellenőrizhető.");};
const instant=(v:unknown)=>{check(typeof v==="string"&&/(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v)));return Date.parse(String(v));};
export type SwimmingDose={schema_version:"swimming-prescription-v0.1"|"swimming-prescription-v0.2";mode:"continuous"|"length_repeats"|"self_paced";stroke:keyof typeof swimStrokes|"self_selected";pool_length_m:string|null;lengths_per_repeat:number|null;rest_seconds:number|null;reported_on:string;report_is_recent:boolean;continuous_distance_limit_m:number|null};
export async function validateSwimmingCandidate(review:Row,c:Row,metadata:unknown) {
  const inputs=object(review.inputs),data=await readDaylightContext(inputs,String(review.athlete_id)),skill=data?.prescription_settings?.swimming;
  if(c.template_version==="v0.2") {await validateProfileSwimming(review,c,metadata,data);return;}
  check(skill?.independent===true&&c.template_key==="SWIM_EASY_AEROBIC"&&c.template_version==="v0.1"&&c.sport==="SWIMMING"&&c.capability_key==="PERIPHERAL_OXIDATIVE_CAPACITY");
  const location=data!.locations.find(l=>l.id===c.location_id);check(location?.pool_length_m&&location.resources.includes("Úszómedence")&&location.sports.includes("SWIMMING")&&!location.archived);
  const cutoff=instant(inputs.captured_at),today=localDay(String(inputs.timezone_name),new Date(cutoff)),s=skill as SwimmingAbility;
  const age=(Date.parse(today)-Date.parse(s.reported_on))/86400000,fresh=age>=0&&age<=56;
  const continuous=fresh&&((s.continuous_minutes??0)>=10||(s.continuous_distance_m??0)>=1000);
  const refs=(inputs.recent_sessions as unknown[]).map(object).filter(r=>r.sport==="SWIMMING"&&r.reference_occasion!==true&&Number.isSafeInteger(r.duration_sec)&&Number(r.duration_sec)>=1200&&r.ended_at!==null&&instant(r.started_at)<=instant(r.ended_at)&&instant(r.ended_at)<=cutoff&&Number(r.duration_sec)*1000<=instant(r.ended_at)-instant(r.started_at))
    .sort((a,b)=>String(b.started_at).localeCompare(String(a.started_at))||String(b.id).localeCompare(String(a.id))).slice(0,3);
  const observed=refs.length?Math.min(...refs.map(r=>Number(r.duration_sec))):null,declared=continuous&&s.continuous_minutes?(s.continuous_minutes+10)*60:null,caps=[observed,declared].filter((v):v is number=>v!==null),cap=caps.length?Math.min(...caps):continuous?1800:1200;
  const seconds=Number(c.duration_sec);check(Number.isSafeInteger(seconds)&&seconds%300===0&&seconds>=1200&&seconds<=Math.min(cap,3600));
  const pool=Number(location!.pool_length_m),limit=fresh?s.continuous_distance_m:null,lengths=limit!==null&&limit>=2*pool?2:1;
  check(limit===null||limit>=pool);
  const mode=continuous?"continuous":"length_repeats",stroke={freestyle:"gyorsúszás",breaststroke:"mellúszás",backstroke:"hátúszás",butterfly:"pillangóúszás"}[s.preferred_stroke];
  const workMinutes=(seconds-600)/60,work=continuous?`${workMinutes} perc folyamatos, könnyű ${stroke}, szükség szerint pihenővel`:`${lengths} medencehossz könnyű ${stroke}, majd 30 másodperc pihenő; ismételd az időkeretben`;
  let description=`Medence: ${location!.pool_length_m} m. 5 perc fokozatos, könnyű úszás bemelegítésként; ${work}; 5 perc nagyon könnyű levezetés. RPE 2–3/10, egyenletes, kényelmes légzéssel. A teljes időkeret a pihenőket is tartalmazza. Egész medencehosszakat ússz; új hosszt csak akkor kezdj, ha várhatóan belefér a maradék időbe. Nem kell mindenáron kitölteni a keretet; szükség szerint pihenj, rövidíts, panasz esetén állj meg. Nincs régi csúcsból vagy pillanatnyi óra-sebességből számolt tempó- vagy pulzuscél.`;
  if(continuous){description+=" Nem szükséges minden 50 méter után megállnod; a folyamatos végrehajtás a most megadott kényelmes teljesítésedre épül.";if(s.continuous_distance_m)description+=` Egy folyamatos szakasz legfeljebb ${s.continuous_distance_m} méter legyen; a táv vagy az időkeret elérésekor tarts pihenőt.`;}
  check(c.title===`${continuous?"Folyamatos könnyű úszás":"Könnyű úszás rövid szakaszokban"} · ${seconds/60} perc`&&c.description===description);
  const dose={schema_version:"swimming-prescription-v0.1",mode,stroke:s.preferred_stroke,pool_length_m:location!.pool_length_m,lengths_per_repeat:continuous?null:lengths,rest_seconds:continuous?null:30,source_kind:"self_report_and_stored_durations",reported_on:s.reported_on,report_is_recent:fresh,options_reference:inputs.training_options_reference??null,
    observed_cap_seconds:observed,declared_cap_seconds:declared,continuous_distance_limit_m:limit,pace_estimated:false,current_capacity_measured:false};
  const expected={schema_version:"training-prescription-v0.4",family_key:"SWIM_EASY_AEROBIC",duration_sec:seconds,minimum_seconds:1200,maximum_seconds:3600,reference_session_ids:refs.map(s=>s.id),reference_cap_seconds:observed,product_default_used:!caps.length,soft_duration_reduced:seconds<1800,progression_applied:false,personal_response_model_applied:false,intensity_basis:"product_default_not_personal_threshold",rpe:{min:2,max:3},swimming:dose};
  check(await sha(metadata)===await sha(expected));
  check(c.duration_reference_session_id===(refs.find(s=>s.duration_sec===observed)?.id??null));
  const blocks=(c.blocks as unknown[]).map(object);check(blocks.length===3);
  blocks.forEach((b,i)=>{check(b.position===i+1&&b.block_type===["WARMUP","WORK","COOLDOWN"][i]&&b.name===["Könnyű úszás bemelegítésként",work,"Nagyon könnyű levezető úszás"][i]&&b.duration_sec===[300,seconds-600,300][i]&&["distance_m","intensity_type","intensity_min","intensity_max","repeat_count","parent_block_id"].every(k=>b[k]===null));});
  const day=(inputs.days as unknown[]).map(object).find(d=>d.date===c.date),group=(day?.opportunities as unknown[]??[]).map(object).find(g=>g.key===c.opportunity_key);
  check(group&&object(group.constraints).location_id===c.location_id&&canonical(location!.resources)===canonical(object(group.constraints).resources));
}

async function validateProfileSwimming(review:Row,c:Row,metadata:unknown,data:Awaited<ReturnType<typeof readDaylightContext>>) {
  const inputs=object(review.inputs);check(!data?.prescription_settings?.swimming);
  const declaration=declaredSwimming(inputs);check(declaration&&["training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(object(review.result).policy).version)));
  const s=declaration!.skill,location=data?.locations.find(l=>l.id===c.location_id);
  check(location&&!location.archived&&location.sports.includes("SWIMMING")&&location.resources.includes("Úszómedence")&&c.template_key==="SWIM_EASY_AEROBIC"&&c.sport==="SWIMMING"&&c.capability_key==="PERIPHERAL_OXIDATIVE_CAPACITY");
  const cutoff=instant(inputs.captured_at),today=localDay(String(inputs.timezone_name),new Date(cutoff)),age=(Date.parse(today)-Date.parse(s.reported_on))/86400000,fresh=age>=0&&age<=56;
  const refs=(inputs.recent_sessions as unknown[]).map(object).filter(r=>r.sport==="SWIMMING"&&r.reference_occasion!==true&&Number.isSafeInteger(r.duration_sec)&&Number(r.duration_sec)>=1200&&r.ended_at!==null&&instant(r.started_at)<=instant(r.ended_at)&&instant(r.ended_at)<=cutoff&&Number(r.duration_sec)*1000<=instant(r.ended_at)-instant(r.started_at)).sort((a,b)=>String(b.started_at).localeCompare(String(a.started_at))||String(b.id).localeCompare(String(a.id))).slice(0,3);
  const observed=refs.length?Math.min(...refs.map(r=>Number(r.duration_sec))):null,cap=observed??1200,seconds=Number(c.duration_sec);
  check(Number.isSafeInteger(seconds)&&seconds%300===0&&seconds>=1200&&seconds<=Math.min(cap,3600));
  const label=({freestyle:"gyorsúszás",breaststroke:"mellúszás",backstroke:"hátúszás",butterfly:"pillangóúszás"} as Record<string,string>)[s.preferred_stroke]??"választott, ismert úszásnem";
  const work=`${(seconds-600)/60} perc könnyű úszás · ${label}, saját szakaszokkal és szükség szerinti pihenővel`;
  const description='A mentett sportelőéletben önálló/rutinos úszást jelöltél. 5 perc fokozatos, könnyű bemelegítés; '+work+'; 5 perc nagyon könnyű levezetés. Nem szükséges minden 50 méter után megállni: válassz kényelmes szakaszokat, és pihenj, amikor szükséges. RPE 2–3/10, nyugodt légzés; nem kell kitölteni az időkeretet. Panasz, romló kontroll vagy nehéz légzés esetén fejezd be. A terv medencés úszásra szól. Nem következtetünk egyéni tempóra, pulzusra vagy folyamatosan leúszható távra a jártasságból.';
  check(c.title===`Könnyű úszás saját szakaszokkal · ${seconds/60} perc`&&c.description===description&&c.duration_reference_session_id===(refs.find(r=>r.duration_sec===observed)?.id??null));
  const dose={schema_version:"swimming-prescription-v0.2",mode:"self_paced",stroke:s.preferred_stroke,pool_length_m:location!.pool_length_m??null,lengths_per_repeat:null,rest_seconds:null,source_kind:"declared_sport_proficiency",reported_on:s.reported_on,report_is_recent:fresh,options_reference:inputs.training_options_reference??null,ability_basis:declaration!.basis,observed_cap_seconds:observed,declared_cap_seconds:null,continuous_distance_limit_m:null,pace_estimated:false,current_capacity_measured:false};
  const expected={schema_version:"training-prescription-v0.4",family_key:"SWIM_EASY_AEROBIC",duration_sec:seconds,minimum_seconds:1200,maximum_seconds:3600,reference_session_ids:refs.map(r=>r.id),reference_cap_seconds:observed,product_default_used:observed===null,soft_duration_reduced:seconds<1800,progression_applied:false,personal_response_model_applied:false,intensity_basis:"product_default_not_personal_threshold",rpe:{min:2,max:3},swimming:dose};
  check(await sha(metadata)===await sha(expected));
  const blocks=(c.blocks as unknown[]).map(object);check(blocks.length===3);
  blocks.forEach((b,i)=>check(b.position===i+1&&b.block_type===["WARMUP","WORK","COOLDOWN"][i]&&b.name===["Könnyű úszás bemelegítésként",work,"Nagyon könnyű levezető úszás"][i]&&b.duration_sec===[300,seconds-600,300][i]&&["distance_m","intensity_type","intensity_min","intensity_max","repeat_count","parent_block_id"].every(k=>b[k]===null)));
  const d=(inputs.days as unknown[]).map(object).find(d=>d.date===c.date),g=((d?.opportunities??[]) as unknown[]).map(object).find(g=>g.key===c.opportunity_key);
  check(g&&object(g.constraints).location_id===c.location_id&&canonical(object(g.constraints).resources)===canonical(location!.resources));
}
