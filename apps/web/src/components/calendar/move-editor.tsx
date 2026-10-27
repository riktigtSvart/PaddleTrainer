"use client";
import { useEffect, useRef, useState } from "react";
import Icon from "@/components/ui/icon";
import { canonical, object } from "@/lib/planning-cycles/contracts";
import { localParts, requireValue } from "@/lib/calendar/contracts";
import type { SlotChange } from "@/lib/calendar/slot-transform";
import { MOVE_PENDING, MOVE_UNDO, loadMove, moveMessages, moveRef, previewMove, readMovePending, readMoveProposal, readMoveReceipt, sendMove, MoveHTTPError } from "@/lib/calendar/moves";
import type { MoveContext, MovePending, MoveReview, MoveUndo, MoveUndoState } from "@/lib/calendar/moves";
import ConflictSummary from "./conflict-summary";
export type MoveRequest = { serial: number; planId: string; change?: SlotChange; expectedSourceHash?: string; undo?: boolean };
const message = (e: unknown) => e instanceof Error ? e.message : "Az áthelyezés nem sikerült.";
export default function MoveEditor({ owner, request, disabled, onSaved, onLockedChange, onUndoChange }: {
  owner: string | null; request: MoveRequest | null; disabled: boolean; onSaved: () => void;
  onLockedChange: (value: boolean) => void; onUndoChange: (value: MoveUndoState | null) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null), transmitting = useRef(false);
  const [base,setBase]=useState<MoveContext|null>(null), [date,setDate]=useState(""), [clock,setClock]=useState(""), [fold,setFold]=useState<0|1|null>(null);
  const [review,setReview]=useState<MoveReview|null>(null), [pending,setPending]=useState<MovePending|null>(null), [undo,setUndo]=useState<MoveUndo|null>(null);
  const [ready,setReady]=useState(false), [busy,setBusy]=useState(false), [blocked,setBlocked]=useState(false), [rejected,setRejected]=useState(false);
  const [error,setError]=useState(""), [notice,setNotice]=useState(""), [untimed,setUntimed]=useState(false);
  useEffect(()=>{
    let active=true;
    queueMicrotask(async()=>{
      try{const raw=localStorage.getItem(MOVE_PENDING);const value=raw?readMovePending(raw):null;if(active)setPending(value);}
      catch{if(active){setBlocked(true);setError("A függő edzésáthelyezés nem olvasható. Előbb ellenőrizni kell a korábbi mentést.");}}
      try{const raw=localStorage.getItem(MOVE_UNDO);if(raw){const value=object(JSON.parse(raw)),a=object(object(value.receipt).artifact);requireValue(typeof a.athlete_id==="string" && typeof value.consumed==="boolean");const receipt=await readMoveReceipt(value.receipt,a.athlete_id);if(active)setUndo({receipt,consumed:value.consumed});}}
      catch{if(active)setError("Az előző edzésáthelyezés visszavonási adata nem ellenőrizhető.");}
      if(active)setReady(true);
    });return()=>{active=false;};
  },[]);
  useEffect(()=>{onLockedChange(!ready||busy||!!base||!!pending||blocked);},[ready,busy,base,pending,blocked,onLockedChange]);
  useEffect(()=>{onUndoChange(undo ? {createdAt:undo.receipt.artifact.created_at,planId:undo.receipt.artifact.proposal.plan_id,owner:undo.receipt.artifact.athlete_id,
    disabled:undo.consumed||!ready||busy||!!base||!!pending||blocked||undo.receipt.artifact.athlete_id!==owner,
    explanation:undo.consumed?"Az edzésáthelyezés visszavonása már megtörtént.":`Edzés időpontjának visszaállítása: ${undo.receipt.artifact.after.date} → ${undo.receipt.artifact.before.date}. Kattintás után ellenőrizhető.`}:null);
  },[undo,ready,busy,base,pending,blocked,owner,onUndoChange]);
  useEffect(()=>{
    if(!request||!owner||!ready||disabled||pending||blocked)return;
    const abort=new AbortController();
    queueMicrotask(()=>{if(!abort.signal.aborted){setBusy(true);setError("");setNotice("");setReview(null);}});
    loadMove(request.planId,owner,abort.signal).then(value=>{
      if(abort.signal.aborted)return;
      if(request.expectedSourceHash)requireValue(value.source_hash===request.expectedSourceHash,"Az edzés közben megváltozott. Olvasd újra a naptárt és húzd újra.");
      let target=value.current;
      if(request.undo){requireValue(undo && undo.receipt.artifact.proposal.timezone_name===value.timezone_name && !undo.consumed && canonical(value.previous_reference)===canonical(moveRef(undo.receipt.artifact)) && canonical(value.current)===canonical(undo.receipt.artifact.after),"Újabb időpontmódosítás történt. A régi állapot már nem vonható vissza.");target=undo.receipt.artifact.before;}
      const local=target.planned_start_time?localParts(target.planned_start_time,value.timezone_name):null;
      const seconds=target.planned_start_time?new Date(target.planned_start_time).getUTCSeconds():0;
      setBase(value);setDate(request.change?.date??local?.date??target.date);setClock(request.change?.start_time ? request.change.start_time+(request.change.start_seconds?":"+String(request.change.start_seconds).padStart(2,"0"):"") : local ? local.clock+":"+String(seconds).padStart(2,"0") : "");
      setUntimed(!!request.undo&&!target.planned_start_time);setFold(null);
    }).catch(e=>{if(!abort.signal.aborted)setError(message(e));}).finally(()=>{if(!abort.signal.aborted)setBusy(false);});
    return()=>abort.abort();
    // A request pins the context once; background refreshes do not replace it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[request,ready]);
  useEffect(()=>{if(base&&dialog.current&&!dialog.current.open)dialog.current.showModal();},[base]);
  function close(){if(!transmitting.current&&!busy){dialog.current?.close();setBase(null);setReview(null);}}
  async function preview(){
    if(!base||!base.allowed||busy||pending||disabled||blocked)return;
    setBusy(true);setError("");setReview(null);
    try{const p=readMoveProposal({request_id:crypto.randomUUID(),plan_id:base.plan_id,expected_source_hash:base.source_hash,previous_reference:base.previous_reference,timezone_name:base.timezone_name,date,start_time:untimed?null:clock,start_fold:fold});const value=await previewMove(p,base.athlete_id);requireValue(canonical(value.before)===canonical(base.current));setReview(value);}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function transmit(value:MovePending){
    if(transmitting.current||value.owner!==owner)return;
    transmitting.current=true;setBusy(true);setError("");setRejected(false);
    try{
      const receipt=await sendMove(value);let note="";
      try{const history={receipt,consumed:value.undo};localStorage.setItem(MOVE_UNDO,JSON.stringify(history));setUndo(history);}
      catch{setUndo(null);note=" A visszavonás adata nem őrizhető meg ebben a böngészőben.";}
      localStorage.removeItem(MOVE_PENDING);setPending(null);setBase(null);setReview(null);dialog.current?.close();
      setNotice((value.undo?"Az edzés korábbi időpontja visszaállítva.":"Az edzés új időpontja elmentve.")+note);onSaved();
    }catch(e){setError(message(e));setRejected(e instanceof MoveHTTPError&&[400,404,409,422].includes(e.status));}
    finally{transmitting.current=false;setBusy(false);}
  }
  async function save(){
    if(!review||busy||pending||blocked||disabled)return;
    const value:MovePending={version:"calendar-move-pending-v0.1",owner:review.athlete_id,body:JSON.stringify({proposal:review.proposal,review_hash:review.review_hash}),undo:!!request?.undo};
    try{if(localStorage.getItem(MOVE_PENDING))throw Error();localStorage.setItem(MOVE_PENDING,JSON.stringify(value));}
    catch{setBlocked(true);setError("A mentési kérés nem őrizhető meg. A mentés nem indult el.");return;}
    setPending(value);await transmit(value);
  }
  function discard(){if(!rejected||busy)return;try{localStorage.removeItem(MOVE_PENDING);setPending(null);setRejected(false);close();onSaved();}catch{setError("A korábbi kérés nem törölhető.");}}
  const change=()=>{setReview(null);setError("");setFold(null);};
  return <section aria-label="Edzések áthelyezése">
    {busy&&!base&&!pending&&<span className="pt-notice" role="status">Edzés adatainak betöltése…</span>}
    {notice&&<div role="status" className="pt-message">{notice}</div>}
    {error&&!base&&<div role="alert" className="pt-message is-error">{error}</div>}
    {pending&&!base&&<div role="status" className="pt-message">Függő edzésáthelyezés. {pending.owner===owner?<button className="pt-button" type="button" disabled={busy} onClick={()=>transmit(pending)}>Ugyanaz az áthelyezési kérés újraküldése</button>:"A kérés másik sportolói fiókhoz tartozik."}{rejected&&<button className="pt-button" type="button" disabled={busy} onClick={discard}>Elutasított áthelyezés elvetése és újraolvasás</button>}</div>}
    <dialog ref={dialog} className="pt-quick-dialog" aria-labelledby="pt-move-title" onCancel={e=>{e.preventDefault();close();}} onClose={()=>{if(!busy){setBase(null);setReview(null);}}}>
      {base&&<><header className="pt-quick-header"><div><h2 id="pt-move-title">{request?.undo?"Edzés időpontjának visszaállítása":"Edzés áthelyezése"}</h2><small>{base.title} · {base.timezone_name}</small></div><button type="button" className="pt-button pt-icon-button" aria-label="Áthelyezés bezárása" onClick={close} disabled={busy}><Icon name="close"/></button></header>
        {!base.allowed?<p role="alert">{moveMessages[base.blocked_reason!]??base.blocked_reason}</p>:<form className="pt-quick-form" onSubmit={e=>{e.preventDefault();void preview();}}><fieldset disabled={busy||!!pending||blocked||disabled}>
          <p>Jelenleg: {base.current.date} · {base.current.planned_start_time?localParts(base.current.planned_start_time,base.timezone_name).clock:"időpont nélkül"}</p>
          <div className="pt-quick-columns"><label>Új nap<input type="date" required min="1900-01-01" max="2100-12-31" value={date} onChange={e=>{setDate(e.target.value);change();}}/></label>
            {untimed?<p>Visszaállítás időpont nélküli napra.</p>:<label>Új kezdés<input type="time" required step="1" value={clock} onChange={e=>{setClock(e.target.value);change();}}/></label>}</div>
          {!untimed&&<label>Óraátállításkor ismétlődő óra<select value={fold??""} onChange={e=>{setFold(e.target.value===""?null:Number(e.target.value) as 0|1);setReview(null);}}><option value="">Nincs kiválasztva</option><option value="0">Első előfordulás</option><option value="1">Második előfordulás</option></select></label>}
          <p className="pt-notice">Az új kezdést az alkalmazás naptárában mentjük. A Polar naptárát külön kell módosítani.</p>
          <button className="pt-primary" type="submit">{busy?"Ellenőrzés…":"Áthelyezés áttekintése"}</button>
        </fieldset></form>}
        {error&&<div role="alert" className="pt-message is-error">{error}</div>}
        {pending&&<div role="status" className="pt-message">A mentés eredményét ellenőrizni kell. <button className="pt-button" type="button" disabled={busy||pending.owner!==owner} onClick={()=>transmit(pending)}>Ugyanaz az áthelyezési kérés újraküldése</button>{rejected&&<button className="pt-button" type="button" disabled={busy} onClick={discard}>Elutasított áthelyezés elvetése és újraolvasás</button>}</div>}
        {review&&<div className="pt-quick-review"><h3>Új időpont: {review.after.date} · {review.after.planned_start_time?localParts(review.after.planned_start_time,base.timezone_name).clock:"időpont nélkül"}</h3>
          {review.period_warning&&<p className="pt-message">{review.period_warning}</p>}
          <ConflictSummary conflicts={review.conflicts} estimates={review.duration_estimate?{[base.plan_id]:review.duration_estimate}:{}} preview/>
          {!review.conflicts.length&&<p>A megadott adatok alapján nem találtunk időbeli ütközést.</p>}
          <p className="pt-notice">Az edzés távja, időtartama és intenzitása megmarad.</p>
          <button className="pt-primary" type="button" disabled={busy||!!pending||blocked||disabled} onClick={save}>{busy?"Mentés…":request?.undo?"Visszaállítás mentése":"Áthelyezés mentése"}</button>
        </div>}
      </>}
    </dialog>
  </section>;
}
