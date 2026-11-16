import { formatDay, requireValue, requireDay } from "./contracts";
import type { CalendarEvent } from "./contracts";
import type { SlotChange } from "./slot-transform";
export type CalendarTarget = { date: string; event: CalendarEvent | null; change?: SlotChange; x: number; y: number };
export function clockSlot(date: string, clientY: number, top: number, height: number, fromHour: number, toHour: number): SlotChange {
  requireDay(date);
  requireValue([clientY, top, height, fromHour, toHour].every(Number.isFinite) && height > 0 && fromHour >= 0 && toHour > fromHour && toHour <= 24);
  const start = Math.min(1435, Math.max(0, Math.floor((fromHour * 60 + Math.max(0, Math.min(1, (clientY - top) / height)) * (toHour - fromHour) * 60) / 5) * 5));
  const clock = (minute: number) => `${String(Math.floor((minute % 1440) / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
  return { date, start_time: clock(start), end_time: clock(start + 60), ends_next_day: start + 60 >= 1440 };
}
export const interactionHint = (date: string) => `${formatDay(date)} · Dupla kattintás: új idősáv. Jobb kattintás vagy menügomb: további műveletek.`;
export function frameHeight(viewportHeight: number, topAtRest: number, minimum = 230) {
  return Math.max(minimum, Math.floor(viewportHeight - topAtRest - 12));
}
