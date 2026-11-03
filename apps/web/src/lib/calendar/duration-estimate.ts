import { object } from "@/lib/planning-cycles/contracts";
export type DurationEstimate = {
  schema_version:
    | "calendar-duration-estimate-v0.1"
    | "calendar-duration-estimate-v0.2";
  method:
    | "personal_similar_distance_median_v1"
    | "personal_power_law_median_v1";
  athlete_id: string;
  plan_id: string;
  sport: string;
  distance_m: number;
  as_of: string;
  lookback_days: 90;
  candidate_limit: 12;
  duration_sec: number;
  lower_sec: number;
  upper_sec: number;
  sample_count: number;
  range_is_calibrated: false;
  doubling_slowdown_pct?: number;
  exponent?: number;
  extrapolated?: boolean;
  max_distance_ratio?: number;
  conditions_verified?: false;
  personal_coefficient_fitted?: false;
  coefficient_source?: "planning_default" | "profile_setting";
  coefficient_profile_reference?: {
    artifact_id: string;
    content_hash: string;
  } | null;
  samples: {
    session_id: string;
    started_at: string;
    ended_at: string;
    distance_m: number;
    elapsed_sec: number;
    basis: "elapsed" | "reported_duration";
    projected_sec: number;
    used: boolean;
  }[];
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function check(value: unknown): asserts value {
  if (!value)
    throw new Error(
      "A naptári időbecslés forrása vagy tartománya nem ellenőrizhető.",
    );
}
const instant = (v: unknown): v is string =>
  typeof v === "string" &&
  /(?:Z|[+-]\d\d:\d\d)$/.test(v) &&
  Number.isFinite(Date.parse(v));
const positive = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v > 0;
export function readDurationEstimate(
  value: unknown,
  plan: string,
  owner: string,
): DurationEstimate {
  const e = object(value);
  const power = e.schema_version === "calendar-duration-estimate-v0.2";
  check(
    (power
      ? e.method === "personal_power_law_median_v1"
      : e.schema_version === "calendar-duration-estimate-v0.1" &&
        e.method === "personal_similar_distance_median_v1") &&
      e.plan_id === plan &&
      uuid.test(plan) &&
      e.athlete_id === owner &&
      uuid.test(owner) &&
      typeof e.sport === "string" &&
      !["OTHER", "STRENGTH"].includes(e.sport) &&
      positive(e.distance_m) &&
      instant(e.as_of) &&
      e.lookback_days === 90 &&
      e.candidate_limit === 12 &&
      e.range_is_calibrated === false &&
      Array.isArray(e.samples) &&
      e.samples.length >= 1 &&
      e.samples.length <= 12 &&
      Number.isInteger(e.sample_count) &&
      Number(e.sample_count) >= 1,
  );
  if (power) {
    check(
      ["KAYAK", "RUNNING", "CYCLING", "SWIMMING"].includes(String(e.sport)) &&
        Number.isInteger(e.doubling_slowdown_pct) &&
        Number(e.doubling_slowdown_pct) >= 0 &&
        Number(e.doubling_slowdown_pct) <= 20 &&
        positive(e.exponent) &&
        Math.abs(
          e.exponent -
            (1 + Math.log2(1 + Number(e.doubling_slowdown_pct) / 100)),
        ) < 1e-10 &&
        e.max_distance_ratio === 2 &&
        typeof e.extrapolated === "boolean" &&
        e.conditions_verified === false &&
        e.personal_coefficient_fitted === false &&
        ["planning_default", "profile_setting"].includes(
          String(e.coefficient_source),
        ),
    );
    if (e.coefficient_source === "planning_default")
      check(
        e.coefficient_profile_reference === null &&
          e.doubling_slowdown_pct === 5,
      );
    else {
      const r = object(e.coefficient_profile_reference);
      check(
        typeof r.artifact_id === "string" &&
          typeof r.content_hash === "string" &&
          /^[0-9a-f]{64}$/.test(r.content_hash),
      );
    }
  }
  check(
    Number.isInteger(e.lower_sec) &&
      Number.isInteger(e.duration_sec) &&
      Number.isInteger(e.upper_sec) &&
      Number(e.lower_sec) > 0 &&
      Number(e.lower_sec) <= Number(e.duration_sec) &&
      Number(e.duration_sec) <= Number(e.upper_sec) &&
      Number(e.upper_sec) <= 86400,
  );
  const seen = new Set();
  let used = 0;
  for (const value of e.samples) {
    const s = object(value);
    check(
      typeof s.session_id === "string" &&
        uuid.test(s.session_id) &&
        !seen.has(s.session_id) &&
        instant(s.started_at) &&
        instant(s.ended_at) &&
        Date.parse(s.started_at) >= Date.parse(e.as_of) - 90 * 86400000 &&
        Date.parse(s.started_at) < Date.parse(s.ended_at) &&
        Date.parse(s.ended_at) <= Date.parse(e.as_of) &&
        positive(s.distance_m) &&
        s.distance_m / e.distance_m >= (power ? 0.5 : 0.8) &&
        s.distance_m / e.distance_m <= (power ? 2 : 1.25) &&
        positive(s.elapsed_sec) &&
        s.elapsed_sec <= 86400 &&
        positive(s.projected_sec) &&
        s.projected_sec <= 86400 &&
        (!power || s.elapsed_sec >= 300) &&
        Math.abs(
          s.elapsed_sec *
            (e.distance_m / s.distance_m) ** (power ? Number(e.exponent) : 1) -
            s.projected_sec,
        ) < 1e-6 &&
        Math.abs(
          (Date.parse(s.ended_at) - Date.parse(s.started_at)) / 1000 -
            s.elapsed_sec,
        ) < 0.002 &&
        ["elapsed", "reported_duration"].includes(String(s.basis)) &&
        typeof s.used === "boolean",
    );
    seen.add(s.session_id);
    if (s.used) used++;
  }
  check(used === e.sample_count);
  if (power) {
    const distances = (e.samples as DurationEstimate["samples"])
      .filter((s) => s.used)
      .map((s) => s.distance_m);
    check(
      e.extrapolated ===
        (Number(e.distance_m) < Math.min(...distances) ||
          Number(e.distance_m) > Math.max(...distances)),
    );
  }
  return e as DurationEstimate;
}
export function estimateLabel(e: DurationEstimate) {
  return e.duration_sec < 60
    ? `~${e.duration_sec} mp`
    : `~${Math.round(e.duration_sec / 60)} p`;
}
export function estimateRange(e: DurationEstimate) {
  return e.lower_sec < 60
    ? `${e.lower_sec} mp–${Math.ceil(e.upper_sec / 60)} p`
    : `${Math.floor(e.lower_sec / 60)}–${Math.ceil(e.upper_sec / 60)} p`;
}
