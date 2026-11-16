import type { Context, Data, Pattern, Snapshot } from "@/lib/initial-assessment/contracts";
import { availableExercises } from "@/lib/training-options/strength-catalog";

type Profile = { patterns: Pattern[]; favorites: Partial<Record<Pattern, string[]>> };
const general: Profile = { patterns: ["pull", "push", "knee", "hip", "core"], favorites: {} };
const profiles: Record<string, Profile> = {
  KAYAK: { patterns: ["pull", "core", "push", "hip", "knee"], favorites: { pull: ["seal_row_barbell", "seal_row_dumbbell", "seated_row"], push: ["barbell_benchpress", "db_benchpress"], core: ["pallof_press", "side_plank", "dead_bug"] } },
  CANOE: { patterns: ["pull", "core", "hip", "knee", "push"], favorites: { pull: ["dumbbell_row", "seated_row"], core: ["pallof_press", "side_plank"] } },
  ROWING: { patterns: ["knee", "hip", "pull", "core", "push"], favorites: { pull: ["seal_row_barbell", "seated_row"], hip: ["romanian_deadlift", "hip_thrust"] } },
  RUNNING: { patterns: ["knee", "hip", "core", "pull", "push"], favorites: { knee: ["step_up", "lunge", "squat"], hip: ["single_leg_rdl", "glute_bridge"] } },
  CYCLING: { patterns: ["knee", "hip", "core", "pull", "push"], favorites: { knee: ["leg_press", "goblet_squat", "squat"], hip: ["hip_thrust", "romanian_deadlift", "glute_bridge"] } },
  SWIMMING: { patterns: ["pull", "core", "push", "knee", "hip"], favorites: { pull: ["lat_pulldown", "assisted_pullup", "seated_row"], core: ["dead_bug", "plank"] } },
  WALKING: { patterns: ["knee", "hip", "core", "pull", "push"], favorites: { knee: ["wall_bars_supported_squat", "step_up", "squat"], hip: ["glute_bridge"] } },
  HIKING: { patterns: ["knee", "hip", "core", "pull", "push"], favorites: { knee: ["step_up", "lunge"], core: ["suitcase_carry", "farmers_carry", "side_plank"] } },
  XC_SKIING: { patterns: ["pull", "hip", "knee", "core", "push"], favorites: { pull: ["lat_pulldown", "seated_row"], hip: ["romanian_deadlift", "glute_bridge"] } },
  FOOTBALL: { patterns: ["knee", "hip", "core", "pull", "push"], favorites: { knee: ["lunge", "step_up"], hip: ["single_leg_rdl", "glute_bridge"] } },
  STRENGTH: general, GYMNASTICS: general, STRETCHING: general, OTHER: general,
};
export type Recommendation = { pattern: Pattern; entryId: string; exerciseId: string; label: string; reasons: string[]; needsReference: boolean; sportLabels: string[]; rank: number };
export function assessmentRecommendations(sources: Snapshot, data: Data, today: string, locationId?: string): Recommendation[] {
  const program = sources.programs.find((p) => p.reference.artifact_id === data.program_reference?.artifact_id);
  const primary = data.sports.filter((s) => s.role === "primary");
  // A general strength role does not replace the main sport's assessment profile.
  const main = primary.some((s) => s.sport_key !== "STRENGTH") ? primary.filter((s) => s.sport_key !== "STRENGTH") : primary;
  const all = [...main, ...data.sports.filter((s) => s.role === "secondary" && s.sport_key !== "STRENGTH")];
  if (!all.length) all.push({ sport_key: "OTHER", role: "primary", discipline: "", goal: "", notes: "" });
  const selected = all.map((s) => profiles[s.sport_key] ?? general);
  const sportLabels = main.map((s) => {
    const label = sources.registry.sports.find((v) => v.key === s.sport_key)?.label ?? s.sport_key;
    return s.discipline ? `${label} · ${s.discipline}` : label;
  });
  const result: Recommendation[] = [];
  for (const group of sources.registry.patterns) {
    const candidates = data.exercises.filter((e) => e.pattern === group.key && e.exercise_id &&
      (!locationId || e.location_id === locationId) && ["independent", "regular"].includes(e.familiarity) && e.comfort === "none" &&
      !e.sets.some((s) => ["pain", "discomfort"].includes(s.symptoms)));
    const available = candidates.filter((e) => {
      const place = sources.locations.find((p) => p.id === e.location_id && !p.archived && p.sports.includes("STRENGTH"));
      return place && availableExercises(sources.catalog, place).some((x) => x.id === e.exercise_id);
    });
    const hasReference = (e: Data["exercises"][number]) => e.performed_on !== null && e.performed_on <= today &&
      (Date.parse(today + "T00:00:00Z") - Date.parse(e.performed_on + "T00:00:00Z")) / 86400000 <= sources.registry.history_days &&
      e.sets.some((s) => (s.repetitions !== null && s.repetitions > 0 || s.hold_seconds !== null && Number(s.hold_seconds) > 0) && s.technique === "stable" && s.symptoms === "none");
    const favorite = (id: string) => Math.min(...selected.map((p, i) => {
      const at = p.favorites[group.key]?.indexOf(id) ?? -1;
      return at < 0 ? 100 : at + i * 10;
    }));
    available.sort((a, b) => Number(hasReference(b)) - Number(hasReference(a)) || favorite(a.exercise_id!) - favorite(b.exercise_id!) || a.id.localeCompare(b.id));
    const chosen = available[0];
    if (!chosen) continue;
    const known = hasReference(chosen);
    const rank = Math.min(...selected.map((p, i) => p.patterns.indexOf(group.key) + i * 5));
    const reasons = [
      sportLabels.length ? `Sportági alap: ${sportLabels.join("; ")}.` : "Általános erőnléti kiindulópont.",
      "Ismert, panaszmentes gyakorlat, a helyszínen elvégezhető.",
      known ? "Van saját referenciád: azonos változattal követhető a teljesítés változása." : "Ehhez a területhez most friss saját referencia szerezhető.",
    ];
    if (program) reasons.push(`Felkészülés: ${program.title}.`);
    if (data.sports.some((s) => s.role === "secondary" && s.sport_key !== "STRENGTH")) reasons.push("A kiegészítő sportágak területi hangsúlyai is szerepelnek a sorrendben.");
    result.push({ pattern: group.key, entryId: chosen.id, exerciseId: chosen.exercise_id!, label: sources.catalog.exercises.find((v) => v.id === chosen.exercise_id)!.label,
      reasons, needsReference: !known, sportLabels, rank });
  }
  return result.sort((a, b) => Number(b.needsReference) - Number(a.needsReference) || a.rank - b.rank || a.pattern.localeCompare(b.pattern));
}
export function recommendationsForContext(c: Context, locationId?: string) {
  return c.data ? assessmentRecommendations(c.sources, c.data, c.local_today, locationId) : [];
}
