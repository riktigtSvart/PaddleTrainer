"use client";
import {useEffect,useState} from "react";
import {blockerLabels,ConnectionError,connectionStorageKey,loadExecutionPreview,readConnectionPending,sendExecutionConnection} from "@/lib/session-analysis/execution-connection";
import type {ConnectionPending,ExecutionPreview} from "@/lib/session-analysis/execution-connection";
export function ExecutionConnection({owner,session,needed,onConnected}:{owner:string;session:string;needed:boolean;onConnected:()=>Promise<void>}){
 const [pending,setPending]=useState<ConnectionPending|null>(null),[preview,setPreview]=useState<ExecutionPreview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const [baseline,setBaseline]=useState(false),[identity,setIdentity]=useState(false),[loaded,setLoaded]=useState(false);
 const key=connectionStorageKey(owner,session);
 useEffect(()=>{Promise.resolve().then(()=>{try{const raw=localStorage.getItem(key);setPending(raw?readConnectionPending(raw,owner,session):null);setLoaded(true);}catch{setError("A korábbi rögzítési kérés nem olvasható ebből a böngészőből.");}});},[key,owner,session]);
 async function inspect(){setBusy(true);setError("");setPreview(null);setBaseline(false);setIdentity(false);try{setPreview(await loadExecutionPreview(owner,session));}catch(e){setError(e instanceof Error?e.message:"Az előnézet nem tölthető be.");}finally{setBusy(false);}}
 async function connect(){setBusy(true);setError("");let attempted:ConnectionPending|null=null;try{
  let p=pending;
  if(!p){if(!preview || preview.state!=="ready_for_review" || !baseline || !identity)throw Error("Előbb ellenőrizd és erősítsd meg az előnézetet.");
   p={owner,session,body:JSON.stringify({request_id:crypto.randomUUID(),review_hash:preview.review_hash,acknowledge_current_state_baseline_only:true,acknowledge_session_identity_only:true})};
   readConnectionPending(JSON.stringify(p),owner,session);const other=localStorage.getItem(key);if(other && other!==JSON.stringify(p))throw Error("Másik lapról függő kérés található. Töltsd újra ezt az oldalt.");
   localStorage.setItem(key,JSON.stringify(p));setPending(p);
  }
  attempted=p;await sendExecutionConnection(p);
  if(localStorage.getItem(key)===JSON.stringify(p))localStorage.removeItem(key);
  setPending(null);setPreview(null);setNotice("Végrehajtási bizonyíték rögzítve.");await onConnected();
 }catch(e){if(e instanceof ConnectionError && e.status>=400 && e.status<500 && ![408,429].includes(e.status)){
   if(attempted && localStorage.getItem(key)===JSON.stringify(attempted))localStorage.removeItem(key);
   setPending(null);setPreview(null);setBaseline(false);setIdentity(false);
  }setError(e instanceof Error?e.message:"A rögzítés eredménye még nem ismert.");}finally{setBusy(false);}}
 if(!needed && !pending && !error && !notice)return null;
 return <div className="pt-execution-connection"><h3>Edzésbizonyíték bekötése</h3>
  {pending?<><p role="status">Egy korábban megerősített rögzítés eredménye még nem igazolt. A pontos kérés megmaradt.</p><button className="pt-button" type="button" disabled={busy} onClick={()=>void connect()}>Azonos rögzítés újrapróbálása</button></>:
   <button className="pt-button" type="button" disabled={busy || !loaded} onClick={()=>void inspect()}>Terv és teljesítés ellenőrzése</button>}
  {preview && <div><p><strong>Teljesítés:</strong> {preview.session_title} · {new Date(preview.session_started_at).toLocaleString("hu-HU",{timeZone:preview.timezone_name})}</p>
   {preview.plan_title && <p><strong>Terv:</strong> {preview.plan_title} · {preview.plan_date}</p>}
   {preview.state==="already_frozen" && <p>A végrehajtási bizonyíték már rögzített. A tanulási kapcsolat frissíthető.</p>}
   {preview.blockers.map((b,i)=><p role="status" key={i}>{blockerLabels[b]??b}</p>)}
   {preview.state==="ready_for_review" && <><p>Azonosítás: {preview.link_basis==="exact_provider_id"?`egyező szolgáltatói célazonosító · ${preview.provider_target_id}`:"korábban kézzel megerősített tervkapcsolat"}.</p>
    <p className="pt-notice">{preview.plan_adoption_required?"A most ismert tervállapot külön, megőrzött alapváltozatot kap. ":"A már rögzített tervazonosságot használjuk. "}A korabeli tervtartalom és a szakaszhatárok ettől még nem igazoltak. Időzóna: {preview.timezone_name}.</p>
    <label><input type="checkbox" checked={baseline} disabled={busy || !!pending} onChange={e=>setBaseline(e.target.checked)}/> Tudomásul veszem, hogy csak a most ismert tervállapotot rögzítjük, nem igazolunk visszamenőleg tervváltozatot.</label>
    <label><input type="checkbox" checked={identity} disabled={busy || !!pending} onChange={e=>setIdentity(e.target.checked)}/> Megerősítem, hogy a fenti teljesítés a fenti tervhez tartozik; ez önmagában nem igazolja a szakaszok teljesítését.</label>
    <button className="pt-button" type="button" disabled={busy || !!pending || !baseline || !identity} onClick={()=>void connect()}>Kapcsolat és bizonyíték rögzítése</button>
   </>}
  </div>}
  {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
 </div>;
}
