import { addDays } from "./contracts";
import type { PlanningInputs } from "./inputs";
import type { GoalRole, Period, Reference } from "@/lib/planning-goals/types";
export type SuggestedRow = {
  capability_key: string;
  role: GoalRole | null;
  rationale: string;
  origin: string;
  sources: {
    kind: string;
    key?: string;
    direction?: string | null;
    basis?: string;
  }[];
  mesocycle_directives: {
    mesocycle_period_id: string;
    role: GoalRole | null;
    rationale: string;
    origin: string;
  }[];
  family_links: {
    family_key: string;
    family_version: string;
    modality_key: string;
    match: string;
    selected: false;
    eligibility_evaluated: false;
  }[];
  family_coverage: "missing" | "linked_not_evaluated";
};
export type StrategyPeriod = {
  mesocycle_period_id: string;
  title: string;
  phase: string;
  label: string;
  confidence: string;
  current_overlay: string | null;
  segments: {
    start_date: string;
    end_date: string;
    phase: string;
    label: string;
    event_title: string | null;
    days: number;
    event_key: string | null;
    event_precision: string | null;
  }[];
};
export type GoalSuggestion = {
  strategy_periods?: StrategyPeriod[];
  macrocycle_period_id: string;
  base_reference: Reference | null;
  base_revision: number;
  rows: SuggestedRow[];
  unprofiled_event_keys: string[];
  unmapped_goal_keys: string[];
};
export type Suggestions = {
  schema_version:
    "planning-goal-suggestions-v0.1" | "planning-goal-suggestions-v0.2";
  rules_version: "declared-goal-review-v0.1" | "mesocycle-strategy-v0.1";
  event_titles?: Record<string, string>;
  strategy?: {
    source_basis: string;
    profile_context: { notes: string[] };
    recent_review_signals: unknown[];
    personal_response_model: { applied: false; status: string; reason: string };
    sources: { key: string; url: string; use: string; limit: string }[];
    boundaries_changed: false;
    race_dates_changed: false;
    workouts_created: false;
    dose_selected: false;
  };
  macrocycles: GoalSuggestion[];
  registry_reference: { version: string; content_hash: string };
  review_required: true;
  periodization_inferred: boolean;
  dose_selected: false;
  family_selection_authorized: false;
  committed: false;
};
const roles = new Set([
  "primary_development",
  "secondary_development",
  "maintenance",
  "permitted_decline",
]);
export function checkedSuggestion(
  inputs: PlanningInputs,
  period: Period,
  children: Period[],
  capabilities: string[],
  base?: { reference: Reference; revision: number },
): GoalSuggestion {
  const v = inputs.goal_suggestions;
  const fail = () => {
    throw Error(
      "A céljavaslat vagy a forrásverzió eltér. Töltsd újra a célok oldalát.",
    );
  };
  const strategic = v?.schema_version === "planning-goal-suggestions-v0.2";
  if (
    !v ||
    (!strategic && v.schema_version !== "planning-goal-suggestions-v0.1") ||
    v.rules_version !==
      (strategic ? "mesocycle-strategy-v0.1" : "declared-goal-review-v0.1") ||
    v.review_required !== true ||
    v.periodization_inferred !== strategic ||
    v.dose_selected !== false ||
    v.family_selection_authorized !== false ||
    v.committed !== false ||
    !Array.isArray(v.macrocycles)
  )
    return fail();
  if (
    strategic &&
    (!v.strategy ||
      v.strategy.personal_response_model.applied !== false ||
      v.strategy.boundaries_changed !== false ||
      v.strategy.race_dates_changed !== false ||
      v.strategy.workouts_created !== false ||
      v.strategy.dose_selected !== false ||
      !Array.isArray(v.strategy.sources) ||
      !v.strategy.sources.length)
  )
    return fail();
  const rows = v.macrocycles.filter(
    (m) => m.macrocycle_period_id === period.id,
  );
  if (rows.length !== 1) return fail();
  const m = rows[0];
  if (
    m.base_revision !== (base?.revision ?? 0) ||
    (base
      ? !m.base_reference ||
        m.base_reference.artifact_id !== base.reference.artifact_id ||
        m.base_reference.content_hash !== base.reference.content_hash
      : m.base_reference !== null)
  )
    return fail();
  const periods = inputs.periods;
  for (const p of [period, ...children]) {
    const exact = periods.filter((v) => v.id === p.id);
    if (
      exact.length !== 1 ||
      ["start_date", "end_date", "title", "parent_id", "period_type"].some(
        (k) => exact[0][k as keyof Period] !== p[k as keyof Period],
      )
    )
      return fail();
  }
  if (
    !Array.isArray(m.rows) ||
    new Set(m.rows.map((r) => r.capability_key)).size !== m.rows.length
  )
    return fail();
  if (strategic) {
    if (
      !Array.isArray(m.strategy_periods) ||
      m.strategy_periods.length !== children.length ||
      new Set(m.strategy_periods.map((p) => p.mesocycle_period_id)).size !==
        children.length
    )
      return fail();
    for (const p of m.strategy_periods) {
      const child = children.find((c) => c.id === p.mesocycle_period_id);
      if (
        !child ||
        !Array.isArray(p.segments) ||
        !p.segments.length ||
        p.segments[0].start_date !== child.start_date ||
        p.segments.at(-1)?.end_date !== child.end_date ||
        p.segments.some(
          (s) =>
            s.start_date > s.end_date ||
            ![
              "foundation",
              "specific",
              "race_readiness",
              "transition",
              "general",
              "historical",
            ].includes(s.phase),
        )
      )
        return fail();
    }
  }
  if (strategic)
    for (const p of m.strategy_periods ?? []) {
      for (let i = 0; i < p.segments.length; i++) {
        const s = p.segments[i];
        if (
          new Date(s.start_date + "T00:00:00Z").toISOString().slice(0, 10) !==
            s.start_date ||
          new Date(s.end_date + "T00:00:00Z").toISOString().slice(0, 10) !==
            s.end_date ||
          (i > 0 && addDays(p.segments[i - 1].end_date, 1) !== s.start_date)
        )
          return fail();
        const count =
          (Date.parse(s.end_date) - Date.parse(s.start_date)) / 86400000 + 1;
        if (s.days !== count) return fail();
      }
    }
  for (const r of m.rows) {
    if (
      !capabilities.includes(r.capability_key) ||
      !(strategic
        ? roles.has(r.role ?? "")
        : r.role === null || roles.has(r.role)) ||
      typeof r.rationale !== "string" ||
      !Array.isArray(r.sources) ||
      !r.sources.length ||
      !Array.isArray(r.mesocycle_directives) ||
      r.mesocycle_directives.length !== children.length ||
      new Set(r.mesocycle_directives.map((d) => d.mesocycle_period_id)).size !==
        children.length
    )
      return fail();
    for (const d of r.mesocycle_directives)
      if (
        !children.some((c) => c.id === d.mesocycle_period_id) ||
        !(strategic
          ? roles.has(d.role ?? "")
          : d.role === null || roles.has(d.role)) ||
        typeof d.rationale !== "string"
      )
        return fail();
    if (
      !Array.isArray(r.family_links) ||
      r.family_links.some(
        (f) =>
          typeof f.family_key !== "string" ||
          typeof f.modality_key !== "string" ||
          f.selected !== false ||
          f.eligibility_evaluated !== false,
      ) ||
      r.family_coverage !==
        (r.family_links.length ? "linked_not_evaluated" : "missing")
    )
      return fail();
  }
  return m;
}
export const familyNames: Record<string, string> = {
  KAYAK_EASY_TECHNICAL: "Könnyű technikai kajakedzés",
  KAYAK_LONG_AEROBIC: "Hosszabb aerob kajakedzés",
  STRENGTH_REFERENCE_AND_DEVELOPMENT: "Erőfejlesztés és referencia",
  RUN_EASY_AEROBIC_FALLBACK:
    "Könnyű futás · általános helyettesítési lehetőség",
};
