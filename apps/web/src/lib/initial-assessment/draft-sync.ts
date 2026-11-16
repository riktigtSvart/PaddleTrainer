import { canonical, day, object } from "@/lib/planning-cycles/contracts";
import { readDraft } from "./contracts";
import type { Data } from "./contracts";
// Recover only the date conflict left by an older merge. Re-run the complete
// draft validator, including owner and parent checks, before accepting it.
export function restoreAssessmentDraft(raw: string, owner: string, saved: Data | null, today?: string) {
  try { return { draft: readDraft(raw, owner), recovered: false }; }
  catch (original) {
    try {
      const value = object(JSON.parse(raw)), data = object(value.data);
      let validReview = typeof data.assessment_date === "string";
      try { if (validReview) day(data.assessment_date as string); } catch { validReview = false; }
      if (!validReview && !today) throw original;
      let reviewedOn: string;
      if (today) {
        day(today);
        const observations = [data.last_strength_date,
          ...(Array.isArray(data.exercises) ? data.exercises.map(e => object(e).performed_on) : []),
          ...(Array.isArray(data.sport_references) ? data.sport_references.map(e => object(e).performed_on) : [])];
        const dates = [validReview ? data.assessment_date as string : today, ...(saved ? [saved.assessment_date] : [])];
        for (const date of observations) if (date !== null && date !== undefined) {
          if (typeof date !== "string") throw original;
          day(date); dates.push(date);
        }
        reviewedOn = dates.sort().at(-1)!;
        if (reviewedOn > today || (validReview && reviewedOn <= (data.assessment_date as string))) throw original;
      } else {
        if (!saved || (data.assessment_date as string) >= saved.assessment_date) throw original;
        reviewedOn = saved.assessment_date;
      }
      const candidate = { ...value, data: { ...data, assessment_date: reviewedOn } };
      return { draft: readDraft(JSON.stringify(candidate), owner), recovered: true };
    } catch { throw original; }
  }
}
// Rebase unfinished answers onto a newly saved result. Independent set IDs and
// source rows are retained; scalar conflicts stay visible as the local answer.
export function mergeAssessmentAnswers(base: Data | null, local: Data, saved: Data): Data {
  function merge(before: unknown, draft: unknown, fresh: unknown): unknown {
    if (canonical(draft ?? null) === canonical(before ?? null)) return structuredClone(fresh);
    if (Array.isArray(draft) && Array.isArray(fresh)) {
      const old = Array.isArray(before) ? before : [];
      const key = [...draft, ...fresh].every(v => v && typeof v === "object" && typeof v.id === "string") ? "id"
        : [...draft, ...fresh].every(v => v && typeof v === "object" && typeof v.sport_key === "string") ? "sport_key" : null;
      if (!key) return structuredClone(draft);
      const previous = new Map(old.map(v => [v[key], v])), edits = new Map(draft.map(v => [v[key], v]));
      const rows = fresh.flatMap(row => {
        const edited = edits.get(row[key]), prior = previous.get(row[key]);
        if (!edited) return prior && canonical(row) === canonical(prior) ? [] : [structuredClone(row)];
        return [merge(prior, edited, row)];
      });
      const freshIds = new Set(fresh.map(v => v[key]));
      for (const row of draft) if (!freshIds.has(row[key]) && (!previous.has(row[key]) || canonical(row) !== canonical(previous.get(row[key])))) rows.push(structuredClone(row));
      return rows;
    }
    if (draft && fresh && typeof draft === "object" && typeof fresh === "object" && !Array.isArray(draft) && !Array.isArray(fresh)) {
      const old = (before ?? {}) as Record<string, unknown>, a = draft as Record<string, unknown>, b = fresh as Record<string, unknown>;
      return Object.fromEntries([...new Set([...Object.keys(a), ...Object.keys(b)])].map(key => [key, merge(old[key], a[key], b[key])]));
    }
    return structuredClone(draft);
  }
  const result = merge(base, local, saved) as Data;
  // Sets share an exercise's date, side and apparatus. Concurrent results from
  // different occasions must remain separate rows, rather than assigning a
  // newer set to an older date or another exercise variant.
  const occasion = (e: Data["exercises"][number]) => canonical([e.exercise_id, e.location_id, e.performed_on, e.side, e.machine_note]);
  const measurement = (e: Data["exercises"][number]) => canonical([occasion(e), e.sets]);
  for (const edited of local.exercises) {
    const before = base?.exercises.find(e => e.id === edited.id), fresh = saved.exercises.find(e => e.id === edited.id);
    if (!fresh || !edited.sets.length || !fresh.sets.length || occasion(edited) === occasion(fresh) ||
      (before && (measurement(edited) === measurement(before) || measurement(fresh) === measurement(before)))) continue;
    const index = result.exercises.findIndex(e => e.id === edited.id);
    if (index < 0) continue;
    const combined = result.exercises[index];
    result.exercises[index] = { ...combined, exercise_id: fresh.exercise_id, location_id: fresh.location_id,
      performed_on: fresh.performed_on, side: fresh.side, machine_note: fresh.machine_note, sets: structuredClone(fresh.sets) };
    result.exercises.push({ ...structuredClone(edited), id: crypto.randomUUID() });
  }
  // The newer saved assessment already contains the real measurement days.
  // An older edited review day must not make those retained results unsavable.
  if (result.assessment_date < saved.assessment_date) result.assessment_date = saved.assessment_date;
  return result;
}
