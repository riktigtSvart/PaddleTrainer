import { canonical, day, object, sha } from "@/lib/planning-cycles/contracts";
import { readReceipt as readProfileReceipt } from "@/lib/athlete-setup/contracts";
import type {
  Receipt as ProfileReceipt,
  Profile,
} from "@/lib/athlete-setup/contracts";
import { readOptionsReceipt } from "@/lib/training-options/contracts";
import type {
  Location,
  OptionsReceipt,
} from "@/lib/training-options/contracts";
import {
  availableExercises,
  declaredExercises,
  readStrengthCatalog,
} from "@/lib/training-options/strength-catalog";
import type { StrengthCatalog } from "@/lib/training-options/strength-catalog";

export type Ref = { artifact_id: string; content_hash: string };
export type Registry = {
  schema_version: "assessment-registry-v0.1";
  version: string;
  history_days: number;
  planning_authorized: false;
  clinical_clearance: false;
  content_hash: string;
  sports: {
    key: string;
    label: string;
    disciplines: string[];
    focus: string[];
    reference_help: string;
    assessment_support: "declarations_and_references";
    planning_support: "sample_family" | "not_implemented";
  }[];
  patterns: { key: Pattern; label: string; exercise_ids: string[] }[];
};
export type Pattern = "pull" | "push" | "knee" | "hip" | "core";
export type SetRecord = {
  id: string;
  repetitions: number | null;
  hold_seconds: string | null;
  load_kind:
    | "unknown"
    | "bodyweight"
    | "external_kg"
    | "assistance_kg"
    | "machine_level"
    | "band";
  load_value: string | null;
  load_basis:
    | "unknown"
    | "total"
    | "per_hand"
    | "machine_display"
    | "assistance"
    | "not_applicable";
  load_note: string;
  rir: "unknown" | "0" | "1" | "2" | "3" | "4" | "5_plus";
  technique: "unknown" | "stable" | "uncertain" | "breakdown";
  symptoms: "unknown" | "none" | "discomfort" | "pain";
};
export type Exercise = {
  id: string;
  pattern: Pattern;
  exercise_id: string | null;
  location_id: string | null;
  familiarity:
    | "unknown"
    | "unfamiliar"
    | "assisted"
    | "independent"
    | "regular";
  comfort:
    | "unknown"
    | "none"
    | "uncertain"
    | "symptoms"
    | "avoid"
    | "no_experience";
  performed_on: string | null;
  side: "unknown" | "both" | "left" | "right" | "alternating";
  machine_note: string;
  notes: string;
  sets: SetRecord[];
};
export type Sport = {
  sport_key: string;
  role: "unknown" | "primary" | "secondary" | "recreation" | "paused";
  discipline: string;
  goal: string;
  notes: string;
};
export type SportReference = {
  id: string;
  sport_key: string;
  performed_on: string | null;
  protocol: string;
  location_id: string | null;
  distance_m: string | null;
  duration_minutes: string | null;
  duration_basis: "unknown" | "elapsed" | "active";
  power_w: string | null;
  heart_rate_bpm: number | null;
  rpe: number | null;
  elevation_gain_m: string | null;
  pool_length_m: string | null;
  equipment: string;
  conditions: string;
  source: "self_report";
};
export type Data = {
  timezone_name: string;
  assessment_date: string;
  program_reference: Ref | null;
  goal_label: string;
  state_change: "unknown" | "unchanged" | "changed" | "review_needed";
  state_notes: string;
  experience: "unknown" | "none" | "occasional" | "returning" | "regular";
  strength_frequency:
    | "unknown"
    | "none"
    | "less_than_weekly"
    | "weekly_1"
    | "weekly_2"
    | "weekly_3_plus";
  last_strength_date: string | null;
  usual_strength_minutes: number | null;
  supervision: "unknown" | "self" | "supervised" | "mixed" | "needed";
  default_location_id: string | null;
  sports: Sport[];
  exercises: Exercise[];
  sport_references: SportReference[];
  references_reviewed: boolean;
  reviewed: boolean;
};
export type Snapshot = {
  athlete_id: string;
  timezone_name: string;
  source_hash: string;
  profile_reference: Ref | null;
  options_reference: Ref | null;
  profile_receipt: ProfileReceipt | null;
  options_receipt: OptionsReceipt | null;
  profile_review: {
    global_entry_gate: string;
    evaluated_on: string;
    clinical_clearance: false;
    constraints: unknown[];
  } | null;
  locations: Location[];
  catalog: StrengthCatalog;
  registry: Registry;
  programs: {
    reference: Ref;
    title: string;
    sport: string;
    start_date: string;
    end_date: string | null;
  }[];
};
export type Summary = {
  steps: boolean[];
  completed_steps: number;
  total_steps: number;
  form_complete: boolean;
  state_review_required: boolean;
  exercise_states: { id: string; state: string; reasons: string[] }[];
  recorded_reference_count: number;
  planning_authorized: false;
  clinical_clearance: false;
  workouts_changed: false;
  source_kind: "self_report";
  evaluated_on: string;
};
export type Proposal = {
  request_id: string;
  previous_reference: Ref | null;
  source_hash: string;
  data: Data;
};
export type AssessmentReceipt = {
  identity_scope: "APPLICATION_DEMO_USER";
  committed: true;
  reused: boolean;
  durable_available_at: string;
  planning_authorized: false;
  workouts_changed: false;
  clinical_clearance: false;
  artifact: {
    schema_version: "initial-assessment-v0.1";
    artifact_id: string;
    athlete_id: string;
    revision: number;
    created_at: string;
    content_hash: string;
    proposal: Proposal;
    snapshot: Snapshot;
    summary: Summary;
    planning_authorized: false;
    workouts_changed: false;
    clinical_clearance: false;
  };
};
export type Context = {
  schema_version: "initial-assessment-v0.1";
  athlete_id: string;
  timezone_name: string;
  local_today: string;
  sources: Snapshot;
  saved: AssessmentReceipt | null;
  reference: Ref | null;
  data: Data | null;
  sources_changed: boolean;
  summary: Summary | null;
  content_hash: string;
  planning_authorized: false;
  workouts_changed: false;
  clinical_clearance: false;
};
export type Pending = {
  version: "initial-assessment-pending-v0.1";
  owner: string;
  body: string;
};
export const key = (owner: string, kind: "draft" | "pending") =>
  `paddletrainer.initial-assessment.${kind}.v1:${owner}`;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const hash = /^[0-9a-f]{64}$/;
const identifier = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
export const requireValue: (v: unknown, message?: string) => asserts v = (
  v,
  message = "A kezdeti felmérés adatai nem ellenőrizhetők.",
) => {
  if (!v) throw Error(message);
};
const text = (v: unknown, n = 2000) => typeof v === "string" && v.length <= n;
const choice = (v: unknown, values: string) =>
  typeof v === "string" && values.split("|").includes(v);
const nullableId = (v: unknown) =>
  v === null || (typeof v === "string" && uuid.test(v));
function validDay(v: unknown): v is string {
  if (typeof v !== "string") return false;
  try {
    day(v);
    return v >= "1900-01-01" && v <= "2100-12-31";
  } catch {
    return false;
  }
}
const nullableDay = (v: unknown) => v === null || validDay(v);
const integer = (v: unknown, max: number) =>
  v === null ||
  (typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= max);
function numeric(v: unknown, draft: boolean) {
  return (
    v === null ||
    (typeof v === "string" &&
      (draft
        ? /^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{0,6})?$/
        : /^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$/
      ).test(v))
  );
}
function list(v: unknown, n: number) {
  requireValue(Array.isArray(v) && v.length <= n);
  return v;
}
function ref(v: unknown) {
  if (v === null) return;
  const r = object(v);
  requireValue(
    text(r.artifact_id, 160) &&
      !!r.artifact_id &&
      typeof r.content_hash === "string" &&
      hash.test(r.content_hash),
  );
}
function closed(v: Record<string, unknown>, sample: string) {
  requireValue(
    Object.keys(v).sort().join("|") === sample.split("|").sort().join("|"),
  );
}
export const loadBases: Record<string, string[]> = {
  unknown: ["unknown"],
  bodyweight: ["not_applicable"],
  band: ["unknown", "not_applicable"],
  external_kg: ["unknown", "total", "per_hand", "machine_display"],
  assistance_kg: ["unknown", "assistance"],
  machine_level: ["unknown", "machine_display"],
};
export function readData(value: unknown, draft = false): Data {
  const d = object(value);
  closed(
    d,
    "timezone_name|assessment_date|program_reference|goal_label|state_change|state_notes|experience|strength_frequency|last_strength_date|usual_strength_minutes|supervision|default_location_id|sports|exercises|sport_references|references_reviewed|reviewed",
  );
  requireValue(validDay(d.assessment_date) && text(d.timezone_name, 64));
  new Intl.DateTimeFormat("hu", { timeZone: String(d.timezone_name) });
  ref(d.program_reference);
  requireValue(
    text(d.goal_label, 200) &&
      text(d.state_notes) &&
      choice(d.state_change, "unknown|unchanged|changed|review_needed") &&
      choice(d.experience, "unknown|none|occasional|returning|regular") &&
      choice(
        d.strength_frequency,
        "unknown|none|less_than_weekly|weekly_1|weekly_2|weekly_3_plus",
      ) &&
      nullableDay(d.last_strength_date) &&
      integer(d.usual_strength_minutes, 1440) &&
      choice(d.supervision, "unknown|self|supervised|mixed|needed") &&
      nullableId(d.default_location_id) &&
      typeof d.references_reviewed === "boolean" &&
      typeof d.reviewed === "boolean",
  );
  const sports = list(d.sports, 32),
    seenSports = new Set<string>();
  for (const raw of sports) {
    const s = object(raw);
    closed(s, "sport_key|role|discipline|goal|notes");
    requireValue(
      typeof s.sport_key === "string" &&
        identifier.test(s.sport_key) &&
        !seenSports.has(s.sport_key) &&
        choice(s.role, "unknown|primary|secondary|recreation|paused") &&
        text(s.discipline, 200) &&
        text(s.goal, 200) &&
        text(s.notes),
    );
    seenSports.add(s.sport_key);
  }
  const ids = new Set();
  for (const raw of list(d.exercises, 64)) {
    const e = object(raw);
    closed(
      e,
      "id|pattern|exercise_id|location_id|familiarity|comfort|performed_on|side|machine_note|notes|sets",
    );
    requireValue(
      typeof e.id === "string" &&
        uuid.test(e.id) &&
        !ids.has(e.id) &&
        choice(e.pattern, "pull|push|knee|hip|core") &&
        (e.exercise_id === null ||
          (typeof e.exercise_id === "string" &&
            identifier.test(e.exercise_id))) &&
        nullableId(e.location_id) &&
        choice(
          e.familiarity,
          "unknown|unfamiliar|assisted|independent|regular",
        ) &&
        choice(
          e.comfort,
          "unknown|none|uncertain|symptoms|avoid|no_experience",
        ) &&
        nullableDay(e.performed_on) &&
        choice(e.side, "unknown|both|left|right|alternating") &&
        text(e.machine_note, 200) &&
        text(e.notes),
    );
    ids.add(e.id);
    const sets = new Set();
    for (const raw of list(e.sets, 20)) {
      const s = object(raw);
      closed(
        s,
        "id|repetitions|hold_seconds|load_kind|load_value|load_basis|load_note|rir|technique|symptoms",
      );
      requireValue(
        typeof s.id === "string" &&
          uuid.test(s.id) &&
          !sets.has(s.id) &&
          integer(s.repetitions, 10000) &&
          numeric(s.hold_seconds, draft) &&
          numeric(s.load_value, draft) &&
          !(s.repetitions !== null && s.hold_seconds !== null) &&
          choice(
            s.load_kind,
            "unknown|bodyweight|external_kg|assistance_kg|machine_level|band",
          ) &&
          choice(
            s.load_basis,
            "unknown|total|per_hand|machine_display|assistance|not_applicable",
          ) &&
          text(s.load_note, 200) &&
          choice(s.rir, "unknown|0|1|2|3|4|5_plus") &&
          choice(s.technique, "unknown|stable|uncertain|breakdown") &&
          choice(s.symptoms, "unknown|none|discomfort|pain"),
      );
      sets.add(s.id);
      requireValue(
        (!["unknown", "bodyweight", "band"].includes(String(s.load_kind)) ||
          s.load_value === null) &&
          loadBases[String(s.load_kind)].includes(String(s.load_basis)) &&
          (s.load_value === null || Number(s.load_value) <= 100000),
      );
    }
  }
  const refs = new Set();
  for (const raw of list(d.sport_references, 100)) {
    const r = object(raw);
    closed(
      r,
      "id|sport_key|performed_on|protocol|location_id|distance_m|duration_minutes|duration_basis|power_w|heart_rate_bpm|rpe|elevation_gain_m|pool_length_m|equipment|conditions|source",
    );
    requireValue(
      typeof r.id === "string" &&
        uuid.test(r.id) &&
        !refs.has(r.id) &&
        typeof r.sport_key === "string" &&
        seenSports.has(r.sport_key) &&
        nullableDay(r.performed_on) &&
        nullableId(r.location_id) &&
        text(r.protocol, 200) &&
        choice(r.duration_basis, "unknown|elapsed|active") &&
        integer(r.heart_rate_bpm, 300) &&
        integer(r.rpe, 10) &&
        text(r.equipment, 200) &&
        text(r.conditions) &&
        r.source === "self_report" &&
        [
          r.distance_m,
          r.duration_minutes,
          r.power_w,
          r.elevation_gain_m,
          r.pool_length_m,
        ].every((v) => numeric(v, draft)),
    );
    refs.add(r.id);
  }
  const data = d as unknown as Data;
  requireValue(
    [
      data.last_strength_date,
      ...data.exercises.map((e) => e.performed_on),
      ...data.sport_references.map((r) => r.performed_on),
    ].every((v) => v === null || v <= data.assessment_date),
    "A teljesítés dátuma nem lehet a felmérés dátuma után.",
  );
  return data;
}
export function normalizeData(value: Data): Data {
  const data = structuredClone(value);
  for (const e of data.exercises)
    for (const s of e.sets)
      for (const k of ["load_value", "hold_seconds"] as const)
        if (s[k]?.endsWith(".")) s[k] = s[k]!.slice(0, -1);
  for (const r of data.sport_references)
    for (const k of [
      "distance_m",
      "duration_minutes",
      "power_w",
      "elevation_gain_m",
      "pool_length_m",
    ] as const)
      if (r[k]?.endsWith(".")) r[k] = r[k]!.slice(0, -1);
  return readData(data);
}
export function sourceBody(s: Snapshot) {
  return {
    timezone_name: s.timezone_name,
    profile_reference: s.profile_reference,
    options_reference: s.options_reference,
    catalog_hash: s.catalog.content_hash,
    registry_hash: s.registry.content_hash,
    programs: s.programs,
  };
}
function profileGate(p: Profile, today: string) {
  const age =
    p.birth_date === null
      ? null
      : Number(today.slice(0, 4)) -
        Number(p.birth_date.slice(0, 4)) -
        Number(today.slice(5) < p.birth_date.slice(5));
  if (p.participation === "paused") return "HOLD";
  if (
    p.participation === "professional_review" ||
    (p.participation === "adapted" && p.constraints.length === 0) ||
    p.constraints.some(
      (c) =>
        c.duration === "temporary" ||
        (c.review_on !== null && c.review_on <= today) ||
        !(
          c.restricted_activities.length ||
          c.adaptations ||
          c.professional_guidance
        ),
    )
  )
    return "REVIEW_REQUIRED";
  if (
    age === null ||
    age < 18 ||
    !p.target_sport ||
    p.sport_history_status === "unknown" ||
    p.constraint_status === "unknown" ||
    p.participation === "unknown"
  )
    return "REVIEW_REQUIRED";
  return p.constraint_status === "present" || p.participation === "adapted"
    ? "OPEN_WITH_CONSTRAINTS"
    : "OPEN";
}
function validateSelections(data: Data, s: Snapshot) {
  for (const place of s.locations) declaredExercises(s.catalog, place);
  const places = new Set(s.locations.map((l) => l.id));
  requireValue(
    data.timezone_name === s.timezone_name &&
      data.sports.every((v) =>
        s.registry.sports.some((r) => r.key === v.sport_key),
      ) &&
      (data.default_location_id === null ||
        places.has(data.default_location_id)) &&
      (data.program_reference === null ||
        s.programs.some(
          (p) => canonical(p.reference) === canonical(data.program_reference),
        )) &&
      data.exercises.every(
        (e) =>
          (e.location_id === null || places.has(e.location_id)) &&
          (e.exercise_id === null ||
            s.registry.patterns
              .find((p) => p.key === e.pattern)!
              .exercise_ids.includes(e.exercise_id)),
      ) &&
      data.sport_references.every(
        (r) => r.location_id === null || places.has(r.location_id),
      ),
  );
}
async function readSnapshot(value: unknown, owner: string): Promise<Snapshot> {
  const s = object(value) as unknown as Snapshot;
  requireValue(s.athlete_id === owner && text(s.timezone_name, 64));
  new Intl.DateTimeFormat("hu", { timeZone: s.timezone_name });
  await readStrengthCatalog(s.catalog);
  const registry = object(s.registry),
    { content_hash, ...body } = registry;
  requireValue(
    registry.schema_version === "assessment-registry-v0.1" &&
      registry.planning_authorized === false &&
      registry.clinical_clearance === false &&
      registry.history_days === 56 &&
      (await sha(body)) === content_hash,
  );
  const keys = new Set();
  for (const raw of list(registry.sports, 64)) {
    const r = object(raw);
    requireValue(
      typeof r.key === "string" &&
        identifier.test(r.key) &&
        !keys.has(r.key) &&
        text(r.label, 200) &&
        text(r.reference_help) &&
        r.assessment_support === "declarations_and_references" &&
        choice(r.planning_support, "sample_family|not_implemented") &&
        list(r.disciplines, 32).every((v) => text(v, 200)) &&
        list(r.focus, 16).every((v) => text(v, 200)),
    );
    keys.add(r.key);
  }
  const patterns = new Set();
  for (const raw of list(registry.patterns, 5)) {
    const p = object(raw);
    requireValue(
      choice(p.key, "pull|push|knee|hip|core") &&
        !patterns.has(p.key) &&
        text(p.label, 200) &&
        list(p.exercise_ids, 128).every((id) =>
          s.catalog.exercises.some((e) => e.id === id),
        ),
    );
    patterns.add(p.key);
  }
  requireValue(patterns.size === 5 && keys.size > 0);
  if (s.profile_receipt) {
    const r = await readProfileReceipt(s.profile_receipt);
    const profile = r.artifact.proposal.data as Profile;
    requireValue(
      r.artifact.athlete_id === owner &&
        r.artifact.kind === "profile" &&
        canonical(s.profile_reference) ===
          canonical({
            artifact_id: r.artifact.artifact_id,
            content_hash: r.artifact.content_hash,
          }) &&
        s.profile_review?.clinical_clearance === false &&
        validDay(s.profile_review.evaluated_on) &&
        s.profile_review.global_entry_gate ===
          profileGate(profile, s.profile_review.evaluated_on) &&
        canonical(s.profile_review.constraints) ===
          canonical(profile.constraints) &&
        ["OPEN", "OPEN_WITH_CONSTRAINTS", "HOLD", "REVIEW_REQUIRED"].includes(
          s.profile_review.global_entry_gate,
        ),
    );
  } else
    requireValue(s.profile_reference === null && s.profile_review === null);
  if (s.options_receipt) {
    const r = await readOptionsReceipt(s.options_receipt, owner);
    requireValue(
      canonical(s.locations) ===
        canonical(r.artifact.proposal.data.locations) &&
        canonical(s.options_reference) ===
          canonical({
            artifact_id: r.artifact.artifact_id,
            content_hash: r.artifact.content_hash,
          }),
    );
  } else
    requireValue(
      s.options_reference === null &&
        Array.isArray(s.locations) &&
        s.locations.length === 0,
    );
  for (const place of s.locations) declaredExercises(s.catalog, place);
  const programs = new Set();
  for (const raw of list(s.programs, 100)) {
    const p = object(raw);
    ref(p.reference);
    const r = object(p.reference);
    requireValue(
      /^pt-cycle:[0-9a-f]{64}$/.test(String(r.artifact_id)) &&
        !programs.has(r.artifact_id) &&
        text(p.title, 200) &&
        text(p.sport, 200) &&
        validDay(p.start_date) &&
        nullableDay(p.end_date),
    );
    programs.add(r.artifact_id);
  }
  requireValue((await sha(sourceBody(s))) === s.source_hash);
  return s;
}
export function summarize(
  data: Data,
  snapshot: Snapshot,
  today: string,
): Summary {
  const review =
    data.state_change !== "unchanged" ||
    !["OPEN", "OPEN_WITH_CONSTRAINTS"].includes(
      snapshot.profile_review?.global_entry_gate ?? "",
    );
  const states = data.exercises.map((e) => {
    const reasons: string[] = [],
      place = snapshot.locations.find((l) => l.id === e.location_id);
    if (e.exercise_id === null) reasons.push("EXERCISE_MISSING");
    if (["unknown", "unfamiliar", "assisted"].includes(e.familiarity))
      reasons.push("INSTRUCTION_OR_FAMILIARITY_NEEDED");
    if (e.comfort !== "none") reasons.push("COMFORT_UNRESOLVED");
    if (!place || place.archived || !place.sports.includes("STRENGTH"))
      reasons.push("LOCATION_REVIEW");
    else if (
      !availableExercises(snapshot.catalog, place).some(
        (x) => x.id === e.exercise_id,
      )
    )
      reasons.push("EQUIPMENT_MISSING");
    const days =
      e.performed_on === null
        ? Infinity
        : (Date.parse(today + "T00:00:00Z") -
            Date.parse(e.performed_on + "T00:00:00Z")) /
          86400000;
    if (!(days >= 0 && days <= snapshot.registry.history_days))
      reasons.push("RECENT_REFERENCE_MISSING");
    if (
      !e.sets.some(
        (s) =>
          ((s.repetitions ?? 0) > 0 || Number(s.hold_seconds) > 0) &&
          (s.load_kind === "bodyweight" ||
            (s.load_kind === "band" && !!s.load_note.trim()) ||
            (["external_kg", "assistance_kg", "machine_level"].includes(
              s.load_kind,
            ) &&
              s.load_value !== null &&
              s.load_basis !== "unknown")) &&
          s.rir !== "unknown" &&
          s.technique === "stable" &&
          s.symptoms === "none",
      )
    )
      reasons.push("SET_REFERENCE_INCOMPLETE");
    const state = review
      ? "review"
      : ["symptoms", "avoid"].includes(e.comfort) ||
          e.sets.some((s) => ["pain", "discomfort"].includes(s.symptoms))
        ? "avoid"
        : ["unfamiliar", "assisted"].includes(e.familiarity)
          ? "needs_instruction"
          : e.exercise_id === null || e.familiarity === "unknown"
            ? "unassessed"
            : reasons.length
              ? "needs_reference"
              : "recorded_reference";
    return { id: e.id, state, reasons };
  });
  const selected = new Set(
    data.exercises.filter((e) => e.exercise_id !== null).map((e) => e.pattern),
  );
  const steps = [
    data.state_change !== "unknown",
    data.experience !== "unknown" &&
      data.strength_frequency !== "unknown" &&
      data.supervision !== "unknown",
    !!data.sports.length &&
      data.sports.some((s) => s.role === "primary") &&
      data.sports.every((s) => s.role !== "unknown"),
    snapshot.registry.patterns.every((p) => selected.has(p.key)) &&
      data.exercises.every(
        (e) => e.familiarity !== "unknown" && e.comfort !== "unknown",
      ),
    data.references_reviewed,
    data.reviewed,
  ];
  return {
    steps,
    completed_steps: steps.filter(Boolean).length,
    total_steps: 6,
    form_complete: steps.every(Boolean),
    state_review_required: review,
    exercise_states: states,
    recorded_reference_count: states.filter(
      (s) => s.state === "recorded_reference",
    ).length,
    planning_authorized: false,
    clinical_clearance: false,
    workouts_changed: false,
    source_kind: "self_report",
    evaluated_on: today,
  };
}
function readProposal(v: unknown): Proposal {
  const p = object(v);
  closed(p, "request_id|previous_reference|source_hash|data");
  requireValue(
    typeof p.request_id === "string" &&
      uuid.test(p.request_id) &&
      typeof p.source_hash === "string" &&
      hash.test(p.source_hash),
  );
  ref(p.previous_reference);
  if (p.previous_reference !== null)
    requireValue(
      /^pt-initial-assessment:[0-9a-f]{32}:[0-9a-f]{32}$/.test(
        String(object(p.previous_reference).artifact_id),
      ),
    );
  readData(p.data);
  return p as unknown as Proposal;
}
export async function readAssessmentReceipt(
  value: unknown,
  owner?: string,
  body?: string,
): Promise<AssessmentReceipt> {
  const r = object(value),
    a = object(r.artifact);
  requireValue(
    r.identity_scope === "APPLICATION_DEMO_USER" &&
      r.committed === true &&
      typeof r.reused === "boolean" &&
      r.planning_authorized === false &&
      r.workouts_changed === false &&
      r.clinical_clearance === false &&
      a.schema_version === "initial-assessment-v0.1" &&
      typeof a.athlete_id === "string" &&
      uuid.test(a.athlete_id) &&
      (!owner || a.athlete_id === owner) &&
      a.planning_authorized === false &&
      a.workouts_changed === false &&
      a.clinical_clearance === false &&
      Number.isInteger(a.revision) &&
      Number(a.revision) >= 1 &&
      typeof a.created_at === "string" &&
      /(Z|[+-]\d\d:\d\d)$/.test(a.created_at) &&
      Number.isFinite(Date.parse(a.created_at)) &&
      typeof r.durable_available_at === "string" &&
      /(Z|[+-]\d\d:\d\d)$/.test(r.durable_available_at) &&
      Number.isFinite(Date.parse(r.durable_available_at)),
  );
  const p = readProposal(a.proposal),
    s = await readSnapshot(a.snapshot, a.athlete_id),
    { content_hash, ...raw } = a;
  requireValue(
    a.artifact_id ===
      `pt-initial-assessment:${a.athlete_id.replaceAll("-", "")}:${p.request_id.replaceAll("-", "")}` &&
      (a.revision === 1) === (p.previous_reference === null) &&
      p.source_hash === s.source_hash &&
      (await sha(raw)) === content_hash &&
      (!body || canonical(p) === canonical(readProposal(JSON.parse(body)))),
  );
  validateSelections(p.data, s);
  requireValue(
    !p.previous_reference ||
      p.previous_reference.artifact_id.startsWith(
        `pt-initial-assessment:${a.athlete_id.replaceAll("-", "")}:`,
      ),
  );
  const sum = object(a.summary);
  requireValue(
    validDay(sum.evaluated_on) &&
      p.data.assessment_date <= sum.evaluated_on &&
      (!s.profile_review ||
        s.profile_review.evaluated_on === sum.evaluated_on) &&
      canonical(a.summary) ===
        canonical(summarize(p.data, s, sum.evaluated_on)),
  );
  return r as unknown as AssessmentReceipt;
}
export async function readContext(value: unknown): Promise<Context> {
  const c = object(value),
    { content_hash, ...raw } = c;
  requireValue(
    c.schema_version === "initial-assessment-v0.1" &&
      typeof c.athlete_id === "string" &&
      uuid.test(c.athlete_id) &&
      text(c.timezone_name, 64) &&
      validDay(c.local_today) &&
      c.planning_authorized === false &&
      c.workouts_changed === false &&
      c.clinical_clearance === false &&
      typeof c.sources_changed === "boolean" &&
      (await sha(raw)) === content_hash,
  );
  const sources = await readSnapshot(c.sources, c.athlete_id);
  requireValue(
    sources.timezone_name === c.timezone_name &&
      (!sources.profile_review ||
        sources.profile_review.evaluated_on === c.local_today),
  );
  if (c.saved !== null) {
    const saved = await readAssessmentReceipt(c.saved, c.athlete_id);
    requireValue(
      canonical(c.data) === canonical(saved.artifact.proposal.data) &&
        canonical(c.reference) ===
          canonical({
            artifact_id: saved.artifact.artifact_id,
            content_hash: saved.artifact.content_hash,
          }) &&
        c.sources_changed ===
          (saved.artifact.proposal.source_hash !== sources.source_hash) &&
        canonical(c.summary) ===
          canonical(
            summarize(
              saved.artifact.proposal.data,
              saved.artifact.snapshot,
              c.local_today,
            ),
          ),
    );
  } else
    requireValue(
      c.data === null &&
        c.reference === null &&
        c.summary === null &&
        c.sources_changed === false,
    );
  return c as unknown as Context;
}
export function readPending(raw: string, owner: string): Pending {
  const p = object(JSON.parse(raw));
  requireValue(
    uuid.test(owner) &&
      p.version === "initial-assessment-pending-v0.1" &&
      p.owner === owner &&
      typeof p.body === "string",
  );
  const proposal = readProposal(JSON.parse(p.body));
  requireValue(
    !proposal.previous_reference ||
      proposal.previous_reference.artifact_id.startsWith(
        `pt-initial-assessment:${owner.replaceAll("-", "")}:`,
      ),
  );
  return p as unknown as Pending;
}
export function readDraft(raw: string, owner: string) {
  const d = object(JSON.parse(raw));
  requireValue(
    d.version === "initial-assessment-draft-v0.1" &&
      d.owner === owner &&
      typeof d.source_hash === "string" &&
      hash.test(d.source_hash) &&
      Number.isInteger(d.open) &&
      Number(d.open) >= 0 &&
      Number(d.open) < 6 &&
      (d.pending_request_id === undefined || d.pending_request_id === null ||
        (typeof d.pending_request_id === "string" && uuid.test(d.pending_request_id))),
  );
  ref(d.previous_reference);
  requireValue(
    !d.previous_reference ||
      String(object(d.previous_reference).artifact_id).startsWith(
        `pt-initial-assessment:${owner.replaceAll("-", "")}:`,
      ),
  );
  return {
    data: readData(d.data, true),
    source_hash: d.source_hash,
    previous_reference: d.previous_reference as Ref | null,
    open: Number(d.open),
    pending_request_id: d.pending_request_id as string | null | undefined,
  };
}
export function newSet(): SetRecord {
  return {
    id: crypto.randomUUID(),
    repetitions: null,
    hold_seconds: null,
    load_kind: "unknown",
    load_value: null,
    load_basis: "unknown",
    load_note: "",
    rir: "unknown",
    technique: "unknown",
    symptoms: "unknown",
  };
}
export function newExercise(
  pattern: Pattern,
  location: string | null,
): Exercise {
  return {
    id: crypto.randomUUID(),
    pattern,
    exercise_id: null,
    location_id: location,
    familiarity: "unknown",
    comfort: "unknown",
    performed_on: null,
    side: "unknown",
    machine_note: "",
    notes: "",
    sets: [],
  };
}
export function emptyData(c: Context): Data {
  const profile = c.sources.profile_receipt?.artifact.proposal.data as
    | Profile
    | undefined;
  const matches: Record<string, string> = {
    kajak: "KAYAK",
    kayak: "KAYAK",
    futás: "RUNNING",
    running: "RUNNING",
    úszás: "SWIMMING",
    swimming: "SWIMMING",
    kerékpár: "CYCLING",
    kerékpározás: "CYCLING",
    cycling: "CYCLING",
    erősítés: "STRENGTH",
    kondi: "STRENGTH",
  };
  const program = c.sources.programs.find(
    (p) =>
      p.start_date <= c.local_today &&
      (!p.end_date || p.end_date >= c.local_today),
  );
  const sport =
    matches[
      (program?.sport ?? profile?.target_sport ?? "")
        .trim()
        .toLocaleLowerCase("hu")
    ];
  const recordedSports: Sport[] = (profile?.sport_history ?? []).flatMap((history) => {
    const text = history.sport.trim().toLocaleLowerCase("hu");
    const key = matches[text] ?? c.sources.registry.sports.find((v) => v.key.toLocaleLowerCase("hu") === text || v.label.toLocaleLowerCase("hu") === text)?.key;
    return key && history.role && history.role !== "unknown" ? [{ sport_key: key, role: history.role, discipline: history.discipline, goal: "", notes: history.notes }] : [];
  });
  const sports = [...new Map(recordedSports.map((v) => [v.sport_key, v])).values()];
  if (sport && !sports.some((v) => v.sport_key === sport)) sports.unshift({ sport_key: sport, role: "primary", discipline: "", goal: "", notes: "" });
  return {
    timezone_name: c.timezone_name,
    assessment_date: c.local_today,
    program_reference: program?.reference ?? null,
    goal_label: program?.title ?? "",
    state_change: "unknown",
    state_notes: "",
    experience: "unknown",
    strength_frequency: "unknown",
    last_strength_date: null,
    usual_strength_minutes: null,
    supervision: "unknown",
    default_location_id: null,
    sports,
    exercises: [],
    sport_references: [],
    references_reviewed: false,
    reviewed: false,
  };
}
