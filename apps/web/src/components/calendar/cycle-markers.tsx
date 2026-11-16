import Link from "next/link";
import { calendarCycles, cycleBoundaries, cycleProgress } from "@/lib/calendar/cycles";
import type { CalendarCycle } from "@/lib/calendar/cycles";
import { formatDay } from "@/lib/calendar/contracts";
import type { Feed } from "@/lib/calendar/contracts";

export function CycleDayMarkers({ cycles, date, onOpenCycle }: { cycles: CalendarCycle[]; date: string; onOpenCycle?: (cycle: CalendarCycle) => void }) {
  const edges = cycleBoundaries(cycles, date);
  if (!edges.length) return null;
  return <span className="pt-cycle-markers" aria-label="Ciklushatárok">{edges.map(({ cycle, edge }) => {
    const text = `${cycle.kind === "meso" ? "Mezociklus" : cycle.title} ${edge === "start" ? "kezdete" : "vége"}`;
    const title=`${text} · ${cycle.kind === "meso" ? cycle.title : "7 napos tervezési szakasz, az utolsó rövidebb lehet"} · ${formatDay(cycle.start_date)} – ${formatDay(cycle.end_date)}`;
    return onOpenCycle ? <button key={`${cycle.id}:${edge}`} type="button" data-cycle-kind={cycle.kind} data-cycle-edge={edge} title={title} aria-label={`${text} · ${cycle.title} részletei`} onClick={e=>{e.stopPropagation();onOpenCycle(cycle);}} onDoubleClick={e=>e.stopPropagation()} onContextMenu={e=>e.stopPropagation()}>{text}</button>
      : <span key={`${cycle.id}:${edge}`} data-cycle-kind={cycle.kind} data-cycle-edge={edge} title={title}>{text}</span>;
  })}</span>;
}
export default function CycleProgress({ feed, date, onOpenCycle }: { feed: Feed; date: string; onOpenCycle?: (cycle: CalendarCycle) => void }) {
  const cycles = calendarCycles(feed.periods), active = cycles.filter(c => c.kind === "meso" && c.start_date <= date && date <= c.end_date);
  if (!active.length) return <p className="pt-cycle-progress">{formatDay(date)} · Erre a napra nincs mentett mezociklus.</p>;
  return <div className="pt-cycle-progress" aria-label="Helyünk a felkészülésben">{active.map(meso => {
    const micro = cycles.find(c => c.kind === "micro" && c.parent_id === meso.id && c.start_date <= date && date <= c.end_date)!;
    const m = cycleProgress(meso, date), w = cycleProgress(micro, date);
    const content=<>
      <span>{date === feed.local_today ? "Ma" : formatDay(date)} · <strong>{meso.title}</strong> · {m.day}/{m.total}. nap</span>
      <span>{micro.title} · {w.day}/{w.total}. nap · {formatDay(micro.start_date)} – {formatDay(micro.end_date)}</span>
    </>;
    const title=`${meso.title}: ${formatDay(meso.start_date)} – ${formatDay(meso.end_date)}. ${micro.title}: ${formatDay(micro.start_date)} – ${formatDay(micro.end_date)}. A mikrociklus jelenleg a mezociklus kezdetéhez igazított, legfeljebb 7 napos tervezési szakasz.`;
    return onOpenCycle ? <button key={meso.id} type="button" title={title} onClick={()=>onOpenCycle(meso)}>{content}</button> : <Link key={meso.id} href={`/training-periods/${meso.id}`} title={title}>{content}</Link>;
  })}</div>;
}
