"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { formatDay, goalLabels } from "@/lib/calendar/contracts";
import { blankManualDraft, loadManualContext, ManualHTTPError, manualPendingKey, manualSports, manualPhaseSeconds, phaseLabels, saveManualWorkout, validateManualDraft, weeklyDates } from "@/lib/calendar/manual-workouts";
import type { ManualContext, ManualDraft, ManualExercise, ManualPhase, ManualReceipt, ManualRequest, ManualSave } from "@/lib/calendar/manual-workouts";
import { alignManualDuration, manualScheduleWarnings } from "@/lib/calendar/manual-duration";
import type { ScheduleContext } from "@/lib/calendar/constraints";
import DurationField from '@/components/ui/duration-field';
import { durationHMS } from '@/lib/duration';

const number = (value: string) => value === "" ? null : Number(value);
const message = (error: unknown) => error instanceof Error ? error.message : "A művelet nem sikerült.";
const newExercise = (): ManualExercise => ({ exercise_id: null, name: "", sets: 3, reps: 8, hold_seconds: null, load_mode: "kg", weight_kg: null, load_basis: "total", rest_seconds: 120, reserve_reps: 2, notes: "" });

function PhaseFields({ phase: p, index, change, remove }: { phase: ManualPhase; index: number; change: (p: ManualPhase) => void; remove: () => void }) {
  return <fieldset className="pt-manual-item"><legend>{index + 1}. edzésszakasz</legend><div className="pt-manual-grid">
    <label>Szakasz típusa<select value={p.block_type} onChange={e => change({ ...p, block_type: e.target.value })}>{Object.entries(phaseLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>Szakasz neve<input maxLength={120} value={p.name} onChange={e => change({ ...p, name: e.target.value })} /></label>
    <DurationField label="Idő egy ismétlésre" value={p.duration_sec} optional onChange={v => change({ ...p, duration_sec: v })} />
    <label>Távolság egy ismétlésre (m)<input type="number" min={0} step="any" value={p.distance_m ?? ""} onChange={e => change({ ...p, distance_m: number(e.target.value) })} /></label>
    <label>Ismétlések száma<input type="number" min={1} max={100} value={p.repeat_count || ""} onChange={e => change({ ...p, repeat_count: Number(e.target.value) })} /></label>
    <DurationField label="Pihenő az ismétlések között" value={p.recovery_duration_sec ?? null} optional onChange={v => change({ ...p, recovery_duration_sec: v })} />
    {p.recovery_duration_sec != null && Number.isFinite(p.recovery_duration_sec) && p.repeat_count > 0 && <p className="pt-manual-wide">{p.repeat_count} × {p.duration_sec === null ? 'távolságalapú munka' : durationHMS(p.duration_sec)} / {durationHMS(p.recovery_duration_sec)} · {Math.max(0, p.repeat_count - 1)} pihenő az ismétlések között. {p.duration_sec !== null && <>Összesen: {durationHMS(manualPhaseSeconds(p))}.</>} Az utolsó ismétlés után nincs külön pihenő.</p>}
    <label>Végrehajtás, intenzitás<textarea rows={2} maxLength={2000} value={p.notes} onChange={e => change({ ...p, notes: e.target.value })} /></label>
  </div><details><summary>Intenzitás számszerű megadása (opcionális)</summary><div className="pt-manual-grid"><label>Intenzitás típusa, mértékegysége<input maxLength={32} value={p.intensity_type ?? ""} placeholder="pl. pulzus bpm vagy RPE" onChange={e => change({ ...p, intensity_type: e.target.value || null })} /></label><label>Alsó határ<input type="number" min={0} step="any" value={p.intensity_min ?? ""} onChange={e => change({ ...p, intensity_min: number(e.target.value) })} /></label><label>Felső határ<input type="number" min={0} step="any" value={p.intensity_max ?? ""} onChange={e => change({ ...p, intensity_max: number(e.target.value) })} /></label></div></details><button type="button" className="pt-button" onClick={remove}>Szakasz törlése</button></fieldset>;
}

function ExerciseFields({ exercise: x, index, catalogue, change, remove }: { exercise: ManualExercise; index: number; catalogue: ManualContext["exercises"]; change: (x: ManualExercise) => void; remove: () => void }) {
  return <fieldset className="pt-manual-item"><legend>{index + 1}. gyakorlat</legend><div className="pt-manual-grid">
    <label>Gyakorlat a katalógusból<select value={x.exercise_id ?? ""} onChange={e => { const v = catalogue.find(c => c.id === e.target.value); change({ ...x, exercise_id: v?.id ?? null, name: v?.label ?? x.name }); }}><option value="">Saját gyakorlatnév</option>{catalogue.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
    <label>Gyakorlat neve<input maxLength={160} value={x.name} readOnly={x.exercise_id !== null} onChange={e => change({ ...x, name: e.target.value })} /></label>
    <label>Munkasorozatok<input type="number" min={1} max={20} value={x.sets || ""} onChange={e => change({ ...x, sets: Number(e.target.value) })} /></label>
    <label>Végrehajtás<select value={x.hold_seconds !== null ? "hold" : "reps"} onChange={e => change({ ...x, reps: e.target.value === "reps" ? 8 : null, hold_seconds: e.target.value === "hold" ? 30 : null })}><option value="reps">Ismétlések</option><option value="hold">Időtartás</option></select></label>
    {x.hold_seconds !== null ? <DurationField label="Tartás sorozatonként" value={x.hold_seconds} onChange={v => change({ ...x, hold_seconds: v ?? NaN })} /> : <label>Ismétlés sorozatonként<input type="number" min={1} max={1000} value={x.reps ?? ""} onChange={e => change({ ...x, reps: number(e.target.value) })} /></label>}
    <label>Terhelés módja<select value={x.load_mode} onChange={e => { const mode = e.target.value as ManualExercise["load_mode"]; change({ ...x, load_mode: mode, weight_kg: mode === "kg" ? x.weight_kg : null, load_basis: mode === "kg" ? x.load_basis : "total" }); }}><option value="kg">Súly kilogrammban</option><option value="bodyweight">Saját testsúly</option><option value="none">Külön terhelés nélkül</option></select></label>
    {x.load_mode === "kg" && <><label>Súly (kg)<input inputMode="decimal" value={x.weight_kg ?? ""} onChange={e => change({ ...x, weight_kg: e.target.value || null })} /></label><label>A súly értelmezése<select value={x.load_basis} onChange={e => change({ ...x, load_basis: e.target.value as "total" | "per_hand" })}><option value="total">Összesen</option><option value="per_hand">Kézenként</option></select></label></>}
    <DurationField label="Pihenő sorozatok között" value={x.rest_seconds} onChange={v => change({ ...x, rest_seconds: v ?? NaN })} />
    <label>Előírt ismétléstartalék (opcionális)<input type="number" min={0} max={10} value={x.reserve_reps ?? ""} onChange={e => change({ ...x, reserve_reps: number(e.target.value) })} /></label>
    <label className="pt-manual-wide">Megjegyzés<textarea rows={2} maxLength={2000} value={x.notes} onChange={e => change({ ...x, notes: e.target.value })} /></label>
  </div><button type="button" className="pt-button" onClick={remove}>Gyakorlat törlése</button></fieldset>;
}

export default function ManualWorkoutEditor({ owner, request, onClose, onSaved, schedule }: { owner: string; request: ManualRequest; onClose: () => void; onSaved: (r: ManualReceipt) => void; schedule?: ScheduleContext | null }) {
  const dialog = useRef<HTMLDialogElement>(null), errorPanel = useRef<HTMLDivElement>(null), sendingRef = useRef(false), alive = useRef(true);
  const [context, setContext] = useState<ManualContext | null>(null), [draft, setDraft] = useState<ManualDraft | null>(null);
  const [error, setError] = useState(""), [issues, setIssues] = useState<string[]>([]), [sending, setSending] = useState(false), [reload, setReload] = useState(0);
  const [pending, setPending] = useState<string | null>(null), [rejected, setRejected] = useState(false), [storageBlocked, setStorageBlocked] = useState(false);
  const [occurrences, setOccurrences] = useState(1), [cancelMode, setCancelMode] = useState(false);
  const [durationNotice, setDurationNotice] = useState("");
  const scheduleWarnings = useMemo(() => {
    if (!draft || !context || cancelMode) return [];
    let dates = [draft.date];
    if (request.mode !== 'edit') { try { dates = [...dates, ...weeklyDates(draft.date, occurrences)]; } catch { /* The ordinary form validator explains invalid recurrence. */ } }
    return manualScheduleWarnings(draft, schedule, owner, context.timezone_name, dates);
  }, [draft, context, cancelMode, request.mode, occurrences, schedule, owner]);
  function changeTimedDraft(value: ManualDraft) {
    const result = alignManualDuration(value);
    setDraft(result.draft);
    setDurationNotice(result.adjusted ? `A teljes edzésidőt a szakaszok alapján automatikusan ${durationHMS(result.draft.duration_sec)} értékre állítottuk, az ismétlésekkel és a köztük lévő pihenőkkel együtt.` : result.issue ?? "");
    setError(""); setIssues([]);
  }
  useEffect(() => {
    alive.current = true;
    const node = dialog.current, previous = document.activeElement as HTMLElement | null;
    node?.showModal();
    return () => { alive.current = false; node?.close(); previous?.focus(); };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    loadManualContext(owner, request.workout_id, abort.signal).then(c => {
      if (abort.signal.aborted) return;
      const source = c.workout;
      const value = source ? structuredClone(source.draft) : blankManualDraft(request.date);
      if (request.mode === "copy") { value.date = request.date; value.mesocycle_id = null; value.start_fold = null; }
      if (request.mode === "create" && request.start_time) value.start_time = request.start_time;
      setContext(c); setDraft(value);
    }).catch(e => { if (!abort.signal.aborted) setError(message(e)); });
    return () => abort.abort();
  }, [owner, request, reload]);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      try {
        const saved = sessionStorage.getItem(manualPendingKey(owner));
        if (saved) { const b = JSON.parse(saved) as ManualSave; if (typeof b.request_id !== "string" || !["create", "update", "cancel"].includes(b.operation)) throw new Error(); setPending(saved); }
      } catch { setStorageBlocked(true); setError("A böngésző mentési tárhelye nem olvasható. A biztonságos újrapróbáláshoz engedélyezd a munkamenet-tárhelyet."); }
    });
    return () => { active = false; };
  }, [owner]);
  useEffect(() => { if (error || issues.length) errorPanel.current?.focus(); }, [error, issues]);

  async function transmit(body: string) {
    if (sendingRef.current) return;
    sendingRef.current = true; setSending(true); setError(""); setIssues([]); setRejected(false);
    try {
      const result = await saveManualWorkout(owner, body);
      sessionStorage.removeItem(manualPendingKey(owner));
      // Invalidate already loaded calendar ranges after the durable commit.
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
      if (alive.current) { setPending(null); onSaved(result); }
    } catch (e) {
      if (alive.current) {
        setError(message(e));
        setIssues(e instanceof ManualHTTPError ? e.issues : []);
        setRejected(e instanceof ManualHTTPError && e.status >= 400 && e.status < 500);
      }
    } finally {
      sendingRef.current = false;
      if (alive.current) setSending(false);
    }
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (sendingRef.current || !context || !draft || pending || storageBlocked) return;
    const aligned = cancelMode ? { draft, adjusted: false, issue: null } : alignManualDuration(draft);
    if (aligned.adjusted) { setDraft(aligned.draft); setDurationNotice(`A teljes edzésidőt a szakaszok alapján automatikusan ${durationHMS(aligned.draft.duration_sec)} értékre állítottuk, az ismétlésekkel és a köztük lévő pihenőkkel együtt.`); }
    const value = { ...aligned.draft, title: draft.title.trim(), exercises: draft.exercises.map(x => ({ ...x, name: x.name.trim(), weight_kg: x.weight_kg?.trim().replace(",", ".") ?? null })) };
    const problems = cancelMode ? [] : validateManualDraft(value);
    if (aligned.issue) { setDraft(aligned.draft); setError("Az edzés még nem menthető."); setIssues([aligned.issue]); return; }
    let dates: string[] = [];
    if (!cancelMode && request.mode !== "edit") {
      try { dates = weeklyDates(value.date, occurrences); } catch { problems.push("Az ismétlés 1–24 alkalom lehet, 1900 és 2100 közötti dátumokkal."); }
    }
    if (problems.length) { setError("Az edzés még nem menthető."); setIssues(problems); return; }
    const source = context.workout;
    if (request.mode === "edit" && !source?.editable || request.mode === "copy" && !source?.copyable) { setError("Ez az edzés ebben a szerkesztőben nem módosítható."); return; }
    const b: ManualSave = { request_id: crypto.randomUUID(), operation: cancelMode ? "cancel" : request.mode === "edit" ? "update" : "create", timezone_name: context.timezone_name,
      workout_id: request.mode === "edit" ? source!.id : null, expected_source_hash: request.mode === "edit" ? source!.source_hash : null,
      expected_goal_reference: request.mode === "edit" ? source!.goal_reference : null, draft: cancelMode ? null : value, repeat_dates: dates,
      copy_from: request.mode === "copy" ? source!.id : null, copy_source_hash: request.mode === "copy" ? source!.source_hash : null };
    const body = JSON.stringify(b);
    try { sessionStorage.setItem(manualPendingKey(owner), body); } catch { setStorageBlocked(true); setError("A mentési kérés nem őrizhető meg a böngészőben. Ellenőrizd a munkamenet-tárhelyet, majd nyisd meg újra a szerkesztőt."); return; }
    setPending(body);
    await transmit(body);
  }
  function discardRejected() {
    if (!rejected || sending) return;
    try { sessionStorage.removeItem(manualPendingKey(owner)); setPending(null); setRejected(false); setError(""); setIssues([]); } catch { setError("A mentési kérés nem törölhető a böngésző tárhelyéről."); }
  }
  const blocked = context?.workout && (request.mode === "edit" ? !context.workout.editable : request.mode === "copy" ? !context.workout.copyable : false);
  const locked = sending || !!pending || !!blocked || storageBlocked;
  const selectedPeriod = context?.mesocycles.find(p => p.id === draft?.mesocycle_id);
  return <dialog ref={dialog} className="pt-calendar-dialog pt-manual-dialog" aria-label="Saját edzés szerkesztése" onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => {
    if (e.target !== e.currentTarget) return;
    const r = e.currentTarget.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) onClose();
  }}>
    <header><div><p>Saját edzésterv</p><h2>{request.mode === "edit" ? "Edzés szerkesztése" : request.mode === "copy" ? "Edzés másolása új alkalomra" : "Új saját edzés"}</h2></div><button type="button" className="pt-button" onClick={onClose}>Bezárás ×</button></header>
    {(error || issues.length > 0) && <div ref={errorPanel} tabIndex={-1} className="pt-warning" role="alert"><p>{error}</p>{issues.length > 0 && <ul>{issues.map((v, i) => <li key={i}>{v}</li>)}</ul>}</div>}
    {pending && <section className="pt-data-panel" aria-label="Függő mentés"><h3>{sending ? "Mentés folyamatban…" : rejected ? "A mentési kérést a rendszer elutasította" : "Korábbi mentés eredményének ellenőrzése"}</h3><p>{rejected ? "A bevitt adatokat a kérés elvetése után javíthatod." : "Az ellenőrzés ugyanazt a kérést küldi újra; nem hoz létre még egy edzést."}</p><div className="pt-manual-actions"><button type="button" className="pt-button" disabled={sending} onClick={() => void transmit(pending)}>Mentés eredményének ellenőrzése</button>{rejected && <button type="button" className="pt-button" disabled={sending} onClick={discardRejected}>Elutasított kérés elvetése, szerkesztés folytatása</button>}</div></section>}
    {!context || !draft ? <p role="status">{error ? <button type="button" className="pt-button" onClick={() => { setError(""); setReload(v => v + 1); }}>Adatok újraolvasása</button> : "Szerkesztő betöltése…"}</p> : <form noValidate onSubmit={e => void submit(e)}>
      {blocked && <p className="pt-warning" role="status">Ez az edzés már teljesített, lezárt, külső forrásból származik, vagy összetett szakaszokat tartalmaz. Közvetlenül nem módosítható.{request.mode === "edit" && context.workout?.copyable ? " A naptárból a Másolás saját edzésként lehetőséggel új alkalmat készíthetsz belőle." : ""}</p>}
      <fieldset disabled={locked} className="pt-manual-form"><legend className="pt-sr-only">Edzés adatai</legend>
        <div className="pt-manual-grid">
          <label className="pt-manual-wide">Edzés neve<input autoFocus maxLength={200} value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
          <label>Sportág<select value={draft.sport} onChange={e => changeTimedDraft({ ...draft, sport: e.target.value })}>{Object.entries(manualSports).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label>Edzésnap<input type="date" min="1900-01-01" max="2100-12-31" value={draft.date} onChange={e => changeTimedDraft({ ...draft, date: e.target.value, start_fold: null })} /></label>
          <label>Kezdés (üresen időpont nélkül)<input type="time" step={1} value={draft.start_time ?? ""} onChange={e => changeTimedDraft({ ...draft, start_time: e.target.value || null, start_fold: null })} /></label>
          <DurationField label="Teljes edzésidő" value={draft.duration_sec} onChange={v => setDraft({ ...draft, duration_sec: v })} onBlur={() => changeTimedDraft(draft)} />
          <label>Távolság (m, opcionális)<input type="number" min={0} step="any" value={draft.distance_m ?? ""} onChange={e => setDraft({ ...draft, distance_m: number(e.target.value) })} /></label>
          <label>Helyszín (opcionális)<input maxLength={200} value={draft.location} onChange={e => changeTimedDraft({ ...draft, location: e.target.value })} /></label>
          <label>Fő edzéscél<select value={draft.primary_goal ?? ""} onChange={e => setDraft({ ...draft, primary_goal: e.target.value || null })}><option value="">Nincs külön megadva</option>{Object.entries(goalLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label>Mezociklus<select value={draft.mesocycle_id ?? ""} onChange={e => setDraft({ ...draft, mesocycle_id: e.target.value || null })}><option value="">Dátum alapján automatikus</option>{context.mesocycles.map(p => <option key={p.id} value={p.id}>{p.title} · {p.start_date} – {p.end_date}</option>)}</select></label>
          <label className="pt-manual-wide">Edzésleírás<textarea rows={4} maxLength={20000} value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label>
        </div>
        <p className="pt-notice">Az edzésidőbe a bemelegítés, a pihenők és a levezetés is beleszámít. Időzóna: {context.timezone_name}.</p>
        {durationNotice && <p className="pt-notice" role="status">{durationNotice}</p>}
        {scheduleWarnings.length > 0 && <div className="pt-warning" role="status" aria-label="Időponttal kapcsolatos figyelmeztetés"><p>Az edzést így is elmentheted. A foglalt időpontot és az időbeosztásodat a mentés nem módosítja.</p><ul>{scheduleWarnings.map(w => <li key={w}>{w}</li>)}</ul></div>}
        <details><summary>Óraátállítás · ismétlődő helyi idő</summary><label>Kezdési idő előfordulása<select value={draft.start_fold ?? ""} onChange={e => setDraft({ ...draft, start_fold: e.target.value === "" ? null : Number(e.target.value) as 0 | 1 })}><option value="">Automatikus, ha egyértelmű</option><option value="0">Első előfordulás</option><option value="1">Második előfordulás</option></select></label></details>
        <details><summary>Teljes edzés intenzitásjelölése (opcionális)</summary><label>Intenzitásjelölés<input maxLength={32} value={draft.intensity_type ?? ""} onChange={e => setDraft({ ...draft, intensity_type: e.target.value || null })} /></label></details>
        <section className="pt-data-panel"><h3>Edzésszakaszok</h3><p>Megadhatod a bemelegítést, a főrészt, az ismétlődő résztávokat és a levezetést.</p>
          {draft.phases.map((p, i) => <PhaseFields key={i} phase={p} index={i} change={v => changeTimedDraft({ ...draft, phases: draft.phases.map((x, j) => j === i ? v : x) })} remove={() => changeTimedDraft({ ...draft, phases: draft.phases.filter((_, j) => j !== i) })} />)}
          <button type="button" className="pt-button" disabled={draft.phases.length >= 50} onClick={() => setDraft({ ...draft, phases: [...draft.phases, { block_type: "WORK", name: "Főrész", duration_sec: null, distance_m: null, repeat_count: 1, notes: "" }] })}>+ Edzésszakasz</button>
          {draft.phases.length > 0 && <p className="pt-notice">Megadott szakaszidők összesen: {durationHMS(draft.phases.reduce((n, p) => n + manualPhaseSeconds(p), 0))}.</p>}
        </section>
        {(draft.sport === "STRENGTH" || draft.exercises.length > 0) && <section className="pt-data-panel"><h3>Erősítő gyakorlatok</h3><p>A saját tervedhez felmérés nélküli gyakorlatot is rögzíthetsz. Itt te adod meg a terhelést, a munkasorozatokat és a pihenőket.</p>
          {draft.exercises.map((x, i) => <ExerciseFields key={i} exercise={x} index={i} catalogue={context.exercises} change={v => setDraft({ ...draft, exercises: draft.exercises.map((p, j) => j === i ? v : p) })} remove={() => setDraft({ ...draft, exercises: draft.exercises.filter((_, j) => j !== i) })} />)}
          <button type="button" className="pt-button" disabled={draft.exercises.length >= 40} onClick={() => setDraft({ ...draft, exercises: [...draft.exercises, newExercise()] })}>+ Erősítő gyakorlat</button>
        </section>}
        {request.mode !== "edit" && <section className="pt-data-panel"><h3>Heti ismétlés</h3><label>Alkalmak száma (az elsővel együtt)<input type="number" min={1} max={24} value={occurrences || ""} onChange={e => setOccurrences(Number(e.target.value))} /></label>{Number.isInteger(occurrences) && occurrences > 1 && occurrences <= 24 && <p>Minden héten ugyanazon a napon, összesen {occurrences} alkalom. Mindegyik később külön szerkeszthető.</p>}</section>}
        {selectedPeriod && (draft.date < selectedPeriod.start_date || draft.date > selectedPeriod.end_date) && <p className="pt-warning">A kiválasztott edzésnap kívül esik ezen a mezocikluson.</p>}
        {request.mode === "edit" && <section className="pt-manual-cancel"><label><input type="checkbox" checked={cancelMode} onChange={e => setCancelMode(e.target.checked)} />Ezt a tervezett edzést elhagyom</label>{cancelMode && <p>Az edzés kikerül az aktív naptári tervből. A korábbi adatai megmaradnak.</p>}</section>}
      </fieldset>
      <footer className="pt-manual-actions"><button type="submit" className="pt-button pt-button-primary" disabled={locked}>{cancelMode ? "Edzés elhagyása" : request.mode === "edit" ? "Módosítások mentése" : occurrences > 1 ? `${occurrences} saját edzés mentése` : "Saját edzés mentése"}</button><button type="button" className="pt-button" onClick={onClose}>Mégse</button></footer>
      <p className="pt-notice">{/^\d{4}-\d{2}-\d{2}$/.test(draft.date) && Number.isFinite(Date.parse(draft.date)) ? formatDay(draft.date) : "Válassz edzésnapot."} · A saját edzés mentése után megjelenik a naptárban; az automatikus tervező a következő frissítéskor figyelembe veszi.</p>
    </form>}
  </dialog>;
}
