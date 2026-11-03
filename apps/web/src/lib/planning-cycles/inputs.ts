import type { Suggestions } from "./goal-suggestions";
import type { Period } from "@/lib/planning-goals/types";
import { addDays, sha } from "./contracts";
import type { Reference } from "./contracts";
export type InputDay = {
  date: string;
  availability_state:
    "unknown" | "declared_unavailable" | "opportunities" | "blocked";
  mesocycle_id: string | null;
  capability_roles: { capability_key: string; role: string }[];
  opportunities: unknown[];
};
export type PlanningInputs = {
  goal_suggestions?: Suggestions;
  periods: Period[];
  schema_version: "planning-inputs-v0.1";
  athlete_id: string;
  program_reference: Reference;
  timezone_name: string;
  captured_at: string;
  start_date: string;
  end_date: string;
  days: InputDay[];
  gaps: string[];
  recent_sessions: unknown[];
  recovery_records: unknown[];
  feedback: unknown[];
  profile: unknown;
  content_hash: string;
};
const object = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw Error("A tervezési adatok válasza hiányos.");
  return v as Record<string, unknown>;
};
export async function readPlanningInputs(
  value: unknown,
  expected: {
    owner: string;
    reference: Reference;
    zone: string;
    first: string;
    last: string;
  },
): Promise<PlanningInputs> {
  const v = object(value),
    p = object(v.program_reference),
    connection = object(v.planner_connection);
  const validDay = (s: unknown) =>
    typeof s === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(s) &&
    Number.isFinite(Date.parse(s + "T00:00:00Z")) &&
    new Date(s + "T00:00:00Z").toISOString().slice(0, 10) === s;
  if (
    v.schema_version !== "planning-inputs-v0.1" ||
    v.athlete_id !== expected.owner ||
    p.artifact_id !== expected.reference.artifact_id ||
    p.content_hash !== expected.reference.content_hash ||
    v.timezone_name !== expected.zone ||
    v.start_date !== expected.first ||
    v.end_date !== expected.last ||
    !validDay(v.start_date) ||
    !validDay(v.end_date) ||
    typeof v.captured_at !== "string" ||
    !/^\d{4}-.*(?:Z|[+-]\d\d:\d\d)$/.test(v.captured_at) ||
    !Number.isFinite(Date.parse(v.captured_at)) ||
    v.has_more !== false ||
    v.planning_authorized !== false ||
    v.workouts_created !== false ||
    v.workouts_changed !== false ||
    v.durable !== false ||
    v.revalidate_before_planning !== true ||
    v.historical_replay_supported !== false ||
    v.windows_share_budgets_across_days !== true ||
    connection.inputs_assembled !== true ||
    connection.workout_generator_connected !== false ||
    connection.dose_policy_connected !== false ||
    connection.personal_model_applied !== false
  )
    throw Error("A tervezési adatok azonosítója vagy hatásköre eltér.");
  const count =
    (Date.parse(expected.last) - Date.parse(expected.first)) / 86400000 + 1;
  if (
    !Number.isInteger(count) ||
    count < 1 ||
    count > 28 ||
    !Array.isArray(v.days) ||
    v.days.length !== count
  )
    throw Error("A tervezési napok listája hiányos.");
  for (let i = 0; i < count; i++) {
    const d = object(v.days[i]);
    if (
      d.date !== addDays(expected.first, i) ||
      !["unknown", "declared_unavailable", "opportunities", "blocked"].includes(
        String(d.availability_state),
      ) ||
      !(
        d.mesocycle_id === null ||
        (typeof d.mesocycle_id === "string" &&
          /^[0-9a-f-]{36}$/.test(d.mesocycle_id))
      ) ||
      !Array.isArray(d.opportunities) ||
      !Array.isArray(d.capability_roles)
    )
      throw Error("A napi tervezési adatok hibásak.");
    for (const item of d.capability_roles) {
      const role = object(item);
      if (
        typeof role.capability_key !== "string" ||
        ![
          "primary_development",
          "secondary_development",
          "maintenance",
          "permitted_decline",
        ].includes(String(role.role))
      )
        throw Error("A cél szerepe nem ellenőrizhető.");
    }
  }
  if (
    !Array.isArray(v.gaps) ||
    v.gaps.some((g) => typeof g !== "string") ||
    !Array.isArray(v.recent_sessions) ||
    !Array.isArray(v.recovery_records) ||
    !Array.isArray(v.feedback) ||
    !(v.profile === null || typeof v.profile === "object")
  )
    throw Error("A tervezési források felsorolása hiányos.");
  const { content_hash, ...body } = v;
  if (
    typeof content_hash !== "string" ||
    !/^[a-f0-9]{64}$/.test(content_hash) ||
    (await sha(body)) !== content_hash
  )
    throw Error("A tervezési adatok tartalomlenyomata eltér.");
  return v as unknown as PlanningInputs;
}
export async function loadPlanningInputs(
  expected: {
    owner: string;
    reference: Reference;
    zone: string;
    first: string;
    last: string;
  },
  signal: AbortSignal,
): Promise<PlanningInputs> {
  const query = new URLSearchParams({
    start_date: expected.first,
    end_date: expected.last,
  });
  const reply = await fetch(
    "/api/goal-workflow/cycles/programs/" +
      encodeURIComponent(expected.reference.artifact_id) +
      "/planning-inputs?" +
      query,
    { cache: "no-store", signal },
  );
  const text = await reply.text();
  if (text.length > 4 * 1024 * 1024)
    throw Error("A tervezési forráscsomag túl nagy.");
  if (!reply.ok)
    throw Error(
      "A tervezési alap nem olvasható. Ellenőrizd a kiválasztott felkészülést és az időszakot, majd próbáld újra.",
    );
  return readPlanningInputs(JSON.parse(text), expected);
}
export const inputGapLabels: Record<string, string> = {
  MEASUREMENT_PROTOCOL_PARENT_OUTDATED:
    "A mérési protokoll egy korábbi célváltozatra hivatkozik; felülvizsgálat szükséges.",
  GOAL_SOURCE_SNAPSHOT_CHANGED:
    "A célokhoz rögzített ciklusadatok azóta módosultak; felülvizsgálat szükséges.",
  PROFILE_NOT_RECORDED: "A sportolói profil még nincs rögzítve.",
  AVAILABILITY_PARTLY_UNKNOWN: "Egyes napok lehetősége még nem ismert.",
  MESOCYCLE_NOT_ASSIGNED_FOR_EVERY_DAY:
    "Az időszak nem minden napja tartozik a kiválasztott program mezociklusához.",
  CAPABILITY_ROLES_NOT_DECLARED:
    "A képességek mezocikluson belüli szerepei még nincsenek megadva.",
  NO_RECENT_SELF_REPORT: "Nincs közelmúltbeli személyes visszajelzés.",
  NO_RECENT_RECOVERY_RECORD: "Nincs közelmúltbeli regenerációs adatsor.",
  EXISTING_PLAN_CONFLICTS:
    "A meglévő edzéseknél időütközés vagy tisztázandó időpont szerepel.",
  PROGRAM_TIMEZONE_REVIEW: "A program eredeti időzónája eltér a jelenlegitől.",
};
