import {
  formatDuration,
  formatNumber,
  goalLabels,
  localParts,
} from "./contracts";
import type { CalendarEvent, Feed } from "./contracts";
import { estimateLabel } from "./duration-estimate";

export function eventHref(event: CalendarEvent): string | null {
  return event.kind === "session"
    ? `/sessions/${event.entityId}`
    : event.kind === "planned"
      ? `/workouts/${event.entityId}`
      : null;
}
/** Only display values already present in the calendar response. */
export function previewLines(event: CalendarEvent, feed: Feed): string[] {
  const actual =
    event.kind === "session"
      ? feed.sessions.find((s) => s.id === event.entityId)
      : null;
  const plan =
    event.kind === "planned"
      ? feed.planned.find((p) => p.id === event.entityId)
      : null;
  const lines = [
    event.kind === "session"
      ? event.linkedPlanId
        ? "Tervhez kapcsolt teljesítés"
        : "Teljesített"
      : "Tervezett",
  ];
  if (event.start)
    lines.push(localParts(event.start, feed.timezone_name).clock);
  if (event.durationEstimate) lines.push(estimateLabel(event.durationEstimate));
  else if (event.duration !== null) lines.push(formatDuration(event.duration));
  const distance = actual?.distance_m ?? plan?.distance_m;
  if (distance !== null && distance !== undefined)
    lines.push(formatNumber(distance / 1000, "km"));
  if (event.goal) lines.push(`Cél: ${goalLabels[event.goal] ?? event.goal}`);
  if (actual?.avg_hr !== null && actual?.avg_hr !== undefined)
    lines.push(formatNumber(actual.avg_hr, "bpm") + " átlagpulzus");
  if (actual?.calories !== null && actual?.calories !== undefined)
    lines.push(formatNumber(actual.calories, "kcal"));
  if (event.pairedPlan) lines.push(`Terv: ${event.pairedPlan.title}`);
  if (event.conflict)
    lines.push(
      event.conflict === "review" ? "Időpont tisztázandó" : "Időpont ütközik",
    );
  return lines;
}
