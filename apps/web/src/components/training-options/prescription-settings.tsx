"use client";
import {useState} from "react";
import {addDays} from "@/lib/planning-cycles/contracts";
import {Field,Select,buttonClass} from "@/components/planning-goals/fields";
import {readPrescriptionSettings,swimStrokes} from "@/lib/training-options/prescription-settings";
import type {PrescriptionSettings,SwimStroke} from "@/lib/training-options/prescription-settings";
import type {OptionsData} from "@/lib/training-options/contracts";
export default function PrescriptionSettingsEditor({data,today,disabled,save}:{data:OptionsData;today:string;disabled:boolean;save:(v:OptionsData)=>Promise<boolean>}) {
  const [baseline,setBaseline]=useState(!!data.prescription_settings?.current_baseline),[swim,setSwim]=useState(!!data.prescription_settings?.swimming),[error,setError]=useState("");
  const [value,setValue]=useState<PrescriptionSettings>(()=>({schema_version:"training-prescription-settings-v0.1",
    current_baseline:data.prescription_settings?.current_baseline??{from_date:addDays(today,-27),to_date:today,weekly_sessions:NaN,weekly_minutes:NaN},
    swimming:data.prescription_settings?.swimming??{reported_on:today,independent:false,strokes:["freestyle"],preferred_stroke:"freestyle",continuous_distance_m:null,continuous_minutes:null}}));
  const b=value.current_baseline!,s=value.swimming!;
  return <div className="pt-options-form" id="prescription-settings"><h3>Jelenlegi edzésmennyiség és úszási kiindulópont</h3>
    <p>A szabad időt az órarendben adod meg. Itt azt rögzítsd, amit mostanában ténylegesen, szokásosan teljesítesz. A régi egyéni csúcsok külön tájékozódási pontok maradnak.</p>
    <fieldset disabled={disabled} className="space-y-4"><label className="flex gap-2"><input type="checkbox" checked={baseline} onChange={e=>setBaseline(e.target.checked)}/>Megadom az aktuális, szokásos heti edzésmennyiségemet</label>
      {baseline&&<div className="pt-options-columns"><Field label="Az ismert aktuális időszak kezdete" type="date" value={b.from_date} max={today} onChange={e=>setValue({...value,current_baseline:{...b,from_date:e.target.value}})}/><Field label="Az ismert aktuális időszak vége" type="date" value={b.to_date} max={today} onChange={e=>setValue({...value,current_baseline:{...b,to_date:e.target.value}})}/>
        <Field label="Tényleges szokásos edzésszám hetente · összes sport együtt" type="number" min={1} max={28} value={Number.isFinite(b.weekly_sessions)?b.weekly_sessions:""} onChange={e=>setValue({...value,current_baseline:{...b,weekly_sessions:e.target.value?Number(e.target.value):NaN}})}/>
        <Field label="Tényleges szokásos edzésidő hetente · perc" type="number" min={1} max={10080} value={Number.isFinite(b.weekly_minutes)?b.weekly_minutes:""} onChange={e=>setValue({...value,current_baseline:{...b,weekly_minutes:e.target.value?Number(e.target.value):NaN}})}/>
        <p className="sm:col-span-2">Legalább két, legfeljebb nyolc hét szokásos terhelését írd le. Ezt a friss önbevallást a tervező kiinduló heti keretként használhatja, a rendelkezésre álló időn és a korlátaidon belül.</p>
      </div>}
      <label className="flex gap-2"><input type="checkbox" checked={swim} onChange={e=>setSwim(e.target.checked)}/>Megadom az úszási kiindulópontomat</label>
      {swim&&<div className="space-y-3"><label className="flex gap-2"><input type="checkbox" checked={s.independent} onChange={e=>setValue({...value,swimming:{...s,independent:e.target.checked}})}/>Önállóan tudok úszni; a megadott úszásnemeket stabilan végzem</label>
        <fieldset className="pt-options-checks"><legend>Ismert úszásnemek</legend>{Object.entries(swimStrokes).map(([key,label])=><label key={key}><input type="checkbox" checked={s.strokes.includes(key as SwimStroke)} onChange={e=>{const strokes=e.target.checked?[...s.strokes,key as SwimStroke]:s.strokes.filter(k=>k!==key);setValue({...value,swimming:{...s,strokes,preferred_stroke:strokes.includes(s.preferred_stroke)?s.preferred_stroke:strokes[0]??"freestyle"}});}}/>{label}</label>)}</fieldset>
        <div className="pt-options-columns"><Select label="Előnyben részesített úszásnem" value={s.preferred_stroke} onChange={e=>setValue({...value,swimming:{...s,preferred_stroke:e.target.value as SwimStroke,continuous_distance_m:null,continuous_minutes:null}})}>{s.strokes.map(k=><option key={k} value={k}>{swimStrokes[k]}</option>)}</Select>
          <Field label="Úszási önbevallás dátuma" type="date" max={today} value={s.reported_on} onChange={e=>setValue({...value,swimming:{...s,reported_on:e.target.value}})}/>
          <Field label="A választott úszásnemben most kényelmes folyamatos táv · méter, ha ismert" type="number" min={10} max={20000} value={s.continuous_distance_m??""} onChange={e=>setValue({...value,swimming:{...s,continuous_distance_m:e.target.value?Number(e.target.value):null}})}/>
          <Field label="A választott úszásnemben most kényelmes folyamatos úszás ideje · perc, ha ismert" type="number" min={1} max={240} value={s.continuous_minutes??""} onChange={e=>setValue({...value,swimming:{...s,continuous_minutes:e.target.value?Number(e.target.value):null}})}/>
        </div><p>Szokásos, könnyű teljesítésből indulj ki. Nem szükséges új maximális próbát végezned. A medence pontos hosszát az edzéshelyszínnél adhatod meg.</p>
      </div>}
      <button type="button" className={buttonClass} onClick={async()=>{setError("");try{const p=readPrescriptionSettings({...value,current_baseline:baseline?b:null,swimming:swim?s:null});if((p.current_baseline&&p.current_baseline.to_date>today)||(p.swimming&&p.swimming.reported_on>today))throw Error("Jövőbeli állapot nem adható meg.");await save({...data,prescription_settings:p});}catch(e){setError(e instanceof Error?e.message:"A tervezési adatok hibásak.");}}}>Terhelési és úszási adatok mentése</button>
    </fieldset>{error&&<p role="alert">{error}</p>}
  </div>;
}
