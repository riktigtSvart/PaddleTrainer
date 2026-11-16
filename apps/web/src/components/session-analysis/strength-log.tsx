"use client";
import { useEffect, useState } from "react";
import { Area, Field, Select } from "@/components/planning-goals/fields";
import { Choice, DecimalField, IntegerField } from "@/components/initial-assessment/fields";
import { newExercise, newSet, loadBases } from "@/lib/initial-assessment/contracts";
import type { Exercise, SetRecord, Pattern } from "@/lib/initial-assessment/contracts";
import { loadLog, saveLog, proposal, logKey } from "@/lib/session-analysis/strength-log";
import type { StrengthLogContext, StrengthLogProposal } from "@/lib/session-analysis/strength-log";
const unknown = "Nincs megadva";
const bases: Record<string, string> = { unknown, total: "Össztömeg", per_hand: "Kézenként", machine_display: "Gép kijelzése", assistance: "Rásegítés", not_applicable: "Nem alkalmazható" };
const loads = { unknown, bodyweight: "Saját testsúly", external_kg: "Külső súly · kg", assistance_kg: "Rásegítés · kg", machine_level: "Gépfokozat", band: "Gumiszalag" };
type Draft = {
    purpose: "training" | "assessment";
    exercises: Exercise[];
    note: string;
};
export function StrengthWorkoutLog({ owner, session }: {
    owner: string;
    session: string;
}) {
    const [context, setContext] = useState<StrengthLogContext | null>(null), [draft, setDraft] = useState<Draft>({ purpose: "training", exercises: [], note: "" }), [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(""), [status, setStatus] = useState(""), [retry, setRetry] = useState(0), [pending, setPending] = useState<string | null>(null);
    const storage = logKey(owner, session);
    useEffect(() => {
        const controller = new AbortController();
        let active = true;
        loadLog(owner, session, controller.signal).then(c => {
            if (!active)
                return;
            let saved = null;
            try {
                const raw = localStorage.getItem(storage);
                saved = raw ? JSON.parse(raw) : null;
            }
            catch {
                setStatus("A helyi vázlat nem olvasható; a szerverre mentett napló látható.");
            }
            let d: Draft = c.current ? c.current.artifact.proposal : { purpose: "training", exercises: [], note: "" };
            if (saved && saved.owner === owner && saved.session === session) {
                if (saved.pending) {
                    proposal(JSON.parse(saved.pending));
                    setPending(saved.pending);
                    d = JSON.parse(saved.pending);
                }
                else if (saved.draft && Array.isArray(saved.draft.exercises))
                    d = saved.draft;
            }
            setContext(c);
            setDraft({ purpose: d.purpose, exercises: d.exercises, note: d.note });
            setError("");
        }).catch(e => { if (active && !controller.signal.aborted)
            setError(e instanceof Error ? e.message : "Az edzésnapló nem tölthető be."); });
        return () => { active = false; controller.abort(); };
    }, [owner, session, storage, retry]);
    function edit(next: Draft) { if (busy || pending)
        return; setDraft(next); setConfirmed(false); setStatus(""); try {
        localStorage.setItem(storage, JSON.stringify({ owner, session, draft: next }));
    }
    catch {
        setError("A böngésző nem tudja tárolni a vázlatot. A bevitt adatok ezen a lapon megmaradtak.");
    } }
    function exercise(id: string, changes: Partial<Exercise>) { edit({ ...draft, exercises: draft.exercises.map(e => e.id === id ? { ...e, ...changes } : e) }); }
    function set(e: Exercise, id: string, changes: Partial<SetRecord>) { exercise(e.id, { sets: e.sets.map(s => s.id === id ? { ...s, ...changes } : s) }); }
    const day = context ? new Intl.DateTimeFormat("sv-SE", { timeZone: context.timezone_name, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(context.session.started_at)) : "";
    async function submit() {
        if (!context || busy)
            return;
        setError("");
        setStatus("");
        let body = pending;
        try {
            if (!body) {
                if (!confirmed)
                    throw Error("Jelöld, hogy a felsorolt sorozatokat valóban elvégezted.");
                const p: StrengthLogProposal = { request_id: crypto.randomUUID(), expected_revision: context.current?.artifact.revision ?? 0, ...draft, confirmed_actual: true };
                proposal(p);
                body = JSON.stringify(p);
                localStorage.setItem(storage, JSON.stringify({ owner, session, pending: body }));
                setPending(body);
            }
            setBusy(true);
            const r = await saveLog(owner, session, body);
            setContext({ ...context, current: r });
            setPending(null);
            setConfirmed(false);
            try {
                localStorage.removeItem(storage);
            }
            catch { /* The server receipt is already durable. */ }
            setStatus("A tényleges munkasorozatok mentve. A következő tervfrissítés már figyelembe veheti őket; a meglévő terv változatlan.");
        }
        catch (e) {
            setError(e instanceof Error ? e.message : "A napló nem menthető. Ellenőrizd az összes mezőt.");
        }
        finally {
            setBusy(false);
        }
    }
    return <details className="pt-data-panel"><summary><strong>Tényleges erősítő gyakorlatok és sorozatok</strong>{context?.current ? ` · ${context.current.artifact.proposal.exercises.reduce((s, e) => s + e.sets.length, 0)} mentett sorozat` : ""}</summary>
  <p>Itt a valóban elvégzett munkasorozatokat rögzítsd, a rávezető sorozatok nélkül. Ez az edzésnapló nem igényel új felmérést. A tervből nem jelölünk automatikusan teljesített sorozatot.</p>
  {error && <p role="alert" className="pt-notice">{error}</p>}{status && <p role="status">{status}</p>}
  {!context ? <button type="button" onClick={() => setRetry(n => n + 1)}>Edzésnapló betöltése újra</button> : <>
  <p className="pt-options-meta">Edzésnap: {day}. A jártasság, kivitelezés és tartalék ismeretlenül is elmenthető; ilyenkor a sorozat nem lesz automatikus terhelési referencia.</p>
  <fieldset disabled={busy || !!pending} className="space-y-5"><Choice label="Alkalom jellege" value={draft.purpose} options={{ training: "Szokásos edzés", assessment: "Felmérés / teszt" }} onChange={v => edit({ ...draft, purpose: v as Draft["purpose"] })}/>
  {draft.exercises.map((e, index) => <section className="pt-data-panel space-y-4" key={e.id}><h4>{index + 1}. gyakorlat</h4><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
   <Choice label="Mozgásminta" value={e.pattern} options={Object.fromEntries(context.patterns.map(p => [p.key, p.label]))} onChange={v => exercise(e.id, { pattern: v as Pattern, exercise_id: null })}/>
   <Select label="Gyakorlat" value={e.exercise_id ?? ""} onChange={ev => exercise(e.id, { exercise_id: ev.target.value || null })}><option value="">Válassz gyakorlatot</option>{context.catalog.exercises.filter(x => context.patterns.find(p => p.key === e.pattern)?.exercise_ids.includes(x.id)).map(x => <option key={x.id} value={x.id}>{x.label}</option>)}</Select>
   <Select label="Helyszín" value={e.location_id ?? ""} onChange={ev => exercise(e.id, { location_id: ev.target.value || null })}><option value="">Válassz helyszínt</option>{context.locations.filter(l => l.sports.includes("STRENGTH") || l.id === e.location_id).map(l => <option key={l.id} value={l.id}>{l.name}{l.archived ? " · archivált" : ""}</option>)}</Select>
   <Choice label="Végrehajtás / oldal" value={e.side} options={{ unknown, both: "Kétoldali", left: "Bal oldal", right: "Jobb oldal", alternating: "Váltott oldal" }} onChange={v => exercise(e.id, { side: v as Exercise["side"] })}/>
   <Choice label="Jártasság a gyakorlatban" value={e.familiarity} options={{ unknown, unfamiliar: "Nem ismerem", assisted: "Segítséggel", independent: "Önállóan végzem", regular: "Rendszeresen végzem" }} onChange={v => exercise(e.id, { familiarity: v as Exercise["familiarity"] })}/>
   <Choice label="Komfort a gyakorlatban" value={e.comfort} options={{ unknown, none: "Panaszmentes", uncertain: "Bizonytalan", symptoms: "Panasz jelentkezett", avoid: "Jelenleg kerülöm", no_experience: "Nincs tapasztalatom" }} onChange={v => exercise(e.id, { comfort: v as Exercise["comfort"] })}/>
   <Field label="Gép és beállítás · gépfokozatnál / rásegítésnél szükséges" value={e.machine_note} maxLength={200} onChange={ev => exercise(e.id, { machine_note: ev.target.value })}/>
  </div>
  {e.sets.map((s, i) => <fieldset className="rounded-xl border border-slate-600 p-4" key={s.id}><legend>{i + 1}. elvégzett munkasorozat</legend><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
   <IntegerField label="Tényleges ismétlés" max={10000} value={s.repetitions} onChange={v => set(e, s.id, { repetitions: v, hold_seconds: null })}/><DecimalField label="Vagy tartás · mp" value={s.hold_seconds} onChange={v => set(e, s.id, { hold_seconds: v, repetitions: null })}/>
   <Choice label="Terhelés típusa" value={s.load_kind} options={loads} onChange={v => set(e, s.id, { load_kind: v as SetRecord["load_kind"], load_basis: (["bodyweight", "band"].includes(v) ? "not_applicable" : "unknown"), load_value: null })}/>
   <DecimalField label="Tényleges súly / gépfokozat" value={s.load_value} onChange={v => set(e, s.id, { load_value: v })}/>
   <Choice label="A terhelés jelentése" value={s.load_basis} options={Object.fromEntries(loadBases[s.load_kind].map(k => [k, bases[k]]))} onChange={v => set(e, s.id, { load_basis: v as SetRecord["load_basis"] })}/><Field label="Terhelés megjegyzése / gumiszalag" value={s.load_note} maxLength={200} onChange={ev => set(e, s.id, { load_note: ev.target.value })}/>
   <Choice label="További szabályos ismétlés ment volna · RIR" value={s.rir} options={{ unknown, "0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5_plus": "Legalább 5" }} onChange={v => set(e, s.id, { rir: v as SetRecord["rir"] })}/>
   <Choice label="Technika" value={s.technique} options={{ unknown, stable: "Stabil", uncertain: "Bizonytalan", breakdown: "Romlott / szétesett" }} onChange={v => set(e, s.id, { technique: v as SetRecord["technique"] })}/>
   <Choice label="Panasz a sorozatban" value={s.symptoms} options={{ unknown, none: "Nem volt", discomfort: "Kellemetlenség", pain: "Fájdalom" }} onChange={v => set(e, s.id, { symptoms: v as SetRecord["symptoms"] })}/>
  </div><button type="button" onClick={() => exercise(e.id, { sets: e.sets.filter(x => x.id !== s.id) })}>Sorozat törlése</button></fieldset>)}
  <div className="flex flex-wrap gap-4"><button type="button" disabled={e.sets.length >= 20} onClick={() => exercise(e.id, { sets: [...e.sets, newSet()] })}>+ Elvégzett munkasorozat</button><button type="button" onClick={() => edit({ ...draft, exercises: draft.exercises.filter(x => x.id !== e.id) })}>Gyakorlat eltávolítása</button></div></section>)}
  <button type="button" disabled={draft.exercises.length >= 16} onClick={() => { const e = newExercise("pull", null); e.performed_on = day; e.sets = [newSet()]; edit({ ...draft, exercises: [...draft.exercises, e] }); }}>+ Elvégzett gyakorlat</button>
  <Area label="Edzésnapló megjegyzése" value={draft.note} maxLength={2000} onChange={e => edit({ ...draft, note: e.target.value })}/>
  <label className="flex gap-3"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>A felsorolt sorozatokat ténylegesen elvégeztem; ez nem a terv másolata.</label></fieldset>
  <div className="mt-5 flex flex-wrap gap-4"><button type="button" disabled={busy} onClick={() => void submit()}>{busy ? "Mentés…" : pending ? "Ugyanazon mentés újrapróbálása" : "Tényleges sorozatok mentése"}</button>{pending && <button type="button" disabled={busy} onClick={() => { setPending(null); setConfirmed(false); setRetry(n => n + 1); localStorage.setItem(storage, JSON.stringify({ owner, session, draft })); }}>Mentés ellenőrzése és szerkesztés</button>}</div>
  <p className="pt-options-meta">A külön edzés-visszajelzésnél rögzítheted az erőfeszítést, fáradtságot és a másnapi állapotot. A tervező ezeket a következő felülvizsgálatkor együtt veszi figyelembe. Az általános induló szabály nem tanult személyes regenerációs modell.</p>
  </>}
 </details>;
}
