"use client";
import { useEffect, useState } from "react";
import { LearningStatus } from "./learning-status";
import { FeedbackError, loadFeedback, readPending, sendFeedback, score, scoreKeys, storageKey, timings } from "@/lib/session-analysis/feedback";
import type { Artifact, Context, Pending, Timing } from "@/lib/session-analysis/feedback";
const titles = {IMMEDIATE:"Edzés utáni", NEXT_MORNING:"Másnap reggeli"};
const labels = {rpe:"Nehézség · RPE", fatigue:"Fáradtság", soreness:"Izomláz", recovery:"Regeneráltság", energy:"Energiaszint"};
type Draft = {observed_at: string; comment: string; base_revision: number} & Record<typeof scoreKeys[number], string>;
const empty = (): Draft => ({base_revision:0, observed_at: new Date().toISOString().slice(0,16), comment:"", rpe:"", fatigue:"", soreness:"", recovery:"", energy:""});
function draft(a: Artifact | null): Draft {
  if (!a) return empty();
  const p=a.proposal;
  return {base_revision:a.revision, observed_at:new Date(p.observed_at).toISOString().slice(0,16), comment:p.comment, ...Object.fromEntries(scoreKeys.map(k => [k,p[k] === null ? "" : String(p[k])]))} as Draft;
}
export function FeedbackPanel({owner, session}: {owner:string; session:string}) {
  const [context,setContext]=useState<Context|null>(null), [timing,setTiming]=useState<Timing>("IMMEDIATE");
  const [drafts,setDrafts]=useState<Record<Timing,Draft>|null>(null), [pending,setPending]=useState<Pending|null>(null);
  const [error,setError]=useState(""), [notice,setNotice]=useState(""), [busy,setBusy]=useState(false), [ready,setReady]=useState(false), [conflict,setConflict]=useState(false);
  const key=storageKey(owner,session), draftKey=key+":draft";
  useEffect(() => {
    const abort=new AbortController();
    Promise.resolve().then(async () => {
      const data=await loadFeedback(owner,session,abort.signal);
      if(abort.signal.aborted)return;
      const local=localStorage.getItem(key), saved=localStorage.getItem(draftKey);
      const initial={IMMEDIATE:draft(data.current.IMMEDIATE), NEXT_MORNING:draft(data.current.NEXT_MORNING)};
      if(saved) {
        try {const parsed=JSON.parse(saved); for(const t of timings) if(parsed[t] && typeof parsed[t].observed_at === "string" && typeof parsed[t].comment === "string" && Number.isSafeInteger(parsed[t].base_revision) && parsed[t].base_revision >= 0 && scoreKeys.every(k=>typeof parsed[t][k] === "string")) initial[t]=parsed[t];} catch {throw Error("A helyi piszkozat nem olvasható. A tárolt értékelések megmaradtak.");}
      }
      setContext(data);setDrafts(initial);setPending(local ? readPending(local,owner,session) : null);setReady(true);
    }).catch(e=>{if(!abort.signal.aborted)setError(e.message || "A visszajelzés nem tölthető be.");});
    return()=>abort.abort();
  },[owner,session,key,draftKey]);
  function edit(field:keyof Draft,value:string) {
    if(!drafts)return;
    const next={...drafts,[timing]:{...drafts[timing],[field]:value}};
    try {localStorage.setItem(draftKey,JSON.stringify(next));setDrafts(next);setNotice("");setError("");} catch {setError("A böngésző nem tudja megőrizni a piszkozatot. Ellenőrizd a tárhelyet.");}
  }
  async function submit() {
    setError("");setNotice("");setBusy(true);
    let attempted: Pending | null = null;
    try {
      let p=pending;
      if(!p) {
        if(!drafts || !context)throw Error("Először töltsd be az előzményeket.");
        const d=drafts[timing];
        const observed=new Date(d.observed_at+":00Z");
        if(!Number.isFinite(observed.getTime()) || observed.toISOString().slice(0,16)!==d.observed_at)throw Error("Adj meg érvényes megfigyelési időpontot (UTC).");
        const body=JSON.stringify({request_id:crypto.randomUUID(),timing,expected_revision:d.base_revision,
          observed_at:observed.toISOString().replace(".000Z","Z"),comment:d.comment,...Object.fromEntries(scoreKeys.map(k=>[k,score(d[k])]))});
        p={owner,session,body}; readPending(JSON.stringify(p),owner,session);
        const other=localStorage.getItem(key);
        if(other && other!==JSON.stringify(p))throw Error("Másik lapról függő mentés található. Olvasd újra ezt az oldalt a folytatáshoz.");
        localStorage.setItem(key,JSON.stringify(p));setPending(p);
      }
      attempted=p;
      const a=await sendFeedback(p);
      // Remove only our exact pending request: another tab may have written a new one.
      if(localStorage.getItem(key)===JSON.stringify(p))localStorage.removeItem(key);
      setPending(null);setConflict(false);setNotice("Visszajelzés elmentve.");
      const next={...drafts!,[a.proposal.timing]:draft(a)};setDrafts(next);localStorage.setItem(draftKey,JSON.stringify(next));
      const data=await loadFeedback(owner,session);setContext(data);
    } catch(e) {
      if(e instanceof FeedbackError && e.status>=400 && e.status<500 && ![408,429].includes(e.status)) {
        // A definite rejection permits editing; unknown outcomes keep identical bytes.
        if(attempted && localStorage.getItem(key)===JSON.stringify(attempted))localStorage.removeItem(key);
        setPending(null);setConflict(e.code==="CALENDAR_FEEDBACK_REVISION_CONFLICT");
      }
      setError(e instanceof Error ? e.message : "A mentés eredménye még nem ismert. Próbáld újra.");
    } finally {setBusy(false);}
  }
  async function refresh() {
    setBusy(true);try {const data=await loadFeedback(owner,session);setContext(data);
      if(drafts){const next={...drafts,[timing]:{...drafts[timing],base_revision:data.current[timing]?.revision ?? 0}};localStorage.setItem(draftKey,JSON.stringify(next));setDrafts(next);}
      setConflict(false);setError("");setNotice("Előzmények újraolvasva. A piszkozatod megmaradt; ellenőrizd, majd mentsd javításként.");} catch(e) {setError(e instanceof Error ? e.message : "Nem tölthető be.");} finally {setBusy(false);}
  }
  const d=drafts?.[timing], current=context?.current[timing];
  return <section className="pt-analysis-card pt-feedback"><h2>Saját visszajelzés</h2>
    <div className="pt-feedback-tabs" role="group" aria-label="Visszajelzés időzítése">{timings.map(t=><button type="button" className="pt-button" aria-pressed={timing===t} disabled={busy || !!pending} key={t} onClick={()=>setTiming(t)}>{titles[t]}</button>)}</div>
    {!ready && !error && <p role="status">Visszajelzések betöltése…</p>}
    {d && <form onSubmit={e=>{e.preventDefault();void submit();}}><fieldset disabled={!ready || busy || !!pending || conflict}>
      <label>Megfigyelés időpontja · UTC<input type="datetime-local" required value={d.observed_at} onChange={e=>edit("observed_at",e.target.value)}/></label>
      <p className="pt-notice">Az értékelt állapot időpontja. Utólagos kitöltésnél állítsd vissza a megfelelő időre. A mentés idejét külön tároljuk.</p>
      <div className="pt-feedback-scores">{scoreKeys.map(k=><label key={k}>{labels[k]}<input type="text" inputMode="decimal" placeholder="Nincs válasz" aria-label={labels[k]} value={d[k]} onChange={e=>edit(k,e.target.value)}/></label>)}</div>
      <p className="pt-notice">0–10 · nehézség, fáradtság, izomláz: több = erősebb; regeneráltság, energia: több = jobb. Az üres mező ismeretlen.</p>
      <label>Megjegyzés · opcionális<textarea rows={2} maxLength={2000} value={d.comment} onChange={e=>edit("comment",e.target.value)}/></label>
      <button className="pt-button" type="submit">{current ? "Javítás mentése" : "Visszajelzés mentése"}</button>
    </fieldset></form>}
    {pending && <div role="status"><p>A mentés eredménye még nem igazolt. A kérés megmaradt ebben a böngészőben.</p><button className="pt-button" disabled={busy} onClick={()=>void submit()}>Azonos mentés újrapróbálása</button></div>}
    {error && <p className="pt-message is-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {(!ready || conflict) && <button className="pt-button" disabled={busy} onClick={()=>{if(!ready)window.location.reload();else void refresh();}}>Előzmények újraolvasása</button>}
    <LearningStatus owner={owner} session={session} revisionKey={timings.map(t=>context?.current[t]?.content_hash ?? "none").join(":")} />
    {context && <details><summary>Mentett előzmények · {context.history.length}</summary>{[...context.history].reverse().map(a=><div className="pt-feedback-history" key={a.artifact_id}>
      <strong>{titles[a.proposal.timing]} · {a.revision}. változat</strong>
      <p>Megfigyelés: {new Date(a.proposal.observed_at).toLocaleString("hu-HU")} · Mentve: {new Date(a.submitted_at).toLocaleString("hu-HU")}</p>
      <p>{scoreKeys.map(k=>`${labels[k]}: ${a.proposal[k] ?? "nincs válasz"}`).join(" · ")}</p>{a.proposal.comment && <p>{a.proposal.comment}</p>}
    </div>)}</details>}
  </section>;
}
