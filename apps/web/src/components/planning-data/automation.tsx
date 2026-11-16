"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { LOCAL_REFRESH_EVENT } from "@/lib/data-connections/preferences";
import { trainingReasons } from "@/lib/planning-cycles/training-plan";
import type { Reference } from "@/lib/planning-cycles/contracts";
import { canonical } from "@/lib/planning-cycles/contracts";
import { AutomaticError, autoKey, loadAutomatic, readAutomaticPending, ref, runAutomatic, saveAutomatic } from "@/lib/planning-data/automation";
import type { AutomaticContext, AutomaticPending } from "@/lib/planning-data/automation";
import { buttonClass, secondaryClass } from "@/components/planning-goals/fields";
import SportAvailabilityDetails from "./sport-availability";

const reasons: Record<string, string> = {
  AUTOMATIC_PLANNING_PROGRAM_SUPERSEDED: "A sportcéloknak újabb mentett változata van. Nézd át az új felkészülés ciklusonkénti céljait, majd az állapotfelmérés végén indítsd a tervezést az új adatokkal.",
  AUTOMATIC_PLANNING_NO_USABLE_WORKOUTS: "A megadott időszakra még nincs összeállítható edzés. Ellenőrizd a célokat, az időlehetőségeket és a saját referenciákat az állapotfelmérésben.",
  AUTOMATIC_PLANNING_CYCLE_EXTENSION_REQUIRED: "A következő időszak ciklusait még meg kell adni.",
  AUTOMATIC_PLANNING_AUTHORITY_CHANGED: "Az automatikus tervezés beállítása közben megváltozott. Frissítsd az állapotot.",
};
export default function AutomaticPlanning({ owner, programReference, canEnable = true, prerequisites = [], prerequisiteActions = [], onComplete, compact = false }: {
  owner: string; programReference?: Reference | null; canEnable?: boolean; prerequisites?: string[];
  prerequisiteActions?: { label: string; action: () => void }[];
  onComplete?: () => void; compact?: boolean;
}) {
  const [data, setData] = useState<AutomaticContext | null>(null), [pending, setPending] = useState<AutomaticPending | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [rejected, setRejected] = useState(false);
  const writing = useRef(false), application = useRef("");
  const update = useCallback((v: AutomaticContext) => {
    setData(v);
    const id = v.last_run?.application_reference?.artifact_id;
    if (id && id !== application.current) { application.current = id; window.dispatchEvent(new Event(LOCAL_REFRESH_EVENT)); }
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    void loadAutomatic(owner, abort.signal).then((v) => { if (!abort.signal.aborted) update(v); }).catch((e) => { if (!abort.signal.aborted) setError(e.message); });
    queueMicrotask(() => { try { const raw = localStorage.getItem(autoKey(owner)); setPending(raw ? readAutomaticPending(raw, owner) : null); } catch { setError("A korábbi automatikus tervezési kérés nem olvasható. Ellenőrizd a mentett állapotot."); } });
    const timer = setInterval(() => { if (!writing.current) void loadAutomatic(owner, abort.signal).then((v) => { if (!abort.signal.aborted) update(v); }).catch(() => {}); }, 60000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [owner, update]);
  async function run(complete = false) {
    if (writing.current) return;
    writing.current = true; setBusy(true); setError("");
    try { const result = await runAutomatic(owner); update(result); if (complete && result.last_run?.state !== "blocked") onComplete?.(); }
    catch (e) {
      setError(e instanceof Error ? e.message : "A terv frissítése nem sikerült.");
      if (!(e instanceof AutomaticError) || e.status >= 500) {
        try {
          const recovered = await loadAutomatic(owner);
          update(recovered);
          if (recovered.last_run && recovered.last_run.artifact_id !== data?.last_run?.artifact_id && recovered.last_run.state !== "blocked") setError("");
        }
        catch { /* Preserve the last verified view and the original failure. */ }
      }
    }
    finally { writing.current = false; setBusy(false); }
  }
  async function save(enabled: boolean, retained?: AutomaticPending) {
    if (!data || writing.current) return;
    if (!retained && enabled && !canEnable) return;
    writing.current = true; setBusy(true); setError(""); setRejected(false);
    try {
      let p = retained;
      if (!p) {
        const selected = programReference ?? data.policy?.proposal.program_reference ?? null;
        if (enabled && !selected) throw Error("Előbb válassz mentett felkészülést.");
        p = { owner, body: JSON.stringify({ request_id: crypto.randomUUID(), previous_reference: data.policy ? ref(data.policy) : null, program_reference: selected, enabled, onboarding_completed: true }) };
        readAutomaticPending(JSON.stringify(p), owner);
        const old = localStorage.getItem(autoKey(owner));
        if (old && old !== JSON.stringify(p)) throw Error("Egy korábbi tervezési beállítás mentése még ellenőrzésre vár.");
        localStorage.setItem(autoKey(owner), JSON.stringify(p)); setPending(p);
      }
      const policy = await saveAutomatic(p);
      if (localStorage.getItem(autoKey(owner)) === JSON.stringify(p)) localStorage.removeItem(autoKey(owner));
      setPending(null);
      const result = policy.proposal.enabled ? await runAutomatic(owner) : await loadAutomatic(owner);
      update(result);
      if (policy.proposal.enabled && result.last_run?.state !== "blocked") onComplete?.();
    } catch (e) { setError(e instanceof Error ? e.message : "A beállítás mentése nem sikerült."); if (e instanceof AutomaticError && e.status >= 400 && e.status < 500 && ![408, 429].includes(e.status)) setRejected(true); }
    finally { writing.current = false; setBusy(false); }
  }
  const enabled = data?.policy?.proposal.enabled === true;
  if (!data) return <section className={compact ? "pt-auto-status" : "pt-data-panel"} aria-label="Automatikus edzéstervezés"><p role={error ? "alert" : "status"}>{error || "Automatikus tervezés mentett állapotának betöltése…"}</p>{error && <button type="button" className={secondaryClass} onClick={() => void loadAutomatic(owner).then(update).catch((e) => setError(e.message))}>Állapot újraolvasása</button>}</section>;
  const runState = data?.last_run;
  const alreadySelected = enabled && (!programReference || canonical(programReference) === canonical(data?.policy?.proposal.program_reference));
  return <section className={compact ? "pt-auto-status" : "pt-data-panel"} data-state={runState?.state ?? (enabled ? "waiting" : "off")} aria-label="Automatikus edzéstervezés">
    {!compact && <h2>Automatikus edzéstervezés</h2>}
    <p><strong>{enabled ? runState?.state === "completed" ? "A beállított felkészülés véget ért." : "Automatikus edzéstervezés bekapcsolva." : "Automatikus edzéstervezés még nincs bekapcsolva."}</strong>{data?.program && ` ${data.program.title}`}</p>
    {enabled && !runState && <p>Az első tervezésre vár. A működő API percenként ellenőrzi a mentett adatokat.</p>}
    {runState?.state === "applied" && <p>{runState.created_count} új edzés került a naptárba{runState.cancelled_count ? `, ${runState.cancelled_count} korábbi saját terv lecserélve` : ""}.</p>}
    {!!runState?.blockers.length && <ul>{runState.blockers.map((v) => <li key={v}>{reasons[v] ?? trainingReasons[v] ?? v}</li>)}</ul>}
    {error && <p role="alert">{error}</p>}
    {runState?.sport_availability && <SportAvailabilityDetails value={runState.sport_availability} />}
    {pending ? <div className="pt-data-actions"><p>Egy beállítás mentése még ellenőrzésre vár.</p><button className={secondaryClass} type="button" disabled={busy || !data} onClick={() => void save(false, pending)}>Azonos beállítás mentésének ellenőrzése</button>{rejected && <button className={secondaryClass} type="button" onClick={() => { localStorage.removeItem(autoKey(owner)); setPending(null); setRejected(false); void loadAutomatic(owner).then(update).catch((e) => setError(e.message)); }}>Elutasított kérés elvetése</button>}</div> : compact ? <div className="pt-context-links"><Link href="/training-planning#assessment">Tervezési adatok és felmérések</Link>{enabled && <button type="button" className={secondaryClass} disabled={busy} onClick={() => void run()}>Terv frissítése most</button>}</div> : <>
      {!canEnable && prerequisites.length > 0 && <ul>{prerequisites.map((v) => <li key={v}>{v}</li>)}</ul>}
      {!canEnable && prerequisiteActions.length > 0 && <div className="pt-data-actions">{prerequisiteActions.map(({ label, action }) => <button type="button" className={secondaryClass} key={label} disabled={busy} onClick={action}>{label}</button>)}</div>}
      <p className="pt-options-meta">A mentett kereteken belül a naptár az aktuális és következő mezociklusra frissül. A felkészülés végén a tervezés lezárul. A támogatott edzésminták jelenleg kajakhoz, futáshoz és erősítéshez állnak rendelkezésre.</p>
      <div className="pt-data-actions"><button type="button" className={buttonClass} disabled={busy || !data || !canEnable} onClick={() => alreadySelected ? void run(true) : void save(true)}>{onComplete ? "Adatfelvétel befejezése és automatikus tervezés indítása" : "Automatikus edzéstervezés bekapcsolása"}</button>{enabled && <button type="button" className={secondaryClass} disabled={busy} onClick={() => void save(false)}>Automatikus tervezés kikapcsolása</button>}</div>
    </>}
  </section>;
}
