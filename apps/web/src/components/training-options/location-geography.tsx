"use client";
import {useState} from "react";
import {Field,Select,secondaryClass} from "@/components/planning-goals/fields";
import {CoordinatesEditor} from "./daylight-settings";
import LocationMap from "./location-map";
import {readGeographicArea,decimalCoordinate} from "@/lib/training-options/daylight-rules";
import type {GeographicArea,DaylightRule} from "@/lib/training-options/daylight-rules";
import {loadDaylightPreview} from "@/lib/training-options/daylight";
import type {DaylightPreview} from "@/lib/training-options/daylight";
import {areaLightIntervals} from "@/lib/training-options/area-daylight";
import type {Location} from "@/lib/training-options/contracts";

export default function LocationGeography({value,change,defaultZone,owner,today,disabled,rules}: {value:Location;change:(v:Location)=>void;defaultZone:string;owner:string;today:string;disabled:boolean;rules:DaylightRule[]}) {
  const [map,setMap]=useState(false),[date,setDate]=useState(today),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [result,setResult]=useState<{key:string;value:DaylightPreview}|null>(null);
  const [mode,setMode]=useState<"point"|"area">(value.area?"area":"point");
  const area:GeographicArea=value.area??{schema_version:"training-area-v0.1",south:"",north:"",west:"",east:"",timezone_name:defaultZone};
  const normalized={...area,...Object.fromEntries(["south","north","west","east"].map(k=>[k,decimalCoordinate(area[k as keyof GeographicArea])]))} as GeographicArea;
  const key=JSON.stringify({date,area:normalized}),preview=result?.key===key?result.value:null;
  const clock=(t:number)=>new Intl.DateTimeFormat("hu",{timeZone:area.timezone_name,hour:"2-digit",minute:"2-digit"}).format(new Date(t*1000));
  return <fieldset disabled={disabled} className="pt-options-form"><legend>Földrajzi hely és edzési körzet</legend>
    <Select label="Földrajzi megadás" value={mode} onChange={e=>{const next=e.target.value as "point"|"area";setMode(next);change({...value,coordinates:undefined,area:undefined});setResult(null);}}>
      <option value="point">Konkrét hely / vízre szállási pont</option><option value="area">Változó helyszín egy kijelölt körzetben</option>
    </Select>
    <details onToggle={e=>setMap(e.currentTarget.open)}><summary>Térképes kijelölés</summary>{map&&<LocationMap mode={mode} point={value.coordinates} area={value.area} zone={value.area?.timezone_name??value.coordinates?.timezone_name??defaultZone}
      onPoint={coordinates=>{if(!disabled)change({...value,coordinates,area:undefined});}} onArea={area=>{if(!disabled)change({...value,kind:"mobile",coordinates:undefined,area});}}/>}</details>
    {mode==="point"?<CoordinatesEditor value={value.coordinates} defaultZone={defaultZone} owner={owner} today={today} disabled={disabled} rules={rules} onChange={coordinates=>change({...value,coordinates,area:undefined})}/>:<>
      <p>A teljes kijelölt körzetben megfelelő közös világos időablakkal tervezünk. A név lehet például „Duna – Győr és Mohács között”; a térképes kijelölés a teljes használható területet fedje le. Szűkebb, konkrét helyszíneket ugyanahhoz az idősávhoz további alternatívaként adhatsz meg.</p>
      <div className="pt-options-columns">{[["south","Déli szélességi határ"],["north","Északi szélességi határ"],["west","Nyugati hosszúsági határ"],["east","Keleti hosszúsági határ"]].map(([k,label])=><Field key={k} label={label} inputMode="decimal" value={area[k as keyof GeographicArea]} onChange={e=>change({...value,kind:"mobile",coordinates:undefined,area:{...area,[k]:e.target.value}})}/>)}
        <Field label="Körzet időzónája (IANA)" value={area.timezone_name} onChange={e=>change({...value,area:{...area,timezone_name:e.target.value}})}/>
        <Field label="Közös napfényidőszak ellenőrzésének dátuma" type="date" value={date} min="1900-01-01" max="2100-12-31" onChange={e=>setDate(e.target.value)}/>
      </div>
      <div className="pt-options-actions"><button type="button" className={secondaryClass} disabled={busy} onClick={async()=>{setBusy(true);setError("");try{readGeographicArea(normalized);setResult({key,value:await loadDaylightPreview(owner,{date,area:normalized})});}catch(e){setError(e instanceof Error?e.message:"A körzet hibás.");}finally{setBusy(false);}}}>{busy?"Számítás…":"Körzet napfényének ellenőrzése"}</button>
        {value.area&&<button type="button" className={secondaryClass} onClick={()=>{change({...value,area:undefined});setResult(null);}}>Körzet törlése</button>}
      </div>
      {error&&<p role="alert">{error}</p>}
      {preview&&<div aria-live="polite">{(["daylight","civil_twilight"] as const).map(mode=><p key={mode}>{mode==="daylight"?"Közös napfényidőszak":"Közös polgári hajnal–alkonyat időszak"}: {preview[mode].intervals.map(i=>`${clock(Date.parse(i.start_at)/1000)}–${clock(Date.parse(i.end_at)/1000)}`).join(", ")||"Nincs közös világos időszak."}</p>)}
        {rules.filter(r=>r.mode!=="none").map(r=><p key={r.sport}>{r.sport} · ráhagyással: {areaLightIntervals(Date.parse(preview.day_start_at)/1000,Date.parse(preview.day_end_at)/1000,normalized,r).map(([a,b])=>`${clock(a)}–${clock(b)}`).join(", ")||"Nem marad használható időablak."}</p>)}
      </div>}
      <small>A körzet számítása a teljes téglalapra, percenkénti időfelbontással és beépített óvatossági ráhagyással készül. Sík horizontot feltételez. Az időjárási korlátok külön ellenőrzést igényelnek.</small>
    </>}
  </fieldset>;
}
