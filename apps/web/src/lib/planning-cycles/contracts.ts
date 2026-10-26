export type Mode = "olympic" | "season" | "race" | "recreation";
export type Reference = { artifact_id: string; content_hash: string };
export type BodyMassGoal = { current_kg: string; target_kg?: string };
export type GoalDetails = {
  version: "cycle-goal-fields-v0.1";
  direction: "improve" | "maintain" | null;
  weekly_sessions: number | null;
  event_keys: string[];
  result_target: string;
  notes: string;
};
export type AthleteContext = {
  profile_reference: Reference | null;
  availability_reference: Reference | null;
};
export type Goal = {
  key: string;
  target_description: string;
  body_mass?: BodyMassGoal;
  details?: GoalDetails;
};
export type EventProfile = {
  discipline: string;
  event_type:
    "sprint" | "endurance" | "technical" | "strength" | "mixed" | "other";
  distance_status: "specified" | "unknown" | "not_applicable";
  distance_value: string | null;
  distance_unit: "m" | "km" | null;
  expected_duration_minutes: string | null;
  course_description: string;
  capability_basis: "unassessed" | "coach_declared" | "icf_sprint_v0_1";
  capability_keys: string[];
};
export type Competition = {
  key: string;
  title: string;
  start_date: string;
  end_date: string;
  precision: "exact" | "window";
  priority: "main" | "supporting";
  status: "planned" | "cancelled";
  profile?: EventProfile;
};
export type PeriodInput = {
  key: string;
  title: string;
  start_date: string;
  end_date: string;
};
export type MacroInput = PeriodInput & {
  season_key: string | null;
  mesocycles: PeriodInput[];
};
export type Program = {
  program_id: string;
  mode: Mode;
  title: string;
  sport: string;
  start_date: string;
  end_date: string | null;
  olympic_key: string | null;
  seasons: PeriodInput[];
  macrocycles: MacroInput[];
  competitions: Competition[];
  goals: Goal[];
  continued_from: Reference | null;
  athlete_context?: AthleteContext;
  planning_basis?: {
    version: "cycle-planning-basis-v0.1";
    mesocycle_dates: "provisional";
    initial_mesocycle_days: number;
  };
};
export type Edition = {
  key: string;
  kind: "summer" | "winter";
  title: string;
  start_date: string;
  end_date: string;
};
export type Catalog = {
  schema_version: "cycle-creation-catalog-v0.1";
  planning_context_version: "cycle-planning-basis-v0.1";
  boundary_revision_schema: "cycle-mesocycle-boundary-revision-v0.1";
  rules_version: "cycle-creation-rules-v0.1";
  timezone_name: string;
  local_today: string;
  olympics: Edition[];
  calendar_version: string;
  calendar_source: string;
  goals: Record<string, string>;
  race_min_days: number;
  race_max_calendar_months: number;
  default_recreation_weeks: number;
  default_mesocycle_days: number;
  limits_are_product_policy: true;
};
export type Period = PeriodInput & {
  id: string;
  parent_id: string | null;
  period_type: string;
};
export type AthleteSnapshot = {
  references: AthleteContext;
  review: {
    global_entry_gate: string;
    reasons: string[];
    age_years: number | null;
    constraints: {
      key: string;
      restricted_activities: string[];
      adaptations: string;
      professional_guidance: string;
    }[];
    weight_change_requires_review: boolean;
  };
  first_mesocycle_availability: {
    status: string;
    missing_days: string[] | null;
    available_days: number;
  };
  manual_observation_count: number;
  imported_observation_count: number;
};
export type Registration = {
  artifact_id: string;
  schema_version:
    | "cycle-program-registration-v0.1"
    | "cycle-program-registration-v0.2"
    | "cycle-program-registration-v0.3";
  rules_version: string;
  athlete_id: string;
  timezone_name: string;
  proposal: Program;
  periods: Period[];
  athlete_context_snapshot?: AthleteSnapshot;
  calendar_snapshot: (Edition & { version: string; source: string }) | null;
  program_family_id: string;
  created_at: string;
  planning_authorized: false;
  workouts_created: false;
  capability_goals_preregistered: false;
  content_hash: string;
};
export type Revision = {
  program_reference: Reference;
  revision: number;
  previous_reference: Reference | null;
  competitions: Competition[];
  rationale: string;
};
export type RevisionArtifact = {
  artifact_id: string;
  schema_version:
    "cycle-competition-revision-v0.1" | "cycle-competition-revision-v0.2";
  athlete_id: string;
  proposal: Revision;
  content_hash: string;
  period_dates_changed: false;
  planning_authorized: false;
  created_at: string;
};
export type Receipt<T = Registration> = {
  identity_scope: "APPLICATION_DEMO_USER";
  artifact: T;
  durable_available_at: string;
  committed: true;
  reused: boolean;
  planning_authorized: false;
  workouts_created: false;
};
export type BoundaryRevision = {
  program_reference: Reference;
  revision: number;
  previous_reference: Reference | null;
  competition_reference: Reference;
  left_period_id: string;
  right_period_id: string;
  new_end_date: string;
  reason: "fatigue" | "progress_continues" | "plateau" | "calendar" | "other";
  observations: string;
  rationale: string;
  review_training_load: true;
};
export type BoundaryArtifact = {
  schema_version: "cycle-mesocycle-boundary-revision-v0.1";
  artifact_id: string;
  content_hash: string;
  athlete_id: string;
  proposal: BoundaryRevision;
  periods: Period[];
  previous_periods: Period[];
  competition_snapshot: Competition[];
  created_at: string;
  effective_local_day: string;
  period_dates_changed: true;
  planning_authorized: false;
  workouts_created: false;
  training_load_replanned: false;
  goal_protocols_rewritten: false;
  required_reviews: string[];
};
export type Detail = {
  program: Receipt;
  competition_revisions: Receipt<RevisionArtifact>[];
  boundary_revisions: Receipt<BoundaryArtifact>[];
};
export type Page = {
  items: Receipt[];
  offset: number;
  limit: number;
  has_more: boolean;
};
export type Preview = {
  athlete_context_snapshot?: AthleteSnapshot;
  proposal_hash: string;
  periods: Period[];
  timezone_name: string;
  calendar_snapshot: Registration["calendar_snapshot"];
  committed: false;
  planning_authorized: false;
};
export type Pending = {
  schema_version: "cycle-pending-v0.1";
  operation: "programs" | "competition-revisions" | "boundary-revisions";
  body: string;
};
export const PENDING_KEY = "paddletrainer.cycle-creation.pending.v1";
export const modeLabels: Record<Mode, string> = {
  olympic: "Olimpiai felkészülés",
  season: "Szezontervezés",
  race: "Felkészülés egy versenyre",
  recreation: "Rekreációs edzés",
};
export const periodLabels: Record<string, string> = {
  OLYMPIC_CYCLE: "Olimpiai ciklus",
  SEASON: "Szezon",
  MACROCYCLE: "Makrociklus",
  MESOCYCLE: "Mezociklus",
};

export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("A válasz szerkezete nem megfelelő.");
  return value as Record<string, unknown>;
}
export function day(value: string): Date {
  const result = new Date(value + "T00:00:00Z");
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    !Number.isFinite(result.getTime()) ||
    result.toISOString().slice(0, 10) !== value ||
    value < "1900-01-01" ||
    value > "2100-12-31"
  )
    throw new Error("Adj meg érvényes naptári dátumot.");
  return result;
}
export function addDays(value: string, count: number): string {
  const result = day(value);
  result.setUTCDate(result.getUTCDate() + count);
  return result.toISOString().slice(0, 10);
}
export function anniversary(value: string): string {
  const result = day(value),
    month = result.getUTCMonth();
  result.setUTCFullYear(result.getUTCFullYear() + 1);
  if (result.getUTCMonth() !== month) result.setUTCDate(0);
  return result.toISOString().slice(0, 10);
}
export function mesocycles(
  start: string,
  end: string,
  key: string,
  blockDays = 28,
): PeriodInput[] {
  day(start);
  day(end);
  if (!Number.isInteger(blockDays) || blockDays < 1 || blockDays > 366)
    throw new Error(
      "A kiinduló mezociklushossz 1–366 egész naptári nap lehet.",
    );
  if (start > end || day(end).getTime() - day(start).getTime() > 550 * 86400000)
    throw new Error("Ellenőrizd a makrociklus dátumait.");
  const result: PeriodInput[] = [];
  let cursor = start;
  while (cursor <= end) {
    if (result.length >= 64)
      throw new Error(
        "Makrociklusonként legfeljebb 64 mezociklus tervezhető. Válassz hosszabb kiinduló blokkokat vagy bontsd több makrociklusra a szezont.",
      );
    const finish = [addDays(cursor, blockDays - 1), end].sort()[0];
    result.push({
      key: `${key}-meso-${result.length + 1}`,
      title: `${result.length + 1}. mezociklus`,
      start_date: cursor,
      end_date: finish,
    });
    cursor = addDays(finish, 1);
  }
  return result;
}
export function defaultStructure(
  program: Program,
  blockEnd: string,
  blockDays = 28,
): Program {
  const p = structuredClone(program);
  blockDays = p.planning_basis?.initial_mesocycle_days ?? blockDays;
  day(p.start_date);
  day(blockEnd);
  if (
    p.start_date > blockEnd ||
    day(blockEnd).getTime() - day(p.start_date).getTime() > 1461 * 86400000
  )
    throw new Error("Ellenőrizd a teljes időkeretet.");
  p.seasons = [];
  if (p.mode === "olympic") {
    let cursor = p.start_date;
    while (cursor <= blockEnd) {
      const end = [addDays(anniversary(cursor), -1), blockEnd].sort()[0];
      p.seasons.push({
        key: `season-${p.seasons.length + 1}`,
        title: `${cursor.slice(0, 4)}–${end.slice(0, 4)} szezon`,
        start_date: cursor,
        end_date: end,
      });
      cursor = addDays(end, 1);
    }
  } else if (p.mode === "season")
    p.seasons = [
      {
        key: "season-1",
        title: p.title,
        start_date: p.start_date,
        end_date: blockEnd,
      },
    ];
  const ranges = p.seasons.length
    ? p.seasons
    : [
        {
          key: "",
          title: p.title,
          start_date: p.start_date,
          end_date: blockEnd,
        },
      ];
  p.macrocycles = ranges.map((s, i) => ({
    key: `macro-${i + 1}`,
    title: `${i + 1}. makrociklus`,
    season_key: s.key || null,
    start_date: s.start_date,
    end_date: s.end_date,
    mesocycles: mesocycles(
      s.start_date,
      s.end_date,
      `macro-${i + 1}`,
      blockDays,
    ),
  }));
  p.end_date = p.mode === "recreation" ? null : blockEnd;
  return p;
}
export function splitMacro(
  program: Program,
  index: number,
  split: string,
  blockDays = 28,
): Program {
  const p = structuredClone(program),
    old = p.macrocycles[index];
  blockDays = p.planning_basis?.initial_mesocycle_days ?? blockDays;
  if (!old || !["olympic", "season"].includes(p.mode))
    throw new Error("Ez a makrociklus itt nem bontható ketté.");
  day(split);
  if (split < old.start_date || split >= old.end_date)
    throw new Error("A bontás napja essen a makrocikluson belülre.");
  let number = p.macrocycles.length + 1;
  while (p.macrocycles.some((m) => m.key === `macro-${number}`)) number++;
  const key = `macro-${number}`,
    nextStart = addDays(split, 1);
  p.macrocycles.splice(
    index,
    1,
    {
      ...old,
      end_date: split,
      mesocycles: mesocycles(old.start_date, split, old.key, blockDays),
    },
    {
      key,
      title: `${number}. makrociklus`,
      season_key: old.season_key,
      start_date: nextStart,
      end_date: old.end_date,
      mesocycles: mesocycles(nextStart, old.end_date, key, blockDays),
    },
  );
  return p;
}
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value !== null && typeof value === "object") {
    const o = object(value);
    return (
      "{" +
      Object.keys(o)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + canonical(o[k]))
        .join(",") +
      "}"
    );
  }
  const text = JSON.stringify(value);
  if (text === undefined) throw new Error("Hiányos kérés.");
  return text;
}
export async function sha(value: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(canonical(value)),
  );
  return Array.from(new Uint8Array(bytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}
export function reference(
  artifact: Registration | RevisionArtifact | BoundaryArtifact,
): Reference {
  return {
    artifact_id: artifact.artifact_id,
    content_hash: artifact.content_hash,
  };
}
export function goalDescription(key: string, details?: GoalDetails): string {
  const labels: Record<string, string> = {
    performance: "Versenyteljesítmény",
    aerobic_fitness: "Állóképesség",
    strength: "Erő",
    regular_activity: "Rendszeres mozgás",
    weight_loss: "Testsúlycsökkentés",
    weight_maintenance: "Testsúly megtartása",
    wellbeing: "Közérzet javítása",
    mobility: "Mobilitás",
  };
  if (key === "regular_activity" && details?.weekly_sessions)
    return `Rendszeres mozgás: heti ${details.weekly_sessions} edzés célként.`;
  if (details?.direction)
    return `${labels[key] ?? key}: ${details.direction === "maintain" ? "szinten tartás" : "fejlesztés"}.`;
  return `${labels[key] ?? key}${details?.result_target ? `: ${details.result_target}` : "."}`;
}
export function normalizeProgram(program: Program): Program {
  const title = <T extends { title: string }>(p: T): T => ({
    ...p,
    title: p.title.trim(),
  });
  return {
    ...program,
    title: program.title.trim(),
    sport: program.sport.trim(),
    goals: program.goals.map((g) => {
      const body = g.body_mass
        ? {
            current_kg: positiveDecimal(g.body_mass.current_kg),
            ...(g.key === "weight_maintenance" && g.details
              ? {}
              : { target_kg: positiveDecimal(g.body_mass.target_kg ?? "") }),
          }
        : undefined;
      const details = g.details
        ? {
            ...g.details,
            notes: g.details.notes.trim(),
            result_target: g.details.result_target.trim(),
            event_keys:
              g.key === "performance" && !g.details.event_keys.length
                ? program.competitions
                    .filter(
                      (e) => e.priority === "main" && e.status === "planned",
                    )
                    .map((e) => e.key)
                : g.details.event_keys,
          }
        : undefined;
      const basic = goalDescription(g.key, details);
      return {
        ...g,
        ...(details ? { details } : {}),
        ...(body ? { body_mass: body } : {}),
        target_description: body
          ? g.key === "weight_maintenance" && details
            ? `Megtartandó testsúly: ${body.current_kg} kg.`
            : `Jelenlegi testsúly: ${body.current_kg} kg; céltestsúly: ${body.target_kg} kg.`
          : details
            ? basic + (details.notes ? ` ${details.notes}` : "")
            : g.target_description.trim(),
      };
    }),
    seasons: program.seasons.map(title),
    competitions: program.competitions.map((c) => ({
      ...title(c),
      ...(c.profile ? { profile: normalizeProfile(c.profile) } : {}),
    })),
    macrocycles: program.macrocycles.map((m) => ({
      ...title(m),
      mesocycles: m.mesocycles.map(title),
    })),
  };
}
export function normalizeRevision(revision: Revision): Revision {
  return {
    ...revision,
    rationale: revision.rationale.trim(),
    competitions: revision.competitions.map((c) => ({
      ...c,
      title: c.title.trim(),
      ...(c.profile ? { profile: normalizeProfile(c.profile) } : {}),
    })),
  };
}
export function readPending(value: string): Pending {
  if (new TextEncoder().encode(value).byteLength > 1100000)
    throw new Error("Túl nagy függő kérés.");
  const p = object(JSON.parse(value));
  if (
    p.schema_version !== "cycle-pending-v0.1" ||
    !["programs", "competition-revisions", "boundary-revisions"].includes(
      String(p.operation),
    ) ||
    typeof p.body !== "string"
  )
    throw new Error("A függő kérés nem olvasható.");
  object(JSON.parse(p.body));
  return p as Pending;
}
export async function readReceipt<T = Registration>(
  value: unknown,
  pending?: Pending,
): Promise<Receipt<T>> {
  const r = object(value),
    a = object(r.artifact);
  const schema = a.schema_version;
  if (
    r.identity_scope !== "APPLICATION_DEMO_USER" ||
    r.committed !== true ||
    r.planning_authorized !== false ||
    r.workouts_created !== false ||
    typeof r.reused !== "boolean" ||
    ![
      "cycle-program-registration-v0.1",
      "cycle-program-registration-v0.2",
      "cycle-program-registration-v0.3",
      "cycle-competition-revision-v0.1",
      "cycle-competition-revision-v0.2",
      "cycle-mesocycle-boundary-revision-v0.1",
    ].includes(String(schema)) ||
    typeof a.artifact_id !== "string" ||
    !/^pt-cycle:[0-9a-f]{64}$/.test(a.artifact_id) ||
    typeof a.athlete_id !== "string" ||
    a.planning_authorized !== false ||
    (String(schema).startsWith("cycle-program-registration-")
      ? a.workouts_created !== false ||
        a.capability_goals_preregistered !== false
      : schema === "cycle-mesocycle-boundary-revision-v0.1"
        ? a.period_dates_changed !== true ||
          a.training_load_replanned !== false ||
          a.goal_protocols_rewritten !== false ||
          a.workouts_created !== false
        : a.period_dates_changed !== false) ||
    typeof r.durable_available_at !== "string" ||
    !/(?:Z|[+-]\d{2}:\d{2})$/.test(r.durable_available_at) ||
    !Number.isFinite(Date.parse(r.durable_available_at))
  )
    throw new Error("A szerver nem igazolta a tartós mentést.");
  const { content_hash, ...content } = a;
  if ((await sha(content)) !== content_hash)
    throw new Error("A mentési bizonylat tartalma eltér.");
  if (pending) {
    const expected =
      pending.operation === "programs"
        ? "cycle-program-registration-"
        : pending.operation === "boundary-revisions"
          ? "cycle-mesocycle-boundary-revision-"
          : "cycle-competition-revision-";
    if (
      !String(schema).startsWith(expected) ||
      canonical(a.proposal) !== canonical(JSON.parse(pending.body))
    )
      throw new Error("A bizonylat másik kéréshez tartozik.");
  }
  return r as Receipt<T>;
}

export function positiveDecimal(raw: string): string {
  const value = raw.trim().replace(",", ".");
  if (
    !/^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,3})?$/.test(value) ||
    Number(value) <= 0
  )
    throw new Error(
      "Pozitív számot adj meg, legfeljebb három tizedesjeggyel (pl. 82,5).",
    );
  return value;
}
export function emptyProfile(sport = ""): EventProfile {
  return {
    discipline: sport,
    event_type: "other",
    distance_status: "specified",
    distance_value: "",
    distance_unit: "m",
    expected_duration_minutes: null,
    course_description: "",
    capability_basis: "unassessed",
    capability_keys: [],
  };
}
export function normalizeProfile(p: EventProfile): EventProfile {
  return {
    ...p,
    discipline: p.discipline.trim(),
    course_description: p.course_description.trim(),
    distance_value:
      p.distance_status === "specified"
        ? positiveDecimal(p.distance_value ?? "")
        : null,
    distance_unit: p.distance_status === "specified" ? p.distance_unit : null,
    expected_duration_minutes: p.expected_duration_minutes?.trim()
      ? positiveDecimal(p.expected_duration_minutes)
      : null,
  };
}
export const ICF_SOURCE =
  "https://www.canoeicf.com/sites/default/files/icf_canoe_sprint_coaching_manual_2-3.pdf";
export function sprintKeys(profile: EventProfile): string[] | null {
  const p = normalizeProfile(profile),
    discipline = p.discipline.toLowerCase();
  if (
    p.event_type !== "sprint" ||
    p.distance_status !== "specified" ||
    !/kajak|kenu|kayak|canoe/.test(discipline) ||
    /slalom|szlalom|maraton|marathon|polo|póló|wildwater|vadvíz/.test(
      discipline,
    )
  )
    return null;
  const distance =
    Number(p.distance_value) * (p.distance_unit === "km" ? 1000 : 1);
  const common = [
    "TECHNICAL_SKILL",
    "TECHNICAL_STABILITY_UNDER_FATIGUE",
    "MAX_STRENGTH",
    "POWER_RFD",
    "SPRINT_SPEED_AND_START",
    "HIGH_INTENSITY_AND_ANAEROBIC_PROFILE",
    "VO2_CAPACITY",
  ];
  if (distance === 200) return common;
  return [500, 1000].includes(distance)
    ? [
        ...common,
        "PERIPHERAL_OXIDATIVE_CAPACITY",
        "MUSCULAR_ENDURANCE",
        "PACING_COMPETENCE",
      ]
    : null;
}
export type DraftIssue = { step: number; name: string; message: string };
export function draftIssues(p: Program, end: string, until = 3): DraftIssue[] {
  const issues: DraftIssue[] = [];
  const issue = (step: number, name: string, message: string) =>
    issues.push({ step, name, message });
  function range(
    start: string,
    finish: string,
    label: string,
    step: number,
    name: string,
  ) {
    try {
      day(start);
      day(finish);
    } catch {
      issue(step, name, `${label}: adj meg érvényes kezdő- és zárónapot.`);
      return false;
    }
    if (start > finish) {
      issue(
        step,
        name,
        `${label}: a zárónap (${finish}) korábbi a kezdőnapnál (${start}).`,
      );
      return false;
    }
    return true;
  }
  range(p.start_date, end, "Felkészülés időkerete", 1, "end_date");
  if (!p.title.trim()) issue(1, "title", "Add meg a felkészülés nevét.");
  if (!p.sport.trim()) issue(1, "sport", "Add meg a sportágat / szakágat.");
  if (!p.goals.length) issue(1, "goals", "Válassz legalább egy célt.");
  for (const g of p.goals) {
    if (
      g.body_mass ||
      (p.planning_basis &&
        ["weight_loss", "weight_maintenance"].includes(g.key))
    ) {
      try {
        if (!g.body_mass)
          throw new Error("Add meg a jelenlegi és a céltestsúlyt.");
        const current = positiveDecimal(g.body_mass.current_kg),
          target =
            g.key === "weight_maintenance" && g.details
              ? current
              : positiveDecimal(g.body_mass.target_kg ?? "");
        if (g.key === "weight_loss" && Number(target) >= Number(current))
          throw new Error(
            "Testsúlycsökkentésnél a céltestsúly legyen kisebb a jelenleginél.",
          );
      } catch (e) {
        issue(
          1,
          `goal.${g.key}.current_kg`,
          e instanceof Error ? e.message : "Ellenőrizd a testsúlyadatokat.",
        );
      }
    } else if (!g.details && !g.target_description.trim())
      issue(1, `goal.${g.key}`, "Fogalmazd meg a kiválasztott célt.");
  }
  if (
    p.goals.some((g) => g.details) &&
    p.goals.some((g) => g.key === "weight_loss") &&
    p.goals.some((g) => g.key === "weight_maintenance")
  )
    issue(
      1,
      "goals",
      "A testsúlycsökkentést és a megtartást egymást követő célként add meg.",
    );
  for (const g of p.goals)
    if (g.details) {
      if (
        ["aerobic_fitness", "strength", "mobility"].includes(g.key) &&
        !g.details.direction
      )
        issue(1, `goal.${g.key}`, "Válassz fejlesztést vagy szinten tartást.");
      if (
        g.details.weekly_sessions !== null &&
        (!Number.isInteger(g.details.weekly_sessions) ||
          g.details.weekly_sessions < 1 ||
          g.details.weekly_sessions > 28)
      )
        issue(
          1,
          `goal.${g.key}`,
          "A heti edzésszám 1–28 közötti egész szám legyen.",
        );
    }
  if (until < 2) return issues;
  p.competitions.forEach((c, i) => {
    range(
      c.start_date,
      c.end_date,
      `${i + 1}. verseny · ${c.title || "név nélkül"}`,
      2,
      `event.${i}.start`,
    );
    if (!c.title.trim())
      issue(2, `event.${i}.title`, `${i + 1}. verseny: add meg a nevet.`);
    if (c.start_date < p.start_date || c.end_date > end)
      issue(
        2,
        `event.${i}.start`,
        `${c.title || "Verseny"}: a verseny essen a felkészülés időkeretébe.`,
      );
    if ((c.precision === "exact") !== (c.start_date === c.end_date))
      issue(
        2,
        `event.${i}.precision`,
        "A pontos nap egy dátum, a közelítő időablak két eltérő dátum legyen.",
      );
    if (p.planning_basis && c.status === "planned" && !c.profile)
      issue(
        2,
        `event.${i}.discipline`,
        "Add meg a verseny szakágát, jellegét és távát, vagy jelezd, hogy a táv még ismeretlen / nem értelmezhető.",
      );
    if (c.profile) {
      if (!c.profile.discipline.trim())
        issue(2, `event.${i}.discipline`, "Add meg a verseny szakágát.");
      try {
        normalizeProfile(c.profile);
      } catch (e) {
        issue(
          2,
          `event.${i}.distance_value`,
          e instanceof Error ? e.message : "Ellenőrizd a távot.",
        );
      }
    }
  });
  if (until < 3) return issues;
  function partition(
    nodes: PeriodInput[],
    start: string,
    finish: string,
    label: string,
    name: (index: number) => string,
  ) {
    if (!range(start, finish, label, 3, name(0))) return;
    let cursor = start;
    const indexed = nodes
      .map((n, i) => ({ n, i }))
      .sort((a, b) => a.n.start_date.localeCompare(b.n.start_date));
    for (const { n, i } of indexed) {
      if (!range(n.start_date, n.end_date, `${label} · ${n.title}`, 3, name(i)))
        continue;
      if (n.start_date !== cursor)
        issue(
          3,
          name(i),
          `${label} · ${n.title}: a kezdőnap legyen ${cursor}, hogy ne legyen rés vagy átfedés.`,
        );
      if (n.end_date > finish)
        issue(
          3,
          name(i),
          `${n.title}: a zárónap túlmegy a szülő ciklus ${finish} zárónapján.`,
        );
      cursor = addDays(n.end_date, 1);
    }
    if (!nodes.length || cursor !== addDays(finish, 1))
      issue(
        3,
        name(0),
        `${label}: a bontás fedje le a teljes ${start} – ${finish} időkeretet.`,
      );
  }
  if (p.seasons.length) {
    partition(p.seasons, p.start_date, end, "Szezon", (i) => `season.${i}.end`);
    p.seasons.forEach((s) =>
      partition(
        p.macrocycles.filter((m) => m.season_key === s.key),
        s.start_date,
        s.end_date,
        "Makrociklus",
        (i) => `macro.${i}.end`,
      ),
    );
  } else
    partition(
      p.macrocycles,
      p.start_date,
      end,
      "Makrociklus",
      (i) => `macro.${i}.end`,
    );
  p.macrocycles.forEach((m, i) =>
    partition(
      m.mesocycles,
      m.start_date,
      m.end_date,
      "Mezociklus",
      (j) => `meso.${i}.${j}.end`,
    ),
  );
  return issues;
}
export function moveDraftBoundary(
  p: Program,
  macroIndex: number,
  leftIndex: number,
  end: string,
): Program {
  day(end);
  const value = structuredClone(p),
    nodes = value.macrocycles[macroIndex]?.mesocycles;
  const left = nodes?.[leftIndex],
    right = nodes?.[leftIndex + 1];
  if (!left || !right || end < left.start_date || end >= right.end_date)
    throw new Error(
      "A közös határ az előző mezociklus kezdete és a következő vége közé essen; mindkét ciklusnak maradjon legalább egy napja.",
    );
  left.end_date = end;
  right.start_date = addDays(end, 1);
  return value;
}
