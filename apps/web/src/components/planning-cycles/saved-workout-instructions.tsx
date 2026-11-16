"use client";
import {useEffect,useState} from "react";
import {loadFeed} from "@/lib/calendar/client";
import type {WorkoutInstructions} from "@/lib/planning-cycles/workout-instructions";
import WorkoutInstructionDetails from "./workout-instructions";
import ManualWorkoutDetails from "@/components/calendar/manual-workout-details";
import type {ManualDraft} from "@/lib/calendar/manual-workouts";

export default function SavedWorkoutInstructions({id,date,sport,duration,description}:{id:string;date:string;sport:string;duration:number|null;description:string|null}) {
  const key=JSON.stringify([id,date,sport,duration,description]);
  const [state,setState]=useState<{key:string;value:WorkoutInstructions|null;manual:ManualDraft|null;error:string}|null>(null),[attempt,setAttempt]=useState(0);
  useEffect(()=>{const abort=new AbortController();loadFeed({start:date,end:date},abort.signal).then(feed=>{
    if(abort.signal.aborted)return;
    const row=feed.planned.find(p=>p.id===id);
    if(row&&(row.sport!==sport||row.duration_sec!==duration||row.description!==description))throw Error("Az edzés közben megváltozott. Frissítsd az adatlapot.");
    if(row?.planning_context?.instructions_issue)throw Error("A részletes gyakorlatsor most nem ellenőrizhető. Az eredeti edzésleírás továbbra is használható.");
    setState({key,value:row?.planning_context?.instructions??null,manual:row?.manual_context?.recipe??null,error:""});
  }).catch(e=>{if(!abort.signal.aborted)setState({key,value:null,manual:null,error:e instanceof Error?e.message:"A gyakorlatsor most nem tölthető be."});});return()=>abort.abort();},[key,id,date,sport,duration,description,attempt]);
  const {value,manual,error}=state?.key===key?state:{value:null,manual:null,error:""};
  if(error)return <div role="status"><p>{error}</p><button type="button" className="pt-button" onClick={()=>setAttempt(n=>n+1)}>Gyakorlatsor újraolvasása</button></div>;
  return manual?<ManualWorkoutDetails value={manual}/>:value?<WorkoutInstructionDetails value={value}/>:null;
}
