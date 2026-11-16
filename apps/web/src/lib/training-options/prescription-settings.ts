import {day,object} from "@/lib/planning-cycles/contracts";
export const swimStrokes={freestyle:"Gyorsúszás",breaststroke:"Mellúszás",backstroke:"Hátúszás",butterfly:"Pillangóúszás"} as const;
export type SwimStroke=keyof typeof swimStrokes;
export type TrainingBaseline={from_date:string;to_date:string;weekly_sessions:number;weekly_minutes:number};
export type SwimmingAbility={reported_on:string;independent:boolean;strokes:SwimStroke[];preferred_stroke:SwimStroke;continuous_distance_m:number|null;continuous_minutes:number|null};
export type PrescriptionSettings={schema_version:"training-prescription-settings-v0.1";current_baseline:TrainingBaseline|null;swimming:SwimmingAbility|null};
export function readPrescriptionSettings(raw:unknown):PrescriptionSettings {
  const p=object(raw),fail=()=>{throw Error("A jelenlegi terhelési alap vagy az úszási adatok hibásak.");};
  const integer=(n:unknown,low:number,high:number)=>typeof n==="number"&&Number.isSafeInteger(n)&&n>=low&&n<=high;
  if(Object.keys(p).sort().join()!=="current_baseline,schema_version,swimming"||p.schema_version!=="training-prescription-settings-v0.1")fail();
  if(p.current_baseline!==null){const b=object(p.current_baseline);day(String(b.from_date));day(String(b.to_date));const span=(Date.parse(String(b.to_date))-Date.parse(String(b.from_date)))/86400000+1;
    if(Object.keys(b).sort().join()!=="from_date,to_date,weekly_minutes,weekly_sessions"||span<14||span>56||!integer(b.weekly_sessions,1,28)||!integer(b.weekly_minutes,1,10080)||Number(b.weekly_minutes)<Number(b.weekly_sessions))fail();}
  if(p.swimming!==null){const s=object(p.swimming);day(String(s.reported_on));
    if(Object.keys(s).sort().join()!=="continuous_distance_m,continuous_minutes,independent,preferred_stroke,reported_on,strokes"||typeof s.independent!=="boolean"||!Array.isArray(s.strokes)||!s.strokes.length||s.strokes.length>4||new Set(s.strokes).size!==s.strokes.length||s.strokes.some(k=>!Object.hasOwn(swimStrokes,String(k)))||!s.strokes.includes(s.preferred_stroke)||
      (s.continuous_distance_m!==null&&!integer(s.continuous_distance_m,10,20000))||(s.continuous_minutes!==null&&!integer(s.continuous_minutes,1,240)))fail();}
  return p as PrescriptionSettings;
}
