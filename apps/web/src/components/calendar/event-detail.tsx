"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { CalendarEvent, Feed } from "@/lib/calendar/contracts";
import { formatDay, formatDuration, goalLabels } from "@/lib/calendar/contracts";
import { eventHref, previewLines } from "@/lib/calendar/event-preview";
import { alternativeLabel } from "@/lib/calendar/training-alternatives";
import WorkoutAlternatives from "./workout-alternatives";
import SessionWorkspace from "@/components/session-analysis/workspace";
import WorkoutInstructionDetails from "@/components/planning-cycles/workout-instructions";
import ManualWorkoutDetails from "./manual-workout-details";

export default function EventDetail({ event, feed, onClose, onEditManual, onCopy }: { event: CalendarEvent; feed: Feed; onClose: () => void; onEditManual?: () => void; onCopy?: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [showSessionLog,setShowSessionLog]=useState(false);
  const plan = feed.planned.find((p) => p.id === event.entityId);
  const context = plan?.planning_context;
  const picker=event.kind==='planned'&&context?.replaceable&&plan;
  useEffect(() => {
    const node = dialog.current, previous = document.activeElement as HTMLElement | null;
    node?.showModal();
    return () => { node?.close(); previous?.focus(); };
  }, []);
  const details=<>
    <div className="pt-context-links"><Link href={eventHref(event)!}>Teljes edzésadatlap külön oldalon →</Link>{event.pairedPlan && <Link href={`/workouts/${event.pairedPlan.entityId}`}>A kapcsolt terv adatlapja →</Link>}</div>
    <section className="pt-data-panel"><h3>{plan?.sport ?? event.sport}</h3><ul>{previewLines(event, feed).map((line, i) => <li key={i}>{line}</li>)}</ul>{plan?.description && <p style={{ whiteSpace: "pre-wrap" }}>{plan.description}</p>}
      <dl><dt>Terv szerinti idő</dt><dd>{plan?.duration_sec === null || plan?.duration_sec === undefined ? "Nincs rögzítve" : formatDuration(plan.duration_sec)}</dd><dt>Fő cél</dt><dd>{event.goal ? goalLabels[event.goal] ?? event.goal : "Nincs külön megadva"}</dd></dl>
      {context && <p className="pt-notice">A mezociklus alapján tervezett cél: {goalLabels[context.primary_goal] ?? context.primary_goal}.{plan?.goal_tag?.primary_goal && plan.goal_tag.primary_goal !== context.primary_goal ? " A naptári céljelölést külön módosítottad." : ""}</p>}
    </section>
    {plan?.manual_context?.recipe && <ManualWorkoutDetails value={plan.manual_context.recipe} />}
    {context?.instructions&&<WorkoutInstructionDetails value={context.instructions}/>}
    {context?.instructions_issue&&<p className="pt-notice" role="status">A részletes gyakorlatsor most nem érhető el. Az eredeti edzésleírás fent látható.</p>}
    {context?.alternative_kinds&&<p className="pt-options-meta">{alternativeLabel(context)}</p>}
  </>;
  return <dialog ref={dialog} className="pt-calendar-dialog" aria-label={picker?'Edzés és alternatívák':'Edzés részletei'} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{
    if(e.target!==e.currentTarget)return;const r=e.currentTarget.getBoundingClientRect();
    if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose();
  }}>
    <header><div><p>{formatDay(event.date)}</p><h2>{event.title}</h2></div><button type="button" className="pt-button" onClick={onClose} aria-label="Edzésablak bezárása">Bezárás ×</button></header>
    {event.kind === 'planned' && <div className="pt-context-links">{plan?.manual_context?.editable && onEditManual && <button type="button" className="pt-button" onClick={onEditManual}>Saját edzés szerkesztése</button>}{onCopy && <button type="button" className="pt-button" onClick={onCopy}>Másolás saját edzésként…</button>}</div>}
    {event.kind === "session" ? <>
      <div className="pt-context-links"><Link href={eventHref(event)!}>Teljes edzésadatlap külön oldalon →</Link></div>
      <section className="pt-data-panel"><h3>{event.sport}</h3><ul>{previewLines(event,feed).map((line,i)=><li key={i}>{line}</li>)}</ul><p>{event.duration===null?'Nincs rögzített időtartam':formatDuration(event.duration)}</p></section>
      <details onToggle={e=>setShowSessionLog(e.currentTarget.open)}><summary>Edzésnapló és részletes elemzés</summary>{showSessionLog&&<SessionWorkspace sessionId={event.entityId}/>}</details>
    </> : picker ? <>
      <p className="pt-notice pt-current-selection" aria-label="Kijelölt edzés">Jelenleg kijelölve: <strong>{event.title}</strong> · {formatDuration(plan.duration_sec??0)} · {goalLabels[context.primary_goal]??context.primary_goal}</p>
      <WorkoutAlternatives owner={feed.athlete_id} zone={feed.timezone_name} today={feed.local_today} target={{...context,id:plan.id}} onApplied={onClose}/>
      <details className="pt-picker-details"><summary>A naptárban lévő edzés részletei</summary>{details}</details>
    </> : details}
  </dialog>;
}
