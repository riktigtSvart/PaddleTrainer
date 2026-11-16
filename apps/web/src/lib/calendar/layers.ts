import { calendarEntries } from "./contracts";
import type { CalendarEvent } from "./contracts";
export type CalendarLayers = { availability: boolean; commitments: boolean; training: boolean; planned?: boolean; sessions?: boolean };
/** Filter source entities before pairing: either side remains independently visible. */
export function calendarLayerEntries(events: CalendarEvent[], layers: CalendarLayers) {
  return calendarEntries(events.filter((e) => e.kind === "availability" ? layers.availability : e.kind === "constraint" ? layers.commitments : layers.training && (e.kind === "planned" ? layers.planned !== false : layers.sessions !== false)));
}
