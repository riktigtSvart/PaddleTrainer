import { day, object, sha } from "@/lib/planning-cycles/contracts";
import {
  readContext as readIntake,
  readAssessmentReceipt,
  readData,
  requireValue as check,
} from "@/lib/initial-assessment/contracts";
import type {
  Context as IntakeContext,
  AssessmentReceipt,
  Data,
  Exercise,
  Ref,
  SetRecord,
} from "@/lib/initial-assessment/contracts";
import { availableExercises } from "@/lib/training-options/strength-catalog";
import { instant, uuid, reference, ref, same, readActivity, elapsedWholeSeconds } from "./activity";
import type { ActivityReceipt } from "./activity";
import {
  protocolVersion, calibrationSchema, calibrationRules, isCalibration,
  calibrationStopped, projectCalibration, validateMeasurement, actualSet,
  measurementDecimals, readProtocolBank, selectedProtocols,
} from "./calibration";
import type { ProtocolBank, SelectedProtocols } from "./calibration";
import { registryExtension } from "./source-updates";
export type Observation = SetRecord & {
  purpose: "practice" | "reference" | "calibration" | "quality" | "repeatability";
  performed_on: string;
  performed_confirmed?: boolean;
  trial_number?: number;
  side?: Exercise["side"];
  stop_reason?: "unknown" | "planned_cap" | "reserve_target" | "effort_limit" | "technique_limit" | "symptom" | "external_interruption" | "measurement_error";
  actual_rest_seconds?: number | null;
  setup_note?: string;
  duration_seconds?: string | null;
  distance_m?: string | null;
  measured_height_m?: string | null;
  metric_name?: string;
  metric_unit?: string;
  metric_value?: string | null;
  plate_configuration?: "not_applicable" | "unknown" | "shared" | "paired";
  left_plates_kg?: string | null;
  right_plates_kg?: string | null;
  shared_plates_kg?: string | null;
  bar_kg?: string | null;
};
export type ExerciseResult = {
  entry_id: string;
  state: "pending" | "recorded" | "skipped" | "stopped";
  side: Exercise["side"];
  machine_note: string;
  note: string;
  observations: Observation[];
};
export type Progress = {
  protocol_version?: typeof protocolVersion;
  phase: "warmup" | "movements" | "review";
  current_index: number;
  warmup_completed: boolean;
  results: ExerciseResult[];
  note: string;
};
export type Command = {
  protocol_version?: typeof protocolVersion;
  protocol_hash?: string;
  measurement_mode?: "calibration" | "repeatability";
  request_id: string;
  action: "start" | "checkpoint" | "finish" | "abandon" | "apply";
  previous_reference: Ref | null;
  assessment_reference: Ref;
  source_hash: string;
  location_id: string;
  selected_entry_ids: string[];
  recording_mode: "device" | "manual";
  precheck_confirmed: boolean;
  progress: Progress;
  actual_start_at: string | null;
  actual_end_at: string | null;
  workout_session_id: string | null;
  no_other_recording_confirmed: boolean;
  reviewed: boolean;
};
export type Preparation = ReturnType<typeof prepare>;
export type Artifact = {
  schema_version: "guided-strength-session-v0.1" | typeof calibrationSchema;
  rules_version: "guided-strength-start-v0.1" | typeof calibrationRules;
  measurement_protocols?: SelectedProtocols | null;
  artifact_id: string;
  athlete_id: string;
  created_at: string;
  session_id: string;
  revision: number;
  base_reference: Ref | null;
  state: "active" | "finished" | "abandoned";
  proposal: Command;
  intake_context: IntakeContext | null;
  preparation: Preparation | null;
  application_context: IntakeContext | null;
  result: null | {
    workout_session_id: string;
    workout_created: boolean;
    workout: Recording & { athlete_id: string };
    assessment_reference: Ref | null;
    stop_required: boolean;
    application_pending: boolean;
  };
  planning_authorized: false;
  clinical_clearance: false;
  content_hash: string;
};
export type Receipt = {
  artifact: Artifact;
  base: Artifact | null;
  committed: true;
  reused: boolean;
  durable_available_at: string;
  assessment_receipt: AssessmentReceipt | null;
  activity_receipt: ActivityReceipt;
  planning_authorized: false;
  clinical_clearance: false;
};
export type Recording = {
  id: string;
  name?: string | null;
  sport: string;
  provider: string | null;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
};
export type Context = {
  calibration_protocols?: ProtocolBank;
  schema_version: "guided-strength-session-v0.1";
  athlete_id: string;
  local_today: string;
  timezone_name: string;
  server_now: string;
  intake: IntakeContext;
  preparation: Preparation;
  latest: Receipt | null;
  history: {
    session_id: string;
    reference: Ref;
    state: string;
    created_at: string;
  }[];
  recordings: Recording[];
  planning_authorized: false;
  clinical_clearance: false;
  content_hash: string;
};
export type Pending = {
  version: "guided-strength-pending-v0.1";
  owner: string;
  body: string;
};
const schema = "guided-strength-session-v0.1",
  rules = "guided-strength-start-v0.1";
export const key = (owner: string, kind: "draft" | "pending") =>
  `paddletrainer.guided-strength.${kind}.v1:${owner}`;
const text = (v: unknown, max = 2000) =>
  typeof v === "string" && v.length <= max;
function closed(v: Record<string, unknown>, keys: string) {
  check(Object.keys(v).sort().join("|") === keys.split("|").sort().join("|"));
}
function validDay(v: unknown): v is string {
  try {
    return typeof v === "string" && day(v).toISOString().slice(0, 10) === v;
  } catch {
    return false;
  }
}
export function prepare(c: IntakeContext) {
  const d = c.data,
    issues: string[] = [];
  if (!d) issues.push("GUIDED_INTAKE_REQUIRED");
  else if (c.sources_changed && !registryExtension(c)) issues.push("GUIDED_SOURCES_CHANGED");
  if (d) {
    if (!d.reviewed) issues.push("GUIDED_INTAKE_REVIEW_REQUIRED");
    if (
      d.state_change !== "unchanged" ||
      c.sources.profile_review?.global_entry_gate !== "OPEN"
    )
      issues.push("GUIDED_STATE_REVIEW");
    if (
      d.experience === "unknown" ||
      d.strength_frequency === "unknown" ||
      ["unknown", "needed"].includes(d.supervision)
    )
      issues.push("GUIDED_HISTORY_OR_SUPERVISION_REVIEW");
    if (
      !d.sports.some(
        (s) =>
          s.sport_key === "STRENGTH" &&
          ["primary", "secondary"].includes(s.role),
      )
    )
      issues.push("GUIDED_STRENGTH_ROLE_REQUIRED");
  }
  const locations = c.sources.locations
    .filter((p) => !p.archived && p.sports.includes("STRENGTH"))
    .map((p) => {
      const available = new Set(
        availableExercises(c.sources.catalog, p).map((e) => e.id),
      );
      return {
        location_id: p.id,
        name: p.name,
        entries: (d?.exercises ?? [])
          .filter((e) => e.location_id === p.id)
          .map((e) => {
            const x = c.sources.catalog.exercises.find(
                (x) => x.id === e.exercise_id,
              ),
              codes: string[] = [];
            if (!x) codes.push("GUIDED_EXERCISE_REQUIRED");
            else if (!available.has(x.id))
              codes.push("GUIDED_EQUIPMENT_MISSING");
            if (!["independent", "regular"].includes(e.familiarity))
              codes.push("GUIDED_INSTRUCTION_REQUIRED");
            if (e.comfort !== "none") codes.push("GUIDED_COMFORT_REVIEW");
            if (e.sets.some((s) => ["pain", "discomfort"].includes(s.symptoms)))
              codes.push("GUIDED_REPORTED_SYMPTOMS");
            return {
              entry_id: e.id,
              exercise_id: e.exercise_id,
              pattern: e.pattern,
              label: x?.label ?? e.pattern,
              ready: !codes.length && !issues.length,
              issues: codes,
            };
          }),
      };
    });
  return {
    rules_version: rules,
    issues,
    locations,
    fresh_reference_required_to_start: false,
    protocol: {
      warmup_minutes: [5, 10],
      practice_repetitions: [3, 5],
      reference_repetitions: [5, 8],
      reference_hold_seconds: [10, 20],
      rest_seconds: 120,
      max_practice_sets: 1,
      max_reference_sets: 1,
      numeric_load_prescribed: false,
      maximal_test: false,
      one_rm_estimated: false,
    },
  };
}
export function stopped(p: Progress) {
  if (isCalibration(p)) return calibrationStopped(p);
  return p.results.some(
    (r) =>
      r.state === "stopped" ||
      r.observations.some(
        (s) =>
          ["pain", "discomfort"].includes(s.symptoms) ||
          s.technique === "breakdown" ||
          ["0", "1"].includes(s.rir),
      ),
  );
}
export function initialProgress(d: Data, ids: string[]): Progress {
  return {
    phase: "warmup",
    current_index: 0,
    warmup_completed: false,
    note: "",
    results: ids.map((id) => {
      const e = d.exercises.find((e) => e.id === id)!;
      return {
        entry_id: id,
        state: "pending",
        side: e.side,
        machine_note: e.machine_note,
        note: "",
        observations: [],
      };
    }),
  };
}
export function projectIntake(d: Data, p: Progress, today: string): Data {
  if (isCalibration(p)) return projectCalibration(d, p, today);
  const value = structuredClone(d),
    dates: string[] = [];
  value.assessment_date = today;
  for (const e of value.exercises) {
    const r = p.results.find((r) => r.entry_id === e.id);
    if (!r) continue;
    const sets = r.observations.filter((s) => s.purpose === "reference");
    if (sets.length) {
      e.sets = sets.map((s) => {
        const v = { ...s };
        delete (v as Partial<Observation>).purpose;
        delete (v as Partial<Observation>).performed_on;
        return v;
      });
      e.performed_on = sets.at(-1)!.performed_on;
      e.side = r.side;
      e.machine_note = r.machine_note;
      dates.push(e.performed_on);
    }
    if (
      r.observations.some((s) => ["pain", "discomfort"].includes(s.symptoms))
    ) {
      e.comfort = "symptoms";
      value.state_change = "changed";
    }
  }
  if (stopped(p)) value.state_change = "changed";
  if (dates.length) value.last_strength_date = dates.sort().at(-1)!;
  value.reviewed = true;
  value.references_reviewed = true;
  return value;
}
export function normalizeCommand(value: Command): Command {
  const command = structuredClone(value);
  for (const result of command.progress.results)
    for (const row of result.observations)
      for (const field of ["load_value", "hold_seconds", ...measurementDecimals] as const) {
        if (row[field] === "") row[field] = null;
        else if (row[field]?.endsWith("."))
          row[field] = row[field]!.slice(0, -1);
      }
  return readCommand(command);
}
export function readCommand(value: unknown, draft = false): Command {
  const c = object(value);
  const calibrated = c.protocol_version !== undefined;
  closed(
    c,
    "request_id|action|previous_reference|assessment_reference|source_hash|location_id|selected_entry_ids|recording_mode|precheck_confirmed|progress|actual_start_at|actual_end_at|workout_session_id|no_other_recording_confirmed|reviewed" + (calibrated ? "|protocol_version|protocol_hash|measurement_mode" : ""),
  );
  if (calibrated) check(c.protocol_version === protocolVersion && typeof c.protocol_hash === "string" && /^[a-f0-9]{64}$/.test(c.protocol_hash) && ["calibration", "repeatability"].includes(String(c.measurement_mode)));
  check(
    uuid(c.request_id) &&
      ["start", "checkpoint", "finish", "abandon", "apply"].includes(
        String(c.action),
      ) &&
      (c.previous_reference === null || reference(c.previous_reference)) &&
      reference(c.assessment_reference) &&
      typeof c.source_hash === "string" &&
      /^[a-f0-9]{64}$/.test(c.source_hash) &&
      uuid(c.location_id) &&
      Array.isArray(c.selected_entry_ids) &&
      c.selected_entry_ids.length >= 1 &&
      c.selected_entry_ids.length <= 5 &&
      c.selected_entry_ids.every(uuid) &&
      new Set(c.selected_entry_ids).size === c.selected_entry_ids.length &&
      ["device", "manual"].includes(String(c.recording_mode)) &&
      typeof c.precheck_confirmed === "boolean" &&
      typeof c.no_other_recording_confirmed === "boolean" &&
      typeof c.reviewed === "boolean" &&
      (c.actual_start_at === null || instant(c.actual_start_at)) &&
      (c.actual_end_at === null || instant(c.actual_end_at)) &&
      (c.workout_session_id === null || uuid(c.workout_session_id)) &&
      (c.action === "start") === (c.previous_reference === null),
  );
  const p = object(c.progress);
  closed(p, "phase|current_index|warmup_completed|results|note" + (calibrated ? "|protocol_version" : ""));
  if (calibrated) check(p.protocol_version === protocolVersion);
  check(
    ["warmup", "movements", "review"].includes(String(p.phase)) &&
      typeof p.warmup_completed === "boolean" &&
      Number.isInteger(p.current_index) &&
      Number(p.current_index) >= 0 &&
      Number(p.current_index) < c.selected_entry_ids.length &&
      text(p.note) &&
      Array.isArray(p.results) &&
      p.results.length === c.selected_entry_ids.length,
  );
  for (const [i, raw] of p.results.entries()) {
    const e = object(raw);
    closed(e, "entry_id|state|side|machine_note|note|observations");
    check(
      e.entry_id === c.selected_entry_ids[i] &&
        ["pending", "recorded", "skipped", "stopped"].includes(
          String(e.state),
        ) &&
        text(e.machine_note, 200) &&
        text(e.note) &&
        Array.isArray(e.observations) &&
        e.observations.length <= (calibrated ? 20 : 2),
    );
    const purposes = new Set(),
      ids = new Set();
    for (const raw of e.observations) {
      const s = object(raw),
        { purpose, performed_on, ...legacySet } = s;
      if (calibrated) validateMeasurement(s);
      const set = calibrated ? actualSet(s as unknown as Observation) : legacySet;
      const purposeKey = calibrated ? `${s.side}:${s.trial_number}` : purpose;
      check(
        (calibrated ? ["calibration", "quality", "repeatability"] : ["practice", "reference"]).includes(String(purpose)) &&
          !purposes.has(purposeKey) &&
          !ids.has(s.id) &&
          validDay(performed_on),
      );
      purposes.add(purposeKey);
      ids.add(s.id);
      // Reuse the exact persisted set contract, including null/zero and load meaning.
      readData(
        {
          timezone_name: "UTC",
          assessment_date: performed_on,
          program_reference: null,
          goal_label: "",
          state_change: "unknown",
          state_notes: "",
          experience: "unknown",
          strength_frequency: "unknown",
          last_strength_date: null,
          usual_strength_minutes: null,
          supervision: "unknown",
          default_location_id: null,
          sports: [],
          exercises: [
            {
              id: e.entry_id,
              pattern: "core",
              exercise_id: null,
              location_id: null,
              familiarity: "unknown",
              comfort: "unknown",
              performed_on,
              side: e.side,
              machine_note: e.machine_note,
              notes: "",
              sets: [set],
            },
          ],
          sport_references: [],
          references_reviewed: false,
          reviewed: false,
        },
        draft,
      );
    }
    check(
      ["unknown", "both", "left", "right", "alternating"].includes(
        String(e.side),
      ),
    );
  }
  return c as unknown as Command;
}
async function readArtifact(value: unknown, owner: string): Promise<Artifact> {
  const a = object(value),
    { content_hash, ...body } = a,
    p = readCommand(a.proposal);
  check(
    a.schema_version === (p.protocol_version ? calibrationSchema : schema) &&
      a.rules_version === (p.protocol_version ? calibrationRules : rules) &&
      a.athlete_id === owner &&
      uuid(a.session_id) &&
      instant(a.created_at) &&
      Number.isInteger(a.revision) &&
      Number(a.revision) >= 1 &&
      a.artifact_id ===
        `pt-guided-strength:${owner.replaceAll("-", "")}:${p.request_id.replaceAll("-", "")}` &&
      ["active", "finished", "abandoned"].includes(String(a.state)) &&
      a.planning_authorized === false &&
      a.clinical_clearance === false &&
      (await sha(body)) === content_hash &&
      (a.base_reference === null || reference(a.base_reference)) &&
      (a.revision === 1) === (p.action === "start") &&
      (a.state === "finished") === ["finish", "apply"].includes(p.action) &&
      (a.state === "abandoned") === (p.action === "abandon"),
  );
  if (p.action === "start") {
    check(
      a.base_reference === null &&
        a.application_context === null &&
        a.result === null,
    );
    const intake = await readIntake(a.intake_context);
    check(
      intake.athlete_id === owner &&
        same(prepare(intake), a.preparation) &&
        same(intake.reference, p.assessment_reference) &&
        intake.sources.source_hash === p.source_hash &&
        p.precheck_confirmed,
    );
    const prepared = prepare(intake),
      place = prepared.locations.find((v) => v.location_id === p.location_id);
    check(
      !prepared.issues.length &&
        place &&
        p.selected_entry_ids.every((id) =>
          place.entries.some((e) => e.entry_id === id && e.ready),
        ) &&
        new Set(
          place.entries
            .filter((e) => p.selected_entry_ids.includes(e.entry_id))
            .map((e) => e.pattern),
        ).size === p.selected_entry_ids.length &&
        !p.progress.warmup_completed &&
        p.progress.phase === "warmup" &&
        p.progress.results.every(
          (r) => !r.observations.length && r.state === "pending",
        ),
    );
    if (p.protocol_version) check(same(a.measurement_protocols, await selectedProtocols(intake.data!, p.selected_entry_ids, p.measurement_mode, p.protocol_hash)));
  } else
    check(
      a.intake_context === null &&
        a.preparation === null &&
        a.base_reference !== null,
    );
  return a as unknown as Artifact;
}
export async function readReceipt(
  value: unknown,
  owner: string,
  body?: string,
): Promise<Receipt> {
  const r = object(value),
    a = await readArtifact(r.artifact, owner);
  check(
    r.committed === true &&
      typeof r.reused === "boolean" &&
      instant(r.durable_available_at) &&
      r.planning_authorized === false &&
      r.clinical_clearance === false &&
      (!body || same(a.proposal, readCommand(JSON.parse(body)))),
  );
  const base = r.base === null ? a : await readArtifact(r.base, owner);
  check(
    base.revision === 1 &&
      base.session_id === a.session_id &&
      (a.revision === 1
        ? r.base === null
        : same(a.base_reference, ref(base))) &&
      same(a.proposal.selected_entry_ids, base.proposal.selected_entry_ids) &&
      a.proposal.location_id === base.proposal.location_id &&
      a.proposal.recording_mode === base.proposal.recording_mode &&
      Date.parse(a.created_at) >= Date.parse(base.created_at),
  );
  check(a.proposal.protocol_version === base.proposal.protocol_version && a.proposal.protocol_hash === base.proposal.protocol_hash && a.proposal.measurement_mode === base.proposal.measurement_mode);
  if (a.proposal.protocol_version) {
    check(a.proposal.protocol_hash === base.measurement_protocols?.protocol_hash && (a.revision === 1 || a.measurement_protocols === null));
    const { validateCalibrationProgress } = await import("./calibration-validation");
    validateCalibrationProgress(a.proposal, base.measurement_protocols!, base.created_at, a.created_at, base.intake_context!.timezone_name);
  }
  if (a.proposal.action !== "apply")
    check(
      same(
        a.proposal.assessment_reference,
        base.proposal.assessment_reference,
      ) && a.proposal.source_hash === base.proposal.source_hash,
    );
  const proof = await readActivity(r.activity_receipt, owner);
  check(
    same(proof.artifact.guided_reference, ref(a)) &&
      proof.artifact.state === a.state &&
      proof.artifact.session_id === a.session_id &&
      proof.artifact.stop_required === stopped(a.proposal.progress),
  );
  if (a.state === "finished") {
    check(a.result !== null);
    const result = a.result,
      w = result.workout;
    check(
      uuid(result.workout_session_id) &&
        w.id === result.workout_session_id &&
        w.athlete_id === owner &&
        w.sport === "STRENGTH" &&
        instant(w.started_at) &&
        instant(w.ended_at) &&
        Date.parse(w.started_at) <= Date.parse(w.ended_at) &&
        Date.parse(w.ended_at) <= Date.parse(a.created_at) &&
        typeof result.workout_created === "boolean" &&
        result.stop_required === stopped(a.proposal.progress) &&
        result.application_pending === (result.assessment_reference === null) &&
        proof.artifact.workout_session_id === w.id &&
        same(proof.artifact.assessment_reference, result.assessment_reference),
    );
    if (result.workout_created)
      check(
        a.proposal.recording_mode === "manual" &&
          w.provider === "PADDLETRAINER_GUIDED" &&
          a.proposal.no_other_recording_confirmed &&
          Date.parse(w.started_at) ===
            Date.parse(a.proposal.actual_start_at!) &&
          Date.parse(w.ended_at) === Date.parse(a.proposal.actual_end_at!) &&
          w.duration_sec ===
            elapsedWholeSeconds(w.started_at, w.ended_at),
      );
    else
      check(
        a.proposal.recording_mode === "device" &&
          a.proposal.workout_session_id === w.id,
      );
    if (result.assessment_reference) {
      const initial = await readIntake(a.application_context),
        saved = await readAssessmentReceipt(r.assessment_receipt, owner);
      check(
        initial.data &&
          same(initial.reference, a.proposal.assessment_reference) &&
          initial.sources.source_hash === a.proposal.source_hash &&
          (!initial.sources_changed || registryExtension(initial)) &&
          same(ref(saved.artifact), result.assessment_reference) &&
          same(saved.artifact.proposal.previous_reference, initial.reference) &&
          same(
            saved.artifact.proposal.data,
            projectIntake(
              initial.data,
              a.proposal.progress,
              initial.local_today,
            ),
          ),
      );
    } else
      check(r.assessment_receipt === null && a.application_context === null);
  } else
    check(
      a.result === null &&
        a.application_context === null &&
        r.assessment_receipt === null &&
        proof.artifact.workout_session_id === null,
    );
  return r as unknown as Receipt;
}
export async function readContext(value: unknown): Promise<Context> {
  const c = object(value),
    { content_hash, ...body } = c;
  check(
    c.schema_version === schema &&
      uuid(c.athlete_id) &&
      instant(c.server_now) &&
      validDay(c.local_today) &&
      c.planning_authorized === false &&
      c.clinical_clearance === false &&
      (await sha(body)) === content_hash &&
      Array.isArray(c.recordings) &&
      Array.isArray(c.history),
  );
  const initial = await readIntake(c.intake);
  check(
    initial.athlete_id === c.athlete_id &&
      initial.timezone_name === c.timezone_name &&
      initial.local_today === c.local_today &&
      same(c.preparation, prepare(initial)),
  );
  if (c.calibration_protocols !== undefined) await readProtocolBank(c.calibration_protocols);
  if (c.latest !== null) await readReceipt(c.latest, c.athlete_id);
  const seen = new Set();
  for (const raw of c.history) {
    const h = object(raw);
    check(
      uuid(h.session_id) &&
        !seen.has(h.session_id) &&
        reference(
          h.reference,
          `pt-guided-strength:${c.athlete_id.replaceAll("-", "")}:`,
        ) &&
        instant(h.created_at) &&
        ["active", "finished", "abandoned"].includes(String(h.state)),
    );
    seen.add(h.session_id);
  }
  if (c.latest !== null)
    check(
      c.history.length &&
        same(
          object(c.history[0]).reference,
          ref(object(object(c.latest).artifact) as unknown as Artifact),
        ),
    );
  for (const raw of c.recordings) {
    const w = object(raw);
    check(
      uuid(w.id) &&
        w.sport === "STRENGTH" &&
        instant(w.started_at) &&
        (w.ended_at === null || instant(w.ended_at)) &&
        (w.duration_sec === null ||
          (Number.isInteger(w.duration_sec) && Number(w.duration_sec) >= 0)),
    );
  }
  return c as unknown as Context;
}
export function readPending(raw: string, owner: string): Pending {
  const p = object(JSON.parse(raw));
  check(
    p.version === "guided-strength-pending-v0.1" &&
      p.owner === owner &&
      typeof p.body === "string",
  );
  const c = readCommand(JSON.parse(p.body));
  check(
    c.assessment_reference.artifact_id.startsWith(
      `pt-initial-assessment:${owner.replaceAll("-", "")}:`,
    ),
  );
  return p as unknown as Pending;
}
export function readDraft(raw: string, owner: string, parent: Ref): Command {
  const d = object(JSON.parse(raw));
  check(
    d.version === "guided-strength-draft-v0.1" &&
      d.owner === owner &&
      same(d.parent, parent),
  );
  return readCommand(d.command, true);
}
