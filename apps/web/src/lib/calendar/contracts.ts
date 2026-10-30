import { addDays, day, object, sha } from "@/lib/planning-cycles/contracts";
import { capabilityLabels } from "@/lib/planning-goals/labels";
import { readDurationEstimate } from "./duration-estimate";
import type { DurationEstimate } from "./duration-estimate";
export { addDays };

export const goalLabels: Record<string, string> = {
  ...capabilityLabels,
  RECOVERY: "Regeneráció",
  MIXED: "Vegyes cél",
};
export type Family =
  | "aerobic"
  | "vo2"
  | "strength"
  | "speed"
  | "technique"
  | "anaerobic"
  | "recovery"
  | "other";
export const familyLabels: Record<Family, string> = {
  aerobic: "Állóképesség",
  vo2: "VO₂max",
  strength: "Erő",
  speed: "Gyorsaság",
  technique: "Technika",
  anaerobic: "Anaerob profil",
  recovery: "Regeneráció",
  other: "Egyéb / nincs cél",
};
export function goalFamily(goal: string | null | undefined): Family {
  if (goal === "VO2_CAPACITY") return "vo2";
  if (
    [
      "PERIPHERAL_OXIDATIVE_CAPACITY",
      "PADDLING_ECONOMY",
      "LONG_DURATION_DURABILITY",
      "MUSCULAR_ENDURANCE",
    ].includes(goal ?? "")
  )
    return "aerobic";
  if (goal === "MAX_STRENGTH") return "strength";
  if (["POWER_RFD", "SPRINT_SPEED_AND_START"].includes(goal ?? ""))
    return "speed";
  if (
    [
      "TECHNICAL_SKILL",
      "TECHNICAL_STABILITY_UNDER_FATIGUE",
      "PACING_COMPETENCE",
    ].includes(goal ?? "")
  )
    return "technique";
  if (goal === "HIGH_INTENSITY_AND_ANAEROBIC_PROFILE") return "anaerobic";
  if (goal === "RECOVERY") return "recovery";
  return "other";
}
export type Reference = { artifact_id: string; content_hash: string };
export type GoalTag = Reference & { primary_goal: string | null };
export type Planned = {
  reschedule?: {
    allowed: boolean;
    blocked_reason: string | null;
    source_hash: string;
  };
  duration_estimate?: DurationEstimate | null;
  id: string;
  date: string;
  planned_start_time: string | null;
  title: string;
  sport: string;
  duration_sec: number | null;
  distance_m: number | null;
  status: string;
  description: string | null;
  training_period_id: string | null;
  goal_tag: GoalTag | null;
};
export type Actual = {
  id: string;
  started_at: string;
  ended_at: string | null;
  name: string | null;
  sport: string;
  duration_sec: number | null;
  distance_m: number | null;
  calories: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_speed: number | null;
  max_speed: number | null;
  avg_power: number | null;
  max_power: number | null;
  avg_cadence: number | null;
  max_cadence: number | null;
  cardio_load: number | null;
  perceived_load: number | null;
  rpe: number | null;
  external_provider: string;
  external_id: string;
  planned_workout_id: string | null;
  goal_tag: GoalTag | null;
  linked_goal_tag: GoalTag | null;
};
export type AvailableWindow = {
  key: string;
  start_at: string;
  end_at: string;
  max_minutes: number;
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  sport_scope: string;
  sports: string[];
  effort_cap: string;
  resources: string[];
  location: string;
  notes: string;
};
export type AvailabilityDay = {
  date: string;
  status: "unknown" | "unavailable" | "available";
  max_total_minutes: number | null;
  notes: string;
  windows: AvailableWindow[];
};
export type Period = {
  id: string;
  title: string;
  period_type: string;
  start_date: string;
  end_date: string;
};
export type Feed = {
  schema_version: "calendar-workspace-v0.1";
  athlete_id: string;
  timezone_name: string;
  local_today: string;
  start_date: string;
  end_date: string;
  retrieved_at: string;
  planned: Planned[];
  sessions: Actual[];
  periods: Period[];
  availability: {
    reference: Reference | null;
    days: AvailabilityDay[];
    carry_windows: (AvailableWindow & { date: string })[];
    absence_means_unavailable: false;
  };
  has_more: false;
  planning_authorized: false;
  workouts_changed: false;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const goalIdentity = /^pt-workout-goal:[0-9a-f]{64}:[0-9a-f]{32}$/;
export function requireValue(
  condition: unknown,
  text = "A naptári válasz nem értelmezhető.",
): asserts condition {
  if (!condition) throw new Error(text);
}
export function requireDay(value: unknown) {
  requireValue(typeof value === "string");
  return day(value);
}
export function validInstant(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  );
}
function tag(value: unknown): GoalTag | null {
  if (value === null) return null;
  const t = object(value);
  requireValue(
    typeof t.artifact_id === "string" &&
      goalIdentity.test(t.artifact_id) &&
      typeof t.content_hash === "string" &&
      /^[a-f0-9]{64}$/.test(t.content_hash) &&
      (t.primary_goal === null ||
        (typeof t.primary_goal === "string" &&
          Object.hasOwn(goalLabels, t.primary_goal))),
  );
  return t as GoalTag;
}
export function readFeed(value: unknown): Feed {
  const x = object(value);
  requireValue(
    x.schema_version === "calendar-workspace-v0.1" &&
      typeof x.athlete_id === "string" &&
      uuid.test(x.athlete_id) &&
      x.has_more === false &&
      x.planning_authorized === false &&
      x.workouts_changed === false,
  );
  requireValue(
    typeof x.timezone_name === "string" && validInstant(x.retrieved_at),
  );
  new Intl.DateTimeFormat("hu-HU", { timeZone: x.timezone_name }).format();
  for (const name of ["start_date", "end_date", "local_today"])
    requireDay(x[name]);
  requireValue(
    String(x.start_date) <= String(x.end_date) &&
      dateDistance(String(x.start_date), String(x.end_date)) < 366,
  );
  requireValue(
    Array.isArray(x.planned) &&
      Array.isArray(x.sessions) &&
      Array.isArray(x.periods),
  );
  for (const [kind, rows] of [
    ["planned", x.planned],
    ["session", x.sessions],
  ] as const) {
    const seen = new Set<string>();
    for (const v of rows) {
      const r = object(v);
      requireValue(
        typeof r.id === "string" &&
          uuid.test(r.id) &&
          !seen.has(r.id) &&
          typeof r.sport === "string",
      );
      seen.add(r.id);
      requireValue(
        r.duration_sec === null ||
          (typeof r.duration_sec === "number" &&
            Number.isFinite(r.duration_sec) &&
            r.duration_sec >= 0),
      );
      requireValue(
        r.distance_m === null ||
          (typeof r.distance_m === "number" &&
            Number.isFinite(r.distance_m) &&
            r.distance_m >= 0),
      );
      tag(r.goal_tag);
      if (kind === "planned") {
        if (r.reschedule !== undefined) {
          const m = object(r.reschedule);
          requireValue(
            typeof m.allowed === "boolean" &&
              (m.allowed
                ? m.blocked_reason === null
                : typeof m.blocked_reason === "string") &&
              typeof m.source_hash === "string" &&
              /^[a-f0-9]{64}$/.test(m.source_hash),
          );
        }
        if (r.duration_estimate !== undefined && r.duration_estimate !== null) {
          const estimate = readDurationEstimate(
            r.duration_estimate,
            r.id as string,
            x.athlete_id as string,
          );
          requireValue(
            r.duration_sec === null &&
              estimate.sport === r.sport &&
              estimate.distance_m === r.distance_m,
          );
        }
        requireDay(r.date);
        requireValue(
          r.planned_start_time === null || validInstant(r.planned_start_time),
        );
        requireValue(
          typeof r.title === "string" && typeof r.status === "string",
        );
      } else {
        requireValue(
          validInstant(r.started_at) &&
            (r.ended_at === null || validInstant(r.ended_at)) &&
            (r.planned_workout_id === null ||
              (typeof r.planned_workout_id === "string" &&
                uuid.test(r.planned_workout_id))),
        );
        tag(r.linked_goal_tag);
        for (const metric of [
          "calories",
          "avg_hr",
          "max_hr",
          "avg_speed",
          "max_speed",
          "avg_power",
          "max_power",
          "avg_cadence",
          "max_cadence",
          "cardio_load",
          "perceived_load",
          "rpe",
        ])
          requireValue(
            r[metric] === null ||
              (typeof r[metric] === "number" && Number.isFinite(r[metric])),
          );
      }
    }
  }
  const a = object(x.availability);
  requireValue(
    a.absence_means_unavailable === false &&
      Array.isArray(a.days) &&
      Array.isArray(a.carry_windows),
  );
  const seenDays = new Set<string>();
  function window(v: unknown) {
    const w = object(v);
    requireValue(
      typeof w.key === "string" &&
        validInstant(w.start_at) &&
        validInstant(w.end_at) &&
        Date.parse(w.end_at) > Date.parse(w.start_at) &&
        typeof w.max_minutes === "number" &&
        w.max_minutes > 0 &&
        Array.isArray(w.sports) &&
        Array.isArray(w.resources),
    );
  }
  for (const v of a.days) {
    const d = object(v);
    requireDay(d.date);
    requireValue(
      typeof d.date === "string" &&
        !seenDays.has(d.date) &&
        d.date >= String(x.start_date) &&
        d.date <= String(x.end_date) &&
        ["unknown", "unavailable", "available"].includes(String(d.status)) &&
        Array.isArray(d.windows),
    );
    seenDays.add(d.date);
    d.windows.forEach(window);
  }
  a.carry_windows.forEach(window);
  for (const v of x.periods) {
    const p = object(v);
    requireValue(
      typeof p.id === "string" &&
        uuid.test(p.id) &&
        typeof p.title === "string" &&
        typeof p.period_type === "string",
    );
    requireDay(p.start_date);
    requireDay(p.end_date);
  }
  return x as Feed;
}
export type Span = 1 | 7 | 28 | 144 | 168;
export function dateDistance(first: string, last: string) {
  return Math.round(
    (Date.parse(last + "T12:00:00Z") - Date.parse(first + "T12:00:00Z")) /
      86400000,
  );
}
export function dayList(first: string, last: string): string[] {
  day(first);
  day(last);
  const n = dateDistance(first, last);
  requireValue(n >= 0 && n < 366, "Legfeljebb 366 napot válassz.");
  return Array.from({ length: n + 1 }, (_, i) => addDays(first, i));
}
export function viewRange(anchor: string, span: Span) {
  day(anchor);
  const weekday = new Date(anchor + "T12:00:00Z").getUTCDay();
  const start =
    span === 7 || span === 28 || span === 168
      ? addDays(anchor, -((weekday + 6) % 7))
      : anchor;
  return { start, end: addDays(start, span - 1) };
}
export function formatDay(value: string, weekday = false) {
  return new Intl.DateTimeFormat("hu-HU", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    ...(weekday ? { weekday: "short" as const } : {}),
  }).format(new Date(value + "T12:00:00Z"));
}
export function localParts(instant: string, zone: string) {
  requireValue(validInstant(instant));
  const values: Record<string, string> = {};
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
    .formatToParts(new Date(instant))
    .forEach((p) => {
      values[p.type] = p.value;
    });
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    minute:
      Number(values.hour) * 60 +
      Number(values.minute) +
      Number(values.second) / 60,
    clock: `${values.hour}:${values.minute}`,
  };
}
export type CalendarEvent = {
  reschedule?: Planned["reschedule"];
  durationEstimate?: DurationEstimate;
  key: string;
  kind: "planned" | "session" | "availability" | "constraint";
  entityId: string;
  title: string;
  sport: string;
  date: string;
  start: string | null;
  end: string | null;
  duration: number | null;
  goal: string | null;
  goalTag: GoalTag | null;
  sourceDate?: string;
  window?: AvailableWindow;
  endEstimated?: boolean;
  linkedPlanId?: string | null;
  pairedPlan?: CalendarEvent;
  occurrence?: import("./constraints").Occurrence;
  conflict?: "fixed" | "flexible" | "review";
};
export function eventsFrom(feed: Feed): CalendarEvent[] {
  const events: CalendarEvent[] = feed.planned.map((p) => ({
    reschedule: p.reschedule,
    key: "planned:" + p.id,
    kind: "planned",
    entityId: p.id,
    title: p.title,
    sport: p.sport,
    date: p.planned_start_time
      ? localParts(p.planned_start_time, feed.timezone_name).date
      : p.date,
    sourceDate: p.date,
    start: p.planned_start_time,
    end:
      p.planned_start_time && (p.duration_sec !== null || p.duration_estimate)
        ? new Date(
            Date.parse(p.planned_start_time) +
              (p.duration_sec ?? p.duration_estimate!.duration_sec) * 1000,
          ).toISOString()
        : null,
    duration: p.duration_sec ?? p.duration_estimate?.duration_sec ?? null,
    durationEstimate:
      p.duration_sec === null ? (p.duration_estimate ?? undefined) : undefined,
    endEstimated: p.duration_sec === null && !!p.duration_estimate,
    goal: p.goal_tag?.primary_goal ?? null,
    goalTag: p.goal_tag,
  }));
  for (const s of feed.sessions)
    events.push({
      key: "session:" + s.id,
      kind: "session",
      entityId: s.id,
      title: s.name || s.sport + " edzés",
      sport: s.sport,
      date: localParts(s.started_at, feed.timezone_name).date,
      start: s.started_at,
      end:
        s.ended_at ??
        (s.duration_sec !== null
          ? new Date(
              Date.parse(s.started_at) + s.duration_sec * 1000,
            ).toISOString()
          : null),
      duration: s.duration_sec,
      goal: (s.goal_tag ?? s.linked_goal_tag)?.primary_goal ?? null,
      goalTag: s.goal_tag,
      endEstimated: !s.ended_at && s.duration_sec !== null,
      linkedPlanId: s.planned_workout_id,
    });
  const windows = [
    ...feed.availability.days.flatMap((d) =>
      d.windows.map((w) => ({ ...w, date: d.date })),
    ),
    ...feed.availability.carry_windows,
  ];
  for (const w of windows)
    events.push({
      key: "availability:" + w.date + ":" + w.key,
      kind: "availability",
      entityId: w.key,
      title: "Edzéslehetőség",
      sport: "OTHER",
      date: w.date,
      start: w.start_at,
      end: w.end_at,
      duration: (Date.parse(w.end_at) - Date.parse(w.start_at)) / 1000,
      goal: null,
      goalTag: null,
      window: w,
    });
  return events;
}
// Keep the source events for selection/editing. Only the calendar projection
// replaces a linked plan with its completion(s), at their actual timestamps.
export function calendarEntries(events: CalendarEvent[]): CalendarEvent[] {
  const plans = new Map(
    events.filter((e) => e.kind === "planned").map((e) => [e.entityId, e]),
  );
  const represented = new Set<string>();
  const entries = events.map((event) => {
    if (event.kind !== "session" || !event.linkedPlanId) return event;
    const plan = plans.get(event.linkedPlanId);
    if (!plan) return event;
    represented.add(plan.entityId);
    return { ...event, pairedPlan: plan };
  });
  return entries.filter(
    (e) => e.kind !== "planned" || !represented.has(e.entityId),
  );
}
export type Segment = {
  event: CalendarEvent;
  day: string;
  top: number;
  bottom: number;
  point: boolean;
  clockChange: boolean;
  lane: number;
  lanes: number;
};
export function segments(
  events: CalendarEvent[],
  first: string,
  last: string,
  zone: string,
): Segment[] {
  const result: Segment[] = [];
  for (const event of events) {
    if (!event.start) continue;
    const a = localParts(event.start, zone),
      b = event.end ? localParts(event.end, zone) : a;
    const endMs = event.end ? Date.parse(event.end) : Date.parse(event.start);
    const elapsed = (endMs - Date.parse(event.start)) / 60000;
    const wall = dateDistance(a.date, b.date) * 1440 + b.minute - a.minute;
    const clockChange = Math.abs(elapsed - wall) > 0.02;
    if (endMs < Date.parse(event.start)) continue;
    const startDay = a.date < first ? first : a.date,
      lastDay = b.date > last ? last : b.date;
    if (startDay > lastDay) continue;
    for (const d of dayList(startDay, lastDay)) {
      const top = d === a.date ? a.minute : 0,
        end = d === b.date ? b.minute : 1440;
      if (d !== a.date && end === 0) continue;
      const point =
        !event.end ||
        elapsed === 0 ||
        (clockChange && d === a.date && a.date === b.date);
      if (end <= top && !point) continue;
      result.push({
        event,
        day: d,
        top,
        bottom: point ? top : end,
        point,
        clockChange,
        lane: 0,
        lanes: 1,
      });
    }
  }
  return result;
}
export const MIN_ACTIVITY_HEIGHT = 32;
export function allocateLanes(
  input: Segment[],
  minimumMinutes = 1,
  clipStart = 0,
): Segment[] {
  const sorted = input
    .map((x) => ({ ...x }))
    .sort(
      (a, b) =>
        Math.max(a.top, clipStart) - Math.max(b.top, clipStart) ||
        b.bottom - a.bottom ||
        a.event.key.localeCompare(b.event.key),
    );
  let group: Segment[] = [],
    ends: number[] = [],
    until = -1;
  const finish = () => {
    for (const item of group) item.lanes = ends.length;
    group = [];
    ends = [];
  };
  for (const item of sorted) {
    const start = Math.max(item.top, clipStart);
    if (start >= until) finish();
    const end = Math.max(item.bottom, start + minimumMinutes);
    let lane = ends.findIndex((e) => e <= start);
    if (lane < 0) lane = ends.length;
    ends[lane] = end;
    item.lane = lane;
    group.push(item);
    until = group.length === 1 ? end : Math.max(until, end);
  }
  finish();
  return sorted;
}
export function formatNumber(
  value: number | null | undefined,
  unit = "",
  digits = 1,
) {
  return value === null || value === undefined
    ? "Nincs adat"
    : new Intl.NumberFormat("hu-HU", { maximumFractionDigits: digits }).format(
        value,
      ) + (unit ? " " + unit : "");
}
export function formatDuration(value: number | null | undefined) {
  if (value === null || value === undefined) return "Nincs adat";
  const seconds = Math.round(value);
  return seconds >= 3600
    ? `${Math.floor(seconds / 3600)} ó ${Math.floor((seconds % 3600) / 60)} p`
    : `${Math.floor(seconds / 60)} p${seconds % 60 ? " " + (seconds % 60) + " mp" : ""}`;
}
export type GoalBody = {
  request_id: string;
  entity_kind: "planned" | "session";
  entity_id: string;
  previous_reference: Reference | null;
  primary_goal: string | null;
};
export function readGoalBody(value: unknown): GoalBody {
  const b = object(value);
  requireValue(
    Object.keys(b).sort().join() ===
      "entity_id,entity_kind,previous_reference,primary_goal,request_id",
  );
  requireValue(
    typeof b.request_id === "string" &&
      uuid.test(b.request_id) &&
      typeof b.entity_id === "string" &&
      uuid.test(b.entity_id) &&
      ["planned", "session"].includes(String(b.entity_kind)) &&
      (b.primary_goal === null ||
        (typeof b.primary_goal === "string" &&
          Object.hasOwn(goalLabels, b.primary_goal))),
  );
  if (b.previous_reference !== null) {
    const r = object(b.previous_reference);
    requireValue(Object.keys(r).sort().join() === "artifact_id,content_hash");
    tag({ ...r, primary_goal: null });
  }
  return b as GoalBody;
}
export const GOAL_PENDING_KEY = "paddletrainer.calendar-goal.pending.v1";
export async function verifyGoalReceipt(
  value: unknown,
  body: string,
  owner: string,
) {
  const r = object(value),
    a = object(r.artifact),
    proposal = readGoalBody(JSON.parse(body));
  const { content_hash: hash, ...raw } = a;
  const scope = await sha({
    athlete_id: owner,
    entity_kind: proposal.entity_kind,
    entity_id: proposal.entity_id,
  });
  requireValue(
    r.identity_scope === "APPLICATION_DEMO_USER" &&
      r.committed === true &&
      r.planning_authorized === false &&
      r.workouts_changed === false &&
      validInstant(r.durable_available_at) &&
      a.schema_version === "calendar-workout-goal-v0.1" &&
      a.athlete_id === owner &&
      a.artifact_id ===
        `pt-workout-goal:${scope}:${proposal.request_id.replaceAll("-", "")}` &&
      a.planning_authorized === false &&
      a.workouts_changed === false &&
      validInstant(a.created_at) &&
      typeof a.revision === "number" &&
      Number.isInteger(a.revision) &&
      a.revision >= 1 &&
      (a.revision === 1) === (proposal.previous_reference === null) &&
      (await sha(a.proposal)) === (await sha(proposal)) &&
      hash === (await sha(raw)),
    "A szerver válasza nem igazolta a cél mentését. Azonos kéréssel újrapróbálható.",
  );
  return a;
}
