import {validateWorkoutCandidate,validateWorkoutContext} from "./strength-workout";
import type {StrengthWorkoutDose} from "./strength-workout";
import { addDays, object, sha } from "./contracts";
import { localDay } from "./plan-view";
import { runningReference, runningPresentation } from "./running-prescription";
import { validateLoadBudget } from "./training-load";
import { validateSwimmingCandidate } from "./swimming-prescription";
import {validateStarterCandidate} from "./strength-starter";
import type { SwimmingDose } from "./swimming-prescription";
import {
  strengthDuration,
  validateStrengthAssessment,
  validateStrengthCandidate,
} from "./strength-assessment";
import type { AssessedStrengthDose } from "./strength-assessment";

type Row = Record<string, unknown>;
export type Prescription = {
  schema_version: "training-prescription-v0.1" | "training-prescription-v0.2" | "training-prescription-v0.3" | "training-prescription-v0.4" | "training-prescription-v0.5" | "training-prescription-v0.6";
  family_key: string;
  duration_sec: number;
  minimum_seconds: number;
  maximum_seconds: number;
  reference_session_ids: string[];
  reference_cap_seconds: number | null;
  product_default_used: boolean;
  soft_duration_reduced: boolean;
  progression_applied: false;
  personal_response_model_applied: false;
  intensity_basis:
    | "product_default_not_personal_threshold"
    | "introductory_product_default"
    | "reviewed_assessment_sets" | "own_reference_independent_volume";
  introductory_strength?: {
    schema_version: "introductory-strength-v0.1";
    movements: {key: string; label: string; instruction: string}[];
    sets_per_movement: 1;
    max_repetitions: 5;
    preparatory_only: true;
    external_load_prescribed: false;
    source_url: string;
  };
  assessment_duration_minutes?: number | null;
  running?: ReturnType<typeof runningReference>["running"];
  swimming?: SwimmingDose;
  rpe?: { min: 2; max: 3 };
  strength?:
    | {
        movements: 2;
        sets_per_movement: 2;
        repetitions: 6;
        rir_min: 3;
        rir_max: 4;
        load_kg: null;
      }
    | AssessedStrengthDose | StrengthWorkoutDose;
};
export type PrescriptionContext = {
  schema_version: "training-prescriptions-v0.1" | "training-prescriptions-v0.2" | "training-prescriptions-v0.3" | "training-prescriptions-v0.4";
  history_days: 56;
  starting_budget: {
    schema_version: "training-starting-budget-v0.1" | "training-starting-budget-v0.2";
    history_days: 56;
    mode: "observed_covered_weeks" | "declared_and_product_defaults" | "declared_current_training";
    baseline_status?: "used" | "stale" | "not_provided";
    weeks: {
      start_date: string;
      end_date: string;
      sessions: number;
      duration_sec: number | null;
      status: string;
    }[];
    used_week_starts: string[];
    max_sessions_per_7_days: number;
    max_minutes_per_7_days: number;
  };
  by_candidate: Record<string, Prescription>;
};
export const families: Record<
  string,
  {
    sport: string;
    min: number;
    max: number;
    nominal: number | null;
    fallback: number | null;
    capabilities: string[];
  }
> = {
  KAYAK_EASY_TECHNICAL: {
    sport: "KAYAK",
    min: 1200,
    max: 2700,
    nominal: 1800,
    fallback: 1800,
    capabilities: [
      "TECHNICAL_SKILL",
      "PERIPHERAL_OXIDATIVE_CAPACITY",
      "PADDLING_ECONOMY",
    ],
  },
  KAYAK_LONG_AEROBIC: {
    sport: "KAYAK",
    min: 3600,
    max: 4500,
    nominal: 3600,
    fallback: null,
    capabilities: [
      "PERIPHERAL_OXIDATIVE_CAPACITY",
      "PADDLING_ECONOMY",
      "LONG_DURATION_DURABILITY",
    ],
  },
  STRENGTH_REFERENCE_AND_DEVELOPMENT: {
    sport: "STRENGTH",
    min: 1200,
    max: 1800,
    nominal: null,
    fallback: null,
    capabilities: ["MAX_STRENGTH", "MUSCULOSKELETAL_ROBUSTNESS"],
  },
  RUN_EASY_AEROBIC_FALLBACK: {
    sport: "RUNNING",
    min: 1200,
    max: 2700,
    nominal: 1800,
    fallback: null,
    capabilities: ["PERIPHERAL_OXIDATIVE_CAPACITY"],
  },
};
const invalid = () =>
  Error(
    "Az edzés időtartama vagy a személyes kezdőkeret forrása nem ellenőrizhető.",
  );
function instant(value: unknown): number {
  if (
    typeof value !== "string" ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    throw invalid();
  return Date.parse(value);
}
function validCompleted(session: Row, cutoff: number) {
  return (
    Number.isSafeInteger(session.duration_sec) &&
    Number(session.duration_sec) >= 0 &&
    session.ended_at !== null &&
    instant(session.started_at) <= instant(session.ended_at) &&
    instant(session.ended_at) <= cutoff &&
    Number(session.duration_sec) * 1000 <=
      instant(session.ended_at) - instant(session.started_at)
  );
}
async function same(actual: unknown, expected: unknown) {
  if ((await sha(actual)) !== (await sha(expected))) throw invalid();
}
function code(value: unknown) {
  const normalized = String(value).trim().toLocaleLowerCase("hu");
  return Object.entries({
    KAYAK: ["kajak", "kayak", "kayaking", "kayak_flatwater"],
    STRENGTH: ["erőnlét", "erőedzés", "erősítés", "strength", "kondi"],
    RUNNING: ["futás", "futas", "run", "running"],
  }).find(([, aliases]) => aliases.includes(normalized))?.[0];
}
// Resolve civil midnight independently of the browser zone, including DST.
function midnight(day: string, zone: string) {
  const target = Date.parse(day + "T00:00:00Z");
  let value = target;
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  for (let i = 0; i < 4; i++) {
    const parts = Object.fromEntries(
      formatter.formatToParts(value).map((p) => [p.type, p.value]),
    );
    const shown = Date.parse(
      `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}Z`,
    );
    if (shown === target) return value;
    value += target - shown;
  }
  throw invalid();
}
const weekday = (day: string) =>
  (new Date(day + "T12:00:00Z").getUTCDay() + 6) % 7;

export async function validatePrescriptionContext(review: Row) {
  const result = object(review.result),
    prep = object(result.preparation ?? {});
  if (result.prescription_context === undefined) {
    if (prep.version === "training-preparation-v0.2") throw invalid();
    return;
  }
  const context = object(result.prescription_context),
    currentInputs = object(review.inputs),
    sourceReview = review.calibration_review
      ? object(review.calibration_review)
      : review,
    inputs = object(sourceReview.inputs),
    zone = String(review.timezone_name);
  if (
    !["training-prescriptions-v0.1", "training-prescriptions-v0.2", "training-prescriptions-v0.3", "training-prescriptions-v0.4"].includes(
      String(context.schema_version),
    ) ||
    context.history_days !== 56 ||
    prep.version !== "training-preparation-v0.2" ||
    currentInputs.athlete_id !== review.athlete_id ||
    currentInputs.timezone_name !== review.timezone_name ||
    currentInputs.start_date !== review.start_date ||
    currentInputs.end_date !== review.end_date ||
    inputs.athlete_id !== review.athlete_id ||
    inputs.timezone_name !== review.timezone_name ||
    inputs.start_date !== sourceReview.start_date ||
    inputs.end_date !== sourceReview.end_date ||
    !Array.isArray(inputs.recent_sessions)
  )
    throw invalid();
  await same(inputs.program_reference, review.program_reference);
  if (context.calibration_reference !== undefined || review.calibration_review)
    await same(
      context.calibration_reference,
      review.calibration_review
        ? {
            artifact_id: sourceReview.artifact_id,
            content_hash: sourceReview.content_hash,
          }
        : null,
    );
  const strengthEvidence = await validateStrengthAssessment(review);
  const runningStart = ["training-prescriptions-v0.3", "training-prescriptions-v0.4"].includes(String(context.schema_version)) ? runningReference(currentInputs) : null;
  const cutoff = instant(inputs.captured_at),
    window = object(inputs.recent_window);
  if (
    instant(window.end_at) !== cutoff ||
    instant(window.start_at) !==
      midnight(addDays(localDay(zone, new Date(cutoff)), -56), zone)
  )
    throw invalid();
  const sessions = inputs.recent_sessions.map(object),
    ids = new Set<string>();
  for (const session of sessions) {
    if (
      typeof session.id !== "string" ||
      ids.has(session.id) ||
      instant(session.started_at) < instant(window.start_at) ||
      instant(session.started_at) > cutoff ||
      (session.duration_sec !== null &&
        (!Number.isSafeInteger(session.duration_sec) ||
          Number(session.duration_sec) < 0)) ||
      (session.ended_at !== null &&
        instant(session.ended_at) < instant(session.started_at))
    )
      throw invalid();
    ids.add(session.id);
  }
  const completed = sessions
    .filter((s) => validCompleted(s, cutoff) && Number(s.duration_sec) > 0)
    .sort(
      (a, b) =>
        String(b.started_at).localeCompare(String(a.started_at)) ||
        String(b.id).localeCompare(String(a.id)),
    );
  const candidates = new Map<string, Row>();
  for (const candidate of [
    ...(result.proposals as unknown[]),
    ...((result.alternatives as unknown[]) ?? []).flatMap(
      (g) => object(g).candidates as unknown[],
    ),
  ]) {
    const c = object(candidate),
      key = String(c.candidate_key);
    if (candidates.has(key)) await same(candidates.get(key), c);
    candidates.set(key, c);
  }
  const metadata = object(context.by_candidate);
  await same(Object.keys(metadata).sort(), [...candidates.keys()].sort());
  if(object(result.policy).version==="training-plan-policy-v0.15") await validateWorkoutContext(review);
  for (const [key, candidate] of candidates) {
    if(candidate.sport==="STRENGTH"&&candidate.template_version==="v0.5"){
      if(!strengthEvidence)throw invalid();
      await validateWorkoutCandidate(review,strengthEvidence,candidate,metadata[key]);
      continue;
    }
    if(candidate.sport==="STRENGTH"&&candidate.template_version==="v0.4") {
      await validateStarterCandidate(review,candidate,metadata[key],strengthEvidence);
      continue;
    }
    if (context.schema_version === "training-prescriptions-v0.4" && candidate.sport === "SWIMMING") {
      await validateSwimmingCandidate(review,candidate,metadata[key]);
      continue;
    }
    const family = families[String(candidate.template_key)];
    if (
      !family ||
      candidate.sport !== family.sport ||
      !family.capabilities.includes(String(candidate.capability_key))
    )
      throw invalid();
    let refs = completed
      .filter(
        (s) =>
          s.sport === family.sport &&
          s.reference_occasion !== true &&
          (candidate.template_key !== "KAYAK_LONG_AEROBIC" ||
            Number(s.duration_sec) >= 3600),
      )
      .slice(0, 3);
    const running = family.sport === "RUNNING" ? runningStart : null;
    if (running) refs = running.refs;
    const cap = running ? running.cap : refs.length
        ? Math.min(...refs.map((s) => Number(s.duration_sec)))
        : null,
      seconds = Number(candidate.duration_sec);
    const assessed =
      family.sport === "STRENGTH" &&
      ["training-prescriptions-v0.2", "training-prescriptions-v0.3", "training-prescriptions-v0.4"].includes(String(context.schema_version));
    const declared =
      strengthEvidence?.receipt?.artifact.proposal.data
        .usual_strength_minutes ?? null;
    const strengthWindow = strengthDuration(cap, declared);
    if (
      (!assessed && !running && cap === null && family.fallback === null) ||
      seconds % 300 !== 0 ||
      seconds < family.min ||
      seconds >
        Math.min(
          assessed ? strengthWindow.cap : (cap ?? (running ? 1200 : family.fallback!)),
          family.max,
        )
    )
      throw invalid();
    const expected: Record<string, unknown> = {
      schema_version: "training-prescription-v0.1",
      family_key: candidate.template_key,
      duration_sec: seconds,
      minimum_seconds: family.min,
      maximum_seconds: family.max,
      reference_session_ids: refs.map((s) => s.id),
      reference_cap_seconds: cap,
      product_default_used: cap === null,
      soft_duration_reduced:
        family.nominal !== null && seconds < family.nominal,
      progression_applied: false,
      personal_response_model_applied: false,
      intensity_basis: "product_default_not_personal_threshold",
      ...(family.sport === "STRENGTH"
        ? {
            strength: {
              movements: 2,
              sets_per_movement: 2,
              repetitions: 6,
              rir_min: 3,
              rir_max: 4,
              load_kg: null,
            },
          }
        : { rpe: { min: 2, max: 3 } }),
    };
    if (running) {
      expected.schema_version = "training-prescription-v0.3";
      expected.running = running.running;
      const presentation = runningPresentation(running.running.mode, seconds);
      if (candidate.template_version !== "v0.3" || candidate.title !== presentation.title || candidate.description !== presentation.description) throw invalid();
      await same((candidate.blocks as unknown[]).map(v => object(v).name), presentation.names);
    }
    if (assessed) {
      if (!strengthEvidence) throw invalid();
      const dose = await validateStrengthCandidate(
        strengthEvidence,
        currentInputs,
        candidate,
      );
      expected.schema_version = "training-prescription-v0.2";
      expected.assessment_duration_minutes = declared;
      expected.product_default_used = strengthWindow.productDefault;
      expected.intensity_basis = "reviewed_assessment_sets";
      expected.strength = dose;
    } else if (candidate.strength_prescription !== undefined) throw invalid();
    await same(metadata[key], expected);
    if (!Array.isArray(candidate.blocks) || candidate.blocks.length !== 3)
      throw invalid();
    const warmup =
      seconds < 1800 || ["STRENGTH", "RUNNING"].includes(family.sport)
        ? 300
        : 600;
    candidate.blocks.forEach((value, i) => {
      const b = object(value);
      if (
        b.position !== i + 1 ||
        b.block_type !== ["WARMUP", "WORK", "COOLDOWN"][i] ||
        b.duration_sec !== [warmup, seconds - warmup - 300, 300][i] ||
        [
          "distance_m",
          "intensity_type",
          "intensity_min",
          "intensity_max",
          "repeat_count",
          "parent_block_id",
        ].some((field) => b[field] !== null)
      )
        throw invalid();
    });
    const anchor = refs.find((s) => s.duration_sec === cap)?.id ?? null;
    if (
      candidate.duration_reference_session_id !==
      (candidate.template_key === "KAYAK_EASY_TECHNICAL" ? null : anchor)
    )
      throw invalid();
  }
  if(context.schema_version === "training-prescriptions-v0.4") { await validateLoadBudget(review); return; }
  const reconciliation = object(
      object(sourceReview.result).execution_reconciliation,
    ),
    sources = (reconciliation.sync_windows as unknown[]).map(object);
  const profile =
    inputs.profile === null ? {} : object(object(inputs.profile).data);
  const today = localDay(zone, new Date(cutoff)),
    currentMonday = addDays(today, -weekday(today));
  const low = localDay(zone, new Date(instant(window.start_at))),
    weeks: Row[] = [];
  for (
    let day = addDays(low, (7 - weekday(low)) % 7);
    day < currentMonday;
    day = addDays(day, 7)
  ) {
    const first = midnight(day, zone),
      last = midnight(addDays(day, 7), zone);
    const source = sources.find(
      (s) =>
        instant(s.from_at) <= first &&
        last <= instant(s.to_exclusive_at) &&
        last <= instant(s.started_at),
    );
    const recorded = sessions.filter(
      (s) => first <= instant(s.started_at) && instant(s.started_at) < last,
    );
    const complete =
      !!source && recorded.every((s) => validCompleted(s, cutoff));
    const positive = recorded.filter(
      (s) => validCompleted(s, cutoff) && Number(s.duration_sec) > 0,
    );
    // Preserve the backend's explicit source-zone midnight offsets for the hash.
    const actual = object(
      ((object(context.starting_budget).weeks as unknown[]) ?? [])[
        weeks.length
      ],
    );
    if (
      instant(actual.from_at) !== first ||
      instant(actual.to_exclusive_at) !== last
    )
      throw invalid();
    weeks.push({
      start_date: day,
      end_date: addDays(day, 6),
      from_at: actual.from_at,
      to_exclusive_at: actual.to_exclusive_at,
      source_reference: source?.result_reference ?? null,
      status: complete
        ? "covered"
        : source
          ? "incomplete_records"
          : "coverage_missing",
      session_ids: positive.map((s) => s.id),
      sessions: positive.length,
      duration_sec: complete
        ? positive.reduce((sum, s) => sum + Number(s.duration_sec), 0)
        : null,
      main_sport_present: positive.some(
        (s) => s.sport === code(inputs.program_sport),
      ),
    });
  }
  const covered = weeks.slice(-2);
  const observed =
    covered.length === 2 &&
    covered.every(
      (w) =>
        w.status === "covered" &&
        Number(w.sessions) > 0 &&
        w.main_sport_present,
    ) &&
    (Date.parse(today) - Date.parse(String(covered[1].end_date))) / 86400000 <=
      14;
  const count = observed
    ? Math.min(7, ...covered.map((w) => Number(w.sessions)))
    : 3;
  const minutes = observed
    ? Math.min(
        10080,
        ...covered.map((w) => Math.floor(Number(w.duration_sec) / 60)),
      )
    : 180;
  const currentProfile =
    currentInputs.profile === null
      ? {}
      : object(object(currentInputs.profile).data);
  const maxCount = Math.min(
    Number(currentProfile.typical_days_per_week ?? 7),
    count,
    Number(profile.typical_days_per_week ?? (observed ? count : 2)),
  );
  const maxMinutes = Math.min(
    Number(currentProfile.typical_minutes_per_week ?? 10080),
    minutes,
    Number(profile.typical_minutes_per_week ?? (observed ? minutes : 90)),
  );
  await same(context.starting_budget, {
    schema_version: "training-starting-budget-v0.1",
    history_days: 56,
    mode: observed ? "observed_covered_weeks" : "declared_and_product_defaults",
    weeks,
    used_week_starts: observed ? covered.map((w) => w.start_date) : [],
    max_sessions_per_7_days: maxCount,
    max_minutes_per_7_days: maxMinutes,
  });
  if (
    prep.max_sessions_per_7_days !== maxCount ||
    prep.max_minutes_per_7_days !== maxMinutes ||
    prep.available_days_per_week !==
      (currentProfile.typical_days_per_week ?? null) ||
    prep.available_minutes_per_week !==
      (currentProfile.typical_minutes_per_week ?? null)
  )
    throw invalid();
}
