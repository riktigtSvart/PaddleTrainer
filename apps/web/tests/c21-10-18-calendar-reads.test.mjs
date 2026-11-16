import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {load} from './load-goal-modules.mjs';

const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const {calendarRead}=load('src/lib/calendar/read-request.ts');
const {loadFeed,saveGoal,CalendarHTTPError}=load('src/lib/calendar/client.ts');
const {loadCycleContext}=load('src/lib/calendar/cycle-context.ts');
const {loadConstraints,previewConstraints}=load('src/lib/calendar/constraint-client.ts');
const fixture=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-17-direct-picker.json.gz',import.meta.url))));
const cycles=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-7-calendar-cycles.json.gz',import.meta.url)))).accepted;
const unavailable=()=>Response.json({detail:{code:'CALENDAR_API_UNAVAILABLE'}},{status:502});
const request=signal=>new Request('http://localhost:3000/api/calendar/feed',{signal});

test('an abandoned view cancels its upstream fetch and is not reported as API unavailability',async()=>{
 const controller=new AbortController();let upstream;
 const response=await forwardCalendar(request(controller.signal),['feed'],'http://api.internal',async(url,init)=>{
  upstream=init.signal;controller.abort();upstream.throwIfAborted();
 });
 assert(upstream.aborted);assert.equal(response.status,499);
 assert.equal((await response.json()).detail.code,'CALENDAR_REQUEST_CANCELLED');
});

test('an already abandoned request never starts a backend request',async()=>{
 const controller=new AbortController();controller.abort();let calls=0;
 const response=await forwardCalendar(request(controller.signal),['feed'],'http://api.internal',async()=>{calls++;return unavailable();});
 assert.equal(calls,0);assert.equal(response.status,499);
});

test('the existing 30 second deadline is identified separately from a network failure',async t=>{
 const deadline=new AbortController();
 t.mock.method(AbortSignal,'timeout',ms=>{assert.equal(ms,30000);return deadline.signal;});
 const response=await forwardCalendar(request(),['feed'],'http://api.internal',async(url,init)=>{
  deadline.abort(new DOMException('deadline','TimeoutError'));init.signal.throwIfAborted();
 });
 assert.equal(response.status,504);assert.equal((await response.json()).detail.code,'CALENDAR_API_TIMEOUT');
});

test('a genuine network failure stays sanitized and the proxy does not retry',async()=>{
 let calls=0;
 const response=await forwardCalendar(request(),['feed'],'http://api.internal',async()=>{calls++;throw TypeError('private backend address');});
 assert.equal(calls,1);assert.equal(response.status,502);
 assert.deepEqual(await response.json(),{detail:{code:'CALENDAR_API_UNAVAILABLE'}});
});

test('a body failure after headers is caught before a successful JSON response escapes',async()=>{
 const response=await forwardCalendar(request(),['feed'],'http://api.internal',async()=>new Response(new ReadableStream({
  start(controller){controller.error(TypeError('connection lost during body'));},
 }),{headers:{'Content-Type':'application/json'}}));
 assert.equal(response.status,502);assert.equal((await response.json()).detail.code,'CALENDAR_API_UNAVAILABLE');
});

test('backend latency is available in headers without changing any response bytes or forwarding credentials',async()=>{
 const bytes='{"planned":[],"note":"ő"}';
 const response=await forwardCalendar(request(),['feed'],'http://api.internal',async(url,init)=>{
  assert(!('Authorization' in init.headers));assert.equal(init.cache,'no-store');
  return new Response(bytes,{headers:{'Content-Type':'application/json','Server-Timing':'calendar;dur=12.3','X-Private':'secret'}});
 });
 assert.equal(await response.text(),bytes);assert.equal(response.headers.get('Server-Timing'),'calendar;dur=12.3');
 assert.equal(response.headers.get('X-Private'),null);assert.equal(response.headers.get('Cache-Control'),'no-store');
});

for(const [status,code] of [[502,'CALENDAR_API_UNAVAILABLE'],[504,'CALENDAR_API_TIMEOUT'],[503,'CALENDAR_SOURCE_UNAVAILABLE']])
test(`a transient GET ${status} ${code} is retried exactly once`,async()=>{
 let calls=0;
 const response=await calendarRead('/api/calendar/feed',undefined,async(url,init)=>{
  calls++;assert(!init.method||init.method==='GET');assert.equal(init.cache,'no-store');
  return calls===1?Response.json({detail:{code}},{status}):Response.json({ok:true});
 });
 assert.equal(calls,2);assert.deepEqual(await response.json(),{ok:true});
});

test('a second temporary failure stops retrying',async()=>{
 let calls=0;
 const response=await calendarRead('/api/calendar/feed',undefined,async()=>{calls++;return unavailable();});
 assert.equal(calls,2);assert.equal(response.status,502);
});

test('a dropped network connection is retried once and a lasting failure has a useful message',async()=>{
 let calls=0;
 const response=await calendarRead('/api/calendar/feed',undefined,async()=>{if(++calls===1)throw TypeError('fetch failed');return Response.json({ok:true});});
 assert.equal(calls,2);assert.equal(response.status,200);calls=0;
 await assert.rejects(()=>calendarRead('/api/calendar/feed',undefined,async()=>{calls++;throw TypeError('private host');}),/kiszolgálója most nem érhető el/);
 assert.equal(calls,2);
});

for(const [status,code] of [[409,'CALENDAR_REVISION_CONFLICT_RELOAD'],[503,'TRAINING_PLAN_STORAGE_INVALID'],[503,'CALENDAR_API_CONFIGURATION_INVALID'],[502,'CALENDAR_API_RESPONSE_INVALID'],[499,'CALENDAR_REQUEST_CANCELLED']])
test(`proof, configuration and cancellation errors are not retried: ${code}`,async()=>{
 let calls=0;const response=await calendarRead('/api/calendar/feed',undefined,async()=>{calls++;return Response.json({detail:{code}},{status});});
 assert.equal(calls,1);assert.equal(response.status,status);
});

test('cancelling during the retry delay prevents the next upstream request',async()=>{
 const controller=new AbortController();let calls=0;
 const pending=calendarRead('/api/calendar/feed',controller.signal,async()=>{calls++;setTimeout(()=>controller.abort(),20);return unavailable();});
 await assert.rejects(pending,error=>error.name==='AbortError');assert.equal(calls,1);
});

test('a recovered feed still passes the original owner, source and prescription validation',async t=>{
 let calls=0;
 t.mock.method(globalThis,'fetch',async url=>{calls++;assert.match(url,/\/api\/calendar\/feed\?/);return calls===1?unavailable():Response.json(fixture.initial_feed);});
 const feed=await loadFeed({start:fixture.initial_feed.start_date,end:fixture.initial_feed.end_date});
 assert.equal(calls,2);assert.deepEqual(feed.planned,fixture.initial_feed.planned);
});

test('a malformed successful feed is rejected without a transport retry',async t=>{
 let calls=0;const forged=structuredClone(fixture.initial_feed);forged.planned[0].date='2026-02-30';
 t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json(forged);});
 await assert.rejects(()=>loadFeed(null));assert.equal(calls,1);
});

test('a persistent timeout explains the read failure in Hungarian',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json({detail:{code:'CALENDAR_API_TIMEOUT'}},{status:504});});
 await assert.rejects(()=>loadFeed(null),error=>error instanceof CalendarHTTPError&&error.status===504&&/túl sokáig tartott/.test(error.message));
 assert.equal(calls,2);
});

test('cycle colours and goals use the same bounded recovery without skipping their validator',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>++calls===1?unavailable():Response.json(cycles.context));
 const value=await loadCycleContext(cycles.feed);assert.equal(calls,2);assert.deepEqual(value,cycles.context);
});

test('constraints reads also retry, but a successful malformed context is not trusted',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>++calls===1?unavailable():Response.json({schema_version:'future'}));
 await assert.rejects(()=>loadConstraints(null));assert.equal(calls,2);
});

test('goal saves are never automatically replayed',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async(url,init)=>{calls++;assert.equal(init.method,'POST');return unavailable();});
 await assert.rejects(()=>saveGoal('{}',fixture.initial_feed.athlete_id));assert.equal(calls,1);
});

test('schedule previews and saves are not routed through GET recovery',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async(url,init)=>{calls++;assert.equal(init.method,'POST');return unavailable();});
 await assert.rejects(()=>previewConstraints({},fixture.initial_feed.athlete_id,'2026-10-26','2026-11-01'));assert.equal(calls,1);
});
