"use client";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import Icon from "@/components/ui/icon";
import { canonical } from "@/lib/planning-cycles/contracts";
import { PENDING_KEY } from "@/lib/athlete-setup/contracts";
import type { Calendar } from "@/lib/athlete-setup/contracts";
import { SetupHTTPError } from "@/lib/athlete-setup/client";
import { formatDay } from "@/lib/calendar/contracts";
import type { CalendarEvent } from "@/lib/calendar/contracts";
import { ConstraintHTTPError, previewConstraints, sendEditor } from "@/lib/calendar/constraint-client";
import { draftFor, prepareEdit } from "@/lib/calendar/constraint-forms";
import type { Draft } from "@/lib/calendar/constraint-forms";
import { categoryLabels, defaultDetails, EDITOR_PENDING, issueLabels, weekLabels } from "@/lib/calendar/constraints";
import type { Details, EditorPending, ScheduleContext } from "@/lib/calendar/constraints";
import { EDITOR_UNDO, makeUndo, prepareUndo, readRecovery, readUndo, undoAvailable, undoChanges, withHistory } from "@/lib/calendar/editor-history";
import type { Recovery, UndoRecord } from "@/lib/calendar/editor-history";
import type { SlotChange } from "@/lib/calendar/slot-transform";

import ConflictSummary from "./conflict-summary";

export type EditRequest = { serial: number; date: string; event: CalendarEvent | null; change?: SlotChange };
const errorText = (e: unknown) => e instanceof Error ? e.message : "A művelet nem sikerült.";
const separated = (s: string) => [...new Set(s.split(",").map((s) => s.trim()).filter(Boolean))];
export function UndoControl({ disabled = true, explanation = "Korábbi napirendi mentések ellenőrzése…", onClick }: {
  disabled?: boolean; explanation?: string; onClick?: () => void;
}) {
  const hintId = useId();
  return <span className="pt-calendar-undo" title={explanation} tabIndex={disabled ? 0 : undefined}
    role={disabled ? "group" : undefined} aria-label={disabled ? "Visszavonás" : undefined} aria-describedby={disabled ? hintId : undefined}>
    <button type="button" className="pt-button" disabled={disabled} onClick={onClick} aria-describedby={hintId}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d="m9 4-5 5 5 5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" /></svg>
      Visszavonás
    </button>
    <span id={hintId} className="pt-sr-only">{explanation}</span>
  </span>;
}
export default function QuickEditor({ context, request, disabled, onSaved, onLockedChange, toolbarTarget }: {
  context: ScheduleContext | null; request: EditRequest | null; disabled: boolean; onSaved: () => void;
  onLockedChange?: (locked: boolean) => void;
  toolbarTarget?: HTMLElement | null;
}) {
  const dialog = useRef<HTMLDialogElement>(null), transmitting = useRef(false);
  const [draft, setDraft] = useState<Draft | null>(null), [base, setBase] = useState<ScheduleContext | null>(null);
  const [source, setSource] = useState<CalendarEvent | null>(null);
  const [review, setReview] = useState<{ pending: EditorPending; context: ScheduleContext; remove: boolean } | null>(null);
  const [pending, setPending] = useState<Recovery | null>(null), [ready, setReady] = useState(false);
  const [undo, setUndo] = useState<UndoRecord | null>(null), [undoMode, setUndoMode] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false), [rejected, setRejected] = useState(false);
  useEffect(() => {
    let active = true;
    queueMicrotask(async () => {
      if (!active) return;
      try { const raw = localStorage.getItem(EDITOR_PENDING); const value = raw ? await readRecovery(raw) : null; if (active) setPending(value); }
      catch { if (active) { setBlocked(true); setError("Az előző napirendi mentés vagy a böngésző tárhelye nem olvasható. Ellenőrizni kell a korábbi mentés eredményét."); } }
      try { const raw = localStorage.getItem(EDITOR_UNDO); const value = raw ? await readUndo(raw) : null; if (active) setUndo(value); }
      catch { if (active) setError("A korábbi visszavonási adat nem olvasható; abból nem indítható módosítás."); }
      if (active) setReady(true);
    });
    return () => { active = false; };
  }, []);
  useEffect(() => { onLockedChange?.(!ready || !!draft || !!pending || blocked || busy); }, [ready, draft, pending, blocked, busy, onLockedChange]);
  useEffect(() => {
    if (!request || !context || disabled || !ready || pending || blocked) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      const value = draftFor(request.date, request.event);
      if (request.event?.window && !request.event.occurrence) {
        const old = (context.availability?.artifact.proposal.data as Calendar | undefined)?.days.find((d) => d.date === request.event!.date)?.windows.find((w) => w.key === request.event!.window!.key);
        if (old) value.details = { ...defaultDetails("available"), ...structuredClone(old) };
      }
      const o = request.event?.occurrence;
      const rule = o ? context.data.rules.find((r) => r.id === o.rule_id) : null;
      if (rule) { value.weekdays = [...rule.weekdays]; value.end = rule.end_date ?? ""; }
      if (request.change) {
        const { date, ...times } = request.change;
        value.date = date;
        value.details = { ...value.details, ...times, start_fold: null, end_fold: null };
      }
      const day = context.availability?.artifact.proposal.data as { days?: { date: string; max_total_minutes: number | null }[] } | undefined;
      const daily = day?.days?.find((d) => d.date === request.date)?.max_total_minutes;
      value.daily = daily === null || daily === undefined ? "" : String(daily);
      setDraft(value); setBase(structuredClone(context)); setSource(request.event);
      setUndoMode(false); setReview(null); setError(""); setNotice("");
    });
    return () => { active = false; };
    // A request pins the snapshot the user opened; later refreshes must not replace a draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request, ready]);
  useEffect(() => {
    const d = dialog.current;
    if (draft && d && !d.open) d.showModal();
  }, [draft]);
  const stale = !!base && !!context && (base.athlete_id !== context.athlete_id ||
    canonical(base.reference) !== canonical(context.reference) ||
    base.availability?.artifact.content_hash !== context.availability?.artifact.content_hash || base.timezone_name !== context.timezone_name);
  const legacy = !!source?.window && !source.occurrence;
  const single = source?.occurrence?.repeat === "weekly" && draft?.scope === "occurrence";
  const relocated = !!source && !!draft && draft.date !== (source.occurrence?.source_date ?? source.date);
  function update(patch: Partial<Draft>) {
    setDraft((d) => d && ({ ...d, ...patch, ...(patch.date ? { scope: "occurrence" as const,
      ...(d.repeat === "once" ? { weekdays: [(new Date(patch.date + "T12:00:00Z").getUTCDay() + 6) % 7] } : {}),
      details: { ...d.details, start_fold: null, end_fold: null } } : {}) }));
    setReview(null); setError("");
  }
  function detail(patch: Partial<Details>) { if (draft) update({ details: { ...draft.details, ...patch } }); }
  function close() { if (!transmitting.current && !busy) { dialog.current?.close(); setDraft(null); setReview(null); } }
  async function preview(remove = false) {
    if (!draft || !base || busy || pending || stale || disabled || undoMode) return;
    setBusy(true); setError(""); setReview(null);
    try {
      if (legacy) {
        const other = sessionStorage.getItem(PENDING_KEY);
        if (other && JSON.parse(other).operation === "availability") throw new Error("A sportolói profilnál függő edzésablak-mentés van. Előbb ott ellenőrizd az eredményét.");
      }
      const prepared = prepareEdit(base, draft, source, remove);
      const result = await previewConstraints(prepared.proposal, base.athlete_id, prepared.first, prepared.last, prepared.availability);
      setReview({ pending: prepared.pending, context: result, remove });
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  async function transmit(value: Recovery) {
    if (!context || value.owner !== context.athlete_id || transmitting.current) return;
    transmitting.current = true; setBusy(true); setError(""); setRejected(false);
    try {
      const receipt = await sendEditor(value);
      let historyNotice = "";
      try {
        const history = await makeUndo(value, receipt);
        if (history) localStorage.setItem(EDITOR_UNDO, JSON.stringify(history)); else localStorage.removeItem(EDITOR_UNDO);
        setUndo(history);
      } catch { setUndo(null); historyNotice = " A mentés sikeres, de a visszavonási adatot a böngésző nem tudta megőrizni."; }
      localStorage.removeItem(EDITOR_PENDING); setPending(null); setReview(null);
      dialog.current?.close(); setDraft(null); setUndoMode(false);
      setNotice((value.history?.isUndo ? "A módosítás visszavonása új revízióként elmentve." : "A napirend módosítása elmentve.") + historyNotice); onSaved();
    } catch (e) {
      setError(errorText(e));
      setRejected((e instanceof ConstraintHTTPError || e instanceof SetupHTTPError) && [400, 404, 409, 422].includes(e.status));
    } finally { transmitting.current = false; setBusy(false); }
  }
  async function save() {
    if (!review || !base || busy || pending || stale || disabled || review.context.occurrences.some((o) => o.issue)) return;
    const value = withHistory(review.pending, base, undoMode);
    try {
      if (localStorage.getItem(EDITOR_PENDING)) throw new Error("Egy másik napirendi kérés eredményét előbb ellenőrizni kell.");
      localStorage.setItem(EDITOR_PENDING, JSON.stringify(value));
    }
    catch { setBlocked(true); setError("A mentési kérés nem őrizhető meg. A mentés nem indult el."); return; }
    setPending(value); await transmit(value);
  }
  async function previewUndo() {
    if (!undo || !context || disabled || busy || pending || blocked || draft || !ready) return;
    setBusy(true); setError(""); setUndoMode(true); setBase(structuredClone(context)); setSource(null);
    setDraft(draftFor(context.local_today, null)); setReview(null);
    try {
      const other = sessionStorage.getItem(PENDING_KEY);
      if (undo.operation === "availability" && other && JSON.parse(other).operation === "availability")
        throw new Error("A sportolói profilnál függő edzésablak-mentés van. Előbb ott ellenőrizd az eredményét.");
      const prepared = prepareUndo(context, undo);
      const result = await previewConstraints(prepared.proposal, context.athlete_id, prepared.first, prepared.last, prepared.availability);
      setReview({ pending: prepared.pending, context: result, remove: false });
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  function discard() {
    if (!rejected || busy) return;
    try { localStorage.removeItem(EDITOR_PENDING); setPending(null); setRejected(false); setDraft(null); dialog.current?.close(); onSaved(); }
    catch { setError("A korábbi kérés nem törölhető a böngésző tárhelyéről."); }
  }
  const d = draft?.details;
  const canUndo = !!undo && !!context && undoAvailable(undo, context);
  const undoDisabled = disabled || busy || !!draft || !!pending || blocked || !ready || !canUndo;
  const changes = canUndo && undo ? undoChanges(undo) : [];
  const short = (text: string) => text.length > 180 ? text.slice(0, 177) + "…" : text;
  const undoExplanation = !ready ? "Korábbi napirendi mentések ellenőrzése…"
    : blocked ? "A böngészőben tárolt mentést előbb ellenőrizni kell."
    : pending ? "Előbb ellenőrizd a függő napirendi mentés eredményét."
    : busy ? "A napirendi művelet folyamatban van."
    : draft ? "Előbb fejezd be vagy zárd be a megnyitott szerkesztést."
    : disabled || !context ? "A naptár és a napirendi adatok betöltése után érhető el."
    : !undo ? "Nincs visszavonható napirendi módosítás ebben a böngészőben."
    : !canUndo ? "Újabb módosítás, időzónaváltás vagy fiókváltás óta ez az állapot már nem vonható vissza."
    : ["A legutóbbi mentett napirendi módosítás visszavonása.",
      ...changes.slice(0, 2).map((change) => `${change.title}\nMost: ${short(change.current)}\nVisszaállítás: ${short(change.restored)}`),
      ...(changes.length > 2 ? [`További ${changes.length - 2} változás az előnézetben.`] : [])].join("\n");
  const undoControl = <UndoControl disabled={undoDisabled} explanation={undoExplanation} onClick={previewUndo} />;
  return <section className="pt-quick-control" aria-label="Napirend szerkesztése">
    {toolbarTarget ? createPortal(undoControl, toolbarTarget) : toolbarTarget === undefined ? <div className="pt-editor-tools">{undoControl}</div> : null}
    {!ready && <span className="pt-notice">Korábbi napirendi mentések ellenőrzése…</span>}
    {notice && <div role="status" className="pt-message">{notice}</div>}
    {error && !draft && <div role="alert" className="pt-message is-error">{error}</div>}
    {pending && <div className="pt-message" role="status">
      Függő napirendi mentés. Az eredmény ugyanazzal a kéréssel ellenőrizhető.
      {pending.owner === context?.athlete_id ? <button className="pt-button" type="button" disabled={busy || disabled} onClick={() => transmit(pending)}>{busy ? "Ellenőrzés…" : "Ugyanaz a napirendi kérés újraküldése"}</button>
        : <p>A kérés másik sportolói fiókhoz tartozik.</p>}
      {rejected && <button className="pt-button" type="button" disabled={busy} onClick={discard}>Elutasított kérés elvetése és újraolvasás</button>}
    </div>}
    <dialog ref={dialog} className="pt-quick-dialog" aria-labelledby="pt-quick-title" onCancel={(e) => { e.preventDefault(); close(); }} onClose={() => { if (!busy) { setDraft(null); setReview(null); } }}>
      {draft && d && <>
        <header className="pt-quick-header"><div><h2 id="pt-quick-title">{undoMode ? "Legutóbbi módosítás visszavonása" : source ? "Idősáv szerkesztése" : "Új idősáv"}</h2><small>{base?.timezone_name} · helyi időpontok</small></div>
          <button type="button" className="pt-button pt-icon-button" aria-label="Idősávszerkesztő bezárása" onClick={close} disabled={busy}><Icon name="close" /></button></header>
        {!undoMode && <form key={request?.serial} className="pt-quick-form" onSubmit={(e: FormEvent) => { e.preventDefault(); void preview(); }}>
          <fieldset disabled={busy || !!pending || blocked || stale || disabled}>
            {source?.occurrence?.repeat === "weekly" && <label>Módosítás hatóköre<select value={draft.scope} onChange={(e) => update({ scope: e.target.value as Draft["scope"] })}>
              <option value="occurrence">Csak ez az alkalom · {formatDay(source.occurrence.source_date)}</option><option value="future" disabled={relocated}>Ettől a naptól minden következő alkalom</option></select></label>}
            {relocated && <p className="pt-notice">A kijelölt alkalom új napra kerül. Heti ismétlődésnél az eredeti nap kimarad, a többi alkalom megmarad. Edzésablaknál a napi keretek nem nőnek automatikusan.</p>}
            <div className="pt-quick-columns">
              <label>Típus<select value={d.kind} disabled={legacy} onChange={(e) => { const kind = e.target.value as Details["kind"]; detail({ ...defaultDetails(kind), start_time: d.start_time, end_time: d.end_time, ends_next_day: d.ends_next_day }); }}>
                <option value="busy">Elfoglaltság / korlát</option><option value="available">Edzéslehetőség</option></select></label>
              {d.kind === "busy" && <label>Jelleg<select value={d.category} onChange={(e) => detail({ category: e.target.value as Details["category"] })}>
                {Object.entries(categoryLabels).filter(([key]) => key !== "training").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
            </div>
            {!legacy && <label>Megnevezés<input autoFocus required maxLength={100} value={d.title} onChange={(e) => detail({ title: e.target.value })} /></label>}
            <div className="pt-quick-columns"><label>{source?.occurrence?.repeat === "weekly" ? "Kiválasztott alkalom" : "Nap / első nap"}<input type="date" min="1900-01-01" max="2100-12-31" required value={draft.date} onChange={(e) => update({ date: e.target.value })} /></label>
              {!legacy && !single && <label>Ismétlődés<select value={draft.repeat} disabled={!!source} onChange={(e) => update({ repeat: e.target.value as Draft["repeat"] })}><option value="once">Egyszeri</option><option value="weekly">Hetente</option></select></label>}
              {d.kind === "busy" && <label>Kötöttség<select value={d.firmness} onChange={(e) => detail({ firmness: e.target.value as Details["firmness"] })}><option value="fixed">Rögzített · edzés nem fér ide</option><option value="flexible">Rugalmas · egyeztethető</option></select></label>}
            </div>
            {draft.repeat === "weekly" && !single && <><div className="pt-quick-week" role="group" aria-label="Ismétlődés napjai">{weekLabels.map((label, day) => <label key={day}><input type="checkbox" checked={draft.weekdays.includes(day)} onChange={(e) => update({ weekdays: e.target.checked ? [...draft.weekdays, day] : draft.weekdays.filter((n) => n !== day) })} />{label}</label>)}</div>
              <label>Ismétlődés utolsó napja · üresen határozatlan<input type="date" min={draft.date} max="2100-12-31" value={draft.end} onChange={(e) => update({ end: e.target.value })} /></label></>}
            <div className="pt-quick-columns"><label>Kezdés<input required type="time" value={d.start_time} onChange={(e) => detail({ start_time: e.target.value })} /></label><label>Befejezés<input required type="time" value={d.end_time} onChange={(e) => detail({ end_time: e.target.value })} /></label></div>
            <label className="pt-quick-check"><input type="checkbox" checked={d.ends_next_day} onChange={(e) => detail({ ends_next_day: e.target.checked })} />Másnap ér véget</label>
            {d.kind === "available" && <div className="pt-quick-columns"><label>Legfeljebb ennyi edzésperc<input type="number" required min="1" max="1440" step="1" value={d.max_minutes ?? ""} onChange={(e) => detail({ max_minutes: e.target.value ? Number(e.target.value) : null })} /></label>
              {legacy && !relocated && <label>Az egész nap edzéskerete · perc, üresen ismeretlen<input type="number" min="1" max="1440" step="1" value={draft.daily} onChange={(e) => update({ daily: e.target.value })} /></label>}</div>}
            {d.kind === "available" && <details className="pt-quick-advanced"><summary>Sportág, terhelési korlát és lehetőségek</summary>
              <label>Sportágak köre<select value={d.sport_scope} onChange={(e) => detail({ sport_scope: e.target.value as Details["sport_scope"], sports: e.target.value === "specified" ? d.sports : [] })}><option value="unknown">Nincs megadva</option><option value="any">Bármely sportág</option><option value="specified">Megadott sportágak</option></select></label>
              {d.sport_scope === "specified" && <label>Sportágak · vesszővel elválasztva<input defaultValue={d.sports.join(", ")} onChange={(e) => detail({ sports: separated(e.target.value) })} /></label>}
              <label>Terhelési felső korlát<select value={d.effort_cap} onChange={(e) => detail({ effort_cap: e.target.value as Details["effort_cap"] })}><option value="unknown">Nincs megadva</option><option value="easy">Könnyű</option><option value="moderate">Mérsékelt</option><option value="any">Nincs külön korlát</option></select></label>
              <label>Elérhető eszközök / lehetőségek · vesszővel<input defaultValue={d.resources.join(", ")} onChange={(e) => detail({ resources: separated(e.target.value) })} /></label></details>}
            <details className="pt-quick-advanced"><summary>Helyszín, megjegyzés és óraátállítás</summary>
              <label>Helyszín<input maxLength={200} value={d.location} onChange={(e) => detail({ location: e.target.value })} /></label>
              <label>Megjegyzés<textarea maxLength={2000} value={d.notes} onChange={(e) => detail({ notes: e.target.value })} /></label>
              <div className="pt-quick-columns">{(["start_fold", "end_fold"] as const).map((key, index) => <label key={key}>{index ? "Befejezés" : "Kezdés"} ismétlődő órában<select value={d[key] ?? ""} onChange={(e) => detail({ [key]: e.target.value === "" ? null : Number(e.target.value) as 0 | 1 })}><option value="">Nincs kiválasztva</option><option value="0">Első előfordulás</option><option value="1">Második előfordulás</option></select></label>)}</div>
            </details>
            <div className="pt-quick-actions"><button type="submit" className="pt-primary">{busy ? "Ellenőrzés…" : "Módosítás áttekintése"}</button>
              {source && <button type="button" className="pt-button" onClick={() => preview(true)}>Alkalom / idősáv elhagyása…</button>}</div>
          </fieldset>
        </form>}
        {stale && <div role="alert" className="pt-message is-error">A naptár közben megváltozott. Zárd be, majd nyisd meg újra a friss idősávot.</div>}
        {error && <div role="alert" className="pt-message is-error">{error}</div>}
        {pending && <div className="pt-message" role="status">A mentés eredményét ellenőrizni kell. <button type="button" className="pt-button" disabled={busy || pending.owner !== context?.athlete_id} onClick={() => transmit(pending)}>Ugyanaz a napirendi kérés újraküldése</button>{rejected && <button type="button" className="pt-button" disabled={busy} onClick={discard}>Elutasított kérés elvetése és újraolvasás</button>}</div>}
        {review && <div className="pt-quick-review" aria-label="Napirendi módosítás áttekintése">
          <h3>{undoMode ? "Visszavonás áttekintése" : review.remove ? "Elhagyás áttekintése" : "Módosítás áttekintése"}</h3>
          <p>{undoMode ? "A legutóbbi mentés előtti napirendi állapot új revízióként áll vissza. A korábbi mentések megmaradnak." : review.remove ? (single ? "Csak a kijelölt alkalom marad ki." : "A kiválasztott hatókörből eltűnik az idősáv.") : `${formatDay(draft.date)} · ${d.title} · ${d.start_time}–${d.end_time}${d.ends_next_day ? " (másnap)" : ""}`}</p>
          {undoMode && undo && <details open><summary>Visszavonás előtti és utáni idősávok</summary><ul>{undoChanges(undo).map((change, index) => <li key={index}><strong>{change.title}</strong><br />Most: {change.current}<br />Visszaállítás: {change.restored}</li>)}</ul></details>}
          <p className="pt-notice">Ellenőrzött időszak: {formatDay(review.context.start_date)} – {formatDay(review.context.end_date)}. Az edzések időpontja változatlan marad.</p>
          {!!review.context.occurrences.filter((o) => o.issue).length && <div className="pt-message is-error" role="alert">Pontosítandó helyi időpontok:<ul>{review.context.occurrences.filter((o) => o.issue).map((o) => <li key={o.key}>{formatDay(o.source_date)} · {o.details.title}: {issueLabels[o.issue!] ?? o.issue}</li>)}</ul></div>}
          <ConflictSummary conflicts={review.context.conflicts} estimates={review.context.duration_estimates} preview />
          <details><summary>Megmaradó edzésablakok · {review.context.opportunities.length}</summary><ul>{review.context.opportunities.map((w) => <li key={w.key}>{formatDay(w.source_date)} · {w.known ? `${w.usable_minutes} használható perc, egy közös ${w.max_minutes} perces keretből` : "A használható idő még nem dönthető el"}{w.daily_max_minutes !== null ? ` · napi felső keret: ${w.daily_max_minutes} p` : ""}</li>)}</ul><p className="pt-notice">Az átfedő ablakok és a napi felső keret nem adódnak össze.</p></details>
          {legacy && review.remove && <p className="pt-notice">Az utolsó ablak elhagyásakor a nap lehetősége ismeretlen lesz. Nem jelöljük automatikusan elérhetetlennek.</p>}
          <button className="pt-primary" type="button" onClick={save} disabled={busy || !!pending || blocked || stale || disabled || review.context.occurrences.some((o) => o.issue)}>{busy ? "Mentés…" : undoMode ? "Visszavonás mentése" : review.remove ? "Elhagyás mentése" : "Napirendi módosítás mentése"}</button>
        </div>}
      </>}
    </dialog>
  </section>;
}
