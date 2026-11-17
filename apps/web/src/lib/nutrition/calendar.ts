import { canonical, object, sha } from '@/lib/planning-cycles/contracts';
import { CATALOG_HASH, civilDay, readNutritionArtifact } from './contracts';
import type { Artifact, Catalog, Context, Meal, Reference } from './contracts';
import { blankJournal, ensure, plannedTime, readJournal } from './journal';
import type { Entry, Journal, JournalData } from './journal';
import { daySchedule, readTimingContext } from './timing';
import type { MealTiming, TimingContext } from './timing';

export type CalendarMeal = Meal & { title: string; people: number; source: Reference; planned_time: string | null; status: 'planned' | 'eaten' | 'skipped'; report_id: string | null; different_report: boolean; timing?: MealTiming };
type Result = { days: { date: string; meals: CalendarMeal[] }[]; actual_entries: Entry[]; meal_count: number; workouts_changed: false; personal_energy_prescribed: false; nutrient_adequacy: 'not_evaluated' };
export type NutritionCalendar = { schema_version: 'nutrition-calendar-v0.1'|'nutrition-calendar-v0.2'; athlete_id: string; timezone: string; start_date: string; end_date: string; catalog: Catalog; sources: Artifact[]; journal: Journal; result: Result; read_only: true; content_hash: string; timing_context?: TimingContext };
export function projectCalendar(sources: Artifact[], data: JournalData, start: string, end: string, c: Catalog, reportedSources: Artifact[] = [], timing?:TimingContext): Result {
  const selected = new Map<string, CalendarMeal[]>();
  for (const source of sources) {
    const plan = source.proposal.data.plan; if (!plan) continue;
    for (let i=0; i<plan.day_count; i++) {
      const day = civilDay(plan.start_date, i); if (day < start || day > end || selected.has(day)) continue;
      const ref = { artifact_id: source.artifact_id, content_hash: source.content_hash };
      const schedule=timing?daySchedule(data,day,plan.meals.filter(m=>m.date===day).map(m=>m.slot),timing):null;
      selected.set(day, plan.meals.filter(m=>m.date===day).map(m=> {
        const report = data.entries.find(e=>e.source?.date===day && e.source.slot===m.slot);
        const originalSource=reportedSources.find(s=>report&&s.artifact_id===report.source!.reference.artifact_id&&s.content_hash===report.source!.reference.content_hash);
        const original=originalSource?.proposal.data.plan?.meals.find(x=>x.date===day&&x.slot===m.slot);
        const same=!!report&&(canonical(report.source!.reference)===canonical(ref)||!!original&&original.recipe_id===m.recipe_id&&original.portion_factor===m.portion_factor);
        return { ...m, title: c.recipes.find(r=>r.id===m.recipe_id)!.title, people: plan.people, source: ref,
          planned_time: schedule?schedule[m.slot].time:plannedTime(data, day, m.slot), ...(schedule?{timing:schedule[m.slot]}:{}), status: same ? report!.status : 'planned', report_id: report?.id ?? null, different_report: !!report && !same };
      }));
    }
  }
  const days = [...selected].sort(([a],[b])=>a.localeCompare(b)).map(([date, meals])=>({ date, meals }));
  return { days, meal_count: days.reduce((n,d)=>n+d.meals.length,0), actual_entries: data.entries.filter(e=>e.date>=start && e.date<=end), workouts_changed: false, personal_energy_prescribed: false, nutrient_adequacy: 'not_evaluated' };
}
export async function readCalendar(raw: unknown, owner: string, range: { start: string; end: string }): Promise<NutritionCalendar> {
  const v=object(raw), c=object(v.catalog), {content_hash,...rest}=v, {content_hash: catalogHash,...catalogRest}=c;
  civilDay(range.start);civilDay(range.end);
  ensure(['nutrition-calendar-v0.1','nutrition-calendar-v0.2'].includes(String(v.schema_version)) && v.athlete_id===owner && v.start_date===range.start && v.end_date===range.end && range.start<=range.end && Date.parse(range.end)-Date.parse(range.start)<366*86400000 && v.read_only===true);
  ensure(await sha(rest)===content_hash && catalogHash===CATALOG_HASH && await sha(catalogRest)===catalogHash);
  const catalog=c as unknown as Catalog; ensure(Array.isArray(v.sources) && v.sources.length<=366);
  const sources=await Promise.all(v.sources.map(s=>readNutritionArtifact(s,owner,catalog)));
  ensure(new Set(sources.map(s=>s.artifact_id)).size===sources.length);
  for(let i=1;i<sources.length;i++)ensure(Date.parse(sources[i-1].created_at)>=Date.parse(sources[i].created_at));
  const journal=await readJournal(v.journal,owner,catalog);ensure(v.timezone===journal.timezone);
  const timing=v.schema_version==='nutrition-calendar-v0.2'?readTimingContext(v.timing_context,owner,range.start,range.end):undefined;
  if(timing)ensure(timing.timezone===v.timezone&&timing.local_today===journal.local_today);else ensure(v.timing_context===undefined);
  ensure(canonical(v.result)===canonical(projectCalendar(sources,journal.saved?.proposal.data??blankJournal(),range.start,range.end,catalog,journal.sources,timing)));
  return v as unknown as NutritionCalendar;
}
export function expandedRange(start: string, end: string) {
  civilDay(start);civilDay(end);
  const last=new Date(end+'T12:00:00Z');last.setUTCMonth(last.getUTCMonth()+1,0);
  const first=start.slice(0,7)+'-01';
  return {start:civilDay(first,-28),end:civilDay(last.toISOString().slice(0,10),28)};
}
export async function loadCalendar(owner: string, range: {start:string;end:string}, signal?: AbortSignal) {
  const abort=new AbortController(),cancel=()=>abort.abort(),timer=setTimeout(cancel,30000);signal?.addEventListener('abort',cancel,{once:true});
  try { if(signal?.aborted)abort.abort();const r=await fetch('/api/goal-workflow/nutrition/calendar?'+new URLSearchParams({start_date:range.start,end_date:range.end}),{signal:abort.signal,cache:'no-store'});ensure(r.ok,'Az étkezések nem tölthetők be. Az edzésnaptár ettől még használható.');return await readCalendar(await r.json(),owner,range); }
  finally {clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
}
export function sourceContext(c: NutritionCalendar, meal: CalendarMeal): Context {
  const saved=c.sources.find(s=>s.artifact_id===meal.source.artifact_id && s.content_hash===meal.source.content_hash);ensure(saved);
  return {schema_version:'nutrition-workspace-v0.1',athlete_id:c.athlete_id,local_today:c.journal.local_today,catalog:c.catalog,saved,reference:meal.source,content_hash:c.content_hash,...(c.timing_context?{timing_context:c.timing_context}:{})};
}
