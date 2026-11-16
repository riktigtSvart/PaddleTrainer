import { addDays, dateDistance } from "./contracts";
import type { Period } from "./contracts";

export type CalendarCycle = { id: string; parent_id: string; title: string; kind: "meso" | "micro"; ordinal: number; start_date: string; end_date: string };
/** The current planner partitions saved mesocycles from their own civil start
 * into seven-day blocks, with a possibly shorter final block. Not ISO weeks. */
export function calendarCycles(periods: Period[]): CalendarCycle[] {
  const result: CalendarCycle[] = [];
  for (const p of periods.filter(p => p.period_type === "MESOCYCLE" && p.start_date <= p.end_date)) {
    result.push({ ...p, parent_id: p.id, kind: "meso", ordinal: 0 });
    const count = Math.ceil((dateDistance(p.start_date, p.end_date) + 1) / 7);
    for (let i = 0; i < count; i++) result.push({ id: `${p.id}:${i + 1}`, parent_id: p.id, kind: "micro", ordinal: i + 1,
      title: `${i + 1}. mikrociklus`, start_date: addDays(p.start_date, i * 7), end_date: [addDays(p.start_date, i * 7 + 6), p.end_date].sort()[0] });
  }
  return result.sort((a, b) => a.start_date.localeCompare(b.start_date) || a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
}
export function cycleBoundaries(cycles: CalendarCycle[], date: string) {
  return cycles.flatMap(cycle => [
    ...(cycle.start_date === date ? [{ cycle, edge: "start" as const }] : []),
    ...(cycle.end_date === date ? [{ cycle, edge: "end" as const }] : []),
  ]);
}
export function cycleProgress(cycle: CalendarCycle, date: string) {
  return { day: dateDistance(cycle.start_date, date) + 1, total: dateDistance(cycle.start_date, cycle.end_date) + 1 };
}
export function calendarWeekStart(anchor:string,periods:Period[],mode:"monday"|"microcycle") {
  const active=periods.filter(p=>p.period_type==="MESOCYCLE"&&p.start_date<=anchor&&anchor<=p.end_date);
  if(mode==="monday"||active.length!==1)return {weekday:1,matched:mode==="monday"};
  return {weekday:new Date(active[0].start_date+"T12:00:00Z").getUTCDay(),matched:true};
}
