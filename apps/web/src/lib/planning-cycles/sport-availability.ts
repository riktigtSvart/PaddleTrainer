import { object } from "./contracts";
import { canonical, day } from "./contracts";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { families } from "./prescription-context";
export type GoalCoverage = { mesocycle_id: string; capability_key: string; role: string; start_date: string; end_date: string; planned_sessions: number; candidate_days: number; template_sports: string[]; status: "represented" | "available_unselected" | "unavailable" | "unsupported"; reasons: string[] };
export type SportAvailability = {
  schema_version: "training-sport-availability-v0.1" | "training-sport-availability-v0.2" | "training-sport-availability-v0.3";
  goal_coverage?: GoalCoverage[];
  weekly_budget?: {mode: "declared_current_training" | "observed_covered_weeks" | "declared_and_product_defaults"; max_sessions_per_7_days: number; max_minutes_per_7_days: number; baseline_status: "used" | "stale" | "not_provided"};
  sports: { sport: string; supported: boolean; opportunity_days: number; daylight_days: number; candidate_days: number; planned_sessions: number; reasons: string[] }[];
};
export function readSportAvailability(raw: unknown): SportAvailability {
  const v = object(raw), seen = new Set();
  const coverage = v.schema_version === "training-sport-availability-v0.3";
  const modern = coverage || v.schema_version === "training-sport-availability-v0.2";
  const supported = new Set(["KAYAK", "RUNNING", "STRENGTH", ...(modern ? ["SWIMMING"] : [])]);
  const invalid = () => Error("A sportágankénti tervezési indokok nem ellenőrizhetők.");
  if ((!modern && v.schema_version !== "training-sport-availability-v0.1") || Object.keys(v).sort().join("|") !== (coverage ? "goal_coverage|schema_version|sports|weekly_budget" : modern ? "schema_version|sports|weekly_budget" : "schema_version|sports") || !Array.isArray(v.sports) || v.sports.length > 7) throw invalid();
  if (modern) {
    const b = object(v.weekly_budget);
    if (Object.keys(b).sort().join("|") !== "baseline_status|max_minutes_per_7_days|max_sessions_per_7_days|mode" ||
      !["declared_current_training", "observed_covered_weeks", "declared_and_product_defaults"].includes(String(b.mode)) ||
      !["used", "stale", "not_provided"].includes(String(b.baseline_status)) ||
      !Number.isInteger(b.max_sessions_per_7_days) || Number(b.max_sessions_per_7_days) < 0 || Number(b.max_sessions_per_7_days) > 7 ||
      !Number.isInteger(b.max_minutes_per_7_days) || Number(b.max_minutes_per_7_days) < 0 || Number(b.max_minutes_per_7_days) > 10080 ||
      (b.mode === "declared_current_training") !== (b.baseline_status === "used")) throw invalid();
  }
  for (const item of v.sports) {
    const r = object(item);
    if (Object.keys(r).sort().join("|") !== "candidate_days|daylight_days|opportunity_days|planned_sessions|reasons|sport|supported" ||
        !["KAYAK", "RUNNING", "STRENGTH", "SWIMMING", "CYCLING", "GYMNASTICS", "STRETCHING"].includes(String(r.sport)) || seen.has(r.sport) ||
        r.supported !== supported.has(String(r.sport)) ||
        ![r.opportunity_days, r.daylight_days, r.candidate_days, r.planned_sessions].every(n => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 366) ||
        Number(r.daylight_days) > Number(r.opportunity_days) || Number(r.candidate_days) > Number(r.daylight_days) || Number(r.planned_sessions) > Number(r.candidate_days) ||
        !Array.isArray(r.reasons) || r.reasons.length > 128 || new Set(r.reasons).size !== r.reasons.length || r.reasons.some(c => typeof c !== "string" || !/^[A-Z][A-Z0-9_]{0,99}$/.test(c)) ||
        (!r.supported && (r.candidate_days !== 0 || r.planned_sessions !== 0 || !r.reasons.includes("SPORT_TEMPLATE_NOT_SUPPORTED")))) throw invalid();
    seen.add(r.sport);
  }
  if (coverage) {
    if (!Array.isArray(v.goal_coverage) || v.goal_coverage.length > 16384) throw invalid();
    const goals = new Set();
    for (const raw of v.goal_coverage) {
      const r = object(raw), id = `${r.mesocycle_id}:${r.capability_key}:${r.role}`;
      if (Object.keys(r).sort().join("|") !== "candidate_days|capability_key|end_date|mesocycle_id|planned_sessions|reasons|role|start_date|status|template_sports" ||
        typeof r.mesocycle_id !== "string" || !/^[a-f0-9-]{36}$/.test(r.mesocycle_id) || typeof r.capability_key !== "string" || !Object.hasOwn(capabilityLabels, r.capability_key) ||
        !["primary_development", "secondary_development", "maintenance"].includes(String(r.role)) || goals.has(id) ||
        typeof r.start_date !== "string" || typeof r.end_date !== "string" || r.start_date > r.end_date ||
        ![r.planned_sessions, r.candidate_days].every(n => Number.isInteger(n) && Number(n) >= 0 && Number(n) <= 366) ||
        !["represented", "available_unselected", "unavailable", "unsupported"].includes(String(r.status)) ||
        !Array.isArray(r.template_sports) || new Set(r.template_sports).size !== r.template_sports.length || r.template_sports.some(s => !supported.has(String(s))) ||
        !Array.isArray(r.reasons) || r.reasons.some(c => typeof c !== "string" || !/^[A-Z][A-Z0-9_]{0,99}$/.test(c)) ||
        r.status !== (Number(r.planned_sessions) > 0 ? "represented" : Number(r.candidate_days) > 0 ? "available_unselected" : r.template_sports.length ? "unavailable" : "unsupported") ||
        (r.status === "represented" && r.reasons.length > 0) || (r.status !== "represented" && r.reasons.length === 0)) throw invalid();
      day(r.start_date); day(r.end_date); goals.add(id);
    }
  }
  return v as unknown as SportAvailability;
}
export function validateSportAvailability(result: Record<string, unknown>, inputs?: Record<string, unknown>) {
  if (result.preparation === undefined) return;
  const preparation = object(result.preparation);
  if (preparation.sport_availability === undefined) return;
  const report = readSportAvailability(preparation.sport_availability);
  if (["training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy ?? {}).version)) && !report.goal_coverage) throw Error("A terv célonkénti ellenőrzése hiányzik.");
  if (report.weekly_budget) {
    const budget = object(object(result.prescription_context).starting_budget);
    if (Object.entries(report.weekly_budget).some(([key,value]) => budget[key] !== value)) throw Error("A heti keret összegzése eltér a terhelési forrástól.");
  }
  const proposals = (result.proposals as unknown[]).map(object);
  const alternatives = ((result.alternatives ?? []) as unknown[]).map(object);
  for (const row of report.sports) {
    const dates = new Set(alternatives.filter(g => (g.candidates as unknown[]).map(object).some(c => c.sport === row.sport)).map(g => g.date));
    if (row.planned_sessions !== proposals.filter(c => c.sport === row.sport).length || row.candidate_days !== dates.size) throw Error("A sportági összegzés eltér a tervjavaslatoktól.");
  }
  if (report.goal_coverage && inputs) {
    const scopes = new Map<string, { period: string; key: string; role: string; dates: string[] }>();
    for (const raw of inputs.days as unknown[]) {
      const d = object(raw); if (!d.mesocycle_id) continue;
      for (const rawRole of d.capability_roles as unknown[]) {
        const r = object(rawRole); if (r.role === "permitted_decline") continue;
        const id = `${d.mesocycle_id}:${r.capability_key}:${r.role}`;
        if (!scopes.has(id)) scopes.set(id, {period:String(d.mesocycle_id), key:String(r.capability_key), role:String(r.role), dates:[]});
        scopes.get(id)!.dates.push(String(d.date));
      }
    }
    if (scopes.size !== report.goal_coverage.length) throw Error("A célonkénti összegzés nem teljes.");
    for (const r of report.goal_coverage) {
      const s = scopes.get(`${r.mesocycle_id}:${r.capability_key}:${r.role}`); if (!s) throw Error("Ismeretlen mezociklus vagy cél az összegzésben.");
      const templates = Object.entries({...families, SWIM_EASY_AEROBIC:{sport:"SWIMMING",capabilities:["PERIPHERAL_OXIDATIVE_CAPACITY"]}}).filter(([,f]) => f.capabilities.includes(s.key));
      const keys = templates.map(([key]) => key), sports = [...new Set(templates.map(([,f]) => f.sport))].sort();
      const dates = new Set(alternatives.filter(g => s.dates.includes(String(g.date)) && (g.candidates as unknown[]).map(object).some(c => c.training_period_id === s.period && keys.includes(String(c.template_key)))).map(g => g.date));
      const count = proposals.filter(c => c.training_period_id === s.period && s.dates.includes(String(c.date)) && c.capability_key === s.key && c.role === s.role).length;
      if (r.start_date !== [...s.dates].sort()[0] || r.end_date !== [...s.dates].sort().at(-1) || r.candidate_days !== dates.size || r.planned_sessions !== count || canonical(r.template_sports) !== canonical(sports)) throw Error("A célok lefedettsége eltér az ellenőrzött tervtől.");
      const reasons = count ? [] : dates.size ? ["GOAL_NOT_SELECTED"] : [...new Set(report.sports.filter(row => sports.includes(row.sport)).flatMap(row => row.reasons))].sort();
      if (!count && !reasons.length) reasons.push("CAPABILITY_NOT_SUPPORTED_BY_AVAILABLE_SPORT");
      if (canonical(r.reasons) !== canonical(reasons)) throw Error("A cél kimaradásának indoka eltér a tervezési forrástól.");
    }
  }
}
