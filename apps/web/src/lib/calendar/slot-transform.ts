import { addDays, requireValue } from "./contracts";
import type { CalendarEvent } from "./contracts";

export type DragMode = "move" | "start" | "end";
export type SlotChange = { date: string; start_time: string; end_time: string; ends_next_day: boolean };
const minutes = (clock: string) => Number(clock.slice(0, 2)) * 60 + Number(clock.slice(3));
const clock = (n: number) => `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
export function canTransform(event: CalendarEvent) {
  return (event.kind === "constraint" || event.kind === "availability") && !!event.start && !!event.end &&
    (!!event.occurrence && !event.occurrence.issue || !!event.window) && Date.parse(event.end) > Date.parse(event.start);
}
export function minuteDelta(y: number, initial: number, height: number, hours: number) {
  requireValue([y, initial, height, hours].every(Number.isFinite) && height > 0 && hours > 0);
  return Math.round((y - initial) / height * hours * 60 / 5) * 5;
}
export function transformSlot(event: CalendarEvent, delta: number, days: number, mode: DragMode): SlotChange {
  requireValue(canTransform(event), "Csak megadott napirendi idősáv mozgatható.");
  requireValue(Number.isInteger(delta) && delta % 5 === 0 && Number.isInteger(days) && ["move", "start", "end"].includes(mode));
  const d = event.occurrence?.details ?? event.window!;
  const a = minutes(d.start_time), b = minutes(d.end_time) + (d.ends_next_day ? 1440 : 0);
  let first = a, last = b;
  if (mode === "move") { first += delta; last += delta; }
  else if (mode === "start") first += delta;
  else last += delta;
  requireValue(last > first && last - first <= 1440, "Az idősáv hossza 0 percnél több és legfeljebb 24 óra lehet.");
  const shift = Math.floor(first / 1440);
  first -= shift * 1440; last -= shift * 1440;
  const date = addDays(event.occurrence?.source_date ?? event.date, shift + (mode === "move" ? days : 0));
  requireValue(date >= "1900-01-01" && date <= "2100-12-31", "Az időpont a támogatott naptáron kívülre esik.");
  return { date, start_time: clock(first), end_time: clock(last % 1440), ends_next_day: last >= 1440 };
}
