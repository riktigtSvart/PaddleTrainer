import { object } from "@/lib/planning-cycles/contracts";
export const metricLabels: Record<string, string> = {
  self_reported_rpe_score: "Érzékelt terhelés",
  self_reported_fatigue_score: "Fáradtság",
  self_reported_soreness_score: "Izomfájdalom",
  self_reported_recovery_score: "Regeneráltság",
  self_reported_energy_score: "Energiaszint",
};
export const timingLabels: Record<string, string> = {
  immediate: "Edzés utáni",
  same_day: "Aznap",
  next_morning: "Másnap reggeli",
  follow_up: "Későbbi",
};
export type Context = {
  metric_key: string;
  unit: string | null;
  response_timing: string;
  stimulus_modality_key: string;
};
export type Observation = {
  observation_id: string;
  athlete_id: string;
  workout_session_id: string;
  content_hash: string;
  response_evidence_id: string;
  response_evidence_hash: string;
  stimulus_id: string;
  stimulus_content_hash: string;
  metric_key: string;
  unit: string | null;
  stimulus_modality_key: string;
  response_timing: string;
  response_observed_at: string;
  response_available_at: string;
  knowledge_status: string;
  value: string | number | boolean | null;
  isolation_status: string;
};
export type Pair = {
  pair_id: string;
  workout_session_id: string;
  response_observation_id: string;
  predictor_numeric_value: number | null;
  response_numeric_value: number | null;
  eligibility: string;
  exclusion_reasons: string[];
};
export type Dataset = {
  dataset_id: string;
  response_key: Context;
  predictor_key: { metric_key: string; unit: string | null };
  pairs: Pair[];
  eligible_numeric_pair_count: number;
  ineligible_pair_count: number;
};
export type PersonalInputs = {
  schema_version: string;
  athlete_id: string;
  timezone_name: string;
  window_start_at: string;
  response_window_end_at: string;
  as_of: string;
  information_cutoff_at: string;
  assembly: {
    response_observations: Observation[];
    datasets: Dataset[];
    data_sufficiency: {
      status: string;
      stimulus_coverage: string;
      response_coverage: string;
      limitation_codes: string[];
    };
  };
};
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const hash = /^[a-f0-9]{64}$/;
function requireValue(ok: unknown): asserts ok {
  if (!ok)
    throw Error(
      "A személyes elemzés válasza nem ellenőrizhető. Próbáld újra, vagy válassz rövidebb időszakot.",
    );
}
const text = (x: unknown): x is string =>
  typeof x === "string" && x.length > 0 && x.length <= 2048;
const instant = (x: unknown): x is string =>
  typeof x === "string" &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(x) &&
  Number.isFinite(Date.parse(x));
const count = (x: unknown): x is number =>
  Number.isSafeInteger(x) && Number(x) >= 0;
const falseFlags = (x: Record<string, unknown>, keys: string[]) =>
  keys.forEach((k) => requireValue(x[k] === false));
const observationFlags = [
  "causal_attribution_established",
  "effect_inference_authorized",
  "readiness_inference_authorized",
  "performance_prediction_authorized",
  "prescription_change_authorized",
];
const assemblyFlags = [
  ...observationFlags,
  "association_supported",
  "prospective_validation_established",
  "planning_authorized",
];
function context(value: unknown): Context {
  const x = object(value);
  requireValue(
    text(x.metric_key) &&
      (x.unit === null || text(x.unit)) &&
      text(x.stimulus_modality_key) &&
      typeof x.response_timing === "string" &&
      Object.hasOwn(timingLabels, x.response_timing),
  );
  return x as Context;
}
export const contextId = (key: Context) =>
  JSON.stringify([
    key.metric_key,
    key.unit,
    key.response_timing,
    key.stimulus_modality_key,
  ]);
export function isScore(x: Context) {
  return Object.hasOwn(metricLabels, x.metric_key) && x.unit === null;
}
export function readPersonalInputs(value: unknown): PersonalInputs {
  const x = object(value),
    a = object(x.assembly);
  requireValue(
    x.schema_version === "feedback-personal-inputs-v0.1" &&
      typeof x.athlete_id === "string" &&
      uuid.test(x.athlete_id),
  );
  requireValue(typeof x.timezone_name === "string");
  try {
    new Intl.DateTimeFormat("hu-HU", { timeZone: x.timezone_name }).format(0);
  } catch {
    requireValue(false);
  }
  requireValue(
    instant(x.window_start_at) &&
      instant(x.as_of) &&
      instant(x.information_cutoff_at),
  );
  requireValue(
    x.selection_scope === "response_observed_at" &&
      instant(x.response_window_end_at) &&
      Date.parse(x.window_start_at) <= Date.parse(x.response_window_end_at) &&
      Date.parse(x.response_window_end_at) <= Date.parse(x.as_of) &&
      Date.parse(x.as_of) === Date.parse(x.information_cutoff_at),
  );
  falseFlags(x, ["planning_authorized", "model_updated"]);
  falseFlags(a, assemblyFlags);
  requireValue(
    a.evidence_level_ceiling === "descriptive" &&
      text(a.source_history_id) &&
      typeof a.source_history_content_hash === "string" &&
      hash.test(a.source_history_content_hash),
  );
  requireValue(
    Array.isArray(a.response_observations) &&
      a.response_observations.length <= 10000 &&
      Array.isArray(a.datasets) &&
      a.datasets.length <= 10000,
  );
  const observations = new Map<string, Observation>();
  for (const raw of a.response_observations) {
    const o = object(raw);
    context(o);
    requireValue(
      o.schema_version === "response-metric-observation-v0.1" &&
        o.athlete_id === x.athlete_id &&
        typeof o.workout_session_id === "string" &&
        uuid.test(o.workout_session_id),
    );
    requireValue(text(o.observation_id) && !observations.has(o.observation_id));
    for (const k of [
      "content_hash",
      "response_evidence_hash",
      "stimulus_content_hash",
    ])
      requireValue(typeof o[k] === "string" && hash.test(o[k] as string));
    for (const k of ["response_evidence_id", "stimulus_id"])
      requireValue(text(o[k]));
    requireValue(
      instant(o.response_observed_at) && instant(o.response_available_at),
    );
    requireValue(
      Date.parse(o.response_observed_at) >= Date.parse(x.window_start_at) &&
        (Date.parse(o.response_observed_at) <
          Date.parse(x.response_window_end_at) ||
          (x.response_window_end_at === x.as_of &&
            Date.parse(o.response_observed_at) === Date.parse(x.as_of))) &&
        Date.parse(o.response_available_at) >=
          Date.parse(o.response_observed_at) &&
        Date.parse(o.response_available_at) <=
          Date.parse(x.information_cutoff_at),
    );
    requireValue(
      [
        "known",
        "unknown",
        "not_applicable",
        "not_measured",
        "not_asked",
      ].includes(String(o.knowledge_status)),
    );
    requireValue(
      o.knowledge_status === "known"
        ? typeof o.value === "string" ||
            typeof o.value === "boolean" ||
            (typeof o.value === "number" && Number.isFinite(o.value))
        : o.value === null,
    );
    if (isScore(o as Context) && o.knowledge_status === "known")
      requireValue(
        typeof o.value === "number" &&
          Number.isFinite(o.value) &&
          o.value >= 0 &&
          o.value <= 10,
      );
    requireValue(text(o.isolation_status));
    falseFlags(o, observationFlags);
    observations.set(o.observation_id, o as Observation);
  }
  const seen = new Set<string>(),
    datasetIds = new Set<string>(),
    datasetContexts = new Set<string>();
  for (const raw of a.datasets) {
    const d = object(raw),
      key = context(d.response_key),
      predictor = object(d.predictor_key);
    requireValue(
      d.schema_version === "personal-association-dataset-v0.1" &&
        d.athlete_id === x.athlete_id &&
        d.evidence_level_ceiling === "descriptive",
    );
    falseFlags(d, assemblyFlags);
    requireValue(
      d.source_history_id === a.source_history_id &&
        d.source_history_content_hash === a.source_history_content_hash,
    );
    requireValue(text(d.dataset_id) && !datasetIds.has(d.dataset_id));
    datasetIds.add(d.dataset_id);
    requireValue(
      text(predictor.metric_key) &&
        (predictor.unit === null || text(predictor.unit)),
    );
    const datasetKey = JSON.stringify([
      contextId(key),
      predictor.metric_key,
      predictor.unit,
    ]);
    requireValue(!datasetContexts.has(datasetKey));
    datasetContexts.add(datasetKey);
    requireValue(
      Array.isArray(d.pairs) &&
        count(d.observed_pair_count) &&
        d.observed_pair_count === d.pairs.length &&
        count(d.eligible_numeric_pair_count) &&
        count(d.ineligible_pair_count),
    );
    let eligible = 0;
    for (const raw of d.pairs) {
      const p = object(raw);
      requireValue(text(p.pair_id) && !seen.has(p.pair_id));
      seen.add(p.pair_id);
      const o = observations.get(String(p.response_observation_id));
      requireValue(o);
      requireValue(
        p.schema_version === "personal-association-pair-v0.1" &&
          p.athlete_id === x.athlete_id &&
          p.workout_session_id === o.workout_session_id &&
          p.response_observation_content_hash === o.content_hash &&
          p.response_evidence_id === o.response_evidence_id &&
          p.response_evidence_hash === o.response_evidence_hash &&
          p.stimulus_id === o.stimulus_id &&
          p.stimulus_content_hash === o.stimulus_content_hash,
      );
      requireValue(
        contextId(context(p.response_key)) === contextId(key) &&
          contextId(o) === contextId(key),
      );
      const pk = object(p.predictor_key);
      requireValue(
        pk.metric_key === predictor.metric_key && pk.unit === predictor.unit,
      );
      requireValue(
        p.response_knowledge_status === o.knowledge_status &&
          p.response_value === o.value &&
          p.response_observed_at === o.response_observed_at &&
          p.response_available_at === o.response_available_at,
      );
      requireValue(
        Array.isArray(p.exclusion_reasons) && p.exclusion_reasons.every(text),
      );
      falseFlags(p, [
        "association_supported",
        "causal_attribution_established",
        "effect_inference_authorized",
        "prediction_authorized",
        "planning_authorized",
      ]);
      if (p.eligibility === "eligible_numeric_pair") {
        requireValue(
          p.exclusion_reasons.length === 0 &&
            p.predictor_knowledge_status === "known" &&
            p.predictor_observed_unit === predictor.unit &&
            typeof p.predictor_numeric_value === "number" &&
            Number.isFinite(p.predictor_numeric_value) &&
            p.predictor_numeric_value === p.predictor_value,
        );
        requireValue(
          o.knowledge_status === "known" &&
            typeof o.value === "number" &&
            p.response_numeric_value === o.value,
        );
        if (predictor.metric_key === "duration_s")
          requireValue(p.predictor_numeric_value >= 0);
        eligible++;
      } else
        requireValue(
          p.eligibility === "ineligible" && p.exclusion_reasons.length > 0,
        );
    }
    requireValue(
      d.eligible_numeric_pair_count === eligible &&
        d.ineligible_pair_count === d.pairs.length - eligible,
    );
  }
  const s = object(a.data_sufficiency);
  requireValue(
    ["unknown", "insufficient", "descriptive_supported"].includes(
      String(s.status),
    ) &&
      ["unknown", "partial", "complete"].includes(
        String(s.stimulus_coverage),
      ) &&
      ["unknown", "partial", "complete"].includes(
        String(s.response_coverage),
      ) &&
      Array.isArray(s.limitation_codes) &&
      s.limitation_codes.every(text),
  );
  falseFlags(s, [
    "association_inference_authorized",
    ...observationFlags,
    "planning_authorized",
  ]);
  return x as PersonalInputs;
}
export type Range = { start: string; end: string };
export function checkedRange(start: string, end: string): Range {
  const valid = (x: string) =>
    /^\d{4}-\d{2}-\d{2}$/.test(x) &&
    Number.isFinite(Date.parse(x + "T00:00:00Z")) &&
    new Date(x + "T00:00:00Z").toISOString().slice(0, 10) === x;
  if (
    !valid(start) ||
    !valid(end) ||
    start < "1900-01-01" ||
    end > "2100-12-31" ||
    start > end ||
    (Date.parse(end) - Date.parse(start)) / 86400000 >= 366
  )
    throw Error("Adj meg legfeljebb 366 napos, érvényes időszakot.");
  return { start, end };
}
export async function loadPersonalInputs(
  range: Range | null,
  signal?: AbortSignal,
): Promise<PersonalInputs> {
  if (range) checkedRange(range.start, range.end);
  const query = range
    ? "?" +
      new URLSearchParams({ start_date: range.start, end_date: range.end })
    : "";
  const reply = await fetch("/api/calendar/learning-inputs" + query, {
    method: "GET",
    cache: "no-store",
    signal,
    headers: { Accept: "application/json" },
  });
  if (!reply.ok)
    throw Error(
      reply.status === 409 || reply.status === 422
        ? "Az időszak vagy a forrásadat most nem értelmezhető. Ellenőrizd a dátumokat; jövőbeli időszak nem kérhető."
        : "A személyes tapasztalatok most nem olvashatók be. Próbáld újra.",
    );
  return readPersonalInputs(await reply.json());
}
