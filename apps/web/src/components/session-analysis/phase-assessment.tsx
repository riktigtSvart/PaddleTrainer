"use client";
import { useMemo, useState } from "react";
import type { Plan, Series } from "@/lib/session-analysis/contracts";
import { clock, paceValue } from "@/lib/session-analysis/chart-data";
import { phaseResults } from "@/lib/session-analysis/phase-statistics";
import type { PhaseResult, PhaseZones, WindowMean } from "@/lib/session-analysis/phase-statistics";
import { axisNumber, speedValue } from "@/lib/session-analysis/presentation";
import type { SpeedUnit } from "@/lib/session-analysis/presentation";
import type { PhaseTransition } from "@/lib/session-analysis/plan-boundaries";
import type { useBoundaryView } from "./plan-boundaries";
import { PhaseCandidateControls } from "./phase-candidates";
import type { PhaseCandidate } from "@/lib/session-analysis/phase-candidates";

type View = ReturnType<typeof useBoundaryView>;
const ratio = (known: number, total: number) => total > 0 ? new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 1 }).format(100 * known / total) + "%" : "—";
function mean(value: WindowMean, unit: string, convert = (v: number) => v) {
  return <>{value.value === null ? "Adathiány" : `${axisNumber(convert(value.value))} ${unit}`}<small>{ratio(value.known_ms, value.observed_ms)} lefedettség</small></>;
}
function TransitionInput({ row, view }: { row: PhaseTransition; view: View }) {
  const [value, setValue] = useState(row.next_ms === null ? "" : clock(row.next_ms));
  return <form className="pt-transition-form" onSubmit={e => { e.preventDefault(); view.setTransition(row.id, value); }}>
    <label>{row.label} után · következő kezdés<input aria-label={`${row.label} utáni kezdés`} value={value} placeholder={clock(row.end_ms)} required onChange={e => setValue(e.target.value)} /></label>
    <span>Cél elérése: {clock(row.end_ms)} · {row.advance === "MANUAL" ? "kézi váltás" : "indítási mód ismeretlen"}{view.receipts[row.id] ? ` · ${view.receipts[row.id].start_ms === view.receipts[row.id].suggested_ms ? "Elfogadott becslés" : "Pontosított javaslat"}` : ""}</span>
    <button type="submit" className="pt-button">Kezdőpont alkalmazása</button>
    {row.next_ms !== null && <button type="button" className="pt-button" onClick={() => view.setTransition(row.id, null)}>Kezdőpont törlése</button>}
  </form>;
}
function GoalCell({ row, unit }: { row: PhaseResult; unit: SpeedUnit }) {
  const target = row.target, times = row.goal_time;
  if (!target) return <span>{row.kind === "phase" ? "Nincs számszerű cél" : "Tervcélon kívüli idő"}</span>;
  const range = target.low === null || target.high === null ? target.zoneLabel ?? "Ismeretlen célhatárok" :
    target.family === "speed" ? `${axisNumber(speedValue(target.low, unit))}–${axisNumber(speedValue(target.high, unit))} ${unit}` :
      `${axisNumber(target.low)}–${axisNumber(target.high)} ${target.family === "heart_rate" ? "bpm" : "W"}`;
  if (target.low === null || target.high === null) return <>{range}<small>Az edzéshez tartozó számszerű zónahatár hiányzik.</small></>;
  const label = `${target.zoneLabel ? target.zoneLabel + " · " : ""}${range}`;
  if (!times || !row.observed_ms) return <>{label}<small>{row.from_ms === null || row.to_ms === null ? "Időablak bizonytalan" : "Nem értékelhető"}</small></>;
  return <><span>{label}</span><div className="pt-goal-time-bar" role="img" aria-label={`Célban ${clock(times.inside_ms)}, alatta ${clock(times.below_ms)}, fölötte ${clock(times.above_ms)}, adathiány ${clock(times.missing_ms)}`}>
    {[["below", times.below_ms], ["inside", times.inside_ms], ["above", times.above_ms], ["missing", times.missing_ms]].map(([kind, value]) =>
      <span key={String(kind)} className={`is-${kind}`} style={{ width: `${100 * Number(value) / row.observed_ms!}%` }} />)}
  </div><small>Célban: {times.known_ms > 0 ? `${ratio(times.inside_ms, times.known_ms)} az ismert időből · ${clock(times.inside_ms)}` : "Nincs értékelhető minta"}</small>
    <small>Lefedettség: {ratio(times.known_ms, row.observed_ms)}{times.missing_ms > 0 ? ` · Adathiány: ${clock(times.missing_ms)}` : ""}</small>
    <details><summary>Idő a célhoz képest</summary><small>Alatta: {clock(times.below_ms)} · Célban: {clock(times.inside_ms)} · Fölötte: {clock(times.above_ms)} · Adathiány: {clock(times.missing_ms)}</small></details></>;
}

export function PhaseAssessment({ view, series, plan, zones, speedUnit, onSelect, onPreview, pickedMs, onCancelPreview }: {
  view: View; series: Series[]; plan: Plan | null; zones: PhaseZones; speedUnit: SpeedUnit; onSelect: (row: PhaseResult) => void;
  onPreview: (candidate: PhaseCandidate) => void; pickedMs: number | null; onCancelPreview: () => void;
}) {
  const rows = useMemo(() => phaseResults(view.part, view.alignment.gaps, series, plan, zones), [view.part, view.alignment.gaps, series, plan, zones]);
  if (!view.part) return null;
  return <section className="pt-phase-assessment" aria-label="Szakaszonkénti értékelés">
    <h3>Szakaszonkénti értékelés</h3>
    <PhaseCandidateControls view={view} onPreview={onPreview} pickedMs={pickedMs} onCancel={onCancelPreview} />
    {!view.manual && view.alignment.transitions.length > 0 && <details className="pt-transition-editor" open={view.alignment.transitions.some(t => t.next_ms === null)}>
      <summary>Kézi szakaszkezdések · {view.alignment.transitions.length}</summary>
      <p className="pt-notice">A következő szakasz kezdését a grafikon 0:00 pontjához képest add meg, perc:mp formában. Az előző cél elérése és e kezdés közé eső idő külön várakozás. Nulla várakozáshoz az előző végpontot írd be. Ezek saját referencia-időpontok, ezen a böngészőlapon őrizve.</p>
      <p className="pt-notice">Egy korábbi kezdés módosítása törli a tőle függő későbbi saját kezdéseket; ezeket újra ellenőrizheted.</p>
      {view.alignment.transitions.map(t => <TransitionInput key={t.id + ":" + t.next_ms} row={t} view={view} />)}
      {view.transitionError && <p role="alert" className="pt-notice">{view.transitionError}</p>}
    </details>}
    <p className="pt-notice">{view.manual || view.hasReferences ? "Kézi referencia-időpontokat is használó értékelés." : "A tervhez illesztett, számított időablakok értékelése."} A határok nem igazolt szolgáltatói fázisváltások. A részleges felvétel és a mintahiány külön jelöltek.</p>
    <div className="pt-analysis-table"><table><thead><tr><th>Szakasz</th><th>Időablak / időtartam</th><th>Táv</th><th>Átlagpulzus</th><th>Átlagsebesség / iram</th><th>Átlagteljesítmény</th><th>Cél teljesülése</th><th>Nézet</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id} className={`pt-phase-row is-${row.kind}`} data-phase-result={row.id}>
        <th>{row.label}{row.kind === "phase" && row.phase?.advance === "MANUAL" && <small>Kézi továbblépés</small>}</th>
        <td>{row.from_ms === null || row.to_ms === null ? "Bizonytalan időablak" : <>{clock(row.from_ms)}–{clock(row.to_ms)}<small>Mért ablak: {clock(row.observed_ms ?? 0)}{row.partial ? " · Részleges" : ""}</small></>}</td>
        <td>{row.observed_ms === null ? "Nem értékelhető" : row.distance_m === null ? "Adathiány" : row.distance_m < 1000 ? `${axisNumber(row.distance_m)} m` : `${axisNumber(row.distance_m / 1000)} km`}</td>
        <td>{row.observed_ms === null ? "Nem értékelhető" : mean(row.heart_rate, "bpm")}</td><td>{row.observed_ms === null ? "Nem értékelhető" : mean(row.speed, speedUnit, v => speedValue(v, speedUnit))}{row.speed.value !== null && row.speed.value > 0 && <small>{paceValue(Math.round(3600 / row.speed.value))} perc/km</small>}</td>
        <td>{row.observed_ms === null ? "Nem értékelhető" : mean(row.power, "W")}</td><td><GoalCell row={row} unit={speedUnit} /></td>
        <td><button type="button" className="pt-button" disabled={row.from_ms === null || row.to_ms === null || row.from_ms === row.to_ms} onClick={() => onSelect(row)}>Kijelölés</button></td>
      </tr>)}</tbody></table></div>
    <div className="pt-goal-time-legend"><span className="is-below">Alatta</span><span className="is-inside">Célban</span><span className="is-above">Fölötte</span><span className="is-missing">Adathiány</span></div>
    <details><summary>Az értékelés számítása</summary><p className="pt-notice">Az átlagok idővel súlyozott mintasor-átlagok. Két ismert szomszédos minta közötti időben a bal oldali értéket használjuk; hiányt nem hidalunk át, a sor végét nem hosszabbítjuk meg. A célban töltött százalék az ismert idejű mintákra vonatkozik. A táv a két pontos végpont közötti, folytonos távsor különbsége. A teljesítményhez együtt mért bal és jobb csatorna kell. A várakozás és a be nem sorolt idő a saját mért adataival megmarad, célzóna-értékelés nélkül.</p></details>
  </section>;
}
