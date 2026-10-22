export type GoalRole =
  | "primary_development"
  | "secondary_development"
  | "maintenance"
  | "permitted_decline";
export type EndpointRole = "primary" | "supporting" | "context";
export type Resource =
  "macrocycle-plans" | "mesocycle-protocols" | "measurements" | "assessments";
export type Criterion =
  | "met_under_declared_error"
  | "not_met_under_declared_error"
  | "withheld"
  | "descriptive_only";
export type Reference = { artifact_id: string; content_hash: string };
export type Period = {
  id: string;
  parent_id: string | null;
  period_type: string;
  title: string;
  start_date: string;
  end_date: string;
};
export type PeriodSnapshot = {
  period_id: string;
  title: string;
  start_date: string;
  end_date: string;
};
export type Metric = {
  metric_key: string;
  capability_key: string;
  unit: string;
  evidence_kind: string;
  scale: "ratio" | "interval" | "ordinal";
  favourable_direction: "higher" | "lower";
  method_family: string;
  primary_endpoint_eligible: boolean;
  interpretation_limit: string;
};
export type Catalog = {
  catalog_version: string;
  catalog_content_hash: string;
  capabilities: string[];
  goal_roles: GoalRole[];
  metrics: Metric[];
};
export type CapabilityGoal = {
  capability_key: string;
  role: GoalRole;
  rationale: string;
};
export type Directive = CapabilityGoal & { mesocycle_period_id: string };
export type Procedure = {
  protocol_key: string;
  protocol_version: string;
  origin: "explicit_custom" | "external_reference";
  source_reference: string;
  modality_key: string;
  exercise_or_task: string;
  procedure: string;
  equipment_and_processing: string;
  comparability_conditions: string[];
};
export type Window = { starts_at: string; ends_at: string };
export type ChangeRequirement = {
  basis: "favourable_absolute_change" | "favourable_percent_change";
  minimum: string;
  maximum: string | null;
  measurement_error_estimate: string | null;
  measurement_error_source: string | null;
};
export type Endpoint = {
  endpoint_key: string;
  capability_key: string;
  metric_key: string;
  role: EndpointRole;
  procedure: Procedure;
  baseline_window: Window;
  followup_window: Window;
  change_requirement: ChangeRequirement | null;
};
export type MacroProposal = {
  macrocycle_period_id: string;
  revision: number;
  supersedes: Reference | null;
  goals: CapabilityGoal[];
  mesocycle_directives: Directive[];
  rationale: string;
};
export type ProtocolProposal = {
  mesocycle_period_id: string;
  revision: number;
  supersedes: Reference | null;
  macrocycle_plan: Reference;
  endpoints: Endpoint[];
  rationale: string;
};
type BaseArtifact = Reference & {
  schema_version: string;
  created_at: string;
  authority: {
    shadow_only: true;
    planning_authorized: false;
    physiological_adaptation_established: false;
    planning_utility_supported: false;
  };
};
export type MacroArtifact = BaseArtifact & {
  proposal: MacroProposal;
  sources: {
    timezone_name: string;
    hierarchy: PeriodSnapshot[];
    mesocycles: PeriodSnapshot[];
  };
  unassigned_capability_keys: string[];
};
export type ProtocolArtifact = BaseArtifact & {
  proposal: ProtocolProposal;
  sources: MacroArtifact["sources"];
  capability_roles: Directive[];
  unassigned_capability_keys: string[];
};
export type Condition = {
  condition: string;
  status: "met" | "not_met" | "unknown";
  observation: string;
  evidence_reference: string;
};
export type Observation = {
  started_at: string;
  ended_at: string;
  completion: "complete" | "incomplete" | "unknown";
  result_level:
    "complete_protocol_result" | "within_protocol_trial" | "unknown";
  conditions: Condition[];
  body_mass_kg: string | null;
  execution_evidence_reference: string;
};
export type MeasurementProposal = {
  client_request_id: string;
  protocol_reference: Reference;
  endpoint_key: string;
  value: string;
  observation: Observation;
};
export type MeasurementArtifact = BaseArtifact & {
  proposal: MeasurementProposal;
  metric_key: string;
  metric_unit: string;
  source_rows_immutable: false;
  assessment_id: string;
  measurement_id: string;
};
export type ExactChange = {
  numerator: string;
  denominator: string;
  display_decimal: string;
};
export type EndpointAssessment = {
  endpoint_key: string;
  capability_key: string;
  endpoint_role: EndpointRole;
  metric_key: string;
  metric_unit: string;
  evidence_kind: string;
  interpretation_limit: string;
  baseline_value: string | null;
  followup_value: string | null;
  favourable_absolute_change: ExactChange | null;
  favourable_percent_change: ExactChange | null;
  declared_error_sensitivity_low: ExactChange | null;
  declared_error_sensitivity_high: ExactChange | null;
  comparison_basis: ChangeRequirement["basis"] | null;
  point_requirement_met: boolean | null;
  criterion_status: Criterion;
  reason_codes: string[];
  candidates: {
    source_id: string;
    window: string;
    eligibility: string;
    reason_codes: string[];
  }[];
};
export type AssessmentArtifact = BaseArtifact & {
  protocol_source: Reference;
  activity_cutoff_at: string;
  endpoint_assessments: EndpointAssessment[];
  capability_assessments: {
    capability_key: string;
    goal_role: GoalRole;
    criterion_status: Criterion;
    reason_codes: string[];
  }[];
  all_primary_criteria_status: Criterion;
  measurement_error_model_validated: false;
  unassigned_capability_keys: string[];
};
export type Artifact =
  MacroArtifact | ProtocolArtifact | MeasurementArtifact | AssessmentArtifact;
export type Receipt<T = Artifact> = {
  identity_scope: "APPLICATION_DEMO_USER";
  artifact: T;
  durable_available_at: string;
  reused: boolean;
  committed: true;
  measurement_schedule_preregistered: boolean;
  physiological_adaptation_established: false;
  planning_utility_supported: false;
  planning_authorized: false;
};
export type ArtifactPage = {
  identity_scope: "APPLICATION_DEMO_USER";
  items: Receipt[];
  limit: number;
  offset: number;
  has_more: boolean;
};
export const RESOURCES: Resource[] = [
  "macrocycle-plans",
  "mesocycle-protocols",
  "measurements",
  "assessments",
];
export const SCHEMAS: Record<Resource, string> = {
  "macrocycle-plans": "macrocycle-capability-plan-v0.1",
  "mesocycle-protocols": "mesocycle-goal-protocol-v0.1",
  measurements: "goal-measurement-registration-v0.1",
  assessments: "mesocycle-goal-assessment-v0.1",
};
