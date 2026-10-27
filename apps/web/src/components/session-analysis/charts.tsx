"use client";
import { useMemo, useState } from "react";
import { metricInfo } from "@/lib/session-analysis/contracts";
import type { HeartRateZones, MetricZones, Plan, PlanTimeline, PowerZones, Series, SpeedZones } from "@/lib/session-analysis/contracts";
import { atCursor, clock, displayValue, extent, paceValue, segments, withPace } from "@/lib/session-analysis/chart-data";

import { axisNumber, graphTargets, speedValue, targetOnChart, timeTicks, valueAxis, zonesOnChart } from "@/lib/session-analysis/presentation";
import type { PulseTarget, SpeedUnit, TargetFamily } from "@/lib/session-analysis/presentation";

import { SpeedUnitControl } from "./speed-unit-control";
import { BoundaryLines } from "./boundary-lines";
import { PlanBoundaryControls, useBoundaryView } from "./plan-boundaries";
import type { Boundary } from "@/lib/session-analysis/plan-boundaries";

const zoneColors = ["var(--pt-muted)", "var(--pt-goal-aerobic)", "var(--pt-goal-technique)", "var(--pt-warning)", "var(--pt-goal-speed)"];

export function SampleChart({ series, from, to, cursor, setCursor, speedUnit = "km/h", zones = null, target = null, referenceOnly = false, boundaries = [], manualBoundaries = false, distanceBoundaries = false }: {
  series: Series; from: number; to: number; cursor: number; setCursor: (value: number) => void;
  speedUnit?: SpeedUnit; zones?: MetricZones | null; target?: PulseTarget | null; referenceOnly?: boolean; boundaries?: Boundary[]; manualBoundaries?: boolean; distanceBoundaries?: boolean;
}) {
  const { geometry, axis, pointCount } = useMemo(() => {
    const geometry = segments(series, from, to);
    let low = Infinity, high = -Infinity, pointCount = 0;
    for (const run of geometry.runs) for (const point of run) {
      const value = series.metric_key === "speed_kmh" ? speedValue(point.value, speedUnit) : point.value;
      low = Math.min(low, value); high = Math.max(high, value); pointCount++;
    }
    if (target?.low !== null && target?.high !== null && target) {
      low = Math.min(low, target.low); high = Math.max(high, target.high);
    }
    return { geometry, axis: valueAxis(low, high, series.metric_key === "pace_sec_km"), pointCount };
  }, [series, from, to, speedUnit, target]);
  const { low, high } = axis, info = metricInfo[series.metric_key];
  const x = (ms: number) => 76 + (ms - from) / Math.max(1, to - from) * 794;
  const scale = Math.max(1, Math.abs(low), Math.abs(high));
  const y = (v: number) => 180 - (v / scale - low / scale) / (high / scale - low / scale) * 154;
  const valueY = (v: number) => y(series.metric_key === "speed_kmh" ? speedValue(v, speedUnit) : v);
  const format = (v: number) => series.metric_key === "pace_sec_km" ? paceValue(v) : axisNumber(v);
  const point = atCursor(series, cursor), tooMany = geometry.runs.length > 1500;
  const unit = series.metric_key === "speed_kmh" ? speedUnit : info.unit;
  const title = `${referenceOnly ? "Csak tervcél" : info.label} · ${unit}`;
  const active = target?.low !== null && target?.high !== null ? target : null;
  const visibleZones = zones?.zones.filter(z => z.high > low && z.low < high) ?? [];
  return <figure className="pt-sample-chart" style={{ color: info.color }}>
    <figcaption><strong>{title}</strong><span>{point ? displayValue(series, point.value, speedUnit) : "Nincs minta"}</span></figcaption>
    {active && <p className="pt-chart-target-caption">Kiemelt tervcél: {active.label} · {active.zoneLabel ? active.zoneLabel + " · " : ""}{format(active.low!)}–{format(active.high!)} {unit}</p>}
    {series.interval_ms === null ? <p className="pt-notice">A mintavételi időköz nincs megadva. Az értékek a forrásadatok táblázatában elérhetők.</p> :
      tooMany ? <p className="pt-notice">Ebben a tartományban túl sok különálló mintaszakasz van. Szűkítsd az időtartományt a részletes rajzhoz.</p> :
      <svg viewBox="0 0 960 218" role="img" aria-label={title + ". A pontos minták alatta billentyűzettel is vizsgálhatók."}
        onPointerMove={event => {
          const box = event.currentTarget.getBoundingClientRect();
          if (box.width > 0) setCursor(from + Math.max(0, Math.min(1, ((event.clientX - box.left) / box.width * 960 - 76) / 794)) * (to - from));
        }}>
        <title>{title}</title>
        {visibleZones.map(z => <g key={z.index} className="pt-chart-zone" style={{ color: zoneColors[z.index - 1] }}>
          <rect x="76" width="794" y={y(Math.min(high, z.high))} height={Math.max(0, y(Math.max(low, z.low)) - y(Math.min(high, z.high)))} />
          <title>{`Z${z.index}: ${format(z.low)}–${format(z.high)} ${unit} · Polar`}</title>
        </g>)}
        {axis.ticks.map(value => <g key={value} className="pt-chart-grid pt-chart-value-grid">
          <line x1="76" x2="870" y1={y(value)} y2={y(value)} />
          <text x="66" y={y(value) + 4} textAnchor="end">{format(value)}</text>
        </g>)}
        {timeTicks(from, to).map(value => <g key={value} className="pt-chart-grid pt-chart-time-grid">
          <line x1={x(value)} x2={x(value)} y1="26" y2="180" />
          <text x={x(value)} y="204" textAnchor={value === from ? "start" : value === to ? "end" : "middle"}>{clock(value)}</text>
        </g>)}
        {visibleZones.flatMap(z => [z.low, z.high]).filter((v, i, a) => a.indexOf(v) === i && v >= low && v <= high).map(value =>
          <line key={value} className="pt-chart-zone-edge" x1="76" x2="870" y1={y(value)} y2={y(value)}><title>{`${format(value)} ${unit} · zónahatár`}</title></line>)}
        {active && <g className="pt-chart-target">
          <rect x="76" width="794" y={y(active.high!)} height={Math.max(0, y(active.low!) - y(active.high!))} />
          {[...new Set([active.low!, active.high!])].map(value => <g key={value}>
            <line x1="76" x2="870" y1={y(value)} y2={y(value)} />
            <text x="880" y={y(value) + 4}>{format(value)}{series.metric_key === "pace_sec_km" ? "" : " " + unit}</text>
          </g>)}
        </g>}
        <BoundaryLines boundaries={boundaries} from={from} to={to} manual={manualBoundaries} distanceBased={distanceBoundaries} />
        {geometry.runs.map((run, index) => run.length === 1 ?
          <circle key={index} cx={x(run[0].ms)} cy={valueY(run[0].value)} r="2.5" fill="currentColor" /> :
          <path key={index} d={run.map((p, i) => `${i ? "L" : "M"}${x(p.ms).toFixed(2)},${valueY(p.value).toFixed(2)}`).join(" ")} fill="none" stroke="currentColor" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />)}
        <line className="pt-chart-cursor" x1={x(cursor)} x2={x(cursor)} y1="20" y2="185" />
        {point && pointCount > 0 && point.ms >= from && point.ms <= to && <circle cx={x(point.ms)} cy={valueY(point.value)} r="3.5" fill="currentColor" />}
      </svg>}
    {!pointCount && series.interval_ms !== null && !referenceOnly && <p className="pt-notice">Nincs érvényes minta a kiválasztott tartományban.</p>}
    {referenceOnly && <p className="pt-notice">A sáv a tervezett cél. Ehhez nincs teljes, megjeleníthető mért mintasor.</p>}
    {!referenceOnly && <small>{series.valid_sample_count} érvényes / {series.slot_count} forrásminta · {series.missing_sample_count} hiányzó vagy érvénytelen
      {geometry.reduced ? " · Egyszerűsített rajz, a szélsőértékek és hiányok megtartásával." : ""}</small>}
  </figure>;
}

export function Charts({ source, speedUnit = "km/h", zones = null, speedZones = null, powerZones = null, plan = null, onSpeedUnitChange, timeline, referenceKey, singleExercise = true }: {
  source: Series[]; speedUnit?: SpeedUnit; zones?: HeartRateZones | null; speedZones?: SpeedZones | null; powerZones?: PowerZones | null; plan?: Plan | null; onSpeedUnitChange?: (unit: SpeedUnit) => void; timeline?: PlanTimeline; referenceKey?: string; singleExercise?: boolean;
}) {
  const series = useMemo(() => withPace(source), [source]), end = extent(series);
  const boundaryView = useBoundaryView(timeline, referenceKey, singleExercise, source);
  const boundaries = boundaryView.show ? boundaryView.boundaries : [];
  const rangeEnd = Math.max(end, boundaryView.boundaries.at(-1)?.ms ?? 0);
  const [enabled, setEnabled] = useState<string[]>(() => {
    const preferred = series.filter(s => ["heart_rate_bpm", "speed_kmh", "power_w"].includes(s.metric_key)).map(s => s.id);
    return preferred.length ? preferred : series.slice(0, 2).map(s => s.id);
  });
  const [from, setFrom] = useState(0), [to, setTo] = useState(end), [cursor, setCursor] = useState(0);
  const targets = useMemo(() => graphTargets(plan, { heart_rate: zones, speed: speedZones, power: powerZones }), [plan, zones, speedZones, powerZones]);
  const firstTarget = (family: TargetFamily) => targets.find(t => t.family === family && plan?.blocks.find(b => b.id === t.id)?.block_type === "WORK")?.id ?? targets.find(t => t.family === family)?.id ?? "";
  const [targetIds, setTargetIds] = useState(() => ({ heart_rate: firstTarget("heart_rate"), speed: firstTarget("speed"), power: firstTarget("power") }));
  const families = ["heart_rate", "speed", "power"] as const;
  const selected = (family: TargetFamily) => targets.find(t => t.family === family && t.id === targetIds[family]) ?? null;
  const definition = (family: TargetFamily) => family === "heart_rate" ? zones : family === "speed" ? speedZones : powerZones;
  const familyFor = (metric: Series["metric_key"]): TargetFamily | null => metric === "heart_rate_bpm" ? "heart_rate" : ["speed_kmh", "pace_sec_km"].includes(metric) ? "speed" : metric === "power_w" ? "power" : null;
  const [rangeError, setRangeError] = useState("");
  const shown = series.filter(s => enabled.includes(s.id));
  const clampedCursor = Math.max(from, Math.min(to, cursor));
  const step = Math.min(...series.filter(s => s.interval_ms !== null).map(s => s.interval_ms!), 1000);
  return <section className="pt-analysis-card" aria-label="Edzés grafikonjai">
    <div className="pt-analysis-heading"><h2>Grafikonok</h2><span>Mintasor ideje · {clock(end)}</span></div>
    {onSpeedUnitChange && <div className="pt-chart-units"><SpeedUnitControl value={speedUnit} onChange={onSpeedUnitChange} /></div>}
    <fieldset className="pt-series-toggle"><legend>Megjelenő adatsorok</legend>{series.map(s =>
      <label key={s.id} style={{ borderColor: enabled.includes(s.id) ? metricInfo[s.metric_key].color : undefined }}>
        <input type="checkbox" checked={enabled.includes(s.id)} onChange={() => setEnabled(current => current.includes(s.id) ? current.filter(id => id !== s.id) : [...current, s.id])} />
        {metricInfo[s.metric_key].label}{series.filter(r => r.metric_key === s.metric_key).length > 1 ? ` · ${s.source_type} / ${s.id}` : ""}
      </label>)}</fieldset>
    {families.filter(f => targets.some(t => t.family === f) || definition(f)).map(family => {
      const choices = targets.filter(t => t.family === family), current = selected(family), sourceZones = definition(family);
      const label = family === "heart_rate" ? "Pulzuscél a grafikonon" : family === "speed" ? "Sebesség/iram célja" : "Teljesítménycél a grafikonon";
      return <div className="pt-chart-references" key={family}>
        {choices.length > 0 && <label className="pt-pulse-target">{label}<select value={targetIds[family]} onChange={e => setTargetIds(ids => ({ ...ids, [family]: e.target.value }))}>
          <option value="">Csak zónák</option>{choices.map(t => <option value={t.id} key={t.id}>{t.label}{t.zoneLabel ? ` · ${t.zoneLabel}` : ""}</option>)}
        </select></label>}
        {sourceZones && <><ul className="pt-zone-legend" aria-label={family === "heart_rate" ? "Az edzéshez tárolt Polar-pulzuszónák" : `${label} · Polar-zónák`}>{sourceZones.zones.map(z => <li key={z.index} style={{ borderColor: zoneColors[z.index - 1] }}>
          <strong>Z{z.index}</strong> {axisNumber(family === "speed" ? speedValue(z.low, speedUnit) : z.low)}–{axisNumber(family === "speed" ? speedValue(z.high, speedUnit) : z.high)} {family === "speed" ? speedUnit : sourceZones.unit}</li>)}</ul>
          <details className="pt-zone-source"><summary>{family === "heart_rate" ? "Pulzuszónák forrása" : "Zónák forrása"}</summary><p>Az edzésrészhez a Polarban tárolt határok · {sourceZones.source_path}</p></details></>}
        {current && current.low === null && <p className="pt-notice">A kijelölt tervcél {current.zoneLabel}; a számszerű határokhoz az edzéshez tartozó zónadefiníció szükséges.</p>}
        {family === "speed" && current?.low === 0 && <p className="pt-notice">A cél nulla sebességet is tartalmaz; ehhez nincs véges iram-felsőhatár. A teljes sáv a sebességgrafikonon látszik.</p>}
      </div>;
    })}
    {targets.length > 0 && <p className="pt-notice">A kiemelés a kiválasztott tervezett blokk célját mutatja. A blokk időbeli helyét a mért görbén nem állapítja meg.</p>}
    <PlanBoundaryControls view={boundaryView} end={end} onZoom={(first, last) => { setRangeError(""); setFrom(first); setTo(last); setCursor(first); }} />
    <form className="pt-chart-range" onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget);
      const first = Number(values.get("from")) * 1000, last = Number(values.get("to")) * 1000;
      if (Number.isFinite(first + last) && first >= 0 && first <= last && last <= rangeEnd) { setRangeError(""); setFrom(first); setTo(last); setCursor(first); }
      else setRangeError("A kezdet ne legyen később a végnél; a tartomány maradjon a mintasor vagy a megadott terv időhatárain belül.");
    }}>
      <label>Kezdet · mp<input key={`from-${from}`} name="from" type="number" min="0" max={rangeEnd / 1000} step="0.001" defaultValue={from / 1000} required /></label>
      <label>Vég · mp<input key={`to-${to}`} name="to" type="number" min={from / 1000} max={rangeEnd / 1000} step="0.001" defaultValue={to / 1000} required /></label>
      <button type="submit" className="pt-button">Tartomány nagyítása</button>
      <button type="button" className="pt-button" onClick={() => { setRangeError(""); setFrom(0); setTo(end); setCursor(0); }}>Teljes mintasor</button>
    </form>
    {rangeError && <p role="alert" className="pt-notice">{rangeError}</p>}
    <p className="pt-notice">Az időtengely az adott edzésrész mintáinak sorszámából és mintavételi időközéből készül. A szünetekkel és a teljes edzés falióraidejével nem feltétlenül egyezik meg. A hiányokat nem kötjük össze.</p>
    {!shown.length && <p className="pt-notice">Válassz legalább egy adatsort.</p>}
    {shown.map(s => {
      const family = familyFor(s.metric_key);
      return <SampleChart key={s.id} series={s} from={from} to={to} cursor={clampedCursor} setCursor={setCursor} speedUnit={speedUnit}
        zones={family ? zonesOnChart(definition(family), s.metric_key, speedUnit) : null}
        target={family ? targetOnChart(selected(family), s.metric_key, speedUnit) : null} boundaries={boundaries} manualBoundaries={boundaryView.manual !== null} distanceBoundaries={!boundaryView.manual && boundaryView.alignment.distanceUsed} />;
    })}
    {families.map(family => {
      const metric = family === "heart_rate" ? "heart_rate_bpm" : family === "speed" ? "speed_kmh" : "power_w";
      const target = targetOnChart(selected(family), metric, speedUnit);
      if (!target || series.some(s => familyFor(s.metric_key) === family)) return null;
      const reference: Series = { id: "reference-" + family, exercise_index: 0, source_path: "plan", source_type: "PLAN_REFERENCE", metric_key: metric,
        unit: metricInfo[metric].unit, interval_ms: 1000, slot_count: 0, valid_sample_count: 0, missing_sample_count: 0, values: [], issues: [] };
      return <SampleChart key={family} series={reference} from={from} to={to} cursor={clampedCursor} setCursor={setCursor} speedUnit={speedUnit}
        zones={zonesOnChart(definition(family), metric, speedUnit)} target={target} referenceOnly boundaries={boundaries} manualBoundaries={boundaryView.manual !== null} distanceBoundaries={!boundaryView.manual && boundaryView.alignment.distanceUsed} />;
    })}
    <label className="pt-chart-slider">Minták vizsgálata · {clock(clampedCursor)}
      <input aria-label="Vizsgált mintavételi idő" type="range" min={from} max={to} step={step} value={clampedCursor} disabled={from === to} onChange={e => setCursor(Number(e.target.value))} />
    </label>
    <div className="pt-analysis-table"><table><caption>Legközelebbi forrásminták a kijelölt időhöz · nincs interpoláció</caption>
      <thead><tr><th>Adatsor</th><th>Minta ideje</th><th>Érték</th></tr></thead><tbody>{shown.map(s => {
        const point = atCursor(s, clampedCursor); return <tr key={s.id}><td>{metricInfo[s.metric_key].label}</td><td>{point ? clock(point.ms) : "Nincs minta"}</td><td>{displayValue(s, point?.value ?? null, speedUnit)}</td></tr>;
      })}</tbody></table></div>
    <details className="pt-sample-provenance"><summary>Források és minták táblázata</summary>{series.map(s => <SourceSeries key={s.id} series={s} cursor={clampedCursor} speedUnit={speedUnit} />)}</details>
  </section>;
}

function SourceSeries({ series: s, cursor, speedUnit }: { series: Series; cursor: number; speedUnit: SpeedUnit }) {
  const [open, setOpen] = useState(false);
  return <details open={open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>{metricInfo[s.metric_key].label} · {s.source_type} · {s.source_path}</summary>
    {open && <><p className="pt-notice">{s.metric_key === "power_w" ? "Az egyidejű, azonos felbontású bal és jobb teljesítményminták összege; hiánynál nincs összeg." : s.derived ? "Az iram a sebességből számított érték. Nulla sebességhez nincs véges iram." : "Tárolt szolgáltatói minták."} Mintavétel: {s.interval_ms === null ? "ismeretlen" : `${s.interval_ms} ms`}. A táblázat a kiválasztott idő körüli legfeljebb 101 forráshelyet mutatja.
      {s.metric_key === "speed_kmh" && speedUnit !== "km/h" ? ` A sebesség ${speedUnit} egységre átszámítva jelenik meg; a tárolt forrásegység km/h.` : ""}</p><SampleTable series={s} cursor={cursor} speedUnit={speedUnit} /></>}
  </details>;
}

function SampleTable({ series: s, cursor, speedUnit }: { series: Series; cursor: number; speedUnit: SpeedUnit }) {
  const [page, setPage] = useState(0);
  const center = Math.min(Math.max(0, s.values.length - 1), s.interval_ms === null ? page * 101 : Math.round(cursor / s.interval_ms));
  const first = Math.max(0, center - (s.interval_ms === null ? 0 : 50)), last = Math.min(s.values.length, first + 101);
  return <><div className="pt-analysis-table"><table><thead><tr><th>Sorszám · 0-tól</th><th>Mintasor ideje</th><th>Érték</th></tr></thead>
    <tbody>{s.values.slice(first, last).map((value, i) => <tr key={first + i}><td>{first + i}</td><td>{s.interval_ms === null ? "Ismeretlen" : clock((first + i) * s.interval_ms)}</td><td>{displayValue(s, value, speedUnit)}</td></tr>)}</tbody></table></div>
    {s.interval_ms === null && <div className="pt-quick-actions"><button type="button" className="pt-button" disabled={!page} onClick={() => setPage(p => p - 1)}>Előző 101</button>
      <button type="button" className="pt-button" disabled={last >= s.values.length} onClick={() => setPage(p => p + 1)}>Következő 101</button></div>}</>;
}
