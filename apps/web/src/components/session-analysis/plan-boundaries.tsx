"use client";
import { useEffect, useMemo, useState } from "react";
import type { PlanTimeline, Series } from "@/lib/session-analysis/contracts";
import { clock } from "@/lib/session-analysis/chart-data";
import { alignDistancePhases, manualPart, planBoundaries, readClock, readReference } from "@/lib/session-analysis/plan-boundaries";
import type { ManualReference } from "@/lib/session-analysis/plan-boundaries";
import { candidateReceipt, readSavedTransitions, reviseTransition, transitionCandidates } from "@/lib/session-analysis/phase-candidates";
import type { CandidateReceipt } from "@/lib/session-analysis/phase-candidates";

export function useBoundaryView(timeline: PlanTimeline | undefined, key: string | undefined, singleExercise: boolean, samples: Series[], clockIssues: string[]) {
  const parts = timeline?.parts.filter(p => p.phases.length > 0) ?? [];
  const [partIndex, setPartIndex] = useState(() => singleExercise && parts.length === 1 ? String(parts[0].index) : "");
  const [manual, setManual] = useState<ManualReference | null>(null), [show, setShow] = useState(true);
  const [draft, setDraft] = useState({ first: "", work: "", recovery: "", count: "" });
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active || !key) return;
      try {
        const saved = sessionStorage.getItem(key);
        if (!saved) return;
        const value = readReference(JSON.parse(saved));
        setManual(value); setDraft({ first: clock(value.first_ms), work: clock(value.work_ms), recovery: clock(value.recovery_ms), count: String(value.count) });
      } catch { setNotice("A böngészőlapon őrzött kézi jelölés nem tölthető be. Új jelölés továbbra is megadható."); }
    });
    return () => { active = false; };
  }, [key]);
  const stored = parts.find(p => String(p.index) === partIndex) ?? null;
  const transitionKey = key && stored ? `${key}:transitions:${stored.index}` : undefined;
  const [references, setReferences] = useState<{ key: string | undefined; starts: Record<string, number>; receipts: Record<string, CandidateReceipt> }>({ key: undefined, starts: {}, receipts: {} });
  const [transitionError, setTransitionError] = useState("");
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active || !transitionKey || !stored) return;
      try {
        const saved = sessionStorage.getItem(transitionKey);
        setReferences({ key: transitionKey, ...(saved ? readSavedTransitions(JSON.parse(saved), stored) : { starts: {}, receipts: {} }) });
      } catch { setNotice("A kézi szakaszkezdések nem tölthetők be. A bizonytalan váltások továbbra is külön jelöltek."); }
    });
    return () => { active = false; };
  }, [transitionKey, stored]);
  const starts = useMemo(() => references.key === transitionKey ? references.starts : {}, [references, transitionKey]);
  const receipts = useMemo(() => references.key === transitionKey ? references.receipts : {}, [references, transitionKey]);
  const prescribed = useMemo(() => manual ? manualPart(manual) : stored, [manual, stored]);
  const alignment = useMemo(() => alignDistancePhases(prescribed, samples, manual ? {} : starts, clockIssues), [prescribed, samples, starts, manual, clockIssues]);
  const part = alignment.part;
  const candidates = useMemo(() => manual ? { options: [], reasons: [], truncated: false } : transitionCandidates(stored, samples, alignment, clockIssues), [manual, stored, samples, alignment, clockIssues]);
  const boundaries = useMemo(() => planBoundaries(part), [part]);
  function apply() {
    try {
      const value = readReference({ version: "manual-plan-reference-v0.1", first_ms: readClock(draft.first), work_ms: readClock(draft.work), recovery_ms: readClock(draft.recovery), count: Number(draft.count) });
      setManual(value); setShow(true); setError(""); setNotice("");
      if (key) {
        try { sessionStorage.setItem(key, JSON.stringify(value)); }
        catch { setNotice("A jelölés ebben a nézetben használható, de a böngészőlapon nem őrizhető meg."); }
      }
    } catch (e) { setError(e instanceof Error ? e.message : "A tervjelölés nem értelmezhető."); }
  }
  function clear() {
    setManual(null); setError(""); setNotice("");
    if (key) try { sessionStorage.removeItem(key); } catch { setNotice("A régi böngészőlapi jelölés nem törölhető. Ebben a nézetben a tárolt terv látszik."); }
  }
  function saveTransition(id: string, ms: number | null, receipt?: CandidateReceipt) {
    try {
      if (!stored) throw new Error("Előbb válassz tervezett részt.");
      const end = Math.max(0, ...samples.filter(s => s.interval_ms !== null && s.values.length).map(s => (s.values.length - 1) * s.interval_ms!));
      if (ms !== null && ms > end) throw new Error("A kezdés maradjon a mintasor végén belül.");
      const value = reviseTransition(stored, alignment, starts, receipts, id, ms, receipt);
      setReferences({ key: transitionKey, starts: value.starts, receipts: value.motion_receipts ?? {} }); setTransitionError("");
      if (transitionKey) try { sessionStorage.setItem(transitionKey, JSON.stringify(value)); }
      catch { setNotice("A kezdőpont most használható, de a böngészőlapon nem őrizhető meg."); }
    } catch (e) { setTransitionError(e instanceof Error ? e.message : "A kezdés nem értelmezhető."); }
  }
  function setTransition(id: string, text: string | null) {
    try { saveTransition(id, text === null ? null : readClock(text)); }
    catch (e) { setTransitionError(e instanceof Error ? e.message : "A kezdés nem értelmezhető."); }
  }
  function acceptCandidate(id: string, text?: string) {
    const option = candidates.options.find(c => c.id === id);
    if (!option) { setTransitionError("A javaslat már nem aktuális. Ellenőrizd a most megjelenő kezdéseket."); return; }
    try {
      const selected = text === undefined ? option.start_ms : readClock(text);
      saveTransition(option.transition_id, selected, candidateReceipt(option, selected));
    } catch (e) { setTransitionError(e instanceof Error ? e.message : "A kezdés nem értelmezhető."); }
  }
  return { parts, part, partIndex, setPartIndex, manual, draft, setDraft, error, notice, show, setShow, apply, clear, boundaries, alignment,
    transitionError, setTransition, candidates, acceptCandidate, receipts, hasReferences: Object.keys(starts).length > 0,
    sourceLabel: manual ? "Kézzel megadott tervjelölés" : alignment.distanceUsed ? "Számított tervhatárok · mért távsor alapján" : timeline?.source === "stored_polar_target" ? "Tervjelölés · megőrzött Polar-forrás" : "Tervjelölés · tárolt blokkok" };
}

export function PlanBoundaryControls({ view, end, onZoom }: { view: ReturnType<typeof useBoundaryView>; end: number; onZoom: (from: number, to: number, id?: string) => void }) {
  const format = (ms: number | null) => ms === null ? "Ismeretlen" : clock(ms);
  const last = view.boundaries.at(-1)?.ms ?? 0;
  const initialDistance = view.alignment.source?.values[0];
  const explanations: Record<string, string> = {
    DISTANCE_INITIAL_OFFSET: `A távsor 0:00 pontja ${initialDistance === null || initialDistance === undefined ? "ismert, nem nulla értékről" : new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 3 }).format(initialDistance) + " m-ről"} indul. A távillesztés ehhez a mért kezdőértékhez viszonyít; a forrásértékeket változatlanul használjuk. Ez továbbra is számított tervillesztés.`,
    DISTANCE_SOURCE_MISSING: "A távval megadott szakaszhoz nincs tárolt távmintasor.",
    DISTANCE_SOURCE_AMBIGUOUS: "A távmintasor nem választható ki egyértelműen ehhez az edzésrészhez.",
    DISTANCE_CLOCK_INVALID: "A távmintasor időköze hiányzik, vagy az össztáv visszafelé ugrik.",
    DISTANCE_START_UNKNOWN: "A távszakasz kezdőpontjához nincs ismert, pontosan illeszkedő távminta.",
    DISTANCE_GOAL_NOT_REACHED: "A tárolt mintasorban még nem érhető el a megadott szakasztáv.",
    DISTANCE_CROSSING_GAP: "A távhatár elérésénél mintahiány van; a határ időpontja bizonytalan.",
    MANUAL_ADVANCE_TIME_UNKNOWN: "Kézi váltás következik. A további határokhoz a következő szakasz kezdőpontja szükséges.",
    ADVANCE_MODE_UNKNOWN: "A következő szakasz indítási módja nem ismert. Kezdőpont megadásáig a további határok bizonytalanok.",
    RECORDING_CLOCK_UNRESOLVED: "Rögzítési szünet érinti az időalapot. A szakaszok automatikus időzítése és értékelése az időalap tisztázásáig nem elérhető; a mért görbék megmaradnak.",
    PHASE_GOAL_AFTER_RECORDING_END: "A szakasz előírt vége a mintasor után van. A későbbi szakaszok kezdetét nem igazolja a felvétel.",
  };
  return <div className="pt-boundary-controls" aria-label="Tervezett szakaszhatárok">
    <div className="pt-boundary-heading"><h3>Szakaszhatárok</h3><label><input type="checkbox" checked={view.show} onChange={e => view.setShow(e.target.checked)} /> Tervhatárok a grafikonokon</label></div>
    {!view.manual && view.parts.length > 0 && <label className="pt-pulse-target">Tervezett rész<select value={view.partIndex} onChange={e => view.setPartIndex(e.target.value)}>
      <option value="">Válassz a mintasorhoz egy tervezett részt</option>{view.parts.map(p => <option key={p.index} value={p.index}>{p.index + 1}. tervezett rész</option>)}
    </select></label>}
    {view.part ? <><p className="pt-notice"><strong>{view.sourceLabel}</strong> · A függőleges vonalak a terv szerinti időpontokat mutatják; nem igazolják a tényleges szakaszváltást. A kezdőpont az edzésrész mintasorának 0:00 pontja.</p>
      {!view.manual && view.alignment.distanceUsed && <p className="pt-notice">A távhatárt az első, célértéket elérő távminta jelöli. Innen a megadott időtartamok következnek. Felbontás: {view.alignment.source?.interval_ms} ms. Az ismétlési csoportok minden alárendelt része sorban ismétlődik.</p>}
      {!view.manual && view.alignment.reasons.filter(r => explanations[r]).map(reason => <p key={reason} className="pt-notice">{explanations[reason]}</p>)}
      {view.part.issues.length > 0 && <p className="pt-notice">Van ismeretlen időtartam vagy szakaszkezdés. Az érintett határok nincsenek pontos időponthoz rendelve.</p>}
      {last > end && <p className="pt-notice">A tervjelölés túlnyúlik a mintasoron. <button type="button" className="pt-button" onClick={() => onZoom(0, last)}>Mutasd a terv végéig</button></p>}
      <details className="pt-boundary-times" open={!view.manual && view.alignment.distanceUsed ? true : undefined}><summary>Tervezett határidőpontok · {view.part.phases.length} szakasz</summary>
        <div className="pt-analysis-table"><table><thead><tr><th>Szakasz</th><th>Előírás</th><th>Kezdet</th><th>Vég</th><th>Időtartam</th><th>Nagyítás</th></tr></thead><tbody>
          {view.part.phases.map(p => <tr key={p.id}><th>{p.label}</th><td>{p.distance_m !== undefined ? new Intl.NumberFormat("hu-HU").format(p.distance_m) + " m" : format(p.duration_ms)}</td><td>{format(p.from_ms)}</td><td>{format(p.to_ms)}</td><td>{p.duration_ms !== null ? format(p.duration_ms) : p.from_ms !== null && p.to_ms !== null ? format(p.to_ms - p.from_ms) + " · távmintákból" : "Ismeretlen"}</td>
            <td><button type="button" className="pt-button" disabled={p.from_ms === null || p.to_ms === null || p.from_ms === p.to_ms} onClick={() => { if (p.from_ms !== null && p.to_ms !== null) onZoom(p.from_ms, p.to_ms, p.id); }}>Mutasd</button></td></tr>)}
        </tbody></table></div>
      </details></> : <p className="pt-notice">Nincs kiválasztott, időben felbontható terv. A cím, például „4×12′”, önmagában nem adja meg a bemelegítés és a pihenők hosszát.</p>}
    <details className="pt-boundary-editor"><summary>Kézi tervjelölés megadása</summary>
      <p className="pt-notice">Ha a tárolt terv szakaszai hiányoznak, itt megadhatod az ismert időket. Ez a jelölés a grafikonhoz tartozik; nem módosítja az edzéstervet vagy a mért adatokat. A kezdőpont és a pihenő külön szükséges; nulla értéket is írj be.</p>
      <button type="button" className="pt-button" onClick={() => view.setDraft(d => ({ ...d, count: "4", work: "12:00" }))}>4 × 12 perc kitöltése</button>
      <form onSubmit={event => { event.preventDefault(); view.apply(); }}>
        <label>Első munka kezdete · perc:mp<input value={view.draft.first} placeholder="20:00" required onChange={e => view.setDraft(d => ({ ...d, first: e.target.value }))} /></label>
        <label>Munka hossza · perc:mp<input value={view.draft.work} placeholder="12:00" required onChange={e => view.setDraft(d => ({ ...d, work: e.target.value }))} /></label>
        <label>Köztes pihenő · perc:mp<input value={view.draft.recovery} placeholder="2:00 vagy 0:00" required onChange={e => view.setDraft(d => ({ ...d, recovery: e.target.value }))} /></label>
        <label>Ismétlések száma<input type="number" min="1" max="99" step="1" value={view.draft.count} required onChange={e => view.setDraft(d => ({ ...d, count: e.target.value }))} /></label>
        <button type="submit" className="pt-button">Tervjelölés megjelenítése</button>
      </form>
      {view.error && <p className="pt-notice" role="alert">{view.error}</p>}
      {view.manual && <button type="button" className="pt-button" onClick={view.clear}>Kézi jelölés törlése</button>}
      <p className="pt-notice">A jelölést ezen a böngészőlapon őrizzük meg, az adott sportolóhoz, edzésrészhez és tervverzióhoz kötve.</p>
    </details>
    {view.notice && <p className="pt-notice" role="status">{view.notice}</p>}
  </div>;
}
