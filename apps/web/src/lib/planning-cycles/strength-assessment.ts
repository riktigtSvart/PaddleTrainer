import { canonical, object, sha } from "./contracts";
import { verifyAssessmentOptions } from "./assessment-options";
import {assessmentProfileContent,strengthProfileContent,verifyAssessmentProfile} from "./assessment-profile";
import type {ProfileComparison} from "./assessment-profile";
import {compareAssessmentSources,verifySourceComparison} from "./assessment-source-changes";
import type {SourceComparison} from "./assessment-source-changes";
import {
  readAssessmentReceipt,
  sourceBody,
  summarize,
} from "@/lib/initial-assessment/contracts";
import type {
  AssessmentReceipt,
  Exercise,
  Ref,
  SetRecord,
} from "@/lib/initial-assessment/contracts";
import { availableExercises } from "@/lib/training-options/strength-catalog";

import {
  readActivity,
  ref as activityRef,
  same as activitySame,
} from "@/lib/guided-strength/activity";
import type { ActivityReceipt } from "@/lib/guided-strength/activity";
import { readReceipt as readGuidedReceipt } from "@/lib/guided-strength/contracts";
import type { Receipt as GuidedReceipt } from "@/lib/guided-strength/contracts";
import { starterTargets } from "@/lib/guided-strength/calibration";
import type { StarterTarget } from "@/lib/guided-strength/calibration";
type Row = Record<string, unknown>;
export const strengthSchema = "training-strength-assessment-v0.1";
export const strengthRules = "assessment-strength-start-v0.1";
const patterns = ["pull", "push", "knee", "hip", "core"];
export type StrengthEvidence = {
  schema_version: typeof strengthSchema;
  rules_version: typeof strengthRules;
  athlete_id: string;
  source_body: ReturnType<typeof sourceBody>;
  source_hash: string;
  receipt: AssessmentReceipt | null;
  guided_activities?: ActivityReceipt[];
  calibration_evidence?: GuidedReceipt[];
  source_comparison?: SourceComparison;
  profile_comparison?: ProfileComparison;
  planning_authorized: false;
  workouts_changed: false;
  automatic_progression_applied: false;
  personal_response_model_applied: false;
};
export type StrengthMovement = {
  entry_id: string;
  exercise_id: string | null;
  label: string;
  pattern: string;
  location_id: string | null;
  performed_on: string | null;
  side: Exercise["side"];
  machine_note: string;
  sets: SetRecord[];
};
export type AssessedStrengthDose = {
  schema_version: "assessed-strength-dose-v0.1";
  rules_version: typeof strengthRules;
  assessment_reference: Ref;
  source_kind: "self_report";
  movements: StrengthMovement[];
  max_sets_per_movement: 2;
  rest_seconds: 120 | 180;
  calibration_derivations?: (StarterTarget["derivation"] & { entry_id: string })[];
  minimum_rir: 3;
  load_increased: false;
  sets_added: false;
  one_rm_estimated: false;
  full_development_claim: false;
};
export type StrengthReadiness = Omit<StrengthMovement, "sets"> & {
  eligible: boolean;
  reasons: string[];
  calibration_derivation?: StarterTarget["derivation"];
};
function calibrationTargets(context: StrengthEvidence) {
  const targets = new Map<string, StarterTarget>(), measuredIds = new Set<string>();
  for (const r of [...(context.calibration_evidence ?? [])].reverse()) {
    for (const row of r.artifact.proposal.progress.results)
      for (const s of row.observations) if (s.performed_confirmed) measuredIds.add(s.id);
    for (const target of starterTargets(r)) targets.set(target.entry_id, target);
  }
  return { targets, measuredIds };
}
export type StrengthAssessmentSummary = {
  schema_version: typeof strengthSchema;
  rules_version: typeof strengthRules;
  reference: Ref | null;
  issues: string[];
  exercise_readiness: StrengthReadiness[];
  source_kind: "self_report";
  automatic_progression_applied: false;
  personal_response_model_applied: false;
  workouts_changed: false;
};
export const strengthReasons: Record<string, string> = {
  STRENGTH_ASSESSMENT_MISSING:
    "Még nincs szerverre mentett kezdeti erőfelmérés.",
  STRENGTH_ASSESSMENT_SOURCES_CHANGED:
    "A profil, helyszínek vagy felkészülések változtak. Vedd át a friss forrásokat a kezdeti felmérésben, nézd át a válaszokat, majd mentsd újra.",
  STRENGTH_ASSESSMENT_PROGRAM_MISMATCH:
    "A mentett felmérés másik felkészüléshez tartozik. Válaszd ki az aktuális felkészülést, vagy az általános felmérést.",
  STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED:
    "A felmérésben az Erősítés / kondi fő vagy kiegészítő szereppel, a felkészülés sportága fő szereppel szerepeljen.",
  STRENGTH_ASSESSMENT_REVIEW_REQUIRED:
    "A kezdeti felmérésben tekintsd át az ismert teljesítéseket és az összegzést, majd mentsd a válaszokat.",
  STRENGTH_ASSESSMENT_STATE_REVIEW:
    "Az állapotváltozás vagy a személyes profil keretei egyeztetést igényelnek.",
  STRENGTH_ASSESSMENT_HISTORY_REVIEW:
    "Az erőedzés-múlt, a gyakoriság vagy a felügyelet még pontosítandó. Betanulási igényből nem készül önálló erőedzés.",
  STRENGTH_NAMED_LOCATION_REQUIRED:
    "Ehhez az erőmintához válassz névvel mentett edzési helyszínt.",
  STRENGTH_TWO_PATTERNS_REQUIRED:
    "Ezen a helyszínen legalább két különböző mozgásmintához kell használható saját gyakorlatreferencia.",
  STRENGTH_MOVEMENT_SYMPTOMS:
    "A gyakorlatnál panasz szerepel. Egy másik panaszmentes sorozat ezt nem oldja fel.",
  STRENGTH_EXECUTION_SIDE_REQUIRED:
    "Add meg az oldalt / végrehajtást az Ismert teljesítések lépésben.",
  STRENGTH_QUALIFYING_SET_REQUIRED:
    "Az induló szabályhoz 1–15 ismétlés vagy legfeljebb 60 másodperc tartás, stabil, panaszmentes sorozat és legalább 3 jelzett ismétléstartalék szükséges. A teher jelentése és gépfokozatnál a konkrét gép/beállítás is szükséges.",
  STRENGTH_REFERENCE_AT_OTHER_LOCATION:
    "A referencia másik helyszínen történt; a tervező nem viszi át automatikusan ide.",
  STRENGTH_LOCATION_EQUIPMENT_MISSING:
    "A kiválasztott helyszínen nincs meg a gyakorlat teljes felszerelése.",
  EXERCISE_MISSING: "Még nincs kiválasztott gyakorlat.",
  INSTRUCTION_OR_FAMILIARITY_NEEDED:
    "A jártasság vagy technikai betanulás még pontosítandó.",
  COMFORT_UNRESOLVED: "A mozgás közbeni komfort még nem tisztázott.",
  LOCATION_REVIEW:
    "A referencia helyszíne vagy erősítési lehetősége még pontosítandó.",
  EQUIPMENT_MISSING:
    "A referencia helyszínének felszereléséből nem áll össze a gyakorlat.",
  RECENT_REFERENCE_MISSING:
    "Nincs ehhez a naphoz képest 56 napon belüli, dátummal ellátott saját referencia.",
  SET_REFERENCE_INCOMPLETE:
    "A sorozat megadott terhelése, ismétlése/tartási ideje, RIR-, technika- vagy panaszadata hiányos.",
};
const fail = () =>
  Error(
    "Az erőjavaslat mentett felmérése vagy a belőle származó sorozatok nem ellenőrizhetők.",
  );
const check = (v: unknown) => {
  if (!v) throw fail();
};
const ref = (r: { artifact_id: string; content_hash: string }): Ref => ({
  artifact_id: r.artifact_id,
  content_hash: r.content_hash,
});
const programSport = (value: unknown) =>
  Object.entries({
    KAYAK: ["kajak", "kayak", "kayaking", "kayak_flatwater"],
    RUNNING: ["futás", "futas", "run", "running"],
    STRENGTH: ["erőnlét", "erőedzés", "erősítés", "strength", "kondi"],
  }).find(([, a]) =>
    a.includes(String(value).trim().toLocaleLowerCase("hu")),
  )?.[0];
export function globalIssues(context: StrengthEvidence, inputs: Row) {
  const a = context.receipt?.artifact,
    value = a?.proposal.data;
  if (!value || !a) return ["STRENGTH_ASSESSMENT_MISSING"];
  const issues = [];
  if (a.proposal.source_hash !== context.source_hash && !(context.source_comparison&&compareAssessmentSources(context as unknown as Row).reusable))
    issues.push("STRENGTH_ASSESSMENT_SOURCES_CHANGED");
  if (
    value.program_reference !== null &&
    canonical(value.program_reference) !== canonical(inputs.program_reference)
  )
    issues.push("STRENGTH_ASSESSMENT_PROGRAM_MISMATCH");
  const roles = Object.fromEntries(
    value.sports.map((v) => [v.sport_key, v.role]),
  );
  if (
    !["primary", "secondary"].includes(roles.STRENGTH) ||
    roles[programSport(inputs.program_sport) ?? ""] !== "primary"
  )
    issues.push("STRENGTH_ASSESSMENT_SPORT_ROLE_REQUIRED");
  if (!value.reviewed || !value.references_reviewed)
    issues.push("STRENGTH_ASSESSMENT_REVIEW_REQUIRED");
  if (value.state_change !== "unchanged")
    issues.push("STRENGTH_ASSESSMENT_STATE_REVIEW");
  if (
    value.experience === "unknown" ||
    (value.experience === "none" &&
      !(context.guided_activities ?? []).some(
        (p) =>
          p.artifact.state === "finished" &&
          activitySame(p.artifact.assessment_reference, activityRef(a)),
      )) ||
    value.strength_frequency === "unknown" ||
    ["unknown", "needed"].includes(value.supervision)
  )
    issues.push("STRENGTH_ASSESSMENT_HISTORY_REVIEW");
  if (a.snapshot.profile_review?.global_entry_gate !== "OPEN")
    issues.push("STRENGTH_ASSESSMENT_STATE_REVIEW");
  return [...new Set(issues)];
}
export function usableSets(entry: Exercise) {
  return entry.sets
    .filter((s) => {
      const dose =
        (s.repetitions !== null && s.repetitions >= 1 && s.repetitions <= 15) ||
        (s.hold_seconds !== null &&
          Number(s.hold_seconds) > 0 &&
          Number(s.hold_seconds) <= 60);
      const load =
        s.load_kind === "bodyweight" ||
        (s.load_kind === "band" && !!s.load_note.trim()) ||
        (["external_kg", "machine_level"].includes(s.load_kind) &&
          s.load_value !== null &&
          Number(s.load_value) > 0 &&
          s.load_basis !== "unknown") ||
        (s.load_kind === "assistance_kg" &&
          s.load_value !== null &&
          s.load_basis === "assistance");
      const machine =
        ["machine_level", "assistance_kg"].includes(s.load_kind) ||
        s.load_basis === "machine_display";
      return (
        dose &&
        load &&
        (!machine || !!entry.machine_note.trim()) &&
        ["3", "4", "5_plus"].includes(s.rir) &&
        s.technique === "stable" &&
        s.symptoms === "none"
      );
    })
    .slice(0, 2);
}
export function evaluateStrength(
  context: StrengthEvidence,
  inputs: Row,
  day: string,
  location?: string,
  resources: string[] = [],
) {
  const issues = globalIssues(context, inputs),
    a = context.receipt?.artifact;
  const entries: (StrengthMovement & {
    eligible: boolean;
    reasons: string[];
    calibration_derivation?: StarterTarget["derivation"];
  })[] = [];
  const { targets, measuredIds } = calibrationTargets(context);
  if (a) {
    const summary = summarize(a.proposal.data, a.snapshot, day),
      place = a.snapshot.locations.find((p) => p.id === location),
      available = new Set(
        place
          ? availableExercises(a.snapshot.catalog, place, resources).map(
              (e) => e.id,
            )
          : [],
      );
    for (const e of a.proposal.data.exercises) {
      const state = summary.exercise_states.find((v) => v.id === e.id)!,
        reasons = [...state.reasons];
      if (state.state === "avoid") reasons.push("STRENGTH_MOVEMENT_SYMPTOMS");
      if (e.side === "unknown")
        reasons.push("STRENGTH_EXECUTION_SIDE_REQUIRED");
      let sets = usableSets(e);
      const target = targets.get(e.id);
      if (e.sets.some((s) => measuredIds.has(s.id))) {
        const matches = target && ["exercise_id", "location_id", "performed_on", "side", "machine_note"].every((k) => e[k as keyof Exercise] === target[k as keyof StarterTarget]) && canonical(e.sets) === canonical(target.actual_sets);
        sets = matches ? target.sets : [];
      }
      if (!sets.length) reasons.push("STRENGTH_QUALIFYING_SET_REQUIRED");
      if (location !== undefined) {
        if (e.location_id !== location)
          reasons.push("STRENGTH_REFERENCE_AT_OTHER_LOCATION");
        if (!e.exercise_id || !available.has(e.exercise_id))
          reasons.push("STRENGTH_LOCATION_EQUIPMENT_MISSING");
      }
      const label =
        e.exercise_id !== null
          ? a.snapshot.catalog.exercises.find((x) => x.id === e.exercise_id)!
              .label
          : a.snapshot.registry.patterns.find((p) => p.key === e.pattern)!
              .label;
      entries.push({
        entry_id: e.id,
        exercise_id: e.exercise_id,
        label,
        pattern: e.pattern,
        location_id: e.location_id,
        performed_on: e.performed_on,
        side: e.side,
        machine_note: e.machine_note,
        eligible:
          !issues.length &&
          !reasons.length &&
          state.state === "recorded_reference",
        reasons: [...new Set(reasons)],
        sets,
        ...(target && canonical(sets) === canonical(target.sets) ? { calibration_derivation: target.derivation } : {}),
      });
    }
  }
  return { issues, entries };
}
export function strengthSummary(
  context: StrengthEvidence,
  inputs: Row,
  today: string,
): StrengthAssessmentSummary {
  const value = evaluateStrength(context, inputs, today);
  return {
    schema_version: strengthSchema,
    rules_version: strengthRules,
    reference: context.receipt ? ref(context.receipt.artifact) : null,
    issues: value.issues,
    exercise_readiness: value.entries.map((e) => ({
      entry_id: e.entry_id,
      exercise_id: e.exercise_id,
      label: e.label,
      pattern: e.pattern,
      location_id: e.location_id,
      performed_on: e.performed_on,
      side: e.side,
      machine_note: e.machine_note,
      eligible: e.eligible,
      reasons: e.reasons,
      ...(e.calibration_derivation ? { calibration_derivation: e.calibration_derivation } : {}),
    })),
    source_kind: "self_report",
    automatic_progression_applied: false,
    personal_response_model_applied: false,
    workouts_changed: false,
  };
}
export async function validateStrengthAssessment(
  review: Row,
): Promise<StrengthEvidence | null> {
  const result = object(review.result),
    inputs = object(review.inputs),
    version = object(result.prescription_context ?? {}).schema_version;
  if (!["training-prescriptions-v0.2", "training-prescriptions-v0.3", "training-prescriptions-v0.4"].includes(String(version))) {
    check(
      !["training-plan-policy-v0.7", "training-plan-policy-v0.8", "training-plan-policy-v0.9", "training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(
        String(object(result.policy ?? {}).version),
      ) &&
        inputs.strength_assessment === undefined &&
        result.strength_assessment === undefined,
    );
    return null;
  }
  const context = object(
      inputs.strength_assessment,
    ) as unknown as StrengthEvidence,
    body = object(context.source_body);
  check(
    context.schema_version === strengthSchema &&
      context.rules_version === strengthRules &&
      context.athlete_id === review.athlete_id &&
      context.planning_authorized === false &&
      context.workouts_changed === false &&
      context.automatic_progression_applied === false &&
      context.personal_response_model_applied === false &&
      (await sha(body)) === context.source_hash &&
      body.timezone_name === review.timezone_name,
  );
  const modern =
    ["training-plan-policy-v0.8", "training-plan-policy-v0.9", "training-plan-policy-v0.10", "training-plan-policy-v0.11", "training-plan-policy-v0.12", "training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy ?? {}).version));
  if (modern) {
    check(Array.isArray(context.guided_activities));
    const sessions = new Set<string>(),
      workouts = new Set<string>();
    for (const raw of context.guided_activities ?? []) {
      const proof = await readActivity(
          raw,
          String(review.athlete_id),
          String(inputs.captured_at),
        ),
        a = proof.artifact;
      check(!sessions.has(a.session_id));
      sessions.add(a.session_id);
      if (a.state === "finished") {
        check(a.workout_session_id && !workouts.has(a.workout_session_id));
        workouts.add(String(a.workout_session_id));
      }
    }
    check(Array.isArray(inputs.recent_sessions));
    for (const raw of inputs.recent_sessions as unknown[]) {
      const s = object(raw);
      check(
        workouts.has(String(s.id))
          ? s.reference_occasion === true && s.sport === "STRENGTH"
          : s.reference_occasion === undefined,
      );
    }
    const { content_hash, ...raw } = inputs;
    check((await sha(raw)) === content_hash);
  } else check(context.guided_activities === undefined);
  const profile =
    inputs.profile === null ? null : object(object(inputs.profile).reference);
  if(["training-plan-policy-v0.13","training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version)))check(context.profile_comparison);
  await verifyAssessmentProfile(inputs,body,context as unknown as Row,String(review.athlete_id));
  await verifyAssessmentOptions(inputs, body, context as unknown as Row, String(review.athlete_id));
  check(
    Array.isArray(body.programs) &&
      body.programs.some(
        (p) =>
          canonical(object(p).reference) ===
          canonical(inputs.program_reference),
      ),
  );
  if (context.receipt !== null) {
    await readAssessmentReceipt(context.receipt, String(review.athlete_id));
    if(context.source_comparison||["training-plan-policy-v0.12","training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version)))await verifySourceComparison(context as unknown as Row,inputs,String(review.athlete_id));
    if (context.receipt.artifact.proposal.source_hash === context.source_hash || context.source_comparison?.reusable) {
      const currentProfile = inputs.profile === null ? null : object(inputs.profile).data;
      const savedProfile = context.receipt.artifact.snapshot.profile_receipt?.artifact.proposal.data ?? null;
      const sameReference = canonical(body.profile_reference) === canonical(profile ? {artifact_id:profile.artifact_id,content_hash:profile.content_hash}:null);
      const projection=context.profile_comparison?strengthProfileContent:assessmentProfileContent;
      check(canonical(sameReference || !currentProfile ? currentProfile : projection(currentProfile)) ===
        canonical(sameReference || !savedProfile ? savedProfile : projection(savedProfile)));
    }
    check(
      Date.parse(context.receipt.artifact.created_at) <=
        Date.parse(String(inputs.captured_at)) &&
        Date.parse(context.receipt.durable_available_at) <=
          Date.parse(String(inputs.captured_at)),
    );
  }
  else if(["training-plan-policy-v0.12","training-plan-policy-v0.13", "training-plan-policy-v0.14", "training-plan-policy-v0.15"].includes(String(object(result.policy).version)))await verifySourceComparison(context as unknown as Row,inputs,String(review.athlete_id));
  const expectedCalibrations = new Set((context.guided_activities ?? []).filter((p) => p.artifact.measurement_protocol_version && p.artifact.state === "finished" && p.artifact.assessment_reference).map((p) => p.artifact.session_id));
  if (expectedCalibrations.size) check(Array.isArray(context.calibration_evidence));
  const calibrationSessions = new Set<string>();
  for (const raw of context.calibration_evidence ?? []) {
    const r = await readGuidedReceipt(raw, String(review.athlete_id)), a = r.artifact;
    check(a.schema_version === "guided-strength-session-v0.2" && a.state === "finished" && a.result?.assessment_reference &&
      !calibrationSessions.has(a.session_id) && expectedCalibrations.has(a.session_id) &&
      Date.parse(a.created_at) <= Date.parse(String(inputs.captured_at)) && Date.parse(r.durable_available_at) <= Date.parse(String(inputs.captured_at)));
    calibrationSessions.add(a.session_id);
    const proof = context.guided_activities!.find((p) => p.artifact.session_id === a.session_id)!;
    check(canonical(proof.artifact.guided_reference) === canonical(ref(a)) && proof.artifact.workout_session_id === a.result!.workout_session_id && canonical(proof.artifact.assessment_reference) === canonical(a.result!.assessment_reference));
  }
  check(expectedCalibrations.size === calibrationSessions.size);
  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: String(review.timezone_name),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(String(inputs.captured_at)));
  check(
    canonical(result.strength_assessment) ===
      canonical(strengthSummary(context, inputs, today)),
  );
  return context;
}
export function selectStrength(
  context: StrengthEvidence,
  inputs: Row,
  day: string,
  location: string,
  resources: string[],
) {
  const value = evaluateStrength(context, inputs, day, location, resources);
  check(!value.issues.length);
  const offset =
    (Math.floor(Date.parse(day + "T00:00:00Z") / 86400000) + 719163) %
    patterns.length;
  const priority = [...patterns.slice(offset), ...patterns.slice(0, offset)];
  const eligible = value.entries
    .filter((e) => e.eligible)
    .sort(
      (a, b) =>
        priority.indexOf(a.pattern) - priority.indexOf(b.pattern) ||
        String(b.performed_on).localeCompare(String(a.performed_on)) ||
        (a.exercise_id! < b.exercise_id!
          ? -1
          : a.exercise_id! > b.exercise_id!
            ? 1
            : 0) ||
        (a.entry_id < b.entry_id ? -1 : 1),
    );
  const used = new Set(),
    chosen: StrengthMovement[] = [];
  for (const e of eligible) {
    if (!used.has(e.pattern)) {
      used.add(e.pattern);
      chosen.push({
        entry_id: e.entry_id,
        exercise_id: e.exercise_id,
        label: e.label,
        pattern: e.pattern,
        location_id: e.location_id,
        performed_on: e.performed_on,
        side: e.side,
        machine_note: e.machine_note,
        sets: e.sets,
      });
    }
    if (chosen.length === 2) break;
  }
  check(chosen.length === 2);
  return chosen;
}
export function strengthDuration(
  recordedCap: number | null,
  declared: number | null,
) {
  const caps = [recordedCap, declared === null ? null : declared * 60].filter(
    (v): v is number => v !== null,
  );
  return {
    cap: caps.length ? Math.min(...caps) : 1200,
    productDefault: !caps.length,
  };
}
export function strengthDose(
  context: StrengthEvidence,
  movements: StrengthMovement[],
): AssessedStrengthDose {
  const { targets } = calibrationTargets(context);
  const derivations = movements.flatMap((e) => {
    const target = targets.get(e.entry_id);
    return target && canonical(e.sets) === canonical(target.sets) ? [{ entry_id: e.entry_id, ...target.derivation }] : [];
  });
  return {
    schema_version: "assessed-strength-dose-v0.1",
    rules_version: strengthRules,
    assessment_reference: ref(context.receipt!.artifact),
    source_kind: "self_report",
    movements,
    max_sets_per_movement: 2,
    rest_seconds: derivations.length ? 180 : 120,
    ...(derivations.length ? { calibration_derivations: derivations } : {}),
    minimum_rir: 3,
    load_increased: false,
    sets_added: false,
    one_rm_estimated: false,
    full_development_claim: false,
  };
}
export function strengthPresentation(
  dose: AssessedStrengthDose,
  seconds: number,
) {
  const basis: Record<string, string> = {
      total: "összsúly",
      per_hand: "kézenként",
      machine_display: "gép kijelzése",
      assistance: "rásegítés",
      not_applicable: "",
      unknown: "",
    },
    sides: Record<string, string> = {
      both: "kétoldali",
      left: "bal oldal",
      right: "jobb oldal",
      alternating: "váltott oldal",
    };
  const texts = dose.movements.map(
    (e) =>
      `${e.label} (${sides[e.side]}): ` +
      e.sets
        .map((s) => {
          const amount =
            s.repetitions !== null
              ? `${s.repetitions} ismétlés`
              : `${s.hold_seconds} másodperc`;
          const load =
            s.load_kind === "bodyweight"
              ? "saját testsúly"
              : s.load_kind === "band"
                ? s.load_note
                : `${s.load_value} ${s.load_kind === "machine_level" ? "fokozat" : "kg"} · ${dose.calibration_derivations?.some((d) => d.entry_id === e.entry_id && d.load_kind === "machine_plate_components") ? "felrakott tárcsák össztömege" : basis[s.load_basis]}`;
          return `${amount}, ${load}`;
        })
        .join("; ") +
      (e.machine_note ? `. Gép/beállítás: ${e.machine_note}` : ""),
  );
  return {
    title: dose.calibration_derivations?.length ? `Erőfelmérésből induló edzés · ${seconds / 60} perces időkeret` : `Saját erőreferenciák · ${seconds / 60} perces időkeret`,
    description:
      dose.calibration_derivations?.length ? "5 perc ismert bemelegítés. " + texts.join(" | ") +
        ". Az új kalibrálásból gyakorlatonként egy kezdő sorozat készült: a mért ismétlésszámnál kettővel kevesebb, legfeljebb nyolc ismétlés, azonos terheléssel. " +
        "Ez felülvizsgálható kezdő alkalmazásszabály, nem mért sorozatkapacitás. A sorozatok között 3 perc pihenő. " +
        "Legalább 3 szabályos ismétlés tartalék maradjon; ha ez nem tartható, előbb állj meg. Panasz vagy romló kontroll esetén hagyd el a hátralévő részt. " +
        "5 perc levezetés. Az időkeret felső határ, nem kitöltendő munkamennyiség. Nincs automatikus súly- vagy sorozatszám-emelés." : "5 perc ismert bemelegítés. " +
      texts.join(" | ") +
      ". Sorozatok között legalább 2 perc nyugodt pihenő; az ismétléses sorozatoknál legalább 3 szabályos ismétlés tartalék maradjon. A tartás is maradjon kényelmes, kifáradás nélkül. Ha a technika romlik, panasz jelentkezik vagy elfogy a kényelmes idő, hagyd el a hátralévő részt. 5 perc levezetés. Az időkeret a pihenőket is tartalmazza; nem kitöltendő munkadózis. A súlyok és sorozatok a mentett saját referenciából származnak; nincs automatikus emelés.",
    names: [
      "Ismert bemelegítés",
      dose.movements.map((e) => e.label).join(" / ") +
        " · rögzített sorozatok, pihenőkkel",
      "Levezetés és terhelésnapló",
    ],
  };
}
export async function validateStrengthCandidate(
  context: StrengthEvidence,
  inputs: Row,
  candidate: Row,
) {
  const days = (inputs.days as unknown[]).map(object),
    d = days.find((d) => d.date === candidate.date);
  check(d && Array.isArray(d.opportunities));
  const group = (d!.opportunities as unknown[])
      .map(object)
      .find((g) => g.key === candidate.opportunity_key),
    constraints = object(group?.constraints);
  check(
    group &&
      typeof candidate.location_id === "string" &&
      constraints.location_id === candidate.location_id &&
      constraints.location === candidate.location &&
      ["moderate", "any"].includes(String(constraints.effort_cap)) &&
      Array.isArray(constraints.resources),
  );
  check(
    constraints.sport_scope === "any" ||
      (constraints.sport_scope === "specified" &&
        (constraints.sports as string[]).some(
          (s) => programSport(s) === "STRENGTH",
        )),
  );
  const place = context.receipt?.artifact.snapshot.locations.find(
    (p) => p.id === candidate.location_id,
  );
  check(
    place &&
      !place.archived &&
      place.sports.includes("STRENGTH") &&
      canonical(context.source_comparison?[...new Set(place.resources.map(r=>r.trim().toLowerCase()))].sort():place.resources) ===
      canonical(context.source_comparison?[...new Set((constraints.resources as string[]).map(r=>r.trim().toLowerCase()))].sort():constraints.resources),
  );
  const movements = selectStrength(
      context,
      inputs,
      String(candidate.date),
      String(candidate.location_id),
      constraints.resources as string[],
    ),
    dose = strengthDose(context, movements),
    presentation = strengthPresentation(dose, Number(candidate.duration_sec));
  check(
    canonical(candidate.strength_prescription) === canonical(dose) &&
      candidate.template_version === "v0.3" &&
      candidate.title === presentation.title &&
      candidate.description === presentation.description,
  );
  check(
    (candidate.blocks as unknown[])
      .map(object)
      .every((b, i) => b.name === presentation.names[i]),
  );
  check(
    Number(candidate.duration_sec) <= Number(group!.max_minutes) * 60 &&
      (d!.daily_max_minutes === null ||
        Number(candidate.duration_sec) <= Number(d!.daily_max_minutes) * 60),
  );
  check(
    (group!.intervals as unknown[])
      .map(object)
      .some(
        (i) =>
          Date.parse(String(i.start_at)) <=
            Date.parse(String(candidate.start_at)) &&
          Date.parse(String(candidate.end_at)) <= Date.parse(String(i.end_at)),
      ),
  );
  return dose;
}
