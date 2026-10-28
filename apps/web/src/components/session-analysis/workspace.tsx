"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchAnalysis } from "@/lib/session-analysis/contracts";
import { UPDATED_EVENT } from "@/lib/data-connections/contracts";
import type { Analysis, Plan } from "@/lib/session-analysis/contracts";
import { clock } from "@/lib/session-analysis/chart-data";
import { Charts } from "./charts";
import { SpeedUnitControl, useSpeedUnit } from "./speed-unit-control";
import { speedValue } from "@/lib/session-analysis/presentation";
import { FeedbackPanel } from "./feedback";
import { SessionSections } from "./sections";

const number = (value: number | null | undefined, unit = "") => value === null || value === undefined ? "Nincs adat" :
  new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 2 }).format(value) + (unit ? " " + unit : "");
const duration = (seconds: number | null | undefined) => seconds === null || seconds === undefined ? "Nincs adat" : clock(seconds * 1000);
function instant(value: string | null, zone: string) { return value === null ? "Időpont nélkül" : new Intl.DateTimeFormat("hu-HU", { timeZone: zone, dateStyle: "short", timeStyle: "short" }).format(new Date(value)); }

export function SessionDetails({ data }: { data: Analysis }) {
  const [speedUnit, setSpeedUnit] = useSpeedUnit();
  const [exercise, setExercise] = useState(data.samples.series[0]?.exercise_index ?? data.samples.exercises[0]?.index ?? 0);
  const s = data.session, p = data.plan, series = data.samples.series.filter(r => r.exercise_index === exercise);
  const actualElapsed = s.ended_at !== null && Date.parse(s.ended_at) >= Date.parse(s.started_at) ? (Date.parse(s.ended_at) - Date.parse(s.started_at)) / 1000 : null;
  return <>
    <header className="pt-analysis-title"><div><span className="pt-analysis-eyebrow">{s.sport} · {instant(s.started_at, data.timezone_name)} · {data.timezone_name}</span>
      <h1>{s.name?.trim() || `${s.sport} edzés`}</h1><p>{s.external_provider} · {p ? "Tervhez kapcsolt teljesítés" : data.link_state === "linked_plan_unavailable" ? "A hivatkozott terv nem érhető el" : "Tervhez még nincs párosítva"}</p></div>
      <SpeedUnitControl value={speedUnit} onChange={setSpeedUnit} /></header>
    <div className="pt-analysis-metrics">{[
      ["Mért táv", number(s.distance_m === null ? null : s.distance_m / 1000, "km")], ["Forrás szerinti idő", duration(s.duration_sec)],
      ["Energia · forrásérték", number(s.calories, "kcal")], ["Átlagpulzus", number(s.avg_hr, "bpm")],
      ["Átlagsebesség", number(s.avg_speed === null ? null : speedValue(s.avg_speed, speedUnit), speedUnit)], ["Átlagteljesítmény", number(s.avg_power, "W")],
    ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
    <div className="pt-analysis-columns"><div className="pt-analysis-plots">
      <SessionSections source={data.sections} plan={p} speedUnit={speedUnit} />
      {data.samples.exercises.length > 1 && <label className="pt-analysis-exercise">Edzésrész<select value={exercise} onChange={e => setExercise(Number(e.target.value))}>
        {data.samples.exercises.map(e => <option value={e.index} key={e.index}>{e.index + 1}. rész{e.source_start ? ` · ${e.source_start}` : " · kezdete nincs megadva"}</option>)}
      </select></label>}
      {series.length ? <Charts key={`${s.id}-${exercise}-${data.plan_timeline?.content_hash ?? "no-plan"}-${data.samples.content_hash ?? data.retrieved_at}`} source={series} speedUnit={speedUnit} onSpeedUnitChange={setSpeedUnit} plan={p} timeline={data.plan_timeline}
        singleExercise={data.samples.exercises.length === 1} referenceKey={data.plan_timeline ? `paddletrainer:plan-reference:v2:${data.athlete_id}:${s.id}:${exercise}:${data.plan_timeline.content_hash}:${data.samples.content_hash ?? "legacy"}` : undefined}
        clockIssues={data.samples.exercises.find(e => e.index === exercise)?.clock_issues ?? []}
        zones={data.samples.exercises.find(e => e.index === exercise)?.heart_rate_zones ?? null}
        speedZones={data.samples.exercises.find(e => e.index === exercise)?.speed_zones ?? null}
        powerZones={data.samples.exercises.find(e => e.index === exercise)?.power_zones ?? null} /> : <section className="pt-analysis-card"><h2>Grafikonok</h2>
        <p className="pt-notice">Ehhez az edzésrészhez nincs megjeleníthető tárolt mintasor. Az összesítő számokból nem készül mért görbe.</p>
        {s.external_provider === "POLAR" && <p className="pt-notice">A felső szinkronizálás az edzésrészleteket is lekéri, először a legutóbbi napokról. A kapcsolat részleteiben látható, ha további átvételre van szükség.</p>}</section>}
      {(data.samples.unsupported.length > 0 || data.samples.issues.length > 0 || data.samples.series.some(s => s.issues.length > 0)) &&
        <details className="pt-analysis-card"><summary>Adatforrások és hiányok</summary>
          {data.samples.issues.length > 0 && <p className="pt-notice">A részletes minták elérhetősége eltérhet az összesítő adatokétól. Az alábbi forrásjelzések segítik az ellenőrzést.</p>}
          <ul>{data.samples.issues.map((issue, i) => <li key={`i${i}`}>{issue}</li>)}
            {data.samples.series.flatMap(s => s.issues.map((issue, i) => <li key={`${s.id}-${i}`}>{s.source_type} · {issue}</li>))}
            {data.samples.unsupported.map((u, i) => <li key={`u${i}`}>Még nem ábrázolt adatsor: {u.source_type} · {u.slot_count} forráshely · {u.source_path}</li>)}
          </ul><p className="pt-notice">A nyers szolgáltatói adatok változatlanul megmaradnak.</p>
        </details>}
    </div><aside className="pt-analysis-context">
      <FeedbackPanel key={data.athlete_id + s.id} owner={data.athlete_id} session={s.id} />
      <section className="pt-analysis-card"><h2>Terv és teljesítés</h2>
        {!p && <p className="pt-notice">{data.link_state === "unlinked" ? "Nincs igazolt tervkapcsolat. Ebből nem állapítható meg, hogy volt-e előzetes terv." : "A tárolt tervhivatkozás nem oldható fel ebben a fiókban."}</p>}
        {p && <p><Link href={`/workouts/${p.id}`}>{p.title} →</Link></p>}
        <div className="pt-analysis-table"><table><thead><tr><th>Mutató</th><th>Terv</th><th>Teljesített</th></tr></thead><tbody>
          <tr><th>Kezdés</th><td>{p ? p.planned_start_time ? instant(p.planned_start_time, data.timezone_name) : p.date + " · időpont nélkül" : "Nincs adat"}</td><td>{instant(s.started_at, data.timezone_name)}</td></tr>
          <tr><th>Időtartam</th><td>{duration(p?.duration_sec)}</td><td>{duration(s.duration_sec)}</td></tr>
          <tr><th>Táv</th><td>{number(p?.distance_m === null || p?.distance_m === undefined ? null : p.distance_m / 1000, "km")}</td><td>{number(s.distance_m === null ? null : s.distance_m / 1000, "km")}</td></tr>
        </tbody></table></div>
        <p className="pt-notice">Befejezés: {s.ended_at === null ? "Nincs adat" : instant(s.ended_at, data.timezone_name)}. Kezdés és befejezés között: {duration(actualElapsed)}. Ez eltérhet a forrás szerinti időtartamtól.</p>
        {p && <PlanBlocks plan={p} />}
      </section>
      <section className="pt-analysis-card"><h2>További mutatók</h2><dl className="pt-analysis-facts">{[
        ["Maximális pulzus", number(s.max_hr, "bpm")], ["Maximális sebesség", number(s.max_speed === null ? null : speedValue(s.max_speed, speedUnit), speedUnit)],
        ["Átlagos frekvencia", number(s.avg_cadence, "1/perc")], ["Maximális frekvencia", number(s.max_cadence, "1/perc")],
        ["Maximális teljesítmény", number(s.max_power, "W")], ["Kardioterhelés · forrásérték", number(s.cardio_load)],
        ["Észlelt terhelés · forrásérték", number(s.perceived_load)], ["RPE · forrásérték", number(s.rpe)],
      ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <p className="pt-notice">A hiányzó VO₂max- vagy izomterhelési adatot nem becsüljük meg ebből a nézetből.</p></section>
      <details className="pt-analysis-card"><summary>Edzés forrása</summary><dl className="pt-analysis-facts"><div><dt>Szolgáltató</dt><dd>{s.external_provider}</dd></div>
        <div><dt>Forrásazonosító</dt><dd>{s.external_id}</dd></div><div><dt>Kapcsolat eredete</dt><dd>{s.planned_workout_link_source ?? "Nincs megadva"}</dd></div>
        <div><dt>Kiolvasva</dt><dd>{instant(data.retrieved_at, data.timezone_name)}</dd></div></dl></details>
    </aside></div>
  </>;
}

function PlanBlocks({ plan }: { plan: Plan }) {
  return <details className="pt-plan-blocks"><summary>Tervezett blokkok · {plan.blocks.length}</summary>
    {plan.description && <p>{plan.description}</p>}
    <ol>{plan.blocks.map(b => <li key={b.id} style={{ marginLeft: b.parent_block_id ? 14 : 0 }}><strong>{b.name ?? b.block_type}</strong>
      <span>{b.block_type} · {duration(b.duration_sec)} · {number(b.distance_m, "m")}{b.repeat_count !== null ? ` · ${b.repeat_count} ismétlés` : ""}</span>
      {b.intensity_type && <span>{b.intensity_type} · {number(b.intensity_min)}–{number(b.intensity_max)}</span>}</li>)}</ol>
    <p className="pt-notice">A terv blokkjai előírások; nem jelentenek igazoltan teljesített szakaszokat.</p>
  </details>;
}

export default function SessionWorkspace({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<{ id: string; data?: Analysis; error?: string }>({ id: sessionId });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchAnalysis(sessionId, controller.signal).then(data => { if (!controller.signal.aborted) setState({ id: sessionId, data }); }).catch(error => {
      if (!controller.signal.aborted) setState({ id: sessionId, error: error instanceof Error ? error.message : "Az edzés nem tölthető be." });
    });
    return () => controller.abort();
  }, [sessionId, refresh]);
  useEffect(() => {
    function updated() { setState({ id: sessionId }); setRefresh(n => n + 1); }
    window.addEventListener(UPDATED_EVENT, updated);
    return () => window.removeEventListener(UPDATED_EVENT, updated);
  }, [sessionId]);
  const current = state.id === sessionId ? state : null;
  function reload() { setState({ id: sessionId }); setRefresh(n => n + 1); }
  return <main className="pt-session-analysis">
    <div className="pt-analysis-toolbar"><Link href="/">← Napirend</Link><button type="button" className="pt-button" onClick={reload}>Adatok újraolvasása</button></div>
    {current?.data ? <SessionDetails key={sessionId + "-" + refresh} data={current.data} /> :
      current?.error ? <div className="pt-message is-error" role="alert">{current.error} <button type="button" className="pt-button" onClick={reload}>Újrapróbálás</button></div> :
        <div className="pt-message" role="status">Edzés és mintasorok betöltése…</div>}
  </main>;
}
