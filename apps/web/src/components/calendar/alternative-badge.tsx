import type { CalendarEvent } from "@/lib/calendar/contracts";
import { alternativeLabel } from "@/lib/calendar/training-alternatives";

export default function AlternativeBadge({ event }: { event: CalendarEvent }) {
  const text = alternativeLabel(event.planningContext);
  if (!text || event.kind !== "planned") return null;
  const count = event.planningContext!.alternatives_count;
  const kinds=event.planningContext!.alternative_kinds;
  return <small className={`pt-alternative-badge${count === 0 ? " is-empty" : ""}`} title={text} aria-label={text}>↔ {kinds?.different_workouts_count??count??"?"}{kinds?.same_workout_schedule_count!==null&&kinds?.same_workout_schedule_count!==undefined?` · ◷ ${kinds.same_workout_schedule_count}`:""}</small>;
}
