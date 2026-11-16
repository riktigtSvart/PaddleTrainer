"use client";

import { useEffect, useRef, useState } from "react";
import { addDays } from "@/lib/planning-cycles/contracts";
import { localDay } from "@/lib/planning-cycles/plan-view";
import { ConnectionError, findSync, loadStatus, runMessages, sendSync } from "@/lib/data-connections/client";
import { UPDATED_EVENT } from "@/lib/data-connections/contracts";
import type { Status } from "@/lib/data-connections/contracts";
import { advanceHistory, historyKey, historyPending, newHistory, readHistory } from "@/lib/data-connections/history-backfill";
import type { HistoryBackfill } from "@/lib/data-connections/history-backfill";

export default function PolarHistoryControl() {
  const [status, setStatus] = useState<Status | null>(null), [state, setState] = useState<HistoryBackfill | null>(null);
  const [first, setFirst] = useState("2021-12-01"), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0), pause = useRef(false), active = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    loadStatus(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setStatus(value);
      const raw = localStorage.getItem(historyKey(value.athlete_id));
      if (raw) { const saved = readHistory(raw, value.athlete_id); setState(saved); setFirst(saved.first_date); }
    }).catch(e => { if (!controller.signal.aborted) setMessage(e instanceof Error ? e.message : "A korábbi betöltés állapota nem olvasható."); });
    return () => { controller.abort(); pause.current = true; };
  }, [revision]);

  function persist(value: HistoryBackfill) {
    localStorage.setItem(historyKey(value.owner), JSON.stringify(value));
    setState(value);
  }
  async function start() {
    if (!status || active.current) return;
    active.current = true; pause.current = false; setBusy(true); setMessage("");
    try {
      let current = state ?? newHistory(status.athlete_id, first, addDays(localDay(status.timezone_name, new Date(status.retrieved_at)), 1));
      persist(current);
      // Explicit button action only. Restoring this component never sends a POST.
      for (let batch = 0; batch < 100 && current.cursor > current.first_date && !pause.current; batch++) {
        let receipt;
        if (current.pending) {
          try { receipt = await findSync(current.pending); }
          catch (e) { if (!(e instanceof ConnectionError && e.status === 404)) throw e; }
          if (receipt && ["failed", "partial", "interrupted"].includes(receipt.run.state)) {
            // This new click authorizes retrying the same range with a new ID.
            current = { ...current, pending: null }; persist(current); receipt = undefined;
          }
        }
        if (!current.pending) { current = { ...current, pending: historyPending(current, crypto.randomUUID()) }; persist(current); }
        receipt ??= await sendSync(current.pending!);
        if (receipt.run.state === "running") {
          setMessage("Az aktuális adag még fut. A Folytatás gomb először az eredményét ellenőrzi."); return;
        }
        if (receipt.run.state !== "succeeded") {
          if (["failed", "partial"].includes(receipt.run.state)) { current = { ...current, pending: null }; persist(current); }
          throw Error(runMessages(receipt.run).join(" ") || "Az aktuális adag nem zárult le. A mentett edzések megmaradnak; a betöltés folytatható.");
        }
        current = await advanceHistory(current, receipt); persist(current);
        window.dispatchEvent(new CustomEvent(UPDATED_EVENT, { detail: { provider: "POLAR", request_id: receipt.run.request_id } }));
      }
      setMessage(current.cursor === current.first_date ? "A kijelölt időszak betöltése befejeződött. A tervezőben frissítsd a tervet." : "A betöltés szünetel; az eddig mentett előzmények megmaradtak.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "A betöltés megszakadt. Az eddig mentett edzések megmaradtak."); }
    finally { active.current = false; setBusy(false); }
  }
  const provider = status?.providers.find(p => p.key === "POLAR");
  const complete = state !== null && state.cursor === state.first_date;
  return <section className="pt-panel" id="polar-history">
    <h3>Régebbi Polar-edzések betöltése</h3>
    <p>A kiválasztott időszak teljesített edzéseit legfeljebb 90 napos adagokban kérjük le, a legújabbaktól visszafelé. Most az összesítő adatok kerülnek be: sportág, időtartam, táv és az elérhető összesítők. A másodpercenkénti mintasorok külön tölthetők be.</p>
    <label>Kezdőnap <input type="date" value={first} min="1900-01-01" disabled={busy || state !== null} onChange={e => setFirst(e.target.value)} /></label>
    {state && <p>Időszak: {state.first_date} – {addDays(state.to_exclusive, -1)}. Ellenőrzött adagok: {state.checked_batches}. Új edzések: {state.imported}; frissített edzések: {state.updated}.
      {!complete && <> Következő adag vége: {addDays(state.cursor, -1)}.</>}</p>}
    <p>A régebbi futások sportmúltat jeleznek. A mostani tempót és terhelhetőséget külön pontosítjuk; a történeti betöltés nem feltétele a kezdő tervezésnek.</p>
    <div className="pt-context-links">
      <button type="button" className="pt-button pt-primary" disabled={busy || complete || provider?.connection_state !== "connected" || !provider.allowed_datasets.includes("sessions")} onClick={() => void start()}>{busy ? "Előzmények betöltése…" : state ? "Betöltés folytatása" : "Előzmények betöltése"}</button>
      {busy && <button type="button" className="pt-button" onClick={() => { pause.current = true; setMessage("Az aktuális adag mentése után szüneteltetjük a betöltést."); }}>Szünet az aktuális adag után</button>}
      {!busy && state && !state.pending && <button type="button" className="pt-button" onClick={() => { localStorage.removeItem(historyKey(state.owner)); setState(null); setMessage(""); }}>Másik időszak választása</button>}
      {!busy && <button type="button" className="pt-button" onClick={() => setRevision(n => n + 1)}>Kapcsolat ellenőrzése</button>}
    </div>
    {provider && provider.connection_state !== "connected" && <p>Az előzményekhez először csatlakoztasd a Polar-fiókodat a fenti adatkapcsolatnál.</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
