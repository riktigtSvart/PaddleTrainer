import { addDays, canonical } from "./contracts";
import type { Candidate, TrainingReview } from "./training-plan";

export type PlanPeriod = {
  id: string;
  period_type: string;
  title: string;
  start_date: string;
  end_date: string;
};
export type PlanEntry = {
  key: string;
  date: string;
  title: string;
  sport: string;
  duration_sec: number | null;
  description: string;
  blocks: Candidate["blocks"];
  location?: string;
  candidate_key?: string;
  kind: "proposal" | "planned" | "protected";
  estimated: boolean;
};
export const planSportLabels: Record<string, string> = {
  KAYAK: "Kajak",
  RUNNING: "Futás",
  SWIMMING: "Úszás",
  STRENGTH: "Kondi",
  CYCLING: "Kerékpár",
  OTHER: "Mozgás",
};
export const planBlockLabels: Record<string, string> = {
  WARMUP: "Bemelegítés",
  WORK: "Fő rész",
  COOLDOWN: "Levezetés",
  REST: "Pihenő",
  RECOVERY: "Regeneráció",
};
export function localDay(zone: string, instant = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(instant);
}
export function rollingDates(first: string) {
  return Array.from({ length: 7 }, (_, i) => addDays(first, i));
}
export function detailedPeriods(periods: PlanPeriod[], first: string) {
  return periods
    .filter((p) => p.period_type === "MESOCYCLE" && p.end_date >= first)
    .sort(
      (a, b) =>
        a.start_date.localeCompare(b.start_date) || a.id.localeCompare(b.id),
    )
    .slice(0, 2);
}
export function detailedEnd(periods: PlanPeriod[], first: string) {
  const end =
    detailedPeriods(periods, first).at(-1)?.end_date ?? addDays(first, 27);
  return end > addDays(first, 365) ? addDays(first, 365) : end;
}
export function entriesOnDay(
  review: TrainingReview,
  date: string,
): PlanEntry[] {
  const proposed = review.result.proposals.filter((c) => c.date === date),
    keys = new Set(proposed.map((c) => c.candidate_key));
  const entries: PlanEntry[] = proposed.map((c) => ({
    key: c.candidate_key,
    candidate_key: c.candidate_key,
    date,
    title: c.title,
    sport: c.sport ?? "OTHER",
    duration_sec: c.duration_sec,
    description: c.description,
    blocks: c.blocks,
    location: c.location,
    estimated: false,
    kind: review.plan_snapshots.some(
      (p) =>
        p.candidate_key === c.candidate_key &&
        review.result.keep.includes(p.workout.id),
    )
      ? "planned"
      : "proposal",
  }));
  for (const snapshot of review.plan_snapshots) {
    const w = snapshot.workout,
      day = w.planned_start_time
        ? localDay(review.timezone_name, new Date(w.planned_start_time))
        : w.date;
    if (
      day !== date ||
      w.status === "CANCELLED" ||
      review.result.cancel.includes(w.id) ||
      (snapshot.candidate_key && keys.has(snapshot.candidate_key))
    )
      continue;
    entries.push({
      key: w.id,
      date,
      title: w.title,
      sport: w.sport ?? "OTHER",
      duration_sec:
        w.duration_sec ?? snapshot.duration_estimate?.duration_sec ?? null,
      description: w.description ?? "",
      blocks: w.blocks,
      estimated: w.duration_sec == null && !!snapshot.duration_estimate,
      kind: review.result.protected_workout_ids.includes(w.id)
        ? "protected"
        : "planned",
    });
  }
  return entries;
}
export function dayReason(
  review: TrainingReview,
  date: string,
): { label: string; reason: string } {
  if (date < review.start_date || date > review.end_date)
    return {
      label: "Tervhatáron túl",
      reason:
        "Ez a nap nem szerepel a most megnyitott részletes felülvizsgálatban.",
    };
  const code = review.result.days_without_proposal.find(
    (day) => day.date === date,
  )?.reason;
  const state = review.inputs?.days?.find(
    (day) => day.date === date,
  )?.availability_state;
  if (state === "declared_unavailable")
    return {
      label: "Nem érsz rá",
      reason:
        "A mentett időbeosztás szerint ezen a napon nincs edzéslehetőség.",
    };
  const issues =
    review.result.preparation?.selection_issues.find((day) => day.date === date)
      ?.codes ?? [];
  if (
    code === "NO_SUPPORTED_SAMPLE_FITS" &&
    issues.length > 0 &&
    issues.every((issue) =>
      ["MINIMUM_SPACING", "ROLLING_BUDGET_REVIEW"].includes(issue),
    )
  )
    return {
      label: "Pihenőnap",
      reason:
        "Az edzések közti időköz vagy a gördülő heti keret miatt nem kerül ide új edzés.",
    };
  return {
    label: "Pontosítandó",
    reason: code ?? "Ehhez a naphoz még nincs ellenőrzött edzésjavaslat.",
  };
}
export function reviewChanges(before: TrainingReview, after: TrainingReview) {
  const dates = [
    ...new Set([
      ...before.result.proposals.map((c) => c.date),
      ...after.result.proposals.map((c) => c.date),
    ]),
  ].sort();
  return dates.flatMap((date) => {
    const previous = entriesOnDay(before, date),
      next = entriesOnDay(after, date);
    const signature = (entries: PlanEntry[]) =>
      canonical(
        entries
          .map((e) => [
            e.title,
            e.duration_sec,
            e.location ?? "",
            e.candidate_key ?? e.key,
          ])
          .sort(),
      );
    return signature(previous) === signature(next)
      ? []
      : [
          {
            date,
            before:
              previous.map((e) => e.title).join(" + ") || "Nincs új javaslat",
            after: next.map((e) => e.title).join(" + ") || "Nincs új javaslat",
          },
        ];
  });
}
