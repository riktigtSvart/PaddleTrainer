import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {performance} from 'node:perf_hooks';
import {load} from './load-goal-modules.mjs';
const f=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-19-prepared-reads.json.gz',import.meta.url))));
const {readSavedOptions,loadSavedOptions,chooseSavedOption,cachedSavedOptions,clearSavedOptions,liveSavedOptions}=load('src/lib/calendar/saved-options.ts');
const {readFeed}=load('src/lib/calendar/contracts.ts');
const {readScheduleContext}=load('src/lib/calendar/constraints.ts');
const {CalendarViewCache,sliceFeed,sliceConstraints}=load('src/lib/calendar/view-cache.ts');
const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const {sha}=load('src/lib/planning-cycles/contracts.ts');
const expected={owner:f.options.athlete_id,zone:f.options.timezone_name,reference:f.options.program_reference};
const target={...f.target.planning_context,id:f.target.id};
const rehash=async value=>{const b={...value};delete b.content_hash;value.content_hash=await sha(b);};

test('real prepared cards retain instructions, exact dose and goal roles without loading the historical planning tree',async()=>{
 const value=await readSavedOptions(f.options,expected,target);
 assert.deepEqual(value,f.options);assert(value.candidates.some(r=>r.candidate.sport==='STRENGTH'&&r.instructions.main.strength));
 assert(!('inputs' in value));assert(!('plan_snapshots' in value));
});
test('opening uses one read-only GET and immediately reusable validated cache data',async t=>{
 clearSavedOptions();let calls=0;t.mock.method(globalThis,'fetch',async(url,init)=>{calls++;assert.equal(url,`/api/calendar/workouts/${target.id}/alternatives`);assert(!init.method);return Response.json(f.options);});
 await loadSavedOptions(expected,target);assert.equal(calls,1);assert.deepEqual(cachedSavedOptions(expected.owner,target),f.options);
 assert.equal(cachedSavedOptions('another-owner',target),null);assert.equal(cachedSavedOptions(expected.owner,{...target,workout_hash:'f'.repeat(64)}),null);
 clearSavedOptions();assert.equal(cachedSavedOptions(expected.owner,target),null);
});
test('a card click sends a scoped selection request and never asks for an opening-time review',async t=>{
 const sent=[];t.mock.method(globalThis,'fetch',async(url,init)=>{sent.push({url,body:JSON.parse(init.body)});return Response.json({review:f.chosen});});
 const chosen=await chooseSavedOption(expected,target,f.options,f.clicked);assert.deepEqual(chosen,f.chosen);
 assert.deepEqual(sent,[{url:`/api/calendar/workouts/${target.id}/alternatives/choose`,body:{expected_workout_hash:target.workout_hash,source_review_reference:f.options.source_review_reference,candidate_key:f.clicked.candidate.candidate_key}}]);
});
for(const name of ['owner','date','workout','hash','program','goal','role','dose','deadline','instructions'])test(`a rehashed prepared response rejects ${name}`,async()=>{
 const value=structuredClone(f.options),row=value.candidates.find(r=>r.instructions);
 if(name==='owner')value.athlete_id=crypto.randomUUID();if(name==='date')value.date='2026-10-27';if(name==='workout')value.workout_id=crypto.randomUUID();if(name==='hash')value.workout_hash='f'.repeat(64);
 if(name==='program')value.program_reference.content_hash='f'.repeat(64);if(name==='goal')row.candidate.capability_key='invented';if(name==='role')row.candidate.role='invented';
 if(name==='dose')row.candidate.duration_sec+=300;if(name==='deadline')row.timing.expires_at=new Date(Date.parse(row.timing.expires_at)+60000).toISOString();
 if(name==='instructions')row.instructions.duration_sec+=300;
 await rehash(value);await assert.rejects(()=>readSavedOptions(value,expected,target));
});
test('expiry is local arithmetic and needs no planner or network request',()=>{
 const expiry=Math.min(...f.options.candidates.map(r=>Date.parse(r.timing.expires_at)));
 const rows=liveSavedOptions(f.options,expiry+1);assert(rows.length<f.options.candidates.length);
 assert(rows.every(r=>Date.parse(r.timing.expires_at)>=expiry+1));
});
for(const name of ['week','day'])test(`a cached ${name} has exactly the same events and opportunities as the real narrow backend read`,async()=>{
 const wide=readFeed(f.ranges.wide.feed),narrow=readFeed(f.ranges[name].feed),range={start:narrow.start_date,end:narrow.end_date};
 const sliced=sliceFeed(wide,range);assert.deepEqual(sliced.planned,narrow.planned);assert.deepEqual(sliced.sessions,narrow.sessions);assert.deepEqual(sliced.periods,narrow.periods);assert.deepEqual(sliced.availability,narrow.availability);
 const full=await readScheduleContext(f.ranges.wide.constraints),small=await readScheduleContext(f.ranges[name].constraints),schedule=sliceConstraints(full,range);
 assert.deepEqual(schedule.occurrences,small.occurrences);assert.deepEqual(schedule.opportunities,small.opportunities);assert.deepEqual(schedule.conflicts,small.conflicts);
 await readScheduleContext(schedule);
});
test('week and day navigation within a loaded month performs zero additional network requests',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async(url)=>{calls++;return Response.json(String(url).includes('/constraints')?f.ranges.wide.constraints:f.ranges.wide.feed);});
 const cache=new CalendarViewCache(),wide={start:f.ranges.wide.feed.start_date,end:f.ranges.wide.feed.end_date};
 await cache.feed(wide);await cache.schedule(wide);assert.equal(calls,2);
 // A cached view must work without a connection. Elapsed time under a
 // concurrent test runner is a measurement, not a portable correctness gate.
 t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('A loaded view must not request the backend again.');});
 const started=performance.now();
 for(let i=0;i<20;i++)for(const name of ['week','day']){
  const r=f.ranges[name].feed,range={start:r.start_date,end:r.end_date};
  const feed=await cache.feed(range),schedule=await cache.schedule(range);
  assert.equal(feed.start_date,range.start);assert.equal(feed.end_date,range.end);
  assert.equal(schedule.start_date,range.start);assert.equal(schedule.end_date,range.end);
  assert.deepEqual(feed.planned.map(p=>p.id),r.planned.map(p=>p.id));
  assert.deepEqual(feed.sessions.map(s=>s.id),r.sessions.map(s=>s.id));
  assert.deepEqual(schedule.occurrences,f.ranges[name].constraints.occurrences);
  assert.deepEqual(schedule.opportunities,f.ranges[name].constraints.opportunities);
 }
 assert.equal(calls,2);
 t.diagnostic(`40 cached view transitions: ${(performance.now()-started).toFixed(1)} ms (informational; correctness requires zero extra requests and matching view data).`);
});
test('refresh creates a new cache generation and reads the current data again',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json(f.ranges.wide.feed);});
 const range={start:f.ranges.wide.feed.start_date,end:f.ranges.wide.feed.end_date};
 await new CalendarViewCache(0).feed(range);await new CalendarViewCache(1).feed(range);assert.equal(calls,2);
});
test('aborted reads are not inserted into a workspace cache',async t=>{
 const abort=new AbortController();let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;abort.abort();return Response.json(f.ranges.wide.feed);});
 const cache=new CalendarViewCache(),range={start:f.ranges.wide.feed.start_date,end:f.ranges.wide.feed.end_date};
 await assert.rejects(()=>cache.feed(range,abort.signal));t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json(f.ranges.wide.feed);});
 await cache.feed(range);assert.equal(calls,2);
});
for(const [suffix,method,status] of [['','GET',200],['/choose','POST',200],['','POST',405],['/choose','GET',405],['?start_date=2026-10-26','GET',422]])test(`saved options proxy is closed: ${method} ${suffix||'read'}`,async()=>{
 const path=`workouts/${target.id}/alternatives${suffix}`,url='http://localhost:3000/api/calendar/'+path;
 const req=new Request(url,{method,headers:method==='POST'?{Origin:'http://localhost:3000','Content-Type':'application/json'}:{},...(method==='POST'?{body:'{}'}:{})});
 const response=await forwardCalendar(req,path.split('?')[0].split('/'),'http://api.internal',async()=>Response.json({ok:true}));assert.equal(response.status,status);
});

test('new completion or changed prescription can close the picker even when the current workout hash has changed',async()=>{
 const value=structuredClone(f.options);value.status='unavailable';value.workout_hash='f'.repeat(64);value.candidates=[];value.recommended_candidate_key=null;value.source_review_reference=null;value.program_reference=null;value.prepared_at=null;
 await rehash(value);assert.equal((await readSavedOptions(value,expected,target)).status,'unavailable');
});
test('cached cycle colours and goals cover narrow views without another backend request',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json(f.ranges.wide.cycles);});
 const cache=new CalendarViewCache();await cache.cycle(readFeed(f.ranges.wide.feed));
 for(const name of ['week','day']){const value=await cache.cycle(readFeed(f.ranges[name].feed));assert.deepEqual(value.cycles,f.ranges[name].cycles.cycles);}
 assert.equal(calls,1);
});
test('local slicing preserves overnight entries and the upper duration bound across a DST weekend',()=>{
 const wide=structuredClone(f.ranges.wide.feed);wide.start_date='2026-10-24';wide.end_date='2026-10-26';wide.sessions=[];wide.availability={...wide.availability,days:[],carry_windows:[]};
 const plan={...wide.planned[0],date:'2026-10-24',planned_start_time:'2026-10-24T21:30:00+00:00',duration_sec:null,duration_estimate:{duration_sec:600,upper_sec:7200}};
 wide.planned=[plan];assert.equal(sliceFeed(wide,{start:'2026-10-25',end:'2026-10-25'}).planned.length,1);
 plan.duration_estimate.upper_sec=600;assert.equal(sliceFeed(wide,{start:'2026-10-25',end:'2026-10-25'}).planned.length,0);
});
