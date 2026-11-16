import { addDays } from "./contracts";
import type { PlanningContext } from "./contracts";
import type { TrainingReview } from "@/lib/planning-cycles/training-plan";

export type FocusWorkout = PlanningContext & { id: string };

export function alternativeRange(review: TrainingReview | null, target: FocusWorkout, today: string) {
  const first = review && review.start_date >= today && review.start_date <= target.date ? review.start_date : today;
  const last = review && review.end_date >= target.date ? review.end_date : target.date > addDays(first, 27) ? target.date : addDays(first, 27);
  return { first, last };
}

/** Match the clicked immutable prescription, never today's date or a title. */
export function focusedChoices(review: TrainingReview | null, target: FocusWorkout) {
  if (!target.replaceable || !review || review.program_id !== target.program_reference.artifact_id ||
      review.program_reference.content_hash !== target.program_reference.content_hash ||
      target.date < review.start_date || target.date > review.end_date) return null;
  const snapshot = review.plan_snapshots.find(p => p.workout.id === target.id);
  if (!snapshot?.replaceable || snapshot.workout_hash !== target.workout_hash ||
      snapshot.candidate_key !== target.candidate_key || snapshot.workout.date !== target.date ||
      review.result.protected_workout_ids.includes(target.id)) return null;
  return { snapshot, group: review.result.alternatives?.find(g => g.date === target.date) ?? null };
}

/** All calendar mutations, including changes outside the clicked day. */
export function alternativeChanges(review: TrainingReview) {
  const cancelled = review.plan_snapshots.filter(p => review.result.cancel.includes(p.workout.id));
  const dates = [...new Set([...cancelled.map(p => p.workout.date!), ...review.result.create.map(c => c.date)])].sort();
  return dates.map(date => ({ date,
    before: cancelled.filter(p => p.workout.date === date).map(p => p.workout.title).join("; ") || "Nincs edzés",
    after: review.result.create.filter(c => c.date === date).map(c => c.title).join("; ") || "Pihenőnap",
  }));
}

export function alternativeLabel(context: PlanningContext | undefined): string | null {
  if (!context?.replaceable) return null;
  if(context.alternative_kinds){const k=context.alternative_kinds;if(k.different_workouts_count!==null)return `Más edzések: ${k.different_workouts_count} · A jelenlegi edzés további időpontjai/helyszínei: ${k.same_workout_schedule_count} · A legutóbbi felülvizsgálatban`;}
  return context.alternatives_count === null
    ? "Alternatív edzések: friss ellenőrzés szükséges"
    : `Alternatív edzések: ${context.alternatives_count} a legutóbbi felülvizsgálatban`;
}
