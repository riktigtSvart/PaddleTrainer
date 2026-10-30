import { contextId, isScore, metricLabels, timingLabels } from "./contracts";
import type {
  Context,
  PersonalInputs,
  Observation,
  Dataset,
} from "./contracts";
export const knownScore = (o: Observation) =>
  o.knowledge_status === "known" && typeof o.value === "number";
export const scoreObservations = (x: PersonalInputs) =>
  x.assembly.response_observations.filter(isScore);
export function contexts(x: PersonalInputs): Context[] {
  const keys = new Map<string, Context>();
  for (const o of scoreObservations(x)) keys.set(contextId(o), o);
  return [...keys.values()].sort((a, b) =>
    contextLabel(a).localeCompare(contextLabel(b), "hu"),
  );
}
export function contextLabel(x: Context) {
  return `${x.stimulus_modality_key} · ${timingLabels[x.response_timing]} · ${metricLabels[x.metric_key] ?? x.metric_key}`;
}
export function selectedObservations(x: PersonalInputs, key: string) {
  return scoreObservations(x)
    .filter((o) => contextId(o) === key)
    .sort(
      (a, b) =>
        Date.parse(a.response_observed_at) -
          Date.parse(b.response_observed_at) ||
        a.observation_id.localeCompare(b.observation_id),
    );
}
export function selectedDataset(
  x: PersonalInputs,
  key: string,
): Dataset | undefined {
  const found = x.assembly.datasets.filter(
    (d) =>
      contextId(d.response_key) === key &&
      d.predictor_key.metric_key === "duration_s" &&
      d.predictor_key.unit === "s",
  );
  if (found.length > 1)
    throw Error("Azonos elemzési környezet többször szerepel.");
  return found[0];
}
export function census(x: PersonalInputs) {
  const obs = scoreObservations(x);
  return {
    sessions: new Set(obs.map((o) => o.workout_session_id)).size,
    occasions: new Set(obs.map((o) => o.response_evidence_id)).size,
    known: obs.filter(knownScore).length,
    missing: obs.filter((o) => !knownScore(o)).length,
  };
}
export function formatInstant(value: string, zone: string, short = false) {
  return new Date(value).toLocaleString("hu-HU", {
    timeZone: zone,
    ...(short
      ? { month: "2-digit", day: "2-digit" }
      : {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }),
  });
}
export function scale(
  value: number,
  low: number,
  high: number,
  width: number,
  start = 0,
) {
  return (
    start + (high === low ? width / 2 : ((value - low) / (high - low)) * width)
  );
}
export const isolationLabels: Record<string, string> = {
  unknown: "Nem ismert",
  no_intervening_stimulus_observed: "Nem látszik köztes edzés",
  intervening_stimulus_observed: "Köztes edzés is ismert",
};
export const limitationLabels: Record<string, string> = {
  stimulus_source_coverage_unknown:
    "Az edzéselőzmények teljessége nem igazolt.",
  stimulus_source_coverage_partial: "Az edzéselőzmények részlegesek.",
  response_source_coverage_partial: "A visszajelzések lefedettsége részleges.",
  response_source_coverage_unknown: "A visszajelzések teljessége nem ismert.",
  no_observed_stimuli: "Még nincs bekötött edzésbizonyíték.",
  no_observed_responses: "Még nincs bekötött válaszmegfigyelés.",
  no_known_response_lags: "A válasz időbeli késése nem ismert.",
  no_response_metric_references: "Még nincs személyes leíró referencia.",
  no_eligible_numeric_response_samples:
    "Még nincs felhasználható számszerű válasz.",
  non_known_response_samples_present:
    "Vannak meg nem adott válaszok; ezek nem számítanak nullának.",
  known_non_numeric_response_samples_present: "Vannak nem számszerű válaszok.",
  context_fragmentation_present:
    "Az adatok több eltérő mérési környezethez tartoznak.",
};
