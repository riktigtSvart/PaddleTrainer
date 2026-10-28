import { object } from "@/lib/planning-cycles/contracts";

export const metricInfo = {
  heart_rate_bpm: { label: "Pulzus", unit: "bpm", color: "var(--pt-goal-speed)" },
  speed_kmh: { label: "Sebesség", unit: "km/h", color: "var(--pt-goal-aerobic)" },
  pace_sec_km: { label: "Iram · sebességből számított", unit: "perc/km", color: "var(--pt-goal-vo2)" },
  distance_m: { label: "Mért táv", unit: "m", color: "var(--pt-goal-technique)" },
  cadence_per_min: { label: "Frekvencia", unit: "1/perc", color: "var(--pt-goal-recovery)" },
  power_w: { label: "Teljesítmény · bal + jobb", unit: "W", color: "var(--pt-goal-strength)" },
  left_power_w: { label: "Bal oldali teljesítmény", unit: "W", color: "var(--pt-goal-strength)" },
  right_power_w: { label: "Jobb oldali teljesítmény", unit: "W", color: "var(--pt-goal-anaerobic)" },
  altitude_m: { label: "Magasság", unit: "m", color: "var(--pt-muted)" },
  temperature_c: { label: "Hőmérséklet", unit: "°C", color: "var(--pt-warning)" },
} as const;
export type MetricKey = keyof typeof metricInfo;
const sourceTypes: Record<string, MetricKey> = { HEART_RATE: "heart_rate_bpm", SPEED: "speed_kmh", DISTANCE: "distance_m",
  CADENCE: "cadence_per_min", LEFT_CRANK_CURRENT_POWER: "left_power_w", RIGHT_CRANK_CURRENT_POWER: "right_power_w",
  ALTITUDE: "altitude_m", TEMPERATURE: "temperature_c" };
export const summaryKeys = ["duration_sec", "distance_m", "calories", "avg_hr", "max_hr", "avg_speed", "max_speed",
  "avg_cadence", "max_cadence", "avg_power", "max_power", "cardio_load", "perceived_load", "rpe"] as const;
export type Series = { id: string; exercise_index: number; source_path: string; source_type: string; metric_key: MetricKey;
  unit: string; interval_ms: number | null; slot_count: number; valid_sample_count: number; missing_sample_count: number;
  values: (number | null)[]; issues: string[]; derived?: boolean };
export type Session = Record<typeof summaryKeys[number], number | null> & { id: string; name: string | null; sport: string;
  external_provider: string; external_id: string; started_at: string; ended_at: string | null;
  planned_workout_id: string | null; planned_workout_link_source: string | null };
export type Block = { id: string; position: number; block_type: string; name: string | null; duration_sec: number | null;
  distance_m: number | null; intensity_type: string | null; intensity_min: number | null; intensity_max: number | null;
  repeat_count: number | null; parent_block_id: string | null };
export type Plan = { id: string; date: string; title: string; description: string | null; sport: string; status: string;
  planned_start_time: string | null; duration_sec: number | null; distance_m: number | null; blocks: Block[] };
export type MetricZones<Unit extends string = string> = { unit: Unit; source_path: string; zones: { index: number; low: number; high: number }[] };
export type HeartRateZones = MetricZones<"bpm">;
export type SpeedZones = MetricZones<"km/h">;
export type PowerZones = MetricZones<"W">;
export type SectionRow = { id: string; position: number; exercise_index: number; duration_sec: number | null; distance_m: number | null;
  avg_hr: number | null; avg_speed: number | null; avg_power: number | null; split_time_sec: number | null; issues: string[] };
export type SectionGroup = { id: string; kind: "exercises" | "manual_laps" | "automatic_laps"; exercise_index: number | null; source_path: string; rows: SectionRow[] };
export type Sections = { groups: SectionGroup[]; row_count: number; issues: string[] };
export type PlannedPhase = { id: string; label: string; source_block_id: string | null; from_ms: number | null; to_ms: number | null; duration_ms: number | null; distance_m?: number;
  advance?: "AUTOMATIC" | "MANUAL" | "UNKNOWN"; target?: { type: string; low: number; high: number } | null; source_pointer?: string | null };
export type PlannedPart = { index: number; phases: PlannedPhase[]; total_ms: number | null; issues: string[] };
export type PlanTimeline = { schema_version: "session-plan-timeline-v0.1"; plan_id: string | null;
  source: "stored_blocks" | "stored_polar_target" | "unavailable"; parts: PlannedPart[]; issues: string[]; content_hash: string };
export type Analysis = { schema_version: "session-analysis-v0.1"; athlete_id: string; timezone_name: string; retrieved_at: string;
  session: Session; plan: Plan | null; link_state: "linked" | "unlinked" | "linked_plan_unavailable";
  samples: { provider: string; time_basis: "exercise_sample_index_times_interval";
    content_hash?: string; exercises: { index: number; source_path: string; source_start: string | null; clock_issues?: string[]; heart_rate_zones?: HeartRateZones | null; speed_zones?: SpeedZones | null; power_zones?: PowerZones | null }[]; series: Series[];
    unsupported: { exercise_index: number; source_path: string; source_type: string; slot_count: number }[];
    issues: string[]; slot_count: number; valid_sample_count: number };
  plan_timeline?: PlanTimeline; sections?: Sections; planning_authorized: false; workouts_changed: false };

export const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function check(v: unknown): asserts v { if (!v) throw new Error("Az edzés adatai vagy mintasorai nem ellenőrizhetők."); }
const text = (v: unknown): v is string => typeof v === "string";
const nullableText = (v: unknown) => v === null || text(v);
const numeric = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v));
const integer = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0;
const instant = (v: unknown) => text(v) && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const nullableInstant = (v: unknown) => v === null || instant(v);
const strings = (v: unknown) => Array.isArray(v) && v.length <= 512 && v.every(text);
export function readAnalysis(value: unknown, sessionId: string): Analysis {
  const a = object(value), s = object(a.session), c = object(a.samples);
  check(a.schema_version === "session-analysis-v0.1" && text(a.athlete_id) && uuid.test(a.athlete_id) &&
    text(a.timezone_name) && instant(a.retrieved_at) && a.planning_authorized === false && a.workouts_changed === false &&
    uuid.test(sessionId) && s.id === sessionId && text(s.sport) && nullableText(s.name) && text(s.external_provider) &&
    text(s.external_id) && instant(s.started_at) && nullableInstant(s.ended_at) &&
    (s.planned_workout_id === null || (text(s.planned_workout_id) && uuid.test(s.planned_workout_id))) && nullableText(s.planned_workout_link_source) &&
    summaryKeys.every(k => numeric(s[k])));
  new Intl.DateTimeFormat("hu-HU", { timeZone: a.timezone_name });
  check(["linked", "unlinked", "linked_plan_unavailable"].includes(String(a.link_state)));
  if (a.plan !== null) {
    const p = object(a.plan);
    check(a.link_state === "linked" && p.id === s.planned_workout_id && text(p.id) && uuid.test(p.id) &&
      text(p.date) && /^\d{4}-\d{2}-\d{2}$/.test(p.date) && new Date(p.date).toISOString().slice(0, 10) === p.date &&
      text(p.title) && text(p.sport) && text(p.status) && nullableText(p.description) && nullableInstant(p.planned_start_time) &&
      numeric(p.duration_sec) && numeric(p.distance_m) && Array.isArray(p.blocks) && p.blocks.length <= 4000);
    const ids = new Set();
    for (const item of p.blocks) { const b = object(item); check(text(b.id) && uuid.test(b.id) && !ids.has(b.id) && integer(b.position) &&
      text(b.block_type) && nullableText(b.name) && numeric(b.duration_sec) && numeric(b.distance_m) && nullableText(b.intensity_type) &&
      numeric(b.intensity_min) && numeric(b.intensity_max) && (b.repeat_count === null || integer(b.repeat_count)) &&
      (b.parent_block_id === null || (text(b.parent_block_id) && uuid.test(b.parent_block_id)))); ids.add(b.id); }
    check(p.blocks.every(b => b.parent_block_id === null || ids.has(b.parent_block_id)));
  } else check(a.link_state === (s.planned_workout_id === null ? "unlinked" : "linked_plan_unavailable"));
  check(c.provider === s.external_provider && c.time_basis === "exercise_sample_index_times_interval" &&
    Array.isArray(c.exercises) && c.exercises.length <= 64 && Array.isArray(c.series) && c.series.length <= 128 &&
    Array.isArray(c.unsupported) && c.unsupported.length <= 128 && strings(c.issues));
  const exercises = new Set();
  if (c.content_hash !== undefined) check(text(c.content_hash) && /^[0-9a-f]{64}$/.test(c.content_hash));
  for (const item of c.exercises) {
    const e = object(item); check(integer(e.index) && !exercises.has(e.index) && text(e.source_path) && nullableText(e.source_start)); exercises.add(e.index);
    if (e.clock_issues !== undefined) check(strings(e.clock_issues));
    for (const [field, unit] of [["heart_rate_zones", "bpm"], ["speed_zones", "km/h"], ["power_zones", "W"]] as const) {
      if (e[field] === undefined || e[field] === null) continue;
      const definition = object(e[field]);
      check(definition.unit === unit && text(definition.source_path) &&
        definition.source_path.startsWith(e.source_path) && /^\.zones\[\d+\]$/.test(definition.source_path.slice(e.source_path.length)) &&
        Array.isArray(definition.zones) && definition.zones.length === 5);
      let previousHigh = 0;
      for (const [index, value] of definition.zones.entries()) {
        const z = object(value);
        check(z.index === index + 1 && typeof z.low === "number" && typeof z.high === "number" &&
          Number.isFinite(z.low) && Number.isFinite(z.high) && z.low >= 0 && z.low < z.high && z.high <= 1e12 && z.low >= previousHigh &&
          (unit !== "bpm" || z.low > 0 && z.high < 1000));
        previousHigh = z.high;
      }
    }
  }
  let slots = 0, valid = 0; const ids = new Set();
  for (const item of c.series) {
    const r = object(item); check(text(r.id) && !ids.has(r.id) && exercises.has(r.exercise_index) && text(r.source_path) &&
      text(r.source_type) && sourceTypes[r.source_type] === r.metric_key && r.metric_key !== undefined &&
      metricInfo[r.metric_key as MetricKey].unit === r.unit && r.derived === undefined &&
      (r.interval_ms === null || (integer(r.interval_ms) && Number(r.interval_ms) > 0 && Number(r.interval_ms) <= 86400000)) &&
      Array.isArray(r.values) && r.values.length <= 360000 && r.values.every(v => numeric(v) &&
        (v === null || Number(v) >= 0 || ["altitude_m", "temperature_c"].includes(String(r.metric_key)))) &&
      r.slot_count === r.values.length && r.valid_sample_count === r.values.filter(v => v !== null).length &&
      r.missing_sample_count === Number(r.slot_count) - Number(r.valid_sample_count) && strings(r.issues));
    slots += Number(r.slot_count); valid += Number(r.valid_sample_count); ids.add(r.id);
  }
  check(slots <= 500000 && slots === c.slot_count && valid === c.valid_sample_count);
  let unsupportedSlots = 0;
  for (const item of c.unsupported) { const u = object(item); check(exercises.has(u.exercise_index) && text(u.source_path) && text(u.source_type) && integer(u.slot_count)); unsupportedSlots += Number(u.slot_count); }
  check(unsupportedSlots + slots <= 500000);
  if (a.sections !== undefined) {
    const sections = object(a.sections);
    check(Array.isArray(sections.groups) && sections.groups.length <= 129 && strings(sections.issues));
    const groupIds = new Set(), rowIds = new Set(); let count = 0;
    for (const item of sections.groups) {
      const group = object(item);
      check(text(group.id) && !groupIds.has(group.id) && text(group.source_path) && Array.isArray(group.rows) &&
        ["exercises", "manual_laps", "automatic_laps"].includes(String(group.kind)));
      groupIds.add(group.id);
      const exercise = c.exercises.map(object).find(e => e.index === group.exercise_index);
      if (group.kind === "exercises") check(group.exercise_index === null && group.id === "exercises" && ["exerciseSamples", "exercises"].includes(group.source_path));
      else check(exercise && group.id === group.source_path && group.source_path === exercise.source_path + ".laps." + (group.kind === "manual_laps" ? "laps" : "autoLaps"));
      let previous = -1;
      for (const value of group.rows) {
        const row = object(value);
        check(text(row.id) && !rowIds.has(row.id) && exercises.has(row.exercise_index) && integer(row.position) && Number(row.position) > previous && strings(row.issues) &&
          ["duration_sec", "distance_m", "avg_hr", "avg_speed", "avg_power", "split_time_sec"].every(k => row[k] === null || typeof row[k] === "number" && Number.isFinite(row[k]) && Number(row[k]) >= 0 && Number(row[k]) <= 1e12));
        if (group.kind === "exercises") check(row.position === row.exercise_index && row.id === group.source_path + "[" + row.position + "]");
        else check(row.exercise_index === group.exercise_index && row.id === group.source_path + "[" + row.position + "]");
        rowIds.add(row.id); previous = Number(row.position); count++;
      }
    }
    check(count <= 4000 && count === sections.row_count);
  }
  if (a.plan_timeline !== undefined) {
    const timeline = object(a.plan_timeline);
    check(timeline.schema_version === "session-plan-timeline-v0.1" && timeline.plan_id === (a.plan === null ? null : object(a.plan).id) &&
      ["stored_blocks", "stored_polar_target", "unavailable"].includes(String(timeline.source)) && Array.isArray(timeline.parts) && timeline.parts.length <= 64 &&
      strings(timeline.issues) && text(timeline.content_hash) && /^[0-9a-f]{64}$/.test(timeline.content_hash));
    check(timeline.source === "unavailable" ? timeline.parts.length === 0 : a.plan !== null);
    let count = 0; const partIds = new Set(), phaseIds = new Set();
    const time = (v: unknown) => v === null || typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1e12;
    for (const value of timeline.parts) {
      const part = object(value); check(integer(part.index) && Number(part.index) < 64 && !partIds.has(part.index) && Array.isArray(part.phases) && strings(part.issues));
      partIds.add(part.index); let cursor: number | null = 0;
      for (const item of part.phases) {
        const phase = object(item); count++;
        check(text(phase.id) && !phaseIds.has(phase.id) && text(phase.label) && time(phase.duration_ms) && phase.from_ms === cursor && time(phase.to_ms));
        if (phase.distance_m !== undefined) check(phase.distance_m !== null && time(phase.distance_m) && phase.duration_ms === null);
        if (phase.advance !== undefined) check(["AUTOMATIC", "MANUAL", "UNKNOWN"].includes(String(phase.advance)));
        if (phase.source_pointer !== undefined) check(phase.source_pointer === null || text(phase.source_pointer) && phase.source_pointer.length <= 1000 && /^exercise\[\d+\]\.phaseOrRepeat\[\d+\](\.phaseOrRepeat\[\d+\])*$/.test(phase.source_pointer));
        if (phase.target !== undefined && phase.target !== null) {
          const target = object(phase.target); check(text(target.type) && target.type.length <= 32 && target.low !== null && target.high !== null && time(target.low) && time(target.high) && Number(target.low) <= Number(target.high));
        }
        const end: number | null = cursor !== null && phase.duration_ms !== null && Number(cursor) + Number(phase.duration_ms) <= 1e12 ? cursor + Number(phase.duration_ms) : null;
        check(phase.to_ms === end);
        if (timeline.source === "stored_blocks") check(a.plan !== null && object(a.plan).blocks instanceof Array && (object(a.plan).blocks as Block[]).some(b => b.id === phase.source_block_id && (phase.distance_m === undefined || b.distance_m === phase.distance_m)));
        else check(phase.source_block_id === null);
        cursor = end; phaseIds.add(phase.id);
      }
      check(part.total_ms === cursor);
    }
    check(count <= 2048);
  }
  return a as Analysis;
}
export async function fetchAnalysis(id: string, signal?: AbortSignal): Promise<Analysis> {
  check(uuid.test(id));
  const response = await fetch(`/api/calendar/sessions/${id}`, { cache: "no-store", signal });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    const code = error?.detail?.code;
    const message = response.status === 404 ? "Az edzés nem található ebben a fiókban." :
      code === "CALENDAR_SESSION_SOURCE_TOO_LARGE" ? "A mintasor a jelenlegi részletező méretkorlátjánál nagyobb. A tárolt adatok megmaradtak." : "Az edzés adatai most nem tölthetők be.";
    throw new Error(message);
  }
  return readAnalysis(await response.json(), id);
}
