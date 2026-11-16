import {object} from "./contracts";
import {localDay} from "./plan-view";
type Row=Record<string,unknown>;
const aliases:Record<string,string[]>={KAYAK:["kajak","kayak","kayaking","kayak_flatwater"],RUNNING:["futás","futas","run","running"],STRENGTH:["erőnlét","erőedzés","erősítés","strength","kondi"],SWIMMING:["úszás","uszas","swimming","swim"]};
const code=(value:unknown)=>String(value).split("/").map(s=>s.trim().toLocaleLowerCase("hu")).map(s=>Object.keys(aliases).find(k=>aliases[k].includes(s))).find(Boolean);
export function declaredSwimming(inputs:Row) {
  if(!inputs.profile)return null;
  const profile=object(inputs.profile),data=object(profile.data),reference=object(profile.reference),target=code(inputs.program_sport);
  const rows=((data.sport_history??[]) as unknown[]).map(object).map((row,index)=>({row,index})).filter(({row})=>code(row.sport)==="SWIMMING"&&row.current===true&&["primary","secondary"].includes(String(row.role))&&
    (row.role==="primary"||!((object(row.planning??{}).supported_sports??[]) as unknown[]).length||((object(row.planning??{}).supported_sports??[]) as unknown[]).some(s=>code(s)===target)));
  if(rows.some(({row})=>object(row.planning??{}).proficiency==="learning"))return null;
  for(const {row,index} of rows){
    const proficiency=object(row.planning??{}).proficiency;if(!["independent","experienced"].includes(String(proficiency)))continue;
    const names:Record<string,string[]>={freestyle:["gyors","gyorsúszás","freestyle","crawl"],breaststroke:["mell","mellúszás","breaststroke"],backstroke:["hát","hátúszás","backstroke"],butterfly:["pillangó","pillangóúszás","butterfly"]};
    const discipline=String(row.discipline??"").trim().toLocaleLowerCase("hu"),stroke=Object.keys(names).find(k=>names[k].includes(discipline))??"self_selected";
    return {skill:{reported_on:localDay(String(inputs.timezone_name),new Date(String(reference.available_at))),independent:true,strokes:stroke==="self_selected"?[]:[stroke],preferred_stroke:stroke,continuous_minutes:null,continuous_distance_m:null},
      basis:{kind:"sport_history",profile_reference:{artifact_id:reference.artifact_id,content_hash:reference.content_hash},history_index:index,proficiency}};
  }
  return null;
}
