"use client";
import { useState } from "react";
import { clock } from "@/lib/session-analysis/chart-data";
import type { PhaseCandidate } from "@/lib/session-analysis/phase-candidates";
import type { useBoundaryView } from "./plan-boundaries";

export function PhaseCandidateControls({ view, onPreview, pickedMs, onCancel }: {
  view: ReturnType<typeof useBoundaryView>; onPreview: (candidate: PhaseCandidate) => void; pickedMs: number | null; onCancel: () => void;
}) {
  const [activeId, setActiveId] = useState(""), [draft, setDraft] = useState("");
  const [dismissed, setDismissed] = useState("");
  const pending = view.alignment.transitions.find(t => t.next_ms === null);
  if (view.manual || !pending) return null;
  const identity = pending.id + ":" + pending.end_ms;
  const active = view.candidates.options.find(c => c.id === activeId);
  const explanations: Record<string, string> = {
    ADVANCE_MODE_UNKNOWN: "Az indítás módja nem ismert; mozgásból sem feltételezünk kézi váltást.",
    MOTION_SOURCE_AMBIGUOUS_OR_MISSING: "A sebesség- és távminták nem választhatók ki egyértelműen ehhez az edzésrészhez.",
    PLAN_EXERCISE_CLOCK_MISMATCH: "A tervrész és a minták edzésrésze nem egyezik. Saját kezdés továbbra is megadható.",
    MOTION_GRID_UNSUITABLE: "A mozgásminták felbontása vagy időalapja nem alkalmas erre a felismerésre.",
    DISTANCE_COUNTER_INVALID: "A távsor visszafelé ugrik vagy hibás értéket tartalmaz. Automatikus javaslat nem készül.",
    NO_SUPPORTED_MOTION_PATTERN: "Nem találtunk összefüggő alacsony sebességet követő tartós megindulást a cél utáni öt percben. A várakozás ettől még lehetséges; kezdése kézzel megadható.",
  };
  return <section className="pt-phase-candidates" aria-label="Várakozási szakaszok felismerése">
    <h4>Várakozás felismerése · {pending.label} után</h4>
    <p className="pt-notice">Ezek mozgásalapú javaslatok, a pulzus nem befolyásolja a határt. Elfogadásig a következő szakasz kezdése és értékelése bizonytalan marad.</p>
    {dismissed === identity ? <p className="pt-notice">A váltás időpontja tisztázatlan maradt. <button className="pt-button" type="button" onClick={() => setDismissed("")}>Javaslatok újramegnyitása</button></p> : <>
      {view.candidates.reasons.filter(r => explanations[r]).map(reason => <p className="pt-notice" key={reason}>{explanations[reason]}</p>)}
      <div className="pt-candidate-options">{view.candidates.options.map(option => <article key={option.id} data-phase-candidate={option.id} className={activeId === option.id ? "is-active" : ""}>
        <strong>{clock(option.start_ms)} · {option.next_label} kezdése</strong>
        <span>Vizsgálandó környék: {clock(option.from_ms)}–{clock(option.to_ms)}</span>
        <span>{option.lead_ms > 0 ? `Feltételezés: a megindulás előtt a terv ${clock(option.lead_ms)} hosszú rövid szakasza futott.` : "Másik értelmezés: a következő szakasz a meginduláskor kezdődött."}</span>
        <small>Alacsony sebesség: {clock(option.low_from_ms)}–{clock(option.low_to_ms)} · Tartós megindulás: {clock(option.moving_ms)}</small>
        <div><button className="pt-button" type="button" onClick={() => { setActiveId(option.id); setDraft(clock(option.start_ms)); onPreview(option); }}>Vizsgálat a grafikonon</button>
          <button className="pt-button" type="button" onClick={() => view.acceptCandidate(option.id)}>Becsült kezdés elfogadása · {clock(option.start_ms)}</button></div>
      </article>)}</div>
      {view.candidates.truncated && <p className="pt-notice">Az első nyolc lehetőséget mutatjuk; a lista nem teljes. A kezdés saját időponttal is megadható.</p>}
      {active && <form className="pt-candidate-edit" onSubmit={e => { e.preventDefault(); view.acceptCandidate(active.id, draft); }}>
        <label>Pontosított kezdés · perc:mp<input aria-label="Javaslat pontosított kezdése" value={draft} required onChange={e => setDraft(e.target.value)} /></label>
        <button className="pt-button" type="button" disabled={pickedMs === null} onClick={() => { if (pickedMs !== null) setDraft(clock(pickedMs)); }}>Grafikonon kijelölt idő átvétele{pickedMs === null ? "" : ` · ${clock(pickedMs)}`}</button>
        <button className="pt-button" type="submit">Pontosított kezdés elfogadása</button>
        <p className="pt-notice">Kattints a nagyított grafikonra, majd vedd át a kijelölt időt; a mezőt közvetlenül is szerkesztheted. A szaggatott sáv csak ellenőrzési ablak. A megindulás nem igazolja a gombnyomás időpontját.</p>
      </form>}
      {view.candidates.options.length > 0 && <button className="pt-button" type="button" onClick={() => { setDismissed(identity); setActiveId(""); onCancel(); }}>Most nem tudom · maradjon bizonytalan</button>}
    </>}
    <details><summary>A javaslat számítása</summary><p className="pt-notice">Legalább 3 másodpercnyi, legfeljebb 2 km/h sebességet követő, legalább 5 másodperces, legalább 4 km/h sebességű mozgást keresünk, a távsor növekedésével együtt. Mindkét szakaszhoz legalább két minta kell; hiányt nem hidalunk át. A rövid előszakasz visszaszámítása külön értelmezés. Az öt másodperces vizsgálati környék durvább mintavételnél tágabb; nem garantált hibahatár. Nem minden várakozás jár megállással. Elfogadás után ez saját referencia marad, az adott forráshoz kötve és ezen a böngészőlapon őrizve.</p></details>
  </section>;
}
