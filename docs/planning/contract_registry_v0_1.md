# Planning Contract Registry v0.1

Implementation states: DESIGNED, SKELETON, DOMAIN_IMPLEMENTED, PERSISTED,
INTEGRATED, VALIDATED, ACTIVE.

| Contract | Schema | Module | Status |
|---|---|---|---|
| VersionRef | v0.1 | planning.domain.common.refs | DOMAIN_IMPLEMENTED |
| RegistryKey | v0.1 | planning.domain.common.refs | DOMAIN_IMPLEMENTED |
| EvidenceRef | v0.1 | planning.domain.common.refs | DOMAIN_IMPLEMENTED |
| SourceSnapshotRef | v0.1 | planning.domain.common.refs | DOMAIN_IMPLEMENTED |
| ImmutableDomainSnapshot | v0.1 | planning.domain.common.snapshot | DOMAIN_IMPLEMENTED |
| SnapshotRecord / repository semantics | v0.1 | planning.domain.persistence / ports.snapshots | DOMAIN_IMPLEMENTED |
| EvidenceItem | v0.1 | planning.domain.evidence | DOMAIN_IMPLEMENTED |
| EvidenceBundle | v0.1 | planning.domain.evidence | DOMAIN_IMPLEMENTED |
| EvidenceSourceAdapter | v0.1 | planning.ports.evidence | DOMAIN_IMPLEMENTED |
| TrainingExposureObservation | v0.1 | planning.domain.training_state | DOMAIN_IMPLEMENTED |
| TrainingExposureWindowSummary | v0.1 | planning.domain.training_state | DOMAIN_IMPLEMENTED |
| LoadAnchorState | v0.1 | planning.domain.training_state | DOMAIN_IMPLEMENTED |
| CurrentTrainingState | cts_v0.1 | planning.domain.training_state | DOMAIN_IMPLEMENTED |
| EntryGateDecision | entry_gate_v0.1 | planning.domain.entry_gate | DOMAIN_IMPLEMENTED |
| WorkoutFamilyPrescription | wf_v0.1 | planning.domain.workout_family | DOMAIN_IMPLEMENTED |
| RuntimePlanningProjection | v0.1 | planning.domain.context | DOMAIN_IMPLEMENTED |
| TrainingSpaceProjection | entry-gate-family-space v0.1 | planning.domain.context | DOMAIN_IMPLEMENTED |
| AthletePlanningContextAggregate | apc_v0.1 | planning.domain.context | DOMAIN_IMPLEMENTED |
| PlannerInputEnvelope | v0.1 | planning.domain.decision | DOMAIN_IMPLEMENTED |
| CandidateActionSet | v0.1 | planning.domain.decision | DOMAIN_IMPLEMENTED |
| PlanningPolicySet | v0.1 | planning.domain.policy | DOMAIN_IMPLEMENTED |
| PolicyExecutionRecord | v0.1 | planning.domain.policy | DOMAIN_IMPLEMENTED |
| PlannerDecision | pd_v0.1 | planning.domain.decision | DOMAIN_IMPLEMENTED |
| DecisionRationale | v0.1 | planning.domain.rationale | DOMAIN_IMPLEMENTED |
| PlannerRunRecord | v0.1 | planning.domain.replay | DOMAIN_IMPLEMENTED |
| ReplayVerification | v0.1 | planning.domain.replay | DOMAIN_IMPLEMENTED |

| WorkoutPlanContractArtifact | bridge v0.1 | planning.domain.plan_revision | DOMAIN_IMPLEMENTED |
| PlanMutationInstruction | v0.1 | planning.domain.plan_revision | DOMAIN_IMPLEMENTED |
| WorkoutPlanRevisionGateway | v0.1 | planning.ports.workout_plan | DOMAIN_IMPLEMENTED |
| PlanRevisionLink | v0.1 | planning.domain.plan_revision | DOMAIN_IMPLEMENTED |

| MicrocyclePlanningResolution | v0.1 | planning.domain.microcycle | DOMAIN_IMPLEMENTED |
| MicrocyclePlan | reanchor_microcycle_plan_v0.1 | planning.domain.microcycle | DOMAIN_IMPLEMENTED |
| REANCHOR Golden Scenario | p0.11 | tests/planning/golden_scenarios | VALIDATED |
| PlanningAuditRepository | v0.1 | planning.ports.audit | DOMAIN_IMPLEMENTED |
| SQLite Planning Snapshot Repository | v0.1 | planning.infrastructure.repositories.sqlite | DOMAIN_IMPLEMENTED |
| SQLite Planning Audit Repository | v0.1 | planning.infrastructure.repositories.sqlite | DOMAIN_IMPLEMENTED |
| Planning Dev API | v0.1 | planning.api.dev | DOMAIN_IMPLEMENTED |

| ExistingWorkoutPlanCapture | p1.0 | planning.domain.integration | DOMAIN_IMPLEMENTED |

| AuthoritativePlanIdentity | authoritative_plan_identity_v0.1 | planning.domain.plan_revision.persistence_contract | DOMAIN_IMPLEMENTED |
| AuthoritativePlanRevision | authoritative_plan_revision_v0.1 | planning.domain.plan_revision.persistence_contract | DOMAIN_IMPLEMENTED |
| CurrentStateAdoptionBinding | current_state_adoption_v0.1 | planning.domain.plan_revision.persistence_contract | DOMAIN_IMPLEMENTED |
| PostgreSQL Authoritative Plan Schema | authoritative-plan-persistence-v0.1 | planning.domain.plan_revision.postgres_schema_contract | PERSISTED |
| SQLAlchemy Authoritative Plan Revision Repository | authoritative-plan-repository-v0.1 | planning.infrastructure.repositories.postgres_authoritative_plan_revision | PERSISTED |
| Locked Current-App Plan Source Hash Provider | v0.1 | planning.infrastructure.adapters.locked_plan_source | INTEGRATED |
