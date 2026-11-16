"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {canonical} from '@/lib/planning-cycles/contracts';
import {selectionRequest} from '@/lib/calendar/alternative-selection';
import {cachedSavedOptions,chooseSavedOption,clearSavedOptions,liveSavedOptions,loadSavedOptions} from '@/lib/calendar/saved-options';
import type {SavedOption,SavedOptions} from '@/lib/calendar/saved-options';
import type {FocusWorkout} from '@/lib/calendar/training-alternatives';
import {scheduleKey} from '@/lib/calendar/alternative-variants';
import {readTrainingPending,sendTraining} from '@/lib/planning-cycles/training-plan';
import type {TrainingPending} from '@/lib/planning-cycles/training-plan';
import {formatDay,formatDuration,goalLabels,localParts} from '@/lib/calendar/contracts';
import {CalendarHTTPError} from '@/lib/calendar/client';
import {CycleHTTPError} from '@/lib/planning-cycles/client';
import {planSportLabels} from '@/lib/planning-cycles/plan-view';
import {goalRoleLabels} from '@/lib/planning-cycles/alternative-availability';
import WorkoutInstructionDetails from '@/components/planning-cycles/workout-instructions';
import {LOCAL_REFRESH_EVENT} from '@/lib/data-connections/preferences';

function AlternativeCard({option,target,zone,locked,recommended,onChoose,now}:{option:SavedOption;target:FocusWorkout;zone:string;locked:boolean;recommended:string|null;onChoose:(option:SavedOption)=>void;now:number}){
 const {candidate:c,timing:t}=option,isCurrent=option.is_current;
 const start=Math.max(Date.parse(c.start_at),now),end=start+c.duration_sec*1000;
 return <article className={`pt-alternative-card${isCurrent?' is-selected':''}`} data-candidate-key={c.candidate_key} data-goal-role={c.role}>
  <button type="button" className="pt-alternative-select" aria-pressed={isCurrent} disabled={locked||isCurrent} onClick={()=>onChoose(option)}>
   <span className="pt-alternative-title">{c.title}</span>
   <span>{isCurrent?'Kijelölt edzés':recommended===c.candidate_key?'Ajánlott a még elérhető változatok közül':'Ezt választom'}</span>
   <span>{planSportLabels[c.sport??'']??c.sport} · {c.location} · {localParts(new Date(start).toISOString(),zone).clock}–{localParts(new Date(end).toISOString(),zone).clock} · {formatDuration(c.duration_sec)}</span>
   <span><strong>{goalRoleLabels[c.role]??'Más edzéscél'}</strong> · {goalLabels[c.capability_key]??c.capability_key}</span>
   <span>{c.capability_key!==target.primary_goal?`Más célt szolgál, mint az eredeti ${goalLabels[target.primary_goal]??target.primary_goal}.`:'Megőrzi az eredeti edzés célját.'}</span>
   <span>Legkésőbbi kezdés: {localParts(t.expires_at,zone).clock}{t.expires_inclusive?'':' előtt'}.{t.limiting_factors.includes('daylight_end')?' Napfénykorláttal szűkített időablak.':''}</span>
  </button>
  <details><summary>Edzés részletei</summary>{option.instructions?<WorkoutInstructionDetails value={option.instructions}/>:<p>{c.description}</p>}</details>
 </article>;
}

/** Read prepared cards on opening. Planning occurs only after an explicit choice. */
export default function WorkoutAlternatives({owner,zone,target,onApplied}:{owner:string;zone:string;today:string;target:FocusWorkout;onApplied:()=>void}){
 const expected=useMemo(()=>({owner,zone,reference:target.program_reference}),[owner,zone,target.program_reference]);
 const [options,setOptions]=useState<SavedOptions|null>(()=>cachedSavedOptions(owner,target));
 const [loading,setLoading]=useState(()=>!cachedSavedOptions(owner,target)),[busy,setBusy]=useState(false),[error,setError]=useState(''),[clock,setClock]=useState(()=>Date.now());
 const [pending,setPending]=useState<TrainingPending|null>(null),[storageBlocked,setStorageBlocked]=useState(false),[rejected,setRejected]=useState(false);
 const mounted=useRef(false),running=useRef(false),loadingRef=useRef(false),pendingRef=useRef(false),valueRef=useRef(options),loadController=useRef<AbortController|null>(null);
 const storageKey=`paddletrainer.training-plan.pending.v1:${owner}:${target.program_reference.artifact_id}`;
 const report=useCallback((e:unknown)=>{
  const code=e instanceof CycleHTTPError||e instanceof CalendarHTTPError?e.code:'';
  setError(code==='TRAINING_PLAN_ALTERNATIVES_NOT_AVAILABLE'?'Az edzés megváltozott, vagy már van hozzá teljesítési adat. Frissítsd a naptárt.':code==='TRAINING_PLAN_ALTERNATIVE_EXPIRED'?'Ez a változat időközben lejárt. Válassz a még elérhető lehetőségek közül.':e instanceof Error?e.message:'Az edzésválasztás nem sikerült.');
 },[]);
 const refresh=useCallback(async()=>{
  if(running.current||loadingRef.current||pendingRef.current)return;
  loadingRef.current=true;const abort=new AbortController();loadController.current=abort;
  if(mounted.current){setLoading(!valueRef.current);setError('');}
  try{const next=await loadSavedOptions(expected,target,abort.signal);if(!abort.signal.aborted&&mounted.current){valueRef.current=next;setOptions(next);setClock(Date.now());}}
  catch(e){if(!abort.signal.aborted&&mounted.current)report(e);}
  finally{if(loadController.current===abort){loadingRef.current=false;if(mounted.current&&!abort.signal.aborted)setLoading(false);}}
 },[expected,target,report]);
 useEffect(()=>{
  mounted.current=true;let active=true,canLoad=true;
  queueMicrotask(()=>{if(!active)return;try{const raw=sessionStorage.getItem(storageKey);if(raw){canLoad=false;pendingRef.current=true;setPending(readTrainingPending(raw,owner,target.program_reference.artifact_id));setLoading(false);}}
   catch{canLoad=false;setStorageBlocked(true);setLoading(false);setError('A korábbi mentés eredménye még nem tisztázott. Új választás előtt ellenőrizni kell.');}if(canLoad)void refresh();});
  const tick=()=>setClock(Date.now()),timer=window.setInterval(tick,1000);
  const focus=()=>{tick();if(canLoad)void refresh();};window.addEventListener('focus',focus);
  // Background checks are small GETs; opening/focusing never creates a review.
  const poll=window.setInterval(()=>{if(canLoad&&document.visibilityState!=='hidden')void refresh();},30000);
  return()=>{active=false;mounted.current=false;loadController.current?.abort();loadingRef.current=false;window.clearInterval(timer);window.clearInterval(poll);window.removeEventListener('focus',focus);};
 },[owner,storageKey,target.program_reference.artifact_id,refresh]);
 async function commit(request:TrainingPending){
  sessionStorage.setItem(storageKey,JSON.stringify(request));pendingRef.current=true;if(mounted.current)setPending(request);
  await sendTraining(request);sessionStorage.removeItem(storageKey);pendingRef.current=false;clearSavedOptions();window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
  if(mounted.current){setPending(null);onApplied();}
 }
 async function handleSelect(option:SavedOption){
  if(!options||busy||loading||pending||storageBlocked||running.current||option.is_current)return;
  running.current=true;setBusy(true);setError('');
  try{const chosen=await chooseSavedOption(expected,target,options,option);await commit(selectionRequest(expected,target,chosen));}
  catch(e){if(mounted.current){setRejected((e instanceof CycleHTTPError||e instanceof CalendarHTTPError)&&e.status>=400&&e.status<500);report(e);}}
  finally{running.current=false;if(mounted.current)setBusy(false);}
 }
 async function retry(){if(!pending||running.current)return;running.current=true;setBusy(true);setError('');try{await commit(pending);}catch(e){if(mounted.current){setRejected(e instanceof CycleHTTPError&&e.status>=400&&e.status<500);report(e);}}finally{running.current=false;if(mounted.current)setBusy(false);}}
 const rows=options?liveSavedOptions(options,clock):[],baseline=canonical(target.alternative_kinds?.workout_variant??rows.find(r=>r.is_current)?.workout_variant??null);
 const groups=new Map<string,SavedOption[]>(),same:SavedOption[]=[];
 for(const row of rows){const k=canonical(row.workout_variant);if(k===baseline){if(!row.is_current&&scheduleKey(row.candidate as unknown as Record<string,unknown>)!==target.alternative_kinds?.original_schedule)same.push(row);}else{const list=groups.get(k)??[];if(!list.some(r=>scheduleKey(r.candidate as unknown as Record<string,unknown>)===scheduleKey(row.candidate as unknown as Record<string,unknown>)))list.push(row);groups.set(k,list);}}
 const other=[...groups.entries()].sort((a,b)=>a[1][0].timing.goal_rank-b[1][0].timing.goal_rank);
 const recommended=rows.some(r=>r.candidate.candidate_key===options?.recommended_candidate_key)?options!.recommended_candidate_key:[...rows].sort((a,b)=>a.timing.goal_rank-b.timing.goal_rank||Number(b.candidate.capability_key===target.primary_goal)-Number(a.candidate.capability_key===target.primary_goal))[0]?.candidate.candidate_key??null;
 const unavailable=options?.status==='unavailable',locked=busy||loading||!!pending||storageBlocked||unavailable;
 const cards=(items:SavedOption[])=><div className="pt-alternative-cards">{items.map(row=><AlternativeCard key={row.candidate.candidate_key} option={row} target={target} zone={zone} locked={locked} recommended={recommended} onChoose={handleSelect} now={clock}/>)}</div>;
 return <div className="pt-workout-alternatives" data-alternatives-date={target.date} aria-busy={loading||busy}>
  <h3>Az adott nap alternatívái · {formatDay(target.date)}</h3>
  <p>Kattints arra az edzésre, amelyiket választod. A kijelölés az adott nap edzését cseréli; a többi nap terve megmarad.</p>
  {(loading||busy)&&<p role="status">{busy?'A kijelölt edzés ellenőrzése és mentése…':'A mentett edzések betöltése…'}</p>}
  {error&&<div role="alert" className="pt-message is-error"><p>{error}</p></div>}
  {unavailable&&<p role="status">Az edzés megváltozott, vagy már van hozzá teljesítési adat. A naptár frissítése után a jelenlegi állapot látszik.</p>}
  {pending&&!busy&&<div className="pt-notice"><p>A korábbi választás mentésének eredménye ellenőrzésre vár.</p><button type="button" className="pt-button" onClick={()=>void retry()}>Mentés eredményének ellenőrzése</button>{rejected&&<button type="button" className="pt-button" onClick={()=>{sessionStorage.removeItem(storageKey);pendingRef.current=false;setPending(null);setRejected(false);setError('');void refresh();}}>Elutasított kérés elvetése</button>}</div>}
  {options?.status==='ready'&&<>
   <section className="pt-alternative-section"><h4>Más edzések ({other.length})</h4>{!other.length&&<p>Most nincs eltérő tartalmú választható edzés.</p>}{other.map(([k,list])=><section className="pt-alternative-workout" key={k}><h5>{list[0].candidate.title}</h5>{cards(list)}</section>)}</section>
   <section className="pt-alternative-section"><h4>Ugyanez az edzés máskor vagy máshol ({same.length})</h4>{same.length?cards(same):<p>Most nincs további időpont vagy helyszín.</p>}</section>
   <p className="pt-options-meta">Mentett javaslatok. A lejárati időt folyamatosan figyeljük; választáskor az aktuális feltételeket is ellenőrizzük.</p>
  </>}
  {!loading&&!busy&&!pending&&!unavailable&&<button type="button" className="pt-button" disabled={storageBlocked} onClick={()=>void refresh()}>Lehetőségek újraolvasása</button>}
 </div>;
}
