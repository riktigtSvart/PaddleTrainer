import {addDays, object, sha} from "@/lib/planning-cycles/contracts";
import {capabilityLabels, roleLabels} from "@/lib/planning-goals/labels";
import type {GoalRole} from "@/lib/planning-goals/types";
import type {CoordinatedBlock} from "@/lib/planning-cycles/mesocycle-coordination";
import type {GoalCoverage, SportAvailability} from "@/lib/planning-cycles/sport-availability";
import {sourceChangeLabels} from "@/lib/planning-cycles/assessment-source-changes";
import {readProfileComparison} from "@/lib/planning-cycles/assessment-profile";
import type {ProfileComparison} from "@/lib/planning-cycles/assessment-profile";
import {dateDistance, requireDay, requireValue, validInstant} from "./contracts";
import type {Feed, Period, Reference} from "./contracts";
import {calendarRead} from "./read-request";

export type CycleData = {
  period: Period & {parent_id: string | null};
  goal_reference: Reference | null;
  goals: {capability_key: string; role: GoalRole; rationale: string}[];
  wave_status: "accepted" | "not_accepted" | "dates_changed" | "short_review" | "outside_accepted_range";
  wave_source: {review_reference: Reference; acceptance_reference: Reference; accepted_at: string; rules_version: "training-mesocycle-policy-v0.1"} | null;
  blocks: CoordinatedBlock[];
  latest_review: {review_reference: Reference; created_at: string; goal_coverage: GoalCoverage[]; sports: SportAvailability["sports"]; source_changes?: string[]; profile_comparison?: ProfileComparison} | null;
};
export type CycleContext = {schema_version: "calendar-cycle-context-v0.1"; athlete_id: string; timezone_name: string; start_date: string; end_date: string; retrieved_at: string; cycles: CycleData[]; content_hash: string};
function check(v: unknown): asserts v { requireValue(v, "A ciklusok mentett céljai vagy szakaszolása nem ellenőrizhető."); }
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const integer = (v: unknown, max=10080) => Number.isSafeInteger(v) && Number(v)>=0 && Number(v)<=max;
function ref(v: unknown) {const r=object(v);check(typeof r.artifact_id==="string"&&r.artifact_id.length>0&&/^[a-f0-9]{64}$/.test(String(r.content_hash)));}
export async function readCycleContext(raw: unknown, expected: {owner: string; zone: string; start: string; end: string}): Promise<CycleContext> {
  const v=object(raw),body={...v};delete body.content_hash;
  check(v.schema_version==="calendar-cycle-context-v0.1"&&v.athlete_id===expected.owner&&v.timezone_name===expected.zone&&v.start_date===expected.start&&v.end_date===expected.end&&validInstant(v.retrieved_at)&&v.has_more===false&&v.planning_authorized===false&&v.workouts_changed===false&&v.adaptation_measured===false&&await sha(body)===v.content_hash);
  check(Array.isArray(v.cycles)&&v.cycles.length<=100);const ids=new Set();
  for(const raw of v.cycles as unknown[]) {
    const row=object(raw),p=object(row.period);requireDay(p.start_date);requireDay(p.end_date);
    check(typeof p.id==="string"&&uuid.test(p.id)&&!ids.has(p.id)&&typeof p.title==="string"&&p.period_type==="MESOCYCLE"&&(p.parent_id===null||uuid.test(String(p.parent_id)))&&String(p.start_date)<=String(p.end_date)&&String(p.start_date)<=expected.end&&String(p.end_date)>=expected.start);ids.add(p.id);
    if(row.goal_reference!==null)ref(row.goal_reference);
    check(Array.isArray(row.goals));const goals=new Set();
    for(const raw of row.goals as unknown[]) {const g=object(raw);check(typeof g.capability_key==="string"&&Object.hasOwn(capabilityLabels,g.capability_key)&&!goals.has(g.capability_key)&&Object.hasOwn(roleLabels,String(g.role))&&typeof g.rationale==="string");goals.add(g.capability_key);}
    check(row.goal_reference!==null||row.goals.length===0);
    check(["accepted","not_accepted","dates_changed","short_review","outside_accepted_range"].includes(String(row.wave_status))&&Array.isArray(row.blocks));
    check((row.wave_status==="accepted")===(row.blocks.length>0&&row.wave_source!==null));
    if(row.wave_status!=="accepted")check(row.blocks.length===0&&row.wave_source===null);
    if(row.wave_source!==null){const s=object(row.wave_source);ref(s.review_reference);ref(s.acceptance_reference);check(s.rules_version==="training-mesocycle-policy-v0.1"&&validInstant(s.accepted_at)&&Date.parse(s.accepted_at)<=Date.parse(String(v.retrieved_at)));}
    const ordinals=new Set();
    for(const raw of row.blocks as unknown[]) {const b=object(raw),n=Number(b.ordinal);check(Number.isSafeInteger(b.ordinal)&&n>=1&&!ordinals.has(n)&&b.mesocycle_id===p.id&&b.key===`${p.id}:${n}`&&["steady","entry","build","consolidation"].includes(String(b.kind))&&typeof b.volume_percent==="number"&&[70,80,90,100].includes(b.volume_percent)&&integer(b.max_sessions,7)&&integer(b.max_minutes));ordinals.add(n);
      check(b.start_date===addDays(String(p.start_date),(n-1)*7)&&String(b.start_date)<=String(p.end_date)&&b.end_date===[addDays(String(b.start_date),6),String(p.end_date)].sort()[0]&&Number(b.max_sessions)<=dateDistance(String(b.start_date),String(b.end_date))+1);
      check((b.kind==="consolidation")===(b.volume_percent===70)&&(b.kind==="entry")===(b.volume_percent===80));
    }
    if(row.latest_review!==null) {
      const r=object(row.latest_review);ref(r.review_reference);check(validInstant(r.created_at)&&Date.parse(r.created_at)<=Date.parse(String(v.retrieved_at))&&Array.isArray(r.goal_coverage)&&Array.isArray(r.sports));
      if(r.source_changes!==undefined)check(Array.isArray(r.source_changes)&&r.source_changes.every(c=>typeof c==="string"&&Object.hasOwn(sourceChangeLabels,c)));
      if(r.profile_comparison!==undefined)readProfileComparison(r.profile_comparison);
      for(const raw of r.goal_coverage as unknown[]) {const g=object(raw);requireDay(g.start_date);requireDay(g.end_date);check(g.mesocycle_id===p.id&&Object.hasOwn(capabilityLabels,String(g.capability_key))&&Object.hasOwn(roleLabels,String(g.role))&&integer(g.planned_sessions,4000)&&integer(g.candidate_days,366)&&Array.isArray(g.reasons)&&g.reasons.every(x=>typeof x==="string")&&["represented","available_unselected","unavailable","unsupported"].includes(String(g.status)));}
      for(const raw of r.sports as unknown[]) {const s=object(raw);check(typeof s.sport==="string"&&typeof s.supported==="boolean"&&[s.opportunity_days,s.daylight_days,s.candidate_days,s.planned_sessions].every(n=>integer(n,4000))&&Array.isArray(s.reasons)&&s.reasons.every(x=>typeof x==="string"));}
    }
  }
  return v as CycleContext;
}
export async function loadCycleContext(feed: Pick<Feed,"athlete_id"|"timezone_name"|"start_date"|"end_date">, signal?: AbortSignal) {
  const q=new URLSearchParams({start_date:feed.start_date,end_date:feed.end_date});
  const r=await calendarRead("/api/calendar/cycles?"+q,signal);
  if(!r.ok)throw Error("A ciklusok részletei most nem tölthetők be. Próbáld újra.");
  return readCycleContext(await r.json(),{owner:feed.athlete_id,zone:feed.timezone_name,start:feed.start_date,end:feed.end_date});
}
export function cycleData(context: CycleContext | null, period: Period) {
  return context?.cycles.find(c=>c.period.id===period.id&&c.period.start_date===period.start_date&&c.period.end_date===period.end_date)??null;
}
export const cycleLoadLabels={green:"Közepes / rávezető keret",yellow:"Emelkedő keret",red:"Felső tervezési keret",blue:"Könnyebb szakasz"};
export function cycleLoad(context: CycleContext | null, feed: Feed, date: string) {
  if(!context||context.athlete_id!==feed.athlete_id||context.timezone_name!==feed.timezone_name)return null;
  const active=feed.periods.filter(p=>p.period_type==="MESOCYCLE"&&p.start_date<=date&&date<=p.end_date);
  if(active.length!==1)return null;
  const row=cycleData(context,active[0]),b=row?.blocks.find(b=>b.start_date<=date&&date<=b.end_date);
  if(!b)return null;
  const tone=b.volume_percent===70?"blue":b.volume_percent===80?"green":b.volume_percent===90?"yellow":"red";
  return {tone,block:b,label:`${b.ordinal}. mikrociklus · ${cycleLoadLabels[tone]} · ${b.volume_percent}% a rögzített kezdőkeretből`};
}
