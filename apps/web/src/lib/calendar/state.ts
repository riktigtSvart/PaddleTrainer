import { metrics } from "@/lib/athlete-setup/contracts";
import type {
  Aggregation,
  Artifact,
  Candidate,
  Method,
  Profile,
} from "@/lib/athlete-setup/contracts";
export const stateMetricLabels: Record<string, string> = {
  sleep_duration_sec: "Alvásidő",
  daily_steps: "Rögzített lépések",
  resting_hr_bpm: "Nyugalmi pulzus",
  hrv_rmssd_ms: "HRV RMSSD",
  body_mass_kg: "Testsúly",
  vo2max_ml_kg_min: "VO₂max",
};
export type StateRow = {
  id: string;
  metric: string;
  value: string;
  unit: string;
  provider: string;
  method: Method;
  aggregation: Aggregation;
  replaced: boolean;
  partial: boolean;
};
/** Keep raw versions and explicitly declared corrections distinct; never combine devices. */
export function stateRows(
  history: Candidate[],
  profile: Artifact | null,
  date: string,
): StateRow[] {
  const sources = new Map(history.map((row) => [row.artifact_id, row]));
  for (const row of profile?.imported_observations ?? [])
    if (!sources.has(row.artifact_id)) sources.set(row.artifact_id, row);
  const observations =
    profile?.kind === "profile"
      ? (profile.proposal.data as Profile).manual_observations
      : [];
  const manual = observations.filter(
    (row) =>
      row.start_date === date &&
      row.end_date === date &&
      Object.hasOwn(stateMetricLabels, row.metric),
  );
  const superseded = new Set(
    manual.flatMap((row) =>
      row.supersedes_candidate_id ? [row.supersedes_candidate_id] : [],
    ),
  );
  const rows: StateRow[] = [...sources.values()]
    .filter(
      (row) =>
        row.start_date === date &&
        row.end_date === date &&
        Object.hasOwn(stateMetricLabels, row.metric),
    )
    .map((row) => ({
      id: row.artifact_id,
      metric: row.metric,
      value: row.value,
      unit: row.unit,
      provider: row.provider,
      method: row.method,
      aggregation: row.aggregation,
      replaced: superseded.has(row.artifact_id),
      partial: row.coverage.completeness === "sampled",
    }));
  for (const row of manual)
    rows.push({
      id: "manual:" + row.observation_id,
      metric: row.metric,
      value: row.value,
      unit: metrics[row.metric].unit,
      provider: "Kézi bevitel",
      method: row.method,
      aggregation: row.aggregation,
      replaced: false,
      partial: false,
    });
  return rows;
}
