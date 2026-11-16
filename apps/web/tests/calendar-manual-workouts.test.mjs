import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {load} from './load-goal-modules.mjs';

const api=JSON.parse(gunzipSync(readFileSync(new URL('./fixtures/c21-10-20-manual-workouts.json.gz',import.meta.url))));
const manual=load('src/lib/calendar/manual-workouts.ts'), contracts=load('src/lib/calendar/contracts.ts');
const {forwardCalendar}=load('src/lib/calendar/proxy.ts');
const {default:Details}=load('src/components/calendar/manual-workout-details.tsx');
const owner=api.context.athlete_id, id=api.opened.workout.id;
const {alignManualDuration,manualDurationRoom,manualScheduleWarnings}=load('src/lib/calendar/manual-duration.ts');
const {durationHMS,parseDurationHMS}=load('src/lib/duration.ts');
const {default:DurationField}=load('src/components/ui/duration-field.tsx');

test('duration fields represent exact amounts in HH:MM:SS, including over one hour',()=>{
  for(const [seconds,text] of [[0,'00:00:00'],[30,'00:00:30'],[75,'00:01:15'],[3723,'01:02:03'],[86400,'24:00:00']]){
    assert.equal(durationHMS(seconds),text);assert.equal(parseDurationHMS(text),seconds);
  }
  assert.equal(parseDurationHMS('1:2:3'),3723);assert.equal(parseDurationHMS(''),null);
  for(const text of ['12','12:00','00:60:00','00:01:60','-00:01:00','00:01:30.5','aa:bb:cc'])assert(Number.isNaN(parseDurationHMS(text)),text);
  assert.equal(durationHMS(null),'Nincs adat');assert.equal(durationHMS(-75),'−00:01:15');
  const html=renderToStaticMarkup(React.createElement(DurationField,{label:'Időtartam',value:75,onChange(){}}));
  assert(html.includes('value="00:01:15"'));assert(html.includes('óra:perc:másodperc'));assert(!html.includes('type="time"'));
});

test('paired 3 x 12 / 2 means exactly 40 minutes with two rests, and auto total includes both',()=>{
  const d=timedDraft({duration_sec:2160,phases:[{...timedDraft().phases[1],recovery_duration_sec:120}]});
  const result=alignManualDuration(d);
  assert.equal(result.draft.duration_sec,2400);assert(result.adjusted);
  assert.equal(manual.manualPhaseSeconds(d.phases[0]),2400);
  assert.equal(manual.manualPhaseSeconds({...d.phases[0],repeat_count:1}),720);
  assert.equal(manual.validateManualDraft(result.draft).length,0);assert(manual.validateManualDraft(d).length>0);
  const html=renderToStaticMarkup(React.createElement(Details,{value:result.draft}));
  for(const phrase of ['00:12:00','00:02:00','2 pihenő','00:40:00','Az utolsó ismétlés után nincs külön pihenő'])assert(html.includes(phrase),phrase);
});

test('sub-minute work and rest are exact while separate legacy recoveries retain their original count',()=>{
  const phase={...timedDraft().phases[1],duration_sec:75,repeat_count:4,recovery_duration_sec:45};
  assert.equal(manual.manualPhaseSeconds(phase),435);
  const legacy=timedDraft({duration_sec:2520,phases:[{...phase,duration_sec:720,repeat_count:3,recovery_duration_sec:null},{...phase,block_type:'RECOVERY',duration_sec:120,repeat_count:3,recovery_duration_sec:null}]});
  assert.equal(legacy.phases.reduce((n,p)=>n+manual.manualPhaseSeconds(p),0),2520);
  assert.equal(manual.validateManualDraft(legacy).length,0);
  for(const value of [NaN,-1,true,1.5,86401])assert(manual.validateManualDraft({...legacy,phases:[{...phase,recovery_duration_sec:value}]}).length>0);
});

function timedDraft(changes={}) {
  return {...manual.blankManualDraft('2026-11-17'),sport:'RUNNING',title:'3 × 12 / 2 futás',start_time:'19:00',duration_sec:53*60,
    phases:[{block_type:'WARMUP',name:'Bemelegítés',duration_sec:600,repeat_count:1},{block_type:'WORK',name:'Résztáv',duration_sec:720,repeat_count:3},{block_type:'RECOVERY',name:'Pihenő',duration_sec:120,repeat_count:2},{block_type:'COOLDOWN',name:'Levezetés',duration_sec:300,repeat_count:1}].map(p=>({...p,distance_m:null,notes:''})),...changes};
}
function opportunity(start='2026-11-17T18:00:00Z',end='2026-11-17T19:00:00Z',changes={}) {
  return {source_date:'2026-11-17',known:true,max_minutes:60,daily_max_minutes:null,intervals:[{start_at:start,end_at:end}],...changes};
}
function schedule(opportunities,changes={}) {return {athlete_id:owner,timezone_name:'Europe/Budapest',start_date:'2026-10-01',end_date:'2026-12-31',timezone_review_required:false,availability:null,occurrences:[],opportunities,...changes};}
function busy(start='2026-11-17T18:00:00Z',end='2026-11-17T19:00:00Z',title='Munka') {return {details:{kind:'busy',title},start_at:start,end_at:end,issue:null};}
const warnings=(draft,s,dates)=>manualScheduleWarnings(draft,s,owner,'Europe/Budapest',dates);

test('phase editing grows 53 minutes to 55 including exact rest repeats without changing the work',()=>{
  const original=timedDraft(),before=structuredClone(original),result=alignManualDuration(original);
  assert(result.adjusted);assert.equal(result.draft.duration_sec,3300);assert.equal(result.issue,null);
  assert.deepEqual(result.draft.phases,original.phases);assert.deepEqual(original,before);
});
test('a larger authored total and unspecified phase durations are preserved',()=>{
  const larger=timedDraft({duration_sec:3600});assert.strictEqual(alignManualDuration(larger).draft,larger);
  const partial=timedDraft({phases:[{...timedDraft().phases[0],duration_sec:null}]});assert.strictEqual(alignManualDuration(partial).draft,partial);
  assert.equal(alignManualDuration(timedDraft({duration_sec:null})).draft.duration_sec,3300);
});
test('insufficient declared room warns while automatic phase totals and valid manual saving remain usable',()=>{
  const d=timedDraft(),result=alignManualDuration(d),s=schedule([opportunity(undefined,undefined,{max_minutes:54})]);
  assert(result.adjusted);assert.equal(result.draft.duration_sec,3300);assert.equal(result.issue,null);
  assert.match(warnings(result.draft,s)[0],/00:55:00.*00:54:00/);
  assert.equal(manual.validateManualDraft(result.draft).length,0);
  assert.match(warnings({...d,duration_sec:3600},s)[0],/01:00:00.*00:54:00/);
  assert.deepEqual(warnings(result.draft,schedule([opportunity(undefined,undefined,{max_minutes:55})])),[]);
});
test('a busy commitment warns by name even without timed phases and never changes any draft or schedule',()=>{
  const d=timedDraft({phases:[],duration_sec:2400}),s=schedule([],{occurrences:[busy()]});
  const before=structuredClone({d,s});
  assert.match(warnings(d,s)[0],/2026-11-17.*Munka/);
  assert.equal(manual.validateManualDraft(d).length,0);assert.strictEqual(alignManualDuration(d).draft,d);
  assert.deepEqual({d,s},before);
});
test('busy overlap is half-open, covers overnight work and stops warning when the time moves away',()=>{
  const d=timedDraft({phases:[],duration_sec:1800}),s=schedule([],{occurrences:[busy()]});
  for(const time of ['18:30','20:00'])assert.deepEqual(warnings({...d,start_time:time},s),[]);
  assert.match(warnings({...d,start_time:'19:59:59'},s)[0],/Munka/);
  assert.match(warnings({...d,date:'2026-11-18',start_time:'00:30'},schedule([],{occurrences:[busy('2026-11-17T22:00:00Z','2026-11-18T01:00:00Z','Éjszakai munka')]}))[0],/Éjszakai munka/);
  assert.deepEqual(warnings({...d,start_time:null},s),[]);
});
test('weekly occurrences are warned separately only where loaded schedule evidence exists',()=>{
  const d=timedDraft({phases:[],duration_sec:2400});
  const s=schedule([],{end_date:'2026-11-30',occurrences:[busy('2026-11-24T18:00:00Z','2026-11-24T19:00:00Z','Második heti munka'),busy('2026-12-01T18:00:00Z','2026-12-01T19:00:00Z','Nem betöltött nap')]});
  const result=warnings(d,s,[d.date,'2026-11-24','2026-11-24','2026-12-01']);
  assert.equal(result.length,1);assert.match(result[0],/2026-11-24.*Második heti munka/);
  for(const changed of [{athlete_id:id},{timezone_name:'UTC'},{timezone_review_required:true}])assert.deepEqual(warnings(d,{...s,...changed},['2026-11-24']),[]);
  assert.deepEqual(warnings(d,undefined),[]);
});
test('unavailable days and ordinary free-text plans receive advisory room warnings without becoming invalid',()=>{
  const d=timedDraft({phases:[],duration_sec:3600});
  const s=schedule([],{availability:{artifact:{proposal:{data:{days:[{date:d.date,status:'unavailable'}]}}}}});
  assert.match(warnings(d,s)[0],/01:00:00.*00:00:00/);assert.equal(manual.validateManualDraft(d).length,0);
  assert.deepEqual(warnings(d,schedule([])),[]);
  assert.deepEqual(warnings(d,schedule([opportunity(undefined,undefined,{known:false,intervals:[]})])),[]);
  for(const value of [NaN,null,-1,86401])assert.deepEqual(warnings({...d,duration_sec:value},s),[]);
});
test('a fraction of a minute remains exact and invalid phases are not repaired by changing the total',()=>{
  const d=timedDraft({duration_sec:60,phases:[{...timedDraft().phases[0],duration_sec:125}]});
  assert.equal(alignManualDuration(d).draft.duration_sec,125);
  for(const change of [{duration_sec:NaN},{duration_sec:-1},{repeat_count:true},{repeat_count:0},{repeat_count:1.5}]){
    const invalid=timedDraft({phases:[{...d.phases[0],...change}]});assert.strictEqual(alignManualDuration(invalid).draft,invalid);
  }
  assert.match(alignManualDuration(timedDraft({phases:[{...d.phases[0],duration_sec:86400,repeat_count:2}]})).issue,/24:00:00/);
});
test('capacity respects the remaining interval, a source budget and a daily cap',()=>{
  const d=timedDraft();assert.equal(manualDurationRoom(d,schedule([opportunity()]),owner,'Europe/Budapest'),3600);
  assert.equal(manualDurationRoom({...d,start_time:'19:10'},schedule([opportunity()]),owner,'Europe/Budapest'),3000);
  assert.equal(manualDurationRoom(d,schedule([opportunity(undefined,undefined,{max_minutes:40})]),owner,'Europe/Budapest'),2400);
  assert.equal(manualDurationRoom(d,schedule([opportunity(undefined,undefined,{daily_max_minutes:30})]),owner,'Europe/Budapest'),1800);
});
test('separate or interrupted opportunities are alternatives, not additive free time',()=>{
  const d=timedDraft({start_time:null});
  assert.equal(manualDurationRoom(d,schedule([opportunity('2026-11-17T18:00:00Z','2026-11-17T18:30:00Z'),opportunity('2026-11-17T19:00:00Z','2026-11-17T19:30:00Z')]),owner,'Europe/Budapest'),1800);
  assert.equal(manualDurationRoom({...d,start_time:'19:00'},schedule([opportunity(undefined,undefined,{intervals:[{start_at:'2026-11-17T18:00:00Z',end_at:'2026-11-17T18:20:00Z'},{start_at:'2026-11-17T18:30:00Z',end_at:'2026-11-17T19:00:00Z'}]})]),owner,'Europe/Budapest'),1200);
});
test('a sport or named location must fit at least one declared alternative',()=>{
  const windows=schedule([opportunity(undefined,undefined,{constraints:{sports:['SWIMMING'],location:'Uszoda'}}),opportunity(undefined,undefined,{constraints:{sports:['RUNNING'],location:'Otthon'},max_minutes:45})]);
  assert.equal(manualDurationRoom(timedDraft({location:' otthon '}),windows,owner,'Europe/Budapest'),2700);
  assert.equal(manualDurationRoom(timedDraft({location:'Csónakház'}),windows,owner,'Europe/Budapest'),0);
});
test('absent, foreign, stale-range and unresolved schedule information never invents zero capacity',()=>{
  const d=timedDraft();for(const s of [undefined,schedule([]),schedule([opportunity()],{athlete_id:id}),schedule([opportunity()],{start_date:'2026-12-01'}),schedule([opportunity()],{timezone_review_required:true}),schedule([opportunity(undefined,undefined,{known:false,intervals:[]})])])assert.equal(manualDurationRoom(d,s,owner,'Europe/Budapest'),null);
  assert.equal(manualDurationRoom(d,schedule([],{availability:{artifact:{proposal:{data:{days:[{date:d.date,status:'unavailable'}]}}}}}),owner,'Europe/Budapest'),0);
});
test('overnight opportunities retain the current start and DST fold changes the actual remaining time',()=>{
  const overnight=schedule([opportunity('2026-11-17T22:00:00Z','2026-11-18T01:00:00Z',{max_minutes:180})]);
  assert.equal(manualDurationRoom(timedDraft({date:'2026-11-18',start_time:'00:30'}),overnight,owner,'Europe/Budapest'),5400);
  const autumn=schedule([opportunity('2026-10-24T23:00:00Z','2026-10-25T03:00:00Z',{source_date:'2026-10-25',max_minutes:240})]);
  const d=timedDraft({date:'2026-10-25',start_time:'02:30'});
  assert.equal(manualDurationRoom(d,autumn,owner,'Europe/Budapest'),null);
  assert.equal(manualDurationRoom({...d,start_fold:0},autumn,owner,'Europe/Budapest'),9000);
  assert.equal(manualDurationRoom({...d,start_fold:1},autumn,owner,'Europe/Budapest'),5400);
});

test('actual API authoring context and saved feed retain exact planned dose without inventing actual history',()=>{
  const opened=manual.readManualContext(api.opened,owner,id);
  const feed=contracts.readFeed(structuredClone(api.feed)),row=feed.planned.find(p=>p.id===id);
  assert.equal(opened.workout.draft.exercises[0].weight_kg,'72.125');
  assert.equal(row.manual_context.recipe.exercises[0].sets,4);
  assert.equal(contracts.eventsFrom(feed).find(e=>e.entityId===id).goal,'MAX_STRENGTH');
  assert(!feed.sessions.some(s=>s.planned_workout_id===id));
});
test('manual prescription displays every set, decimal load, bodyweight and hold without a formal assessment',()=>{
  const d=structuredClone(api.opened.workout.draft);
  d.exercises.push({...d.exercises[1],name:'Oldalsó plank',reps:null,hold_seconds:35,sets:2});
  const html=renderToStaticMarkup(React.createElement(Details,{value:d}));
  for(const text of ['összesen 9 sorozat','4 × 8 ismétlés','72.125 kg','3 × 6 ismétlés','Saját testsúly','2 × 00:00:35 tartás'])assert(html.includes(text),text);
  assert(!html.includes('felmérési referencia'));
});
test('weekly repetition follows local calendar dates across DST and includes the first occurrence exactly once',()=>{
  assert.deepEqual(manual.weeklyDates('2027-03-21',4),['2027-03-28','2027-04-04','2027-04-11']);
  assert.deepEqual(manual.weeklyDates('2026-11-20',1),[]);
  for(const [day,n] of [['2026-02-30',2],['2100-12-30',2],['2026-11-20',25],['2026-11-20',true]])assert.throws(()=>manual.weeklyDates(day,n));
});
for(const [name,change] of [
 ['missing title',d=>d.title=' '],['negative duration',d=>d.duration_sec=-60],
 ['phase duration over total',d=>d.duration_sec=100],['zero sets',d=>d.exercises[0].sets=0],
 ['boolean reserve',d=>d.exercises[0].reserve_reps=true],['ambiguous dose',d=>d.exercises[0].hold_seconds=30],
 ['missing weight',d=>d.exercises[0].weight_kg=null],['other sport',d=>d.sport='RUNNING'],
 ['bad date',d=>d.date='2026-02-30'],['invalid time',d=>d.start_time='25:30'],
])test('save validation explains '+name,()=>{const d=structuredClone(api.opened.workout.draft);change(d);assert(manual.validateManualDraft(d).length);});
for(const change of [c=>c.athlete_id='00000000-0000-0000-0000-000000000001',c=>c.workout.id=c.athlete_id,c=>c.workout.source_hash='bad'])test('editor context refuses another owner, target or missing source identity',()=>{
  const c=structuredClone(api.opened);change(c);assert.throws(()=>manual.readManualContext(c,owner,id));
});
test('an invalid optional manual recipe never hides a valid calendar or other workout',()=>{
  const x=structuredClone(api.feed);x.planned.find(p=>p.id===id).manual_context.recipe.exercises[0].sets=-10;
  const read=contracts.readFeed(x);assert(!read.planned.find(p=>p.id===id).manual_context);assert.equal(read.planned.length,api.feed.planned.length);
});
test('an optional recipe from another workout cannot appear under the current workout title',()=>{
  const x=structuredClone(api.feed);x.planned.find(p=>p.id===id).manual_context.recipe.title='Another workout';
  assert(!contracts.readFeed(x).planned.find(p=>p.id===id).manual_context);
});
test('real receipt is bound to owner, request, operation, occurrence count and target',()=>{
  assert(manual.readManualReceipt(api.edited,owner,api.edit_body).committed);
  assert(manual.readManualReceipt(api.copied,owner,api.copy_body).committed);
  for(const change of [r=>r.athlete_id=id,r=>r.request_id=id,r=>r.operation='cancel',r=>r.workout_ids=[],r=>r.workout_ids=[owner]]){
    const r=structuredClone(api.edited);change(r);assert.throws(()=>manual.readManualReceipt(r,owner,api.edit_body));
  }
});
test('manual proxy exposes only the exact owner-scoped read/write paths and never forwards unexpected queries',async()=>{
  const calls=[];const send=async(url,init)=>{calls.push({url:String(url),init});return Response.json({ok:true});};
  const request=(path,method='GET',body)=>new Request('https://paddle.test/api/calendar/'+path,{method,headers:{origin:'https://paddle.test','content-type':'application/json'},...(body?{body}:{} )});
  for(const path of ['manual-workouts/context','manual-workouts/'+id])assert.equal((await forwardCalendar(request(path),path.split('/'),'http://api.internal',send)).status,200);
  const body=JSON.stringify(api.edit_body);assert.equal((await forwardCalendar(request('manual-workouts','POST',body),['manual-workouts'],'http://api.internal',send)).status,200);
  assert.equal(calls[2].init.body,body);
  for(const [path,method,status] of [['manual-workouts','GET',405],['manual-workouts/context','POST',405],['manual-workouts/foreign','GET',404],['manual-workouts/'+id+'/delete','POST',404],['manual-workouts/context?athlete_id='+owner,'GET',422]]){
    const count=calls.length;assert.equal((await forwardCalendar(request(path,method,method==='POST'?'{}':undefined),path.split('?')[0].split('/'),'http://api.internal',send)).status,status);assert.equal(calls.length,count);
  }
});
test('manual proxy retains origin and bounded-body protection',async()=>{
  let sent=0;const send=async()=>{sent++;return Response.json({});};
  for(const [origin,body,status] of [['https://evil.test','{}',403],['https://paddle.test','x'.repeat(262145),413]]){
    const r=new Request('https://paddle.test/api/calendar/manual-workouts',{method:'POST',headers:{origin,'content-type':'application/json'},body});
    assert.equal((await forwardCalendar(r,['manual-workouts'],'http://api.internal',send)).status,status);
  }
  assert.equal(sent,0);
});
