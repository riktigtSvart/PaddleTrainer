import { decimal, lines, reference, utcInput } from "./contracts";
import type {
  Catalog,
  Endpoint,
  GoalRole,
  MacroArtifact,
  MacroProposal,
  MeasurementProposal,
  Period,
  ProtocolArtifact,
  ProtocolProposal,
  Receipt,
} from "./types";

export function text(data: FormData, key: string): string {
  const value = data.get(key);
  if (typeof value !== "string" || !value.trim())
    throw new Error("Minden kötelező mezőt tölts ki.");
  if (value.length > 4000)
    throw new Error("Egy szöveges mező legfeljebb 4000 karakter lehet.");
  return value.trim();
}
function optional(data: FormData, key: string) {
  const value = data.get(key);
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
function revision(base?: Receipt<MacroArtifact | ProtocolArtifact>) {
  const value = base ? base.artifact.proposal.revision + 1 : 1;
  if (value > 64) throw new Error("A verziószám felső határa 64.");
  return {
    revision: value,
    supersedes: base ? reference(base.artifact) : null,
  };
}
function role(data: FormData, key: string, catalog: Catalog): GoalRole {
  const value = text(data, key) as GoalRole;
  if (!catalog.goal_roles.includes(value))
    throw new Error(
      "Válassz kifejezett célszerepet minden képességhez és mezociklushoz.",
    );
  return value;
}
export function macroProposal(
  data: FormData,
  catalog: Catalog,
  period: Period,
  children: Period[],
  base?: Receipt<MacroArtifact>,
): MacroProposal {
  const keys = data.getAll("capability").map(String);
  if (
    !keys.length ||
    new Set(keys).size !== keys.length ||
    keys.some((key) => !catalog.capabilities.includes(key))
  )
    throw new Error(
      "Válassz legalább egy fejlesztendő vagy karbantartandó képességet.",
    );
  if (!children.length || children.length * keys.length > 4096)
    throw new Error(
      "A makrociklushoz 1–4096 kifejezett képesség–mezociklus hozzárendelés szükséges.",
    );
  return {
    macrocycle_period_id: period.id,
    ...revision(base),
    rationale: text(data, "rationale"),
    goals: keys.map((capability_key) => ({
      capability_key,
      role: role(data, `${capability_key}.role`, catalog),
      rationale: text(data, `${capability_key}.rationale`),
    })),
    mesocycle_directives: children.flatMap((child) =>
      keys.map((capability_key) => ({
        mesocycle_period_id: child.id,
        capability_key,
        role: role(data, `${child.id}.${capability_key}.role`, catalog),
        rationale: text(data, `${child.id}.${capability_key}.rationale`),
      })),
    ),
  };
}
export function protocolProposal(
  data: FormData,
  catalog: Catalog,
  macro: Receipt<MacroArtifact>,
  mesocycleId: string,
  ids: string[],
  base?: Receipt<ProtocolArtifact>,
): ProtocolProposal {
  const directives = macro.artifact.proposal.mesocycle_directives.filter(
    (d) => d.mesocycle_period_id === mesocycleId,
  );
  if (
    !directives.length ||
    !macro.artifact.sources.mesocycles.some((p) => p.period_id === mesocycleId)
  )
    throw new Error("Válassz mezociklust a pontos makrociklus-verzióból.");
  const endpoints: Endpoint[] = ids.map((id) => {
    const key = `e.${id}.`,
      metric = catalog.metrics.find(
        (m) => m.metric_key === text(data, key + "metric"),
      );
    if (
      !metric ||
      !directives.some((d) => d.capability_key === metric.capability_key)
    )
      throw new Error(
        "A mérőszám képessége nem szerepel ebben a mezociklusban.",
      );
    const endpointRole = text(data, key + "role");
    if (!["primary", "supporting", "context"].includes(endpointRole))
      throw new Error("Válaszd ki a mérési cél szerepét.");
    if (
      (!metric.primary_endpoint_eligible && endpointRole === "primary") ||
      (metric.evidence_kind === "subjective_context" &&
        endpointRole !== "context")
    )
      throw new Error(
        "Ez a mérőszám csak a megengedett mérési szerepben használható.",
      );
    const origin = text(data, key + "origin");
    if (origin !== "explicit_custom" && origin !== "external_reference")
      throw new Error("Add meg a protokoll eredetét.");
    const error = optional(data, key + "error"),
      source = optional(data, key + "errorSource");
    if (endpointRole === "primary" && Boolean(error) !== Boolean(source))
      throw new Error("A mérési hiba és a forrása együtt adható meg.");
    const basis = text(data, key + "basis");
    if (
      endpointRole === "primary" &&
      basis === "favourable_percent_change" &&
      metric.scale !== "ratio"
    )
      throw new Error(
        "Ehhez a mérőszámhoz nem használható százalékos változás.",
      );
    if (
      !["favourable_absolute_change", "favourable_percent_change"].includes(
        basis,
      )
    )
      throw new Error("Válaszd ki a változás mértékét.");
    const maximum = optional(data, key + "maximum");
    const endpoint: Endpoint = {
      endpoint_key: text(data, key + "key"),
      capability_key: metric.capability_key,
      metric_key: metric.metric_key,
      role: endpointRole as Endpoint["role"],
      procedure: {
        protocol_key: text(data, key + "protocolKey"),
        protocol_version: text(data, key + "protocolVersion"),
        origin,
        source_reference: text(data, key + "source"),
        modality_key: text(data, key + "modality"),
        exercise_or_task: text(data, key + "task"),
        procedure: text(data, key + "procedure"),
        equipment_and_processing: text(data, key + "equipment"),
        comparability_conditions: lines(text(data, key + "conditions")),
      },
      baseline_window: {
        starts_at: utcInput(text(data, key + "baselineStart")),
        ends_at: utcInput(text(data, key + "baselineEnd")),
      },
      followup_window: {
        starts_at: utcInput(text(data, key + "followupStart")),
        ends_at: utcInput(text(data, key + "followupEnd")),
      },
      change_requirement:
        endpointRole === "primary"
          ? {
              basis: basis as
                "favourable_absolute_change" | "favourable_percent_change",
              minimum: decimal(text(data, key + "minimum")),
              maximum: maximum ? decimal(maximum) : null,
              measurement_error_estimate: error ? decimal(error) : null,
              measurement_error_source: source,
            }
          : null,
    };
    if (!(
      endpoint.baseline_window.starts_at <= endpoint.baseline_window.ends_at &&
      endpoint.baseline_window.ends_at < endpoint.followup_window.starts_at &&
      endpoint.followup_window.starts_at <= endpoint.followup_window.ends_at
    ))
      throw new Error("A két mérési időablak legyen rendezett és különálló.");
    return endpoint;
  });
  if (
    !endpoints.length ||
    endpoints.length > 64 ||
    new Set(endpoints.map((e) => e.endpoint_key)).size !== endpoints.length
  )
    throw new Error("1–64, egymástól eltérő nevű mérési cél szükséges.");
  if (
    directives.some(
      (d) =>
        !endpoints.some(
          (e) => e.capability_key === d.capability_key && e.role === "primary",
        ),
    )
  )
    throw new Error(
      "Minden hozzárendelt képességhez legalább egy elsődleges mérési cél szükséges.",
    );
  return {
    mesocycle_period_id: mesocycleId,
    ...revision(base),
    macrocycle_plan: reference(macro.artifact),
    endpoints,
    rationale: text(data, "rationale"),
  };
}
export function measurementProposal(
  data: FormData,
  protocol: Receipt<ProtocolArtifact>,
  endpoint: Endpoint,
  requestId: string,
): MeasurementProposal {
  const conditions = endpoint.procedure.comparability_conditions.map(
    (condition, i) => {
      const status = text(data, `condition.${i}.status`);
      if (!["met", "not_met", "unknown"].includes(status))
        throw new Error("Add meg minden feltétel tényleges állapotát.");
      return {
        condition,
        status: status as "met" | "not_met" | "unknown",
        observation: text(data, `condition.${i}.observation`),
        evidence_reference: text(data, `condition.${i}.evidence`),
      };
    },
  );
  const completion = text(data, "completion"),
    result = text(data, "resultLevel");
  if (
    !["complete", "incomplete", "unknown"].includes(completion) ||
    !["complete_protocol_result", "within_protocol_trial", "unknown"].includes(
      result,
    )
  )
    throw new Error("Add meg a végrehajtás és az eredmény szintjét.");
  const bodyMass = optional(data, "bodyMass");
  const proposal: MeasurementProposal = {
    client_request_id: requestId,
    protocol_reference: reference(protocol.artifact),
    endpoint_key: endpoint.endpoint_key,
    value: decimal(text(data, "value")),
    observation: {
      started_at: utcInput(text(data, "startedAt")),
      ended_at: utcInput(text(data, "endedAt")),
      completion:
        completion as MeasurementProposal["observation"]["completion"],
      result_level:
        result as MeasurementProposal["observation"]["result_level"],
      conditions,
      body_mass_kg: bodyMass ? decimal(bodyMass) : null,
      execution_evidence_reference: text(data, "executionEvidence"),
    },
  };
  const started = Date.parse(proposal.observation.started_at),
    ended = Date.parse(proposal.observation.ended_at);
  if (
    ended < started ||
    ![endpoint.baseline_window, endpoint.followup_window].some(
      (w) =>
        Date.parse(w.starts_at) <= started && ended <= Date.parse(w.ends_at),
    )
  )
    throw new Error(
      "A teljes végrehajtásnak az egyik rögzített időablakba kell férnie.",
    );
  return proposal;
}
