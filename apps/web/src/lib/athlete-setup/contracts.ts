import { addDays, day, object, sha } from "@/lib/planning-cycles/contracts";

export type Reference = { artifact_id: string; content_hash: string };
export type SportHistory = {
  sport: string;
  discipline: string;
  start_year: number | null;
  current: boolean;
  last_active_date: string | null;
  level:
    "unknown" | "beginner" | "recreational" | "competitive" | "professional";
  usual_sessions_per_week: number | null;
  notes: string;
};
export type Constraint = {
  key: string;
  duration: "permanent" | "temporary";
  area: "movement" | "vision" | "hearing" | "medical" | "other";
  affected_area: string;
  restricted_activities: string[];
  adaptations: string;
  professional_guidance: string;
  starts_on: string | null;
  review_on: string | null;
};
export const metrics: Record<string, { label: string; unit: string }> = {
  training_sessions: { label: "Edzések száma", unit: "count" },
  training_minutes: { label: "Edzésidő", unit: "min" },
  sleep_duration_sec: { label: "Alvásidő", unit: "s" },
  sleep_score: { label: "Alvás pontszám", unit: "score" },
  daily_steps: { label: "Rögzített lépésszám", unit: "count" },
  background_hr_mean_bpm: {
    label: "Háttérpulzus mintáinak átlaga",
    unit: "bpm",
  },
  background_hr_median_bpm: {
    label: "Háttérpulzus mintáinak mediánja",
    unit: "bpm",
  },
  resting_hr_bpm: { label: "Nyugalmi pulzus", unit: "bpm" },
  hrv_rmssd_ms: { label: "HRV RMSSD", unit: "ms" },
  body_mass_kg: { label: "Testsúly", unit: "kg" },
  vo2max_ml_kg_min: { label: "VO2max", unit: "ml/kg/min" },
  strength_load_kg: { label: "Erőfelmérés terhe", unit: "kg" },
  test_duration_sec: { label: "Felmérés ideje", unit: "s" },
  test_distance_m: { label: "Felmérés távja", unit: "m" },
};
export const methods = {
  unknown: "Mérési módszer még nincs tisztázva",
  self_report: "Saját adat / visszaemlékezés",
  laboratory: "Laboratóriumi mérés",
  field_test: "Célzott terepi felmérés",
  device_estimate: "Eszköz becslése",
  device_measurement: "Eszköz mérése",
  recorded_activity: "Rögzített tevékenység",
};
export type Method = keyof typeof methods;
export const aggregations = {
  single: "Egy mérés / tevékenység",
  total: "Időszak összesen",
  mean: "Időszak átlaga",
  median: "Időszak mediánja",
};
export type Aggregation = keyof typeof aggregations;
export type Manual = {
  observation_id: string;
  metric: string;
  value: string;
  start_date: string;
  end_date: string;
  method: Method;
  aggregation: Aggregation;
  sport: string;
  protocol: string;
  conditions: string;
  supersedes_candidate_id: string | null;
};
export type Profile = {
  birth_date: string | null;
  sex_reference:
    "unknown" | "female" | "male" | "intersex" | "prefer_not_to_say";
  competition_category: string;
  target_sport: string;
  sport_history_status: "unknown" | "none" | "recorded";
  sport_history: SportHistory[];
  constraint_status: "unknown" | "none_known" | "present";
  constraints: Constraint[];
  participation:
    "unknown" | "unrestricted" | "adapted" | "professional_review" | "paused";
  interruption: "unknown" | "none" | "returning";
  last_training_date: string | null;
  typical_days_per_week: number | null;
  typical_minutes_per_week: number | null;
  resources: string[];
  accessibility_needs: string;
  recovery_notes: string;
  manual_observations: Manual[];
  source_window: { start_date: string; end_date: string } | null;
  source_selections: Reference[];
};
export type Window = {
  key: string;
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  start_fold: 0 | 1 | null;
  end_fold: 0 | 1 | null;
  max_minutes: number;
  sport_scope: "unknown" | "any" | "specified";
  sports: string[];
  effort_cap: "unknown" | "easy" | "moderate" | "any";
  resources: string[];
  location: string;
  notes: string;
};
export type CalendarDay = {
  date: string;
  status: "unknown" | "unavailable" | "available";
  max_total_minutes: number | null;
  windows: Window[];
  notes: string;
};
export type Calendar = {
  timezone_name: string;
  start_date: string;
  end_date: string;
  mesocycle_id: string | null;
  days: CalendarDay[];
};
export type Review = {
  age_years: number | null;
  age_path: string;
  evaluated_on: string;
  global_entry_gate: string;
  participation_status: string;
  entry_mode: string;
  reasons: string[];
  weight_change_requires_review: boolean;
  clinical_clearance: false;
};
export type Candidate = Reference & {
  normalizer_version: "athlete-history-candidates-v0.1";
  metric: string;
  value: string;
  unit: string;
  start_date: string;
  end_date: string;
  provider: string;
  source_id: string;
  source_content_hash: string;
  received_at: string;
  method: Method;
  aggregation: Aggregation;
  logical_key: string;
  sport: string;
  protocol: string;
  coverage: Record<string, unknown>;
};
export type Artifact = {
  schema_version: "athlete-setup-v0.1";
  artifact_id: string;
  athlete_id: string;
  kind: "profile" | "availability" | "polar_import";
  revision?: number;
  content_hash: string;
  proposal: {
    request_id: string;
    previous_reference?: Reference | null;
    data?: Profile | Calendar;
    day?: string;
    domain?: Domain;
  };
  review?: Review;
  imported_observations?: Candidate[];
  calendar?: { coverage: Record<string, number>; availability_status: string };
  planning_authorized: false;
  workouts_created: false;
  created_at: string;
};
export type Receipt = {
  identity_scope: "APPLICATION_DEMO_USER";
  artifact: Artifact;
  durable_available_at: string;
  committed: true;
  reused: boolean;
  planning_authorized: false;
  workouts_created: false;
};
export type Context = {
  athlete_id: string;
  schema_version: "athlete-setup-v0.1";
  timezone_name: string;
  local_today: string;
  profile: Receipt | null;
  availability: Receipt | null;
  current_review: Review | null;
  references: {
    profile_reference: Reference | null;
    availability_reference: Reference | null;
  };
  polar: { connected: boolean; domains: Record<Domain, boolean> };
  planning_authorized: false;
  workouts_created: false;
};
export const domains = {
  sessions: "Edzések",
  sleep: "Alvás",
  nightly_recharge: "Éjszakai HRV",
  continuous_hr: "Egész napos pulzusminták",
  activity: "Lépések",
  tests: "Órás felmérések",
};
export type Domain = keyof typeof domains;
export type Operation = "profiles" | "availability" | "polar-imports";
export type Pending = {
  schema_version: "athlete-pending-v0.1";
  operation: Operation;
  body: string;
};
export const PENDING_KEY = "paddletrainer.athlete-setup.pending.v1";
export function ref(value: Reference): Reference {
  return { artifact_id: value.artifact_id, content_hash: value.content_hash };
}
export function emptyProfile(): Profile {
  return {
    birth_date: null,
    sex_reference: "unknown",
    competition_category: "",
    target_sport: "",
    sport_history_status: "unknown",
    sport_history: [],
    constraint_status: "unknown",
    constraints: [],
    participation: "unknown",
    interruption: "unknown",
    last_training_date: null,
    typical_days_per_week: null,
    typical_minutes_per_week: null,
    resources: [],
    accessibility_needs: "",
    recovery_notes: "",
    manual_observations: [],
    source_window: null,
    source_selections: [],
  };
}
export function newWindow(): Window {
  return {
    key: "w-" + crypto.randomUUID(),
    start_time: "",
    end_time: "",
    ends_next_day: false,
    start_fold: null,
    end_fold: null,
    max_minutes: 0,
    sport_scope: "unknown",
    sports: [],
    effort_cap: "unknown",
    resources: [],
    location: "",
    notes: "",
  };
}
export function dates(start: string, end: string, maximum = 366): string[] {
  day(start);
  day(end);
  const result: string[] = [];
  for (let d = start; d <= end && result.length <= maximum; d = addDays(d, 1))
    result.push(d);
  if (!result.length || result.length > maximum)
    throw new Error(`Válassz 1–${maximum} napos időszakot.`);
  return result;
}
export function resizeCalendar(
  calendar: Calendar | null,
  start: string,
  end: string,
  timezone: string,
  mesocycle: string | null = null,
): Calendar {
  const old = new Map(calendar?.days.map((d) => [d.date, d]));
  return {
    timezone_name: timezone,
    start_date: start,
    end_date: end,
    mesocycle_id: mesocycle,
    days: dates(start, end).map(
      (date) =>
        old.get(date) ?? {
          date,
          status: "unknown",
          windows: [],
          max_total_minutes: null,
          notes: "",
        },
    ),
  };
}
export function copyDay(
  calendar: Calendar,
  source: string,
  targets: string[],
): Calendar {
  const value = calendar.days.find((d) => d.date === source);
  if (!value) throw new Error("A másolandó nap hiányzik.");
  return {
    ...calendar,
    days: calendar.days.map((d) =>
      targets.includes(d.date) && d.date !== source
        ? { ...structuredClone(value), date: d.date }
        : d,
    ),
  };
}
export function list(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
    ),
  );
}
export function decimal(value: string): string {
  const result = value.trim().replace(",", ".");
  if (!/^(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$/.test(result))
    throw new Error("Adj meg számot tizedesponttal vagy tizedesvesszővel.");
  return result;
}
export function normalizeProfile(value: Profile, today: string): Profile {
  if (value.birth_date) {
    day(value.birth_date);
    if (value.birth_date > today)
      throw new Error("A születési dátum nem lehet jövőbeli.");
  }
  if ((value.constraint_status === "present") !== !!value.constraints.length)
    throw new Error(
      "A jelzett korlátozáshoz adj meg legalább egy részletes bejegyzést.",
    );
  const manual = value.manual_observations.map((o) => {
    day(o.start_date);
    day(o.end_date);
    if (o.start_date > o.end_date || o.end_date > today)
      throw new Error("Ellenőrizd a mérés időszakát.");
    const number = decimal(o.value);
    const aggregation = o.aggregation ?? "single";
    if (o.start_date !== o.end_date && aggregation === "single")
      throw new Error(
        "Több napos adatnál válassz összeget, átlagot vagy mediánt.",
      );
    if (
      ["training_sessions", "daily_steps"].includes(o.metric) &&
      ["single", "total"].includes(aggregation) &&
      Number(number) % 1
    )
      throw new Error("A darabszám egész szám legyen.");
    return {
      ...o,
      value: number,
      aggregation,
      sport: o.sport.trim(),
      protocol: o.protocol.trim(),
      conditions: o.conditions.trim(),
    };
  });
  return {
    ...value,
    target_sport: value.target_sport.trim(),
    competition_category: value.competition_category.trim(),
    recovery_notes: value.recovery_notes.trim(),
    accessibility_needs: value.accessibility_needs.trim(),
    manual_observations: manual,
  };
}
export function validateCalendar(value: Calendar): void {
  const wanted = dates(value.start_date, value.end_date);
  if (JSON.stringify(wanted) !== JSON.stringify(value.days.map((d) => d.date)))
    throw new Error("A naptár napjai hiányosak vagy ismétlődnek.");
  for (const d of value.days) {
    if ((d.status === "available") !== !!d.windows.length)
      throw new Error(`${d.date}: az elérhető naphoz adj meg edzésablakot.`);
    for (const w of d.windows) {
      if (
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(w.start_time) ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(w.end_time) ||
        !Number.isInteger(w.max_minutes) ||
        w.max_minutes < 1
      )
        throw new Error(
          `${d.date}: add meg az időablak kezdetét, végét és maximális edzésidejét.`,
        );
      if (w.sport_scope === "specified" && !w.sports.length)
        throw new Error(`${d.date}: válassz sportágat.`);
    }
  }
}
export function readPending(value: string): Pending {
  const p = object(JSON.parse(value));
  if (
    p.schema_version !== "athlete-pending-v0.1" ||
    !["profiles", "availability", "polar-imports"].includes(
      String(p.operation),
    ) ||
    typeof p.body !== "string"
  )
    throw new Error("A függő sportolói mentés nem olvasható.");
  object(JSON.parse(p.body));
  return p as Pending;
}
export async function readReceipt(
  value: unknown,
  pending?: Pending,
): Promise<Receipt> {
  const r = object(value),
    a = object(r.artifact);
  const expected =
    pending?.operation === "profiles"
      ? "profile"
      : pending?.operation === "availability"
        ? "availability"
        : "polar_import";
  if (
    r.identity_scope !== "APPLICATION_DEMO_USER" ||
    r.committed !== true ||
    r.planning_authorized !== false ||
    r.workouts_created !== false ||
    typeof r.reused !== "boolean" ||
    a.schema_version !== "athlete-setup-v0.1" ||
    !["profile", "availability", "polar_import"].includes(String(a.kind)) ||
    a.planning_authorized !== false ||
    a.workouts_created !== false ||
    !/^pt-athlete:[0-9a-f]{64}$/.test(String(a.artifact_id)) ||
    typeof a.athlete_id !== "string" ||
    typeof r.durable_available_at !== "string" ||
    !/(Z|[+-]\d\d:\d\d)$/.test(r.durable_available_at) ||
    !Number.isFinite(Date.parse(r.durable_available_at))
  )
    throw new Error("A szerver nem igazolta a tartós sportolói mentést.");
  const { content_hash, ...body } = a;
  if ((await sha(body)) !== content_hash)
    throw new Error("A sportolói bizonylat tartalma eltér.");
  if (
    pending &&
    (a.kind !== expected ||
      (await sha(a.proposal)) !== (await sha(JSON.parse(pending.body))))
  )
    throw new Error("A sportolói bizonylat másik kéréshez tartozik.");
  return r as Receipt;
}
export async function readContext(value: unknown): Promise<Context> {
  const c = object(value);
  if (
    c.schema_version !== "athlete-setup-v0.1" ||
    typeof c.athlete_id !== "string" ||
    !/^[0-9a-f-]{36}$/.test(c.athlete_id) ||
    typeof c.local_today !== "string" ||
    typeof c.timezone_name !== "string" ||
    c.planning_authorized !== false ||
    c.workouts_created !== false
  )
    throw new Error("A sportolói környezet nem olvasható.");
  day(c.local_today);
  const references = object(c.references),
    polar = object(c.polar),
    access = object(polar.domains);
  if (
    typeof polar.connected !== "boolean" ||
    Object.keys(domains).some((key) => typeof access[key] !== "boolean")
  )
    throw new Error("A sportolói adatkapcsolat állapota nem olvasható.");
  for (const [field, kind] of [
    ["profile", "profile"],
    ["availability", "availability"],
  ] as const) {
    if (c[field]) {
      const saved = await readReceipt(c[field]);
      if (
        saved.artifact.kind !== kind ||
        saved.artifact.athlete_id !== c.athlete_id ||
        (await sha(ref(saved.artifact))) !==
          (await sha(references[field + "_reference"]))
      )
        throw new Error("A sportolói hivatkozások eltérnek.");
    } else if (c[field] !== null || references[field + "_reference"] !== null)
      throw new Error("A sportolói hivatkozás hiányos.");
  }
  return c as Context;
}
export const reasonLabels: Record<string, string> = {
  AGE_UNKNOWN: "Életkor még nincs megadva",
  YOUTH_PLANNING_REVIEW:
    "Utánpótlás: életkornak megfelelő tervezés felülvizsgálata",
  TARGET_SPORT_UNKNOWN: "Célsportág még nincs megadva",
  SPORT_HISTORY_UNKNOWN: "Sportmúlt még nincs felmérve",
  FUNCTIONAL_CONSTRAINTS_UNKNOWN: "Korlátozások még nincsenek felmérve",
  PARTICIPATION_UNKNOWN: "Terhelhetőségi keret még nincs megadva",
  TEMPORARY_CONSTRAINT_REVIEW: "Ideiglenes korlátozás felülvizsgálata",
  CONSTRAINT_REVIEW_DUE: "A korlátozás felülvizsgálata esedékes",
  CONSTRAINT_EFFECT_UNSPECIFIED:
    "A korlátozás gyakorlati hatása még nincs megadva",
  USER_DECLARED_PAUSE: "A sportoló szünetet jelölt",
};
export const gateLabels: Record<string, string> = {
  OPEN: "A megadott keretek áttekinthetők",
  OPEN_WITH_CONSTRAINTS: "Alkalmazkodást igénylő tervezési keret",
  REVIEW_REQUIRED: "Tervezés előtt felülvizsgálandó",
  HOLD: "Edzéstervezés szüneteltetve",
};

export type PendingQueue = {
  schema_version: "athlete-queue-v0.1";
  athlete_id: string;
  items: Pending[];
  history_window?: { start_date: string; end_date: string };
};
export function readQueue(value: string): PendingQueue {
  const q = object(JSON.parse(value));
  if (
    q.schema_version !== "athlete-queue-v0.1" ||
    typeof q.athlete_id !== "string" ||
    !Array.isArray(q.items) ||
    !q.items.length ||
    q.items.length > 31
  )
    throw new Error("A függő sportolói kéréslista nem olvasható.");
  for (const p of q.items) readPending(JSON.stringify(p));
  return q as PendingQueue;
}
