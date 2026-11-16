"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import {loadFeed} from "@/lib/calendar/client";
import {calendarCycles,cycleProgress} from "@/lib/calendar/cycles";
import {cycleData,cycleLoad,cycleLoadLabels,loadCycleContext} from "@/lib/calendar/cycle-context";
import type {CycleContext} from "@/lib/calendar/cycle-context";
import {cycleCoverage} from "@/lib/calendar/cycle-coverage";
import {formatDay,formatDuration,localParts,requireValue} from "@/lib/calendar/contracts";
import type {Feed,Period} from "@/lib/calendar/contracts";
import {capabilityLabels,roleLabels} from "@/lib/planning-goals/labels";
import type {GoalRole} from "@/lib/planning-goals/types";
import {strengthReasons} from "@/lib/planning-cycles/strength-assessment";
import {sourceChangeLabels} from "@/lib/planning-cycles/assessment-source-changes";
import ProfileChanges from "@/components/planning-cycles/profile-changes";
import {daylightReasons} from "@/lib/training-options/daylight-rules";
import {waveLabels} from "@/lib/planning-cycles/mesocycle-coordination";

const reasonLabels:Record<string,string>={...strengthReasons,...daylightReasons,GOAL_NOT_SELECTED:"Volt választható edzés, de másik változat került a tervbe.",ROLLING_BUDGET_REVIEW:"A gördülő heti keret nem engedett további alkalmat.",MINIMUM_SPACING:"Nem maradt megfelelő idő a többi edzéshez képest.",SWIMMING_ABILITY_REQUIRED:"Az önálló úszástudás még tisztázandó.",OPPORTUNITY_OR_DAILY_MINUTE_CAP:"Az edzés nem fért a használható időkeretbe.",CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT:"Az adott célhoz az elérhető sportágakban még nincs használható minta."};
const totals=(v:{count:number;seconds:number;unknown:number})=>`${v.count} alkalom · ${formatDuration(v.seconds)}${v.unknown?` ismert idő; ${v.unknown} alkalom időtartama hiányzik`:""}`;
const exactDay=(value:string)=>`${value.slice(0,4)}. ${formatDay(value)}`;
export function CycleLoadLegend() {
  return <div className="pt-cycle-load-legend" aria-label="Mikrociklusok tervezett időkerete">{Object.entries(cycleLoadLabels).map(([tone,label])=><span key={tone}><b data-cycle-load={tone}/>{label}</span>)}<small>A színek a mentett időkeret hullámzását jelzik. A piros a kezdőkeret 100%-a; nem személyes határterhelés vagy intenzitási zóna. Szín nélkül: nincs ehhez a naphoz igazolt, elfogadott szakaszolás.</small></div>;
}
export function CycleDetailContent({feed,context,period,focusOrdinal=0}:{feed:Feed;context:CycleContext;period:Period;focusOrdinal?:number}) {
  const data=cycleData(context,period),coverage=cycleCoverage(feed,period),cycles=calendarCycles([period]);
  const active=cycles.find(c=>c.kind==="meso")!,date=feed.local_today;
  const progress=cycleProgress(active,date),roles:GoalRole[]=["primary_development","secondary_development","maintenance","permitted_decline"];
  return <>
    <section className="pt-data-panel"><h3>A szakasz időrendje</h3><p><strong>Kezdés:</strong> {exactDay(period.start_date)} · <strong>Tervezett befejezés:</strong> {exactDay(period.end_date)}</p><p>{date<period.start_date?"Még nem kezdődött el.":date>period.end_date?"A tervezett időszak lezárult.":`Jelenleg a ${progress.day}/${progress.total}. napnál tartunk.`}</p><div className="pt-cycle-totals"><p><strong>Igazolt befejezett teljesítések</strong><br/>{totals(coverage.completed)}</p><p><strong>Hátralévő naptári terv</strong><br/>{totals(coverage.upcoming)}</p></div>
      {coverage.incomplete>0&&<p>{coverage.incomplete} megkezdett rögzítésnél a befejezés még nem igazolt.</p>}
      {coverage.elapsedUnconfirmed>0&&<p>{coverage.elapsedUnconfirmed} lejárt tervhez nem látható rögzített teljesítés; ebből kihagyást nem állapítunk meg.</p>}
      {coverage.reportedOnly>0&&<p>{coverage.reportedOnly} terv teljesítettnek jelölt, kapcsolt tényleges edzésadat nélkül.</p>}
    </section>
    <section className="pt-data-panel"><h3>A mezociklus mentett céljai</h3>
      {data?.latest_review&&<p className="pt-notice">A tervezési indokok legutóbbi felülvizsgálata: {formatDay(localParts(data.latest_review.created_at,feed.timezone_name).date)}.</p>}
      {!data?.goals.length&&<p>Ehhez a mezociklushoz még nincs mentett képességcél. A célokat az edzés címéből vagy sportágából nem találjuk ki.</p>}
      {roles.map(role=>{const goals=data?.goals.filter(g=>g.role===role)??[];return goals.length>0&&<div className="pt-cycle-goal-group" key={role}><h4>{roleLabels[role]}</h4>{goals.map(g=>{const actual=coverage.byGoal[g.capability_key]?.actual??{count:0,seconds:0,unknown:0},planned=coverage.byGoal[g.capability_key]?.planned??{count:0,seconds:0,unknown:0};
        const report=data?.latest_review?.goal_coverage.find(r=>r.capability_key===g.capability_key&&r.role===g.role);
        return <article key={g.capability_key}><strong>{capabilityLabels[g.capability_key]}</strong><dl><dt>Rögzített teljesítés ezzel a fő céllal</dt><dd>{totals(actual)}</dd><dt>Hátralévő terv ezzel a fő céllal</dt><dd>{totals(planned)}</dd></dl>
          {g.rationale&&<p className="pt-notice">{g.rationale}</p>}
          {planned.count===0&&role!=="permitted_decline"&&<p className="pt-notice">Jelenleg nincs ehhez a célhoz rendelt hátralévő edzés.</p>}
          {report&&report.status!=="represented"&&<p className="pt-notice">A legutóbbi felülvizsgálat: {report.status==="unsupported"?"ehhez a célhoz még nincs automatikus minta.":[...new Set(report.reasons.map(code=>reasonLabels[code]??"További megadott feltétel korlátozta az elhelyezést."))].join(" ")}</p>}
          {report?.reasons.includes("STRENGTH_ASSESSMENT_SOURCES_CHANGED")&&data?.latest_review?.source_changes?.map(code=><p key={code} className="pt-notice">{sourceChangeLabels[code]}</p>)}
          {g.capability_key==="MAX_STRENGTH"&&<ProfileChanges value={data?.latest_review?.profile_comparison}/>}
        </article>;})}</div>;})}
      {coverage.unassigned>0&&<p className="pt-notice">{coverage.unassigned} befejezett edzésnél nincs hozzárendelt fő cél; ezeket egyik képességhez sem számoltuk hozzá.</p>}
      <p className="pt-notice">Ez a célok edzésbeli képviselete. Az alkalmak száma és időtartama önmagában nem igazolja a képesség javulását vagy a cél elérését; ehhez összehasonlítható felmérés kell.</p>
      <Link href="/planning-goals">Sportcélok és képességhangsúlyok megtekintése / módosítása →</Link>
    </section>
    <section className="pt-data-panel"><h3>Mikrociklusok a mezocikluson belül</h3><CycleLoadLegend/>
      <div className="pt-cycle-table-scroll"><table className="pt-cycle-table"><thead><tr><th>Szakasz és dátum</th><th>Mentett felső keret</th><th>Rögzített teljesítések</th><th>Hátralévő terv</th></tr></thead><tbody>{cycles.filter(c=>c.kind==="micro").map(c=>{const block=data?.blocks.find(b=>b.ordinal===c.ordinal),band=cycleLoad(context,feed,c.start_date),v=cycleCoverage(feed,{...period,start_date:c.start_date,end_date:c.end_date});return <tr key={c.id} data-micro-ordinal={c.ordinal} data-cycle-load={band?.tone} aria-current={c.start_date<=date&&date<=c.end_date?"step":undefined} className={focusOrdinal===c.ordinal?"is-focused":""}><th scope="row">{c.title}<small>{formatDay(c.start_date)} – {formatDay(c.end_date)}</small>{block&&<small>{waveLabels[block.kind]}</small>}</th><td>{block?`${block.volume_percent}% · ${block.max_minutes} perc · legfeljebb ${block.max_sessions} alkalom`:"Nincs elfogadott szakaszkeret"}</td><td>{totals(v.completed)}</td><td>{totals(v.upcoming)}</td></tr>;})}</tbody></table></div>
      {data?.wave_source&&<p className="pt-notice">Elfogadott szakaszolás: {formatDay(localParts(data.wave_source.accepted_at,feed.timezone_name).date)}. A felső keret nem kitöltendő kvóta.</p>}
      {data?.wave_status==="dates_changed"&&<p>A ciklus dátumai megváltoztak az utolsó elfogadott terv óta. A régi szakaszok színét nem vetítjük az új dátumokra.</p>}
      {data?.wave_status==="short_review"&&<p>Az utolsó elfogadott terv rövid dátumablakra készült; ebből nem állapítjuk meg a teljes mezociklus terhelési hullámát.</p>}
    </section>
    {Object.keys(coverage.bySport).length>0&&<section className="pt-data-panel"><h3>Befejezett edzések sportáganként</h3>{Object.entries(coverage.bySport).map(([sport,v])=><p key={sport}>{({STRENGTH:"Erősítés",RUNNING:"Futás",SWIMMING:"Úszás",KAYAK:"Kajak"} as Record<string,string>)[sport]??sport}: {totals(v)}</p>)}</section>}
    <div className="pt-context-links"><Link href={`/training-periods/${period.id}`}>Teljes mezociklus-adatlap →</Link><Link href="/planning-cycles">Sportcélok és felkészülés →</Link></div>
  </>;
}
export default function CycleDetail({period,owner,zone,focusOrdinal=0,onClose}:{period:Period;owner:string;zone:string;focusOrdinal?:number;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null),[result,setResult]=useState<{feed:Feed;context:CycleContext}|null>(null),[error,setError]=useState(""),[retry,setRetry]=useState(0);
  useEffect(()=>{const node=dialog.current,previous=document.activeElement as HTMLElement|null;node?.showModal();return()=>{node?.close();previous?.focus();};},[]);
  useEffect(()=>{const abort=new AbortController();Promise.all([loadFeed({start:period.start_date,end:period.end_date},abort.signal),loadCycleContext({athlete_id:owner,timezone_name:zone,start_date:period.start_date,end_date:period.end_date},abort.signal)]).then(([feed,context])=>{
    if(abort.signal.aborted)return;
    requireValue(feed.athlete_id===owner&&feed.timezone_name===zone&&feed.start_date===period.start_date&&feed.end_date===period.end_date&&feed.periods.some(p=>p.id===period.id&&p.start_date===period.start_date&&p.end_date===period.end_date)&&cycleData(context,period)!==null,"A mezociklus közben megváltozott. Frissítsd a naptárat, majd nyisd meg újra.");setResult({feed,context});setError("");
  }).catch(e=>{if(!abort.signal.aborted)setError(e instanceof Error?e.message:"A ciklusadatok nem tölthetők be.");});return()=>abort.abort();},[period,owner,zone,retry]);
  useEffect(()=>{if(result&&focusOrdinal)dialog.current?.querySelector(`[data-micro-ordinal="${focusOrdinal}"]`)?.scrollIntoView({block:"nearest"});},[result,focusOrdinal]);
  return <dialog ref={dialog} className="pt-calendar-dialog pt-cycle-dialog" aria-label="Mezociklus részletei" onCancel={onClose} onClose={onClose}><header><div><p>{exactDay(period.start_date)} – {exactDay(period.end_date)}</p><h2>{period.title}</h2></div><button type="button" className="pt-button" onClick={onClose} aria-label="Mezociklusablak bezárása">Bezárás ×</button></header>
    {!result&&!error&&<p role="status">A teljes mezociklus céljainak és edzésadatainak betöltése…</p>}
    {error&&<div role="alert"><p>{error}</p><button type="button" className="pt-button" onClick={()=>{setError("");setRetry(n=>n+1);}}>Újrapróbálás</button> <Link href={`/training-periods/${period.id}`}>Teljes mezociklus-adatlap →</Link></div>}
    {result&&<CycleDetailContent {...result} period={period} focusOrdinal={focusOrdinal}/>}</dialog>;
}
