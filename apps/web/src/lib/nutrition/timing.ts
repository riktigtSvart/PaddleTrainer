import { canonical, day, object } from '@/lib/planning-cycles/contracts';
import type { JournalData, Slot } from './journal';
import type { Context, Meal } from './contracts';

export type TimingContext = { schema_version:'nutrition-timing-v0.1';rules_version:'meal-clock-0.1';athlete_id:string;timezone:string;start_date:string;end_date:string;now:string;local_today:string;activities:{workout_id:string;date:string;start_second:number;end_second:number}[];uncertain_dates:string[] };
export type MealTiming = {time:string|null;origin:'manual'|'unset'|'routine'|'learned'|'default'|'past_unknown'|'no_window';shifted:boolean;conflict:boolean;incomplete:boolean};
const order:Slot[]=['breakfast','lunch','snack','dinner'];
const defaults:Record<Slot,number>={breakfast:27000,lunch:45000,snack:57600,dinner:68400};
const bounds:Record<Slot,[number,number]>={breakfast:[18000,39600],lunch:[39600,55800],snack:[50400,66600],dinner:[61200,81000]};
const seconds=(s:string)=>s.split(':').reduce((n,x)=>n*60+Number(x),0);
const clock=(s:number)=>[Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(x=>String(x).padStart(2,'0')).join(':');
const formatters=new Map<string,Intl.DateTimeFormat>(),offsets=new Map<string,number[]>();
function check(v:unknown):asserts v {if(!v)throw Error('Az automatikus étkezési időpontok adatai nem ellenőrizhetők.');}
function local(at:number,zone:string){let f=formatters.get(zone);if(!f){f=new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});formatters.set(zone,f);}const p=Object.fromEntries(f.formatToParts(at).map(p=>[p.type,p.value]));return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;}
function realClock(date:string,value:number,zone:string){const wall=date+'T'+clock(value),base=Date.parse(wall+'Z'),key=zone+'/'+date;let os=offsets.get(key);if(!os){const found=new Set<number>();for(let h=-36;h<=36;h+=6){const at=base+h*3600000;found.add(Date.parse(local(at,zone)+'Z')-at);}os=[...found];offsets.set(key,os);}return new Set(os.map(o=>base-o).filter(at=>local(at,zone)===wall)).size===1;}
export function readTimingContext(raw:unknown,owner:string,start?:string,end?:string):TimingContext {
 const c=object(raw);check(c.schema_version==='nutrition-timing-v0.1'&&c.rules_version==='meal-clock-0.1'&&c.athlete_id===owner&&typeof c.timezone==='string'&&typeof c.start_date==='string'&&typeof c.end_date==='string'&&typeof c.now==='string'&&typeof c.local_today==='string');
 day(c.start_date);day(c.end_date);day(c.local_today);check(c.start_date<=c.end_date&&Date.parse(c.end_date)-Date.parse(c.start_date)<366*86400000&&(!start||c.start_date===start)&&(!end||c.end_date===end)&&/(?:Z|[+-]\d\d:\d\d)$/.test(c.now)&&Number.isFinite(Date.parse(c.now))&&local(Date.parse(c.now),c.timezone).slice(0,10)===c.local_today);
 check(Array.isArray(c.activities)&&c.activities.length<=16000&&Array.isArray(c.uncertain_dates)&&c.uncertain_dates.length<=366);
 const keys=new Set<string>();for(const raw of c.activities){const a=object(raw);check(typeof a.workout_id==='string'&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(a.workout_id)&&typeof a.date==='string'&&a.date>=c.start_date&&a.date<=c.end_date&&Number.isInteger(a.start_second)&&Number.isInteger(a.end_second)&&Number(a.start_second)>=0&&Number(a.end_second)<=86400&&Number(a.start_second)<Number(a.end_second));day(a.date);const k=a.workout_id+'/'+a.date;check(!keys.has(k));keys.add(k);}
 check(new Set(c.uncertain_dates).size===c.uncertain_dates.length&&c.uncertain_dates.every(d=>typeof d==='string'&&d>=c.start_date!&&d<=c.end_date!));for(const d of c.uncertain_dates)day(d as string);
 return c as unknown as TimingContext;
}
export function daySchedule(data:JournalData,date:string,slots:Slot[],context:TimingContext):Record<Slot,MealTiming> {
 const blocks=context.activities.filter(a=>a.date===date),incomplete=context.uncertain_dates.includes(date),wallNow=local(Date.parse(context.now),context.timezone);
 const overrides=new Map(data.timings.filter(t=>t.date===date).map(t=>[t.slot,t.time])),used:number[]=[],result={} as Record<Slot,MealTiming>,anchors=new Map<Slot,{anchor:number;origin:MealTiming['origin']}>();
 const collision=(value:number)=>blocks.some(a=>value<a.end_second+900&&value+1800>a.start_second-900);
 const item=(value:number|null,origin:MealTiming['origin'],shifted=false):MealTiming=>({time:value===null?null:clock(value),origin,shifted,conflict:value!==null&&collision(value),incomplete});
 for(const slot of slots){if(overrides.has(slot)){const raw=overrides.get(slot)!,value=raw===null?null:seconds(raw);result[slot]=item(value,value===null?'unset':'manual');if(value!==null)used.push(value);continue;}
  const routine=data.default_times[slot];let anchor:number,origin:MealTiming['origin'];
  if(routine!==null){anchor=seconds(routine);origin='routine';}else{const observed=data.entries.filter(e=>e.status==='eaten'&&e.source?.slot===slot&&e.timezone===context.timezone&&e.date+'T'+e.time!<=wallNow).map(e=>seconds(e.time!)).sort((a,b)=>a-b);anchor=observed.length>=3?observed[Math.floor(observed.length/2)]:defaults[slot];origin=observed.length>=3?'learned':'default';}
  if(date<context.local_today){result[slot]=routine!==null?item(seconds(routine),'routine'):item(null,'past_unknown');continue;}anchors.set(slot,{anchor,origin});
 }
 for(const [slot,{anchor,origin}] of [...anchors].sort(([a,x],[b,y])=>x.anchor-y.anchor||order.indexOf(a)-order.indexOf(b))){const [low,high]=origin==='default'?bounds[slot]:[Math.max(0,anchor-7200),Math.min(84600,anchor+7200)],free=(v:number)=>!collision(v)&&used.every(u=>Math.abs(v-u)>=3600)&&realClock(date,v,context.timezone);
  let value:number|null=low<=anchor&&anchor<=high&&free(anchor)?anchor:null;
  if(value===null){const candidates:number[]=[];for(let v=Math.ceil(low/300)*300;v<=high;v+=300)if(free(v))candidates.push(v);const after=candidates.find(v=>v>=anchor);if(collision(anchor)&&after!==undefined&&after-anchor<=7200)value=after;else if(candidates.length)value=candidates.sort((a,b)=>Math.abs(a-anchor)-Math.abs(b-anchor)||Number(a<anchor)-Number(b<anchor)||a-b)[0];}
  result[slot]=item(value,value===null?'no_window':origin,value!==null&&value!==anchor);if(value!==null)used.push(value);
 }return result;
}
export function mealTiming(menu:Context,data:JournalData,meal:Meal,slots?:Slot[]):MealTiming|null {
 const c=menu.timing_context;if(!c||meal.date<c.start_date||meal.date>c.end_date)return null;
 const list=slots??menu.saved?.proposal.data.plan?.meals.filter(m=>m.date===meal.date).map(m=>m.slot)??order;
 return daySchedule(data,meal.date,list.includes(meal.slot)?list:[...list,meal.slot],c)[meal.slot];
}
export function timingLabel(t:MealTiming):string {
 const text={manual:'Kézzel megadott időpont',unset:'Kézzel időpont nélkül hagyva',routine:'A szokásos időpontodból',learned:'A naplózott szokásaidból',default:'Automatikus kiinduló időpont',past_unknown:'Korábbi időpont nincs rögzítve',no_window:'Nem találtunk szabad időpontot'}[t.origin];
 return text+(t.shifted?' · naptárhoz igazítva':'')+(t.conflict?' · edzés közelében':'')+(t.incomplete?' · egy edzés időpontja vagy hossza hiányzik':'');
}
export function timingChanged(data:JournalData,saved:JournalData|undefined,meal:Meal){return canonical(data.timings.find(t=>t.date===meal.date&&t.slot===meal.slot)??null)!==canonical(saved?.timings.find(t=>t.date===meal.date&&t.slot===meal.slot)??null);}
