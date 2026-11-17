"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { loadContext } from "@/lib/athlete-setup/client";
import { BodyHTTPError, bodyChangedKey, bodyPendingKey, loadBodyState, massNumber, nutritionLabels, readBodyPending, sendBody } from "@/lib/athlete-setup/body-mass";
import type { BodyPending, BodyState, NutritionKind } from "@/lib/athlete-setup/body-mass";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { Area, buttonClass, Field, secondaryClass, Select } from "@/components/planning-goals/fields";

const message = (e: unknown) => e instanceof Error ? e.message : "Az adatok nem tölthetők be.";
export default function BodyWorkspace() {
  const [owner, setOwner] = useState(""), [state, setState] = useState<BodyState | null>(null), [pending, setPending] = useState<BodyPending | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState(""), [rejected, setRejected] = useState(false), [blocked, setBlocked] = useState(false), [ready, setReady] = useState(false);
  const [mass, setMass] = useState(""), [date, setDate] = useState(""), [massNote, setMassNote] = useState("");
  const [goal, setGoal] = useState<NutritionKind>("weight_maintenance"), [target, setTarget] = useState(""), [goalNote, setGoalNote] = useState("");
  const [history, setHistory] = useState<BodyState["items"]>([]), [paging, setPaging] = useState(false);
  const [reload, setReload] = useState(0);
  const writing = useRef(false), massEdited = useRef(false), goalEdited = useRef(false);
  const install = useCallback((value: BodyState) => {
    setState(value); setHistory(value.items);
    if (!massEdited.current) { setMass(value.current?.value_kg ?? ""); setDate(value.local_today); }
    if (!goalEdited.current) { setGoal((value.nutrition_goal?.proposal.goal as NutritionKind | undefined) ?? "weight_maintenance"); setTarget(String(value.nutrition_goal?.proposal.target_kg ?? "")); setGoalNote(String(value.nutrition_goal?.proposal.note ?? "")); }
  }, []);
  useEffect(() => {
    let active = true;
    void loadContext().then(async (context) => {
      const value = await loadBodyState(context.athlete_id);
      if (!active) return;
      setOwner(context.athlete_id); install(value);
      try { const raw = localStorage.getItem(bodyPendingKey(context.athlete_id)); if (raw) setPending(readBodyPending(raw, context.athlete_id)); }
      catch { setBlocked(true); setError("A korábbi testtömeg- vagy célmentés nem olvasható. Az eredményét ellenőrizni kell."); }
      setReady(true);
    }).catch((e) => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, [install, reload]);
  useEffect(() => {
    if (!owner) return;
    let active = true;
    const refresh = () => { if (!writing.current) void loadBodyState(owner).then((value) => { if (active) install(value); }).catch((e) => { if (active) setError(message(e)); }); };
    const storage = (e: StorageEvent) => { if (e.key === bodyChangedKey(owner)) refresh(); };
    window.addEventListener(LOCAL_REFRESH_EVENT, refresh); window.addEventListener("focus", refresh); window.addEventListener("storage", storage);
    return () => { active = false; window.removeEventListener(LOCAL_REFRESH_EVENT, refresh); window.removeEventListener("focus", refresh); window.removeEventListener("storage", storage); };
  }, [owner, install]);
  const locked = busy || !!pending || blocked || !ready;
  async function perform(p: BodyPending) {
    if (writing.current || blocked) return;
    writing.current = true; setBusy(true); setError(""); setNotice(""); setRejected(false);
    let committed = false;
    try {
      const stored = localStorage.getItem(bodyPendingKey(owner));
      if (stored && stored !== JSON.stringify(p)) throw Error("Előbb ellenőrizd a korábbi mentést.");
      localStorage.setItem(bodyPendingKey(owner), JSON.stringify(p)); setPending(p);
      await sendBody(p); committed = true;
      localStorage.removeItem(bodyPendingKey(owner)); setPending(null);
      if (p.operation === "body-mass") { massEdited.current = false; setMassNote(""); } else goalEdited.current = false;
      install(await loadBodyState(owner));
      localStorage.setItem(bodyChangedKey(owner), crypto.randomUUID());
      window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT));
      setNotice(p.operation === "body-mass" ? "A mérés mentve. A legutóbbi testtömeg minden felületen ebből az előzményből származik." : "A táplálkozási testsúlycél mentve.");
    } catch (e) {
      setError(committed ? "A mentés sikerült, de az adatok visszaolvasása megszakadt. Frissítsd a mentett állapotot." : message(e));
      setRejected(!committed && e instanceof BodyHTTPError && [400, 403, 404, 409, 413, 415, 422].includes(e.status));
    } finally { writing.current = false; setBusy(false); }
  }
  function freeze(operation: BodyPending["operation"], proposal: unknown) {
    const p: BodyPending = { version: "body-pending-v0.1", owner, operation, body: JSON.stringify(proposal) };
    readBodyPending(JSON.stringify(p), owner); return p;
  }
  async function more() {
    if (!state || paging) return;
    setPaging(true);
    try {
      const page = await loadBodyState(owner, history.length);
      if (page.total !== state.total || page.current?.measurement_id !== state.current?.measurement_id) { install(await loadBodyState(owner)); setNotice("Az előzmény közben bővült; a legfrissebb lista töltődött be."); }
      else setHistory((old) => [...old, ...page.items]);
    } catch (e) { setError(message(e)); } finally { setPaging(false); }
  }
  async function correctRejected() {
    if (!pending) return;
    try {
      const body = JSON.parse(pending.body);
      if (pending.operation === "body-mass") { setMass(body.value_kg); setDate(body.recorded_on); setMassNote(body.note); massEdited.current = true; }
      else { setGoal(body.goal); setTarget(body.target_kg ?? ""); setGoalNote(body.note); goalEdited.current = true; }
      install(await loadBodyState(owner));
      localStorage.removeItem(bodyPendingKey(owner)); setPending(null); setRejected(false); setError("");
    } catch (e) { setError(message(e)); }
  }
  return <div className="pt-body-workspace space-y-5">
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <button className={secondaryClass} type="button" disabled={busy} onClick={() => { setError(""); setReload((n) => n + 1); }}>Mentett adatok frissítése</button>
    {pending && <section className="pt-body-pending"><p>A korábbi mentés visszaigazolása még szükséges. Az eredeti adatokat megőriztük.</p><button className={buttonClass} type="button" disabled={busy || blocked} onClick={() => void perform(pending)}>Mentés ellenőrzése és folytatása</button>{rejected && <button className={secondaryClass} type="button" disabled={busy} onClick={() => void correctRejected()}>Vissza a szerkesztéshez</button>}</section>}
    {!state && !error && <p role="status">Testtömegadatok betöltése…</p>}
    {state && <>
      <section className="pt-panel" id="body-goals"><h2>Testsúlycél és testtömeg</h2>
        {state.current ? <p className="pt-current-mass"><strong>Legutóbbi mért testtömeg: {state.current.value_kg} kg</strong> · {state.current.recorded_on}</p> : <p>Még nincs dátummal rögzített testtömegmérés.</p>}
        <p className="pt-options-meta">A mért tömeg és a kívánt céltömeg külön adat. A mérések megmaradnak; régebbi mérés felvétele a történeti előzményt bővíti.</p>
        <form onSubmit={(e) => { e.preventDefault(); try { void perform(freeze("body-mass", { request_id: crypto.randomUUID(), value_kg: massNumber(mass), recorded_on: date, note: massNote.trim() })); } catch (error) { setError(message(error)); } }}><fieldset disabled={locked} className="space-y-4"><legend>Testtömegmérés rögzítése</legend><div className="grid gap-4 sm:grid-cols-2">
          <Field label="Mért testtömeg (kg)" inputMode="decimal" required value={mass} onChange={(e) => { massEdited.current = true; setMass(e.target.value); }} />
          <Field label="A mérés tényleges napja" type="date" max={state.local_today} required value={date} onChange={(e) => { massEdited.current = true; setDate(e.target.value); }} />
        </div><Area label="Mérés körülményei (opcionális)" maxLength={500} value={massNote} onChange={(e) => setMassNote(e.target.value)} /><button className={buttonClass} type="submit">Testtömegmérés mentése</button></fieldset></form>
        <form className="pt-nutrition-goal" onSubmit={(e) => { e.preventDefault(); try { const current = state.nutrition_goal; void perform(freeze("nutrition-goal", { request_id: crypto.randomUUID(), previous_reference: current ? { artifact_id: current.artifact_id, content_hash: current.content_hash } : null, goal, target_kg: ["weight_loss", "weight_gain"].includes(goal) ? massNumber(target) : null, note: goalNote.trim() })); } catch (error) { setError(message(error)); } }}><fieldset disabled={locked} className="space-y-4"><legend>Táplálkozási testsúlycél</legend>
          <Select label="Testsúlycél" value={goal} onChange={(e) => { goalEdited.current = true; setGoal(e.target.value as NutritionKind); }}>{Object.entries(nutritionLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select>
          {["weight_loss", "weight_gain"].includes(goal) && <Field label="Céltestsúly (kg)" inputMode="decimal" required value={target} onChange={(e) => { goalEdited.current = true; setTarget(e.target.value); }} />}
          <Area label="Megjegyzés a célhoz (opcionális)" maxLength={500} value={goalNote} onChange={(e) => { goalEdited.current = true; setGoalNote(e.target.value); }} /><button className={buttonClass} type="submit">Táplálkozási testsúlycél mentése</button>
          <p className="pt-options-meta">A célt az előzményekkel együtt tároljuk. A receptalapú étrend adagjai kézzel állíthatók; a személyes energiaszükséglet számítása későbbi bővítés.</p>
        </fieldset></form>
        {state.legacy_goals.length > 0 && <details><summary>Korábban edzéscélként megadott testsúlycélok</summary>{state.legacy_goals.map((legacy, i) => <div key={i} className="pt-legacy-weight-goal"><p><strong>{legacy.program_title}</strong> · {nutritionLabels[legacy.goal]}</p>{legacy.body_mass && <p>A cél korábbi rögzítésekor: {legacy.body_mass.current_kg} kg{legacy.body_mass.target_kg ? ` · korábbi céltömeg: ${legacy.body_mass.target_kg} kg` : ""}</p>}<button type="button" className={secondaryClass} disabled={locked} onClick={() => { goalEdited.current = true; setGoal(legacy.goal); setTarget(legacy.body_mass?.target_kg ?? ""); setGoalNote(`Korábbi szándék átvétele: ${legacy.program_title}`); }}>Átvétel táplálkozási célként</button></div>)}</details>}
      </section>
      <section className="pt-panel" id="body-history"><h2>Testtömeg-előzmények</h2><p className="pt-options-meta">{state.total} rögzített érték. A sorrendet a mérési nap, azonos nap esetén a rögzítés sorrendje adja. A korábbi bizonylatok változatlanul megmaradnak.</p>
        {history.length ? <div className="pt-body-history-scroll"><table><thead><tr><th>Mérési nap</th><th>Testtömeg</th><th>Forrás és megjegyzés</th></tr></thead><tbody>{history.map((row) => <tr key={row.measurement_id}><td>{row.recorded_on}</td><td>{row.value_kg} kg</td><td>{row.source === "imported" ? "Átvett mérés" : row.source === "profile" ? "Személyes alapadatok" : "Kézi mérés"}{row.note ? ` · ${row.note}` : ""}</td></tr>)}</tbody></table></div> : <p>A hiányzó mérés nem nulla kilogramm.</p>}
        {history.length < state.total && <button type="button" className={secondaryClass} disabled={paging} onClick={() => void more()}>Korábbi mérések betöltése</button>}
      </section>
    </>}
  </div>;
}
