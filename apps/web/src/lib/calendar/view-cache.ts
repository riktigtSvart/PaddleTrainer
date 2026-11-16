/** A workspace-local cache of already validated reads. No cross-account persistence. */
import {loadFeed} from './client';
import {loadConstraints} from './constraint-client';
import {loadCycleContext} from './cycle-context';
import {addDays,localParts} from './contracts';
import type {Feed} from './contracts';
import type {ScheduleContext} from './constraints';
import type {CycleContext} from './cycle-context';
import {sha} from '@/lib/planning-cycles/contracts';

export type Range={start:string;end:string};
const covers=(v:{start_date:string;end_date:string},r:Range)=>v.start_date<=r.start&&v.end_date>=r.end;
function intersects(start:string,end:string|null,r:Range,zone:string){
 return localParts(start,zone).date<=r.end&&localParts(end?new Date(Math.max(Date.parse(start),Date.parse(end)-1)).toISOString():start,zone).date>=r.start;
}
export function sliceFeed(feed:Feed,range:Range):Feed{
 if(!covers(feed,range))throw Error('A kért időszak nincs teljesen a betöltött adatok között.');
 const windows=[...feed.availability.carry_windows,...feed.availability.days.flatMap(d=>d.windows.map(w=>({...w,date:d.date})))];
 return {...feed,start_date:range.start,end_date:range.end,
  planned:feed.planned.filter(p=>p.date>=range.start&&p.date<=range.end||p.planned_start_time&&intersects(p.planned_start_time,p.duration_sec!==null?new Date(Date.parse(p.planned_start_time)+p.duration_sec*1000).toISOString():p.duration_estimate?new Date(Date.parse(p.planned_start_time)+p.duration_estimate.upper_sec*1000).toISOString():null,range,feed.timezone_name)),
  sessions:feed.sessions.filter(s=>intersects(s.started_at,s.ended_at??(s.duration_sec!==null?new Date(Date.parse(s.started_at)+s.duration_sec*1000).toISOString():null),range,feed.timezone_name)),
  periods:feed.periods.filter(p=>p.start_date<=range.end&&p.end_date>=range.start),
  availability:{...feed.availability,days:feed.availability.days.filter(d=>d.date>=range.start&&d.date<=range.end),carry_windows:windows.filter(w=>w.date<range.start&&intersects(w.start_at,w.end_at,range,feed.timezone_name))}};
}
export function sliceConstraints(value:ScheduleContext,range:Range):ScheduleContext{
 if(!covers(value,range))throw Error('A napirend kért időszaka még nincs betöltve.');
 return {...value,start_date:range.start,end_date:range.end,
  occurrences:value.occurrences.filter(o=>o.start_at?intersects(o.start_at,o.end_at,range,value.timezone_name):o.source_date>=range.start&&o.source_date<=range.end),
  conflicts:value.conflicts.filter(c=>c.date>=range.start&&c.date<=range.end),
  opportunities:value.opportunities.filter(o=>o.source_date>=range.start&&o.source_date<=range.end||o.intervals.some(i=>intersects(i.start_at,i.end_at,range,value.timezone_name)))};
}
export class CalendarViewCache{
 constructor(readonly generation=0){}
 private feeds:Feed[]=[];
 private constraints:ScheduleContext[]=[];
 private cycles:CycleContext[]=[];
 private remember<T>(rows:T[],value:T){rows.push(value);if(rows.length>12)rows.shift();return value;}
 async feed(range:Range|null,signal?:AbortSignal){
  signal?.throwIfAborted();
  const hit=range?[...this.feeds].reverse().find(f=>covers(f,range)):undefined;
  if(hit)return sliceFeed(hit,range!);
  const value=await loadFeed(range,signal);signal?.throwIfAborted();return this.remember(this.feeds,value);
 }
 async schedule(range:Range|null,signal?:AbortSignal){
  signal?.throwIfAborted();const hit=range?[...this.constraints].reverse().find(v=>covers(v,range)):undefined;
  if(hit)return sliceConstraints(hit,range!);
  const value=await loadConstraints(range,signal);signal?.throwIfAborted();return this.remember(this.constraints,value);
 }
 async cycle(feed:Feed,signal?:AbortSignal){
  signal?.throwIfAborted();const range={start:feed.start_date,end:feed.end_date};
  const hit=[...this.cycles].reverse().find(c=>c.athlete_id===feed.athlete_id&&c.timezone_name===feed.timezone_name&&covers(c,range));
  if(hit){const body={...hit,start_date:range.start,end_date:range.end,cycles:hit.cycles.filter(c=>c.period.start_date<=range.end&&c.period.end_date>=range.start)};body.content_hash=await sha(Object.fromEntries(Object.entries(body).filter(([k])=>k!=='content_hash')));return body;}
  const value=await loadCycleContext(feed,signal);signal?.throwIfAborted();return this.remember(this.cycles,value);
 }
 async prefetch(feed:Feed,signal?:AbortSignal){
  // A four-week block covers the small views, including either week alignment.
  const range={start:addDays(feed.start_date,-7),end:addDays(feed.start_date,34)};
  if(feed.end_date>=range.end)return;
  await Promise.all([this.feed(range,signal),this.schedule(range,signal)]);
 }
}
