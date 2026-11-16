"use client";
import {useEffect,useState} from "react";
import {loadCycleContext} from "@/lib/calendar/cycle-context";
import type {CycleContext} from "@/lib/calendar/cycle-context";
import type {Feed} from "@/lib/calendar/contracts";
import type {CalendarViewCache} from '@/lib/calendar/view-cache';
export function useCycleContext(feed: Feed | null, enabled: boolean, cache?:CalendarViewCache) {
  const [state,setState]=useState<{key:string;data:CycleContext|null;error:string}>({key:"",data:null,error:""});
  const key=feed?`${feed.athlete_id}:${feed.timezone_name}:${feed.start_date}:${feed.end_date}:${feed.retrieved_at}`:"";
  useEffect(()=>{
    if(!feed||!enabled)return;
    const abort=new AbortController();
    (cache?cache.cycle(feed,abort.signal):loadCycleContext(feed,abort.signal)).then(data=>{if(!abort.signal.aborted)setState({key,data,error:""});}).catch(e=>{if(!abort.signal.aborted)setState({key,data:null,error:e instanceof Error?e.message:"A ciklusadatok nem tölthetők be."});});
    return()=>abort.abort();
  },[feed,key,enabled,cache]);
  return {data:enabled&&state.key===key?state.data:null,error:enabled&&state.key===key?state.error:""};
}
