"""Synthetic acceptance, ambiguity and numerical boundaries; no efficacy claim."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_UP, Inexact, localcontext
from hashlib import sha256
from uuid import UUID

import pytest

from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.goals.assessment import (
    GOAL_MEASUREMENT_CENSUS_LIMIT,
    MEASUREMENT_EXECUTION_KEY,
    MEASUREMENT_EXECUTION_SCHEMA,
    MEASUREMENT_SOURCE_SCHEMA,
    CapturedGoalMeasurement,
    ConditionStatus,
    ExecutionCompletion,
    GoalCriterionStatus,
    GoalMeasurementCensus,
    GoalMeasurementExecution,
    GoalMeasurementSourceKind,
    MeasurementConditionObservation,
    MeasurementEligibility,
    ResultLevel,
    build_mesocycle_goal_assessment,
    goal_assessment_id,
)
from app.planning.domain.goals.catalog import CapabilityKey, MeasurementEvidenceKind, goal_metric
from app.planning.domain.goals.protocol import (
    CapabilityGoalRole,
    ChangeBasis,
    DurableGoalSourceReference,
    EndpointRole,
    GoalChangeRequirement,
)
from app.planning.domain.persistence.audit import AuditArtifactKind
from tests.planning.test_p2_4c1_goal_protocol import (
    ATHLETE,
    MESO,
    MESO2,
    NOW,
    endpoint,
    macro_plan,
    macro_proposal,
    meso_proposal,
    meso_protocol,
)

CAPTURE = datetime(2030, 2, 1, 12, tzinfo=UTC)
CUTOFF = datetime(2030, 1, 27, 12, tzinfo=UTC)
STATUS = GoalCriterionStatus
ROLE = CapabilityGoalRole
BASIS = ChangeBasis


def plan_for(metric_key, role):
    metric = goal_metric(metric_key)
    proposal = macro_proposal()
    goal = replace(proposal.goals[0], capability_key=metric.capability_key, role=role)
    directives = tuple(
        replace(
            proposal.mesocycle_directives[0],
            mesocycle_period_id=period,
            capability_key=metric.capability_key,
            role=role,
        )
        for period in (MESO, MESO2)
    )
    return macro_plan(replace(proposal, goals=(goal,), mesocycle_directives=directives))


def protocol_for(
    metric_key="VO2MAX_RELATIVE",
    role=ROLE.PRIMARY_DEVELOPMENT,
    basis=BASIS.FAVOURABLE_PERCENT_CHANGE,
    minimum="2",
    maximum=None,
    error="1",
):
    metric = goal_metric(metric_key)
    plan = plan_for(metric_key, role)
    primary = endpoint(metric.capability_key, metric_key, minimum, maximum)
    primary = replace(
        primary,
        change_requirement=GoalChangeRequirement(
            basis,
            minimum,
            maximum,
            error,
            "synthetic:declared-change-error-v1" if error is not None else None,
        ),
    )
    return meso_protocol(replace(meso_proposal(plan), endpoints=(primary,)), plan)


def protocol_ref(protocol):
    return DurableGoalSourceReference(
        AuditArtifactKind.MESOCYCLE_GOAL_PROTOCOL,
        protocol.artifact_id,
        protocol.content_hash,
        sha256(canonical_json(protocol).encode()).hexdigest(),
        NOW + timedelta(seconds=3),
    )


def execution_for(endpoint, *, followup=False):
    interval = endpoint.followup_window if followup else endpoint.baseline_window
    return GoalMeasurementExecution(
        MEASUREMENT_EXECUTION_SCHEMA,
        endpoint.procedure,
        goal_metric(endpoint.metric_key).evidence_kind,
        interval.starts_at,
        interval.starts_at + timedelta(minutes=10),
        ExecutionCompletion.COMPLETE,
        ResultLevel.COMPLETE_PROTOCOL_RESULT,
        tuple(
            MeasurementConditionObservation(
                c, ConditionStatus.MET, "Synthetic observed condition", "synthetic:observation"
            )
            for c in endpoint.procedure.comparability_conditions
        ),
        "70",
        "synthetic:complete-result-evidence",
    )


def source_from_packet(packet):
    encoded = canonical_json(packet)
    return CapturedGoalMeasurement(
        GoalMeasurementSourceKind(packet["source_kind"]),
        packet["source_id"],
        encoded,
        sha256(encoded.encode()).hexdigest(),
    )


def measurement_source(endpoint, value, *, followup=False, identity=101, execution=None, **changes):
    execution = execution or execution_for(endpoint, followup=followup)
    packet = {
        "schema_version": MEASUREMENT_SOURCE_SCHEMA,
        "source_kind": GoalMeasurementSourceKind.ASSESSMENT_MEASUREMENT.value,
        "source_id": str(UUID(int=identity)),
        "athlete_id": ATHLETE,
        "parent_id": str(UUID(int=identity + 10000)),
        "metric_key": endpoint.metric_key,
        "value_float_text": str(value) if value is not None else None,
        "value_text": None,
        "unit": goal_metric(endpoint.metric_key).unit,
        "measured_at": execution.started_at,
        "created_at": execution.ended_at + timedelta(seconds=1),
        "parent_created_at": execution.ended_at + timedelta(seconds=1),
        "sport": None,
        "parent_sport": None,
        "source_label": "SYNTHETIC",
        "extra_data": {MEASUREMENT_EXECUTION_KEY: json.loads(canonical_json(execution))},
        "parent_extra_data": {},
        "period_start": None,
        "period_end": None,
        "device_id": None,
        "device_model": None,
        "quality": None,
        "source_record_id": None,
        "parent_type": "OTHER",
        "parent_title": "Synthetic assessment",
        "parent_notes": None,
    }
    packet.update(changes)
    return source_from_packet(json.loads(canonical_json(packet)))


def assess(
    protocol, base="50", followup="55", *, sources=None, cutoff=CUTOFF, census=None, ref=None
):
    primary = protocol.proposal.endpoints[0]
    if sources is None:
        sources = (
            measurement_source(primary, base),
            measurement_source(primary, followup, followup=True, identity=102),
        )
    if census is None:
        census = GoalMeasurementCensus(
            ATHLETE,
            min(e.baseline_window.starts_at for e in protocol.proposal.endpoints),
            min(cutoff, max(e.followup_window.ends_at for e in protocol.proposal.endpoints)),
            CAPTURE,
            CAPTURE + timedelta(microseconds=1),
            tuple(sorted(sources, key=lambda s: (s.source_kind.value, s.source_id))),
        )
    return build_mesocycle_goal_assessment(
        protocol=protocol,
        protocol_source=ref or protocol_ref(protocol),
        activity_cutoff_at=cutoff,
        census=census,
        created_at=CAPTURE + timedelta(microseconds=2),
    )


@pytest.mark.parametrize(
    "metric,role,basis,low,high,error,base,end,expected",
    (
        (
            "VO2MAX_RELATIVE",
            ROLE.PRIMARY_DEVELOPMENT,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "2",
            None,
            "1",
            "50",
            "55",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "STRENGTH_REFERENCE_LOAD",
            ROLE.SECONDARY_DEVELOPMENT,
            BASIS.FAVOURABLE_ABSOLUTE_CHANGE,
            "2",
            None,
            "0",
            "100",
            "102",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "STANDING_START_TIME",
            ROLE.PRIMARY_DEVELOPMENT,
            BASIS.FAVOURABLE_ABSOLUTE_CHANGE,
            "0.5",
            None,
            "0.1",
            "10",
            "9",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "PEAK_POWER",
            ROLE.MAINTENANCE,
            BASIS.FAVOURABLE_ABSOLUTE_CHANGE,
            "-2",
            "2",
            "0.5",
            "100",
            "99",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "PEAK_POWER",
            ROLE.MAINTENANCE,
            BASIS.FAVOURABLE_ABSOLUTE_CHANGE,
            "-2",
            "2",
            "0.5",
            "100",
            "110",
            STATUS.NOT_MET_UNDER_DECLARED_ERROR,
        ),
        (
            "PEAK_POWER",
            ROLE.PERMITTED_DECLINE,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "-5",
            None,
            "1",
            "100",
            "97",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "PEAK_POWER",
            ROLE.PERMITTED_DECLINE,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "-5",
            None,
            "1",
            "100",
            "110",
            STATUS.MET_UNDER_DECLARED_ERROR,
        ),
        (
            "PEAK_POWER",
            ROLE.PERMITTED_DECLINE,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "-5",
            None,
            "1",
            "100",
            "90",
            STATUS.NOT_MET_UNDER_DECLARED_ERROR,
        ),
        (
            "VO2MAX_RELATIVE",
            ROLE.PRIMARY_DEVELOPMENT,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "2",
            None,
            "1",
            "50",
            "51",
            STATUS.WITHHELD,
        ),
        (
            "VO2MAX_RELATIVE",
            ROLE.PRIMARY_DEVELOPMENT,
            BASIS.FAVOURABLE_PERCENT_CHANGE,
            "2",
            None,
            None,
            "50",
            "55",
            STATUS.WITHHELD,
        ),
    ),
)
def test_goal_roles_and_declared_error_sensitivity(
    metric, role, basis, low, high, error, base, end, expected
):
    protocol = protocol_for(metric, role, basis, low, high, error)
    result = assess(protocol, base, end)
    assert result.endpoint_assessments[0].criterion_status == expected
    assert result.capability_assessments[0].goal_role == role
    assert result.capability_assessments[0].criterion_status == expected
    assert result.all_primary_criteria_status == expected
    assert result.verify_content_hash()
    assert result.measurement_error_model_validated is False
    assert result.execution_details_independently_verified is False
    assert result.source_availability_at_activity_cutoff_verified is False
    assert result.authority.capability_change_established is False
    assert result.authority.physiological_adaptation_established is False
    assert result.authority.planning_utility_supported is False
    assert result.authority.planning_authorized is False


@pytest.mark.parametrize(
    "threshold,status",
    (
        ("33.3333333333333333333333333333333333333", STATUS.MET_UNDER_DECLARED_ERROR),
        ("33.3333333333333333333333333333333333334", STATUS.NOT_MET_UNDER_DECLARED_ERROR),
    ),
)
def test_exact_fraction_comparison_never_uses_rounded_display(threshold, status):
    result = assess(protocol_for(minimum=threshold, error="0"), "3", "4").endpoint_assessments[0]
    assert result.favourable_percent_change.numerator == "100"
    assert result.favourable_percent_change.denominator == "3"
    assert result.favourable_percent_change.display_decimal == "33.33333333333333333333333333"
    assert result.criterion_status == status


def test_ambient_decimal_context_cannot_change_comparisons_or_display():
    protocol = protocol_for(minimum="33", error="0")
    normal = assess(protocol, "3", "4")
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        changed_context = assess(protocol, "3", "4")
    assert changed_context == normal


@pytest.mark.parametrize("base", ("0", "-1"))
def test_nonpositive_baseline_withholds_percent_change(base):
    result = assess(protocol_for(), base, "5").endpoint_assessments[0]
    assert result.favourable_percent_change is None
    assert result.favourable_absolute_change is not None
    assert result.criterion_status == STATUS.WITHHELD
    assert "PERCENT_CHANGE_REQUIRES_POSITIVE_BASELINE" in result.reason_codes


def test_lower_is_better_changes_have_positive_favourable_sign():
    result = assess(
        protocol_for("STANDING_START_TIME", minimum="5", error="0"), "10", "9"
    ).endpoint_assessments[0]
    assert result.favourable_absolute_change.numerator == "1"
    assert result.favourable_percent_change.numerator == "10"


def test_missing_is_not_zero_and_does_not_pick_a_supporting_result():
    protocol = protocol_for()
    primary = protocol.proposal.endpoints[0]
    only_followup = measurement_source(primary, "55", followup=True)
    result = assess(protocol, sources=(only_followup,)).endpoint_assessments[0]
    assert result.baseline_value is None
    assert result.followup_value == "55"
    assert result.favourable_absolute_change is None
    assert "BASELINE_RESULT_MISSING" in result.reason_codes


def test_duplicate_complete_results_withhold_even_if_the_values_are_equal():
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    result = assess(
        protocol,
        sources=(
            measurement_source(e, "50", identity=1),
            measurement_source(e, "50", identity=2),
            measurement_source(e, "55", followup=True, identity=3),
        ),
    )
    endpoint_result = result.endpoint_assessments[0]
    assert "BASELINE_RESULT_AMBIGUOUS" in endpoint_result.reason_codes
    assert endpoint_result.baseline_source is None
    assert len(endpoint_result.candidates) == 3


@pytest.mark.parametrize(
    "problem",
    (
        "metadata_absent",
        "condition_unknown",
        "condition_missing",
        "body_mass_missing",
        "extra_execution_field",
        "numeric_missing",
        "numeric_nan",
        "two_values",
    ),
)
def test_unresolved_relevant_candidates_block_selection_of_another_complete_result(problem):
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    execution = execution_for(e)
    changes = {}
    if problem == "metadata_absent":
        changes["extra_data"] = {}
    elif problem == "condition_unknown":
        execution = replace(
            execution,
            conditions=(replace(execution.conditions[0], status=ConditionStatus.UNKNOWN),)
            + execution.conditions[1:],
        )
    elif problem == "condition_missing":
        execution = replace(execution, conditions=execution.conditions[:1])
    elif problem == "body_mass_missing":
        execution = replace(execution, body_mass_kg=None)
    elif problem == "extra_execution_field":
        raw = json.loads(canonical_json(execution))
        raw["caller_selected_result"] = True
        changes["extra_data"] = {MEASUREMENT_EXECUTION_KEY: raw}
    elif problem == "numeric_missing":
        changes["value_float_text"] = None
    elif problem == "numeric_nan":
        changes["value_float_text"] = "nan"
    else:
        changes["value_text"] = "choose this instead"
    unknown = measurement_source(e, "900", identity=3, execution=execution, **changes)
    result = assess(
        protocol,
        sources=(
            measurement_source(e, "50", identity=1),
            measurement_source(e, "55", followup=True, identity=2),
            unknown,
        ),
    ).endpoint_assessments[0]
    assert result.criterion_status == STATUS.WITHHELD
    assert "BASELINE_CANDIDATE_UNRESOLVED" in result.reason_codes


@pytest.mark.parametrize(
    "problem",
    (
        "unit",
        "metric",
        "procedure",
        "evidence_kind",
        "incomplete",
        "trial",
        "condition_not_met",
        "execution_straddles_window",
        "recorded_before_end",
    ),
)
def test_known_ineligible_results_are_retained_without_substituting_them(problem):
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    execution = execution_for(e)
    changes = {}
    if problem == "unit":
        changes["unit"] = "other-unit"
    elif problem == "metric":
        changes["metric_key"] = "VO2MAX_ESTIMATED_RELATIVE"
    elif problem == "procedure":
        execution = replace(execution, procedure=replace(execution.procedure, protocol_version="2"))
    elif problem == "evidence_kind":
        execution = replace(execution, evidence_kind=MeasurementEvidenceKind.ESTIMATE)
    elif problem == "incomplete":
        execution = replace(execution, completion=ExecutionCompletion.INCOMPLETE)
    elif problem == "trial":
        execution = replace(execution, result_level=ResultLevel.WITHIN_PROTOCOL_TRIAL)
    elif problem == "condition_not_met":
        execution = replace(
            execution,
            conditions=(replace(execution.conditions[0], status=ConditionStatus.NOT_MET),)
            + execution.conditions[1:],
        )
    elif problem == "execution_straddles_window":
        execution = replace(
            execution, started_at=e.baseline_window.starts_at - timedelta(minutes=1)
        )
        changes["measured_at"] = e.baseline_window.starts_at
    else:
        changes["created_at"] = execution.started_at
    other = measurement_source(e, "900", identity=3, execution=execution, **changes)
    result = assess(
        protocol,
        sources=(
            measurement_source(e, "50", identity=1),
            measurement_source(e, "55", followup=True, identity=2),
            other,
        ),
    ).endpoint_assessments[0]
    assert result.criterion_status == STATUS.MET_UNDER_DECLARED_ERROR
    assert len(result.candidates) == 3
    assert result.candidates[-1].eligibility == MeasurementEligibility.INELIGIBLE
    assert result.baseline_value == "50"


def test_open_followup_window_cannot_be_assessed_early():
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    cutoff = e.followup_window.starts_at + timedelta(minutes=20)
    result = assess(protocol, cutoff=cutoff).endpoint_assessments[0]
    assert "FOLLOWUP_WINDOW_NOT_CLOSED" in result.reason_codes
    assert result.criterion_status == STATUS.WITHHELD


def test_closed_window_boundary_is_inclusive():
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    result = assess(protocol, cutoff=e.followup_window.ends_at)
    assert result.all_primary_criteria_status == STATUS.MET_UNDER_DECLARED_ERROR


def test_all_primary_endpoints_required_supporting_and_context_cannot_replace_them():
    protocol = protocol_for()
    primary = protocol.proposal.endpoints[0]
    extra = replace(
        primary,
        endpoint_key="another-primary",
        procedure=replace(primary.procedure, protocol_key="other-task"),
    )
    protocol = meso_protocol(
        replace(protocol.proposal, endpoints=(primary, extra)),
        plan=plan_for("VO2MAX_RELATIVE", ROLE.PRIMARY_DEVELOPMENT),
    )
    result = assess(protocol)
    assert result.endpoint_assessments[0].criterion_status == STATUS.MET_UNDER_DECLARED_ERROR
    assert result.endpoint_assessments[1].criterion_status == STATUS.WITHHELD
    assert result.capability_assessments[0].criterion_status == STATUS.WITHHELD
    assert result.all_primary_criteria_status == STATUS.WITHHELD


@pytest.mark.parametrize("role", (EndpointRole.SUPPORTING, EndpointRole.CONTEXT))
def test_missing_nonprimary_endpoint_does_not_replace_or_block_a_primary(role):
    protocol = protocol_for()
    primary = protocol.proposal.endpoints[0]
    other = replace(
        primary,
        endpoint_key="extra-description",
        role=role,
        change_requirement=None,
        procedure=replace(primary.procedure, protocol_key="other-procedure"),
    )
    protocol = meso_protocol(
        replace(protocol.proposal, endpoints=(primary, other)),
        plan=plan_for("VO2MAX_RELATIVE", ROLE.PRIMARY_DEVELOPMENT),
    )
    result = assess(protocol)
    assert result.endpoint_assessments[1].criterion_status == STATUS.WITHHELD
    assert result.all_primary_criteria_status == STATUS.MET_UNDER_DECLARED_ERROR


def test_ordinal_context_retains_values_without_arithmetic_or_acceptance():
    metric_key = "FUNCTIONAL_TASK_REPETITIONS"
    protocol = protocol_for(
        metric_key, basis=BASIS.FAVOURABLE_ABSOLUTE_CHANGE, minimum="1", error="0"
    )
    primary = protocol.proposal.endpoints[0]
    context = endpoint(CapabilityKey.MUSCULOSKELETAL_ROBUSTNESS, "PAIN_RATING", "1", None)
    context = replace(
        context, endpoint_key="context-pain", role=EndpointRole.CONTEXT, change_requirement=None
    )
    protocol = meso_protocol(
        replace(protocol.proposal, endpoints=(primary, context)),
        plan=plan_for(metric_key, ROLE.PRIMARY_DEVELOPMENT),
    )
    sources = (
        measurement_source(primary, "10", identity=1),
        measurement_source(primary, "12", followup=True, identity=2),
        measurement_source(context, "4", identity=3),
        measurement_source(context, "2", followup=True, identity=4),
    )
    result = assess(protocol, sources=sources)
    observed_context = result.endpoint_assessments[1]
    assert observed_context.baseline_value == "4" and observed_context.followup_value == "2"
    assert observed_context.favourable_absolute_change is None
    assert observed_context.favourable_percent_change is None
    assert observed_context.point_requirement_met is None
    assert observed_context.criterion_status == STATUS.DESCRIPTIVE_ONLY
    assert result.all_primary_criteria_status == STATUS.MET_UNDER_DECLARED_ERROR


def test_interval_metric_has_absolute_change_but_no_percentage_change():
    protocol = protocol_for(
        "HEART_RATE_DRIFT", basis=BASIS.FAVOURABLE_ABSOLUTE_CHANGE, minimum="1", error="0"
    )
    result = assess(protocol, "5", "3").endpoint_assessments[0]
    assert result.favourable_absolute_change.numerator == "2"
    assert result.favourable_percent_change is None
    assert result.criterion_status == STATUS.MET_UNDER_DECLARED_ERROR


def test_estimate_keeps_its_evidence_kind_and_does_not_establish_physiological_change():
    result = assess(protocol_for("VO2MAX_ESTIMATED_RELATIVE"))
    assert result.endpoint_assessments[0].evidence_kind == MeasurementEvidenceKind.ESTIMATE
    assert result.authority.physiological_adaptation_established is False


@pytest.mark.parametrize(
    "problem",
    (
        "hash",
        "noncanonical",
        "athlete",
        "outside_span",
        "future_record",
        "duplicate",
        "order",
        "limit",
        "wrong_parent_digest",
        "late_protocol",
    ),
)
def test_census_and_provenance_fail_closed(problem):
    protocol = protocol_for()
    e = protocol.proposal.endpoints[0]
    sources = [
        measurement_source(e, "50", identity=1),
        measurement_source(e, "55", followup=True, identity=2),
    ]
    ref = protocol_ref(protocol)
    if problem == "hash":
        sources[0] = replace(sources[0], source_sha256="0" * 64)
    elif problem == "noncanonical":
        sources[0] = replace(
            sources[0], source_json=json.dumps(json.loads(sources[0].source_json), indent=2)
        )
    elif problem in {"athlete", "outside_span", "future_record"}:
        packet = json.loads(sources[0].source_json)
        packet.update(
            {
                "athlete": {"athlete_id": str(UUID(int=999))},
                "outside_span": {"measured_at": "2020-01-01T00:00:00.000000Z"},
                "future_record": {"created_at": "2040-01-01T00:00:00.000000Z"},
            }[problem]
        )
        sources[0] = source_from_packet(packet)
    elif problem == "duplicate":
        sources.append(sources[0])
    elif problem == "limit":
        sources = [sources[0]] * GOAL_MEASUREMENT_CENSUS_LIMIT
    elif problem == "wrong_parent_digest":
        ref = replace(ref, canonical_contract_sha256="0" * 64)
    elif problem == "late_protocol":
        ref = replace(ref, persisted_at=e.baseline_window.starts_at)
    if problem == "order":
        census = GoalMeasurementCensus(
            ATHLETE,
            e.baseline_window.starts_at,
            e.followup_window.ends_at,
            CAPTURE,
            CAPTURE,
            tuple(reversed(sources)),
        )
        with pytest.raises(ValueError, match="unique and sorted"):
            assess(protocol, census=census)
    else:
        with pytest.raises(ValueError):
            assess(protocol, sources=tuple(sources), ref=ref)


def test_artifacts_are_frozen_and_slot_is_cutoff_specific():
    protocol = protocol_for()
    result = assess(protocol)
    with pytest.raises(FrozenInstanceError):
        result.planning_authorized = True
    assert result.artifact_id == goal_assessment_id(ATHLETE, protocol.artifact_id, CUTOFF)
    assert result.artifact_id != goal_assessment_id(
        ATHLETE, protocol.artifact_id, CUTOFF + timedelta(seconds=1)
    )
