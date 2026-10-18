from datetime import datetime, timezone

from app.planning.domain.common.enums import (
    DecisionPurpose,
    KnowledgeStatus,
    PlanningScope,
    ProvenanceKind,
)
from app.planning.domain.common.refs import VersionRef
from app.planning.domain.context.models import UnresolvedPlanningDimension
from app.planning.domain.context.runtime import build_runtime_planning_context
from app.planning.domain.entry_gate.models import (
    AvailabilityConstraintStatus,
    EntryGatePolicy,
    InterruptionStatus,
    ParticipationConstraintStatus,
    RecoveryConstraintStatus,
    StimulusGateSignal,
    StimulusGateStatus,
)
from app.planning.domain.entry_gate.resolver import assess_entry_gate
from app.planning.domain.evidence.models import (
    EvidenceQuality,
    SourceRecordRef,
    create_evidence_bundle,
    create_evidence_item,
)
from app.planning.domain.microcycle.models import (
    DayPart,
    MicrocycleItemRole,
    PlanningDimensionResolution,
    ResolutionStatus,
    finalize_microcycle_planning_resolution,
)
from app.planning.domain.microcycle.reanchor import (
    REANCHOR_MICROCYCLE_POLICY_VERSION,
    ExternalLoadSlot,
    FamilySlot,
    FallbackFamilySlot,
    PftCompositionSlot,
    ReanchorMicrocycleRequest,
    RestDaySlot,
)
from app.planning.domain.training_state.evidence import EXECUTED_TRAINING_SESSION
from app.planning.domain.training_state.models import (
    EvidenceCoverage,
    ObservationWindow,
)
from app.planning.domain.training_state.resolver import build_current_training_state
from app.planning.domain.workout_family.builtins import (
    KAYAK_EASY_TECHNICAL_KEY,
    KAYAK_LONG_AEROBIC_KEY,
    RUN_EASY_AEROBIC_FALLBACK_KEY,
    STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
    builtin_workout_family_registry_v0_1,
)
from app.planning.domain.workout_family.models import FamilyRef


def _dt(day: int, hour: int = 6) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def build_golden_reanchor_inputs():
    # This is a structural synthetic fixture. It deliberately does not encode
    # invented real training metrics. One historical exposure has UNKNOWN
    # duration solely to exercise conservative-reanchor missing-data logic.
    historical = create_evidence_item(
        evidence_id='synthetic-history-1',
        athlete_id='golden-athlete',
        evidence_type=EXECUTED_TRAINING_SESSION,
        observed_at=_dt(1),
        available_at=_dt(1),
        created_at=_dt(16, 3),
        source_ref=SourceRecordRef(
            source_system='golden_fixture',
            source_record_id='synthetic-session-1',
        ),
        provenance=ProvenanceKind.SOURCE,
        knowledge_status=KnowledgeStatus.KNOWN,
        quality=EvidenceQuality.MODERATE,
        payload={
            'schema_version': 'executed_training_session_evidence_v0.1',
            'session_id': 'synthetic-session-1',
            'modality_key': 'KAYAK',
            'duration_status': KnowledgeStatus.UNKNOWN.value,
            'duration_s': None,
        },
    )
    bundle = create_evidence_bundle(
        bundle_id='golden-bundle',
        athlete_id='golden-athlete',
        as_of=_dt(16, 4),
        information_cutoff_at=_dt(16, 4),
        created_at=_dt(16, 4),
        items=(historical,),
    )
    state = build_current_training_state(
        bundle=bundle,
        state_id='golden-cts',
        schema_version='cts_v0.1',
        created_at=_dt(16, 4),
        recent_window=ObservationWindow(
            start_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
            end_at=_dt(16, 4),
        ),
        load_anchor_window=ObservationWindow(
            start_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
            end_at=_dt(16, 4),
        ),
        recent_training_coverage=EvidenceCoverage.COMPLETE,
        load_anchor_training_coverage=EvidenceCoverage.COMPLETE,
    )
    gate = assess_entry_gate(
        current_state=state,
        decision_id='golden-entry-gate',
        schema_version='entry_gate_v0.1',
        created_at=_dt(16, 4),
        policy=EntryGatePolicy(
            policy_version='entry_gate_policy_v0.1',
            recent_exposure_max_age_s_for_normal_start=7 * 24 * 3600,
        ),
        participation=ParticipationConstraintStatus.READY,
        recovery=RecoveryConstraintStatus.NONE,
        availability=AvailabilityConstraintStatus.AVAILABLE,
        interruption=InterruptionStatus.NONE,
        stimulus_keys=('AEROBIC', 'STRENGTH'),
        stimulus_signals=(
            StimulusGateSignal(
                stimulus_key='AEROBIC',
                status=StimulusGateStatus.BUILD_ALLOWED,
                reason_code='SYNTHETIC_AEROBIC_ALLOWED',
            ),
            StimulusGateSignal(
                stimulus_key='STRENGTH',
                status=StimulusGateStatus.BUILD_ALLOWED,
                reason_code='SYNTHETIC_STRENGTH_ALLOWED',
            ),
        ),
    )
    registry = builtin_workout_family_registry_v0_1()
    context = build_runtime_planning_context(
        current_state=state,
        entry_gate=gate,
        workout_family_registry=registry,
        context_id='golden-context',
        schema_version='apc_v0.1',
        as_of=_dt(16, 5),
        created_at=_dt(16, 5),
        planning_scope=PlanningScope.MICROCYCLE,
        decision_purpose=DecisionPurpose.CREATE_MICROCYCLE,
        engine_version=VersionRef('planner_engine', 'planner_engine_v0.1'),
        rules_version=VersionRef('planning_rules', 'planning_rules_v0.1'),
        evidence_pack_version=VersionRef(
            'evidence_pack',
            'training_planning_evidence_v0.1',
        ),
    )

    resolution = finalize_microcycle_planning_resolution(
        resolution_id='golden-resolution',
        base_context_hash=context.content_hash,
        resolutions=tuple(
            PlanningDimensionResolution(
                dimension=dimension,
                status=ResolutionStatus.RESOLVED,
                source_ref=f'golden:{dimension.value}',
                summary_code={
                    UnresolvedPlanningDimension.GOAL_PRIORITY:
                        '2027_500M_A_DOMINANT_WITHIN_SEASON',
                    UnresolvedPlanningDimension.OBJECTIVE_REGIME:
                        'PERFORMANCE_DEVELOPMENT',
                    UnresolvedPlanningDimension.SPORT_READINESS:
                        'KAYAK_RUN_STRENGTH_USABLE',
                    UnresolvedPlanningDimension.PLANNING_AUTHORITY:
                        'PADDLETRAINER_PRIMARY_AUTHORIZED',
                    UnresolvedPlanningDimension.DETAILED_AVAILABILITY:
                        'REANCHOR_WEEK_AVAILABILITY_RESOLVED',
                    UnresolvedPlanningDimension.ENVIRONMENT:
                        'CONDITIONAL_KAYAK_ENVIRONMENT',
                }[dimension],
            )
            for dimension in UnresolvedPlanningDimension
        ),
        objective_regime_code='PERFORMANCE_DEVELOPMENT',
        planning_authority_code='PADDLETRAINER_PRIMARY_AUTHORIZED',
        policy_version=REANCHOR_MICROCYCLE_POLICY_VERSION,
        created_at=_dt(16, 5),
    )

    easy = FamilyRef(KAYAK_EASY_TECHNICAL_KEY, 'v0.1')
    long_kayak = FamilyRef(KAYAK_LONG_AEROBIC_KEY, 'v0.1')
    strength = FamilyRef(STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY, 'v0.1')
    run_fallback = FamilyRef(RUN_EASY_AEROBIC_FALLBACK_KEY, 'v0.1')

    request = ReanchorMicrocycleRequest(
        window_start_date='2026-10-16',
        window_end_date='2026-10-22',
        family_slots=(
            FamilySlot(
                'fri_easy_kayak', '2026-10-16', DayPart.AM,
                easy, MicrocycleItemRole.PLANNED,
                ('OPENING_EASY_KAYAK',),
            ),
            FamilySlot(
                'fri_strength', '2026-10-16', DayPart.PM,
                strength, MicrocycleItemRole.PREFERRED,
                ('STRENGTH_PRIORITY_1',),
            ),
            FamilySlot(
                'sat_long_kayak', '2026-10-17', DayPart.AM,
                long_kayak, MicrocycleItemRole.PLANNED,
                ('LONG_KAYAK_KEY_SESSION', 'SUNDAY_AVAILABILITY_UNCERTAIN'),
            ),
            FamilySlot(
                'sun_easy_kayak', '2026-10-18', DayPart.AM,
                easy, MicrocycleItemRole.PLANNED,
                ('SHORT_EASY_KAYAK',),
            ),
            FamilySlot(
                'sun_strength_fallback', '2026-10-18', DayPart.PM,
                strength, MicrocycleItemRole.FALLBACK,
                ('STRENGTH_FALLBACK_ONLY',),
            ),
            FamilySlot(
                'wed_strength', '2026-10-21', DayPart.AFTERNOON,
                strength, MicrocycleItemRole.PREFERRED,
                ('STRENGTH_PRIORITY_2', 'LIMITED_TIME'),
            ),
        ),
        fallback_slots=(
            FallbackFamilySlot(
                'thu_easy_or_run', '2026-10-22', DayPart.DAWN,
                easy, run_fallback,
                ('PREFER_KAYAK', 'RUN_IF_KAYAK_IMPOSSIBLE'),
            ),
        ),
        pft_slots=(
            PftCompositionSlot(
                'tue_pft_easy_kayak', '2026-10-20', DayPart.DAWN,
                easy,
                ('PFT_MEASUREMENT', 'EASY_KAYAK_30_40_MIN'),
            ),
        ),
        external_load_slots=(
            ExternalLoadSlot(
                'sun_family_hike', '2026-10-18', DayPart.DAYTIME,
                'FAMILY_HIKE',
                ('EXTERNAL_PHYSICAL_LOAD_OBSERVATION',),
            ),
        ),
        rest_slots=(
            RestDaySlot(
                'mon_rest', '2026-10-19',
                ('PLANNED_REST', 'BUSY_DAY'),
            ),
        ),
        strength_candidate_slot_ids=('fri_strength', 'wed_strength'),
        strength_fallback_slot_ids=('sun_strength_fallback',),
        strength_minimum_count=1,
        strength_preferred_count=2,
        strength_maximum_count=2,
    )
    return state, gate, registry, context, resolution, request
