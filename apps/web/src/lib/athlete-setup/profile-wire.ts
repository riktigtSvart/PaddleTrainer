// The explicit serialization rules of schemas/athlete_setup.py. This only
// supplies declared defaults, strips declared text fields, and omits the nullable
// fields that the API's model serializers omit. Numbers and identities stay exact.
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("Hiányos személyesadat-kérés.");
  return value as Record<string, unknown>;
}
function texts(value: Record<string, unknown>, keys: string[]) {
  for (const key of keys) if (typeof value[key] === "string") value[key] = value[key].trim();
}
function rows(value: unknown, transform: (row: Record<string, unknown>) => Record<string, unknown>) {
  if (!Array.isArray(value)) return value;
  return value.map((row) => transform({ ...record(row) }));
}
export function profileWireData(input: unknown): Record<string, unknown> {
  const data: Record<string, unknown> = {
    birth_date: null, sex_reference: "unknown", competition_category: "", target_sport: "",
    sport_history_status: "unknown", sport_history: [], constraint_status: "unknown", constraints: [],
    participation: "unknown", interruption: "unknown", last_training_date: null,
    typical_days_per_week: null, typical_minutes_per_week: null, resources: [],
    duration_doubling_slowdown_pct: null, accessibility_needs: "", recovery_notes: "",
    manual_observations: [], source_window: null, source_selections: [], ...record(input),
  };
  texts(data, ["competition_category", "target_sport", "accessibility_needs", "recovery_notes"]);
  if (Array.isArray(data.resources)) data.resources = data.resources.map((v) => typeof v === "string" ? v.trim() : v);
  for (const key of ["body_mass_kg", "height_cm", "body_measurements_recorded_on", "body_mass_recorded_on"]) if (data[key] == null) delete data[key];
  data.sport_history = rows(data.sport_history, (row) => {
    const result: Record<string, unknown> = { discipline: "", start_year: null, last_active_date: null, usual_sessions_per_week: null, notes: "", ...row };
    texts(result, ["sport", "discipline", "notes"]);
    for (const key of ["role", "current_level", "planning", "performances"]) if (result[key] == null) delete result[key];
    if (result.planning) {
      const planning = { ...record(result.planning) };
      if (Array.isArray(planning.supported_sports)) planning.supported_sports = planning.supported_sports.map((v) => typeof v === "string" ? v.trim() : v);
      result.planning = planning;
    }
    if (result.performances) result.performances = rows(result.performances, (performance) => { texts(performance, ["conditions", "exercise"]); for (const k of ["protocol", "distance_m", "time", "exercise", "repetitions", "load_kind", "load_kg", "load_basis"]) if (performance[k] == null) delete performance[k]; return performance; });
    return result;
  });
  data.constraints = rows(data.constraints, (row) => {
    const result: Record<string, unknown> = { affected_area: "", restricted_activities: [], adaptations: "", professional_guidance: "", starts_on: null, review_on: null, ...row };
    texts(result, ["key", "affected_area", "adaptations", "professional_guidance"]);
    if (Array.isArray(result.restricted_activities)) result.restricted_activities = result.restricted_activities.map((v) => typeof v === "string" ? v.trim() : v);
    return result;
  });
  data.manual_observations = rows(data.manual_observations, (row) => {
    const result: Record<string, unknown> = { aggregation: "single", sport: "", protocol: "", conditions: "", supersedes_candidate_id: null, ...row };
    texts(result, ["sport", "protocol", "conditions"]);
    return result;
  });
  return data;
}
export function profileWireProposal(input: unknown) {
  const proposal = record(input);
  return { ...proposal, data: profileWireData(proposal.data) };
}
