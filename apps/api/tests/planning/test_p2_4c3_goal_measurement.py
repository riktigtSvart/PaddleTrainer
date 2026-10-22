"""Measurement ingestion intent and strict HTTP schema boundaries."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.goals.assessment import ConditionStatus
from app.planning.domain.goals.measurement_registration import (
    GoalExecutionObservation,
    GoalMeasurementProposal,
    build_goal_measurement_registration,
    goal_measurement_id,
    measurement_float,
)
from app.planning.domain.goals.protocol import GoalVersionReference
from app.schemas.planning_goals import GoalMeasurementInput, MacrocyclePlanInput
from tests.planning.test_p2_4c1_goal_protocol import ATHLETE, macro_proposal
from tests.planning.test_p2_4c2_goal_assessment import execution_for, protocol_for, protocol_ref


def proposal_for(protocol=None, *, client_request_id=None, value="50", followup=False):
    protocol = protocol or protocol_for()
    endpoint = protocol.proposal.endpoints[0]
    execution = execution_for(endpoint, followup=followup)
    return GoalMeasurementProposal(
        client_request_id or str(UUID(int=9001)),
        GoalVersionReference(protocol.artifact_id, protocol.content_hash),
        endpoint.endpoint_key,
        value,
        GoalExecutionObservation(
            execution.started_at,
            execution.ended_at,
            execution.completion,
            execution.result_level,
            execution.conditions,
            execution.body_mass_kg,
            execution.execution_evidence_reference,
        ),
    )


def registration(proposal=None, protocol=None, created=None, ref=None, athlete=ATHLETE):
    protocol = protocol or protocol_for()
    proposal = proposal or proposal_for(protocol)
    return build_goal_measurement_registration(
        athlete_id=athlete,
        proposal=proposal,
        protocol=protocol,
        protocol_source=ref or protocol_ref(protocol),
        created_at=created or proposal.observation.ended_at + timedelta(seconds=1),
    )


def test_metric_unit_procedure_and_evidence_are_bound_by_the_frozen_parent():
    protocol = protocol_for()
    result = registration(protocol=protocol)
    assert result.metric_key == "VO2MAX_RELATIVE"
    assert result.metric_unit == "mL/kg/min"
    assert result.execution.procedure == protocol.proposal.endpoints[0].procedure
    assert result.execution.evidence_kind.value == "physiological_measurement"
    assert result.verify_content_hash()
    assert result.execution_details_independently_verified is False
    assert result.source_rows_immutable is False
    assert result.authority.planning_authorized is False
    assert result.authority.physiological_adaptation_established is False
    with pytest.raises(FrozenInstanceError):
        result.metric_unit = "kg"


def test_request_slot_is_owner_scoped_and_independent_of_the_proposed_value():
    first = registration()
    second = registration(replace(proposal_for(), value="51"))
    assert first.artifact_id == second.artifact_id
    assert first.content_hash != second.content_hash
    assert first.measurement_id == second.measurement_id
    assert first.assessment_id == second.assessment_id
    assert goal_measurement_id(ATHLETE, str(UUID(int=9001))) != goal_measurement_id(
        str(UUID(int=888)), str(UUID(int=9001))
    )


@pytest.mark.parametrize(
    "value",
    (
        "NaN",
        "Infinity",
        "1.0",
        "01",
        "1e3",
        "-0",
        "0.1000000000000000001",
        "123456789012345678901234567890123456789",
    ),
)
def test_noncanonical_or_lossy_scalar_is_rejected(value):
    with pytest.raises(ValueError):
        registration(replace(proposal_for(), value=value))


@pytest.mark.parametrize("value", ("0", "0.1", "-1", "50", "100000000000000000000"))
def test_supported_scalar_keeps_its_decimal_representation(value):
    assert measurement_float(value) == float(value)


@pytest.mark.parametrize(
    "problem",
    (
        "endpoint",
        "hash",
        "parent_digest",
        "athlete",
        "future",
        "outside_window",
        "condition_missing",
        "condition_evidence",
        "body_mass",
        "naive",
    ),
)
def test_measurement_provenance_and_execution_guards(problem):
    protocol = protocol_for()
    proposal = proposal_for(protocol)
    ref = protocol_ref(protocol)
    athlete = ATHLETE
    created = proposal.observation.ended_at + timedelta(seconds=1)
    if problem == "endpoint":
        proposal = replace(proposal, endpoint_key="not-registered")
    elif problem == "hash":
        proposal = replace(
            proposal, protocol_reference=replace(proposal.protocol_reference, content_hash="0" * 64)
        )
    elif problem == "parent_digest":
        ref = replace(ref, canonical_contract_sha256="0" * 64)
    elif problem == "athlete":
        athlete = str(UUID(int=888))
    elif problem == "future":
        created = proposal.observation.started_at
    elif problem == "outside_window":
        proposal = replace(
            proposal,
            observation=replace(
                proposal.observation, started_at=proposal.observation.started_at - timedelta(days=1)
            ),
        )
    elif problem == "condition_missing":
        proposal = replace(
            proposal,
            observation=replace(
                proposal.observation, conditions=proposal.observation.conditions[:1]
            ),
        )
    elif problem == "condition_evidence":
        conditions = proposal.observation.conditions
        proposal = replace(
            proposal,
            observation=replace(
                proposal.observation,
                conditions=(replace(conditions[0], evidence_reference=" "),) + conditions[1:],
            ),
        )
    elif problem == "body_mass":
        proposal = replace(proposal, observation=replace(proposal.observation, body_mass_kg="-1"))
    else:
        proposal = replace(
            proposal,
            observation=replace(
                proposal.observation,
                started_at=proposal.observation.started_at.replace(tzinfo=None),
            ),
        )
    with pytest.raises(ValueError):
        registration(proposal, protocol, created, ref, athlete)


def test_unknown_conditions_are_retained_as_observations_without_a_validity_claim():
    proposal = proposal_for()
    conditions = proposal.observation.conditions
    proposal = replace(
        proposal,
        observation=replace(
            proposal.observation,
            conditions=(replace(conditions[0], status=ConditionStatus.UNKNOWN),) + conditions[1:],
        ),
    )
    result = registration(proposal)
    assert result.execution.conditions[0].status == ConditionStatus.UNKNOWN
    assert result.execution_details_independently_verified is False


@pytest.mark.parametrize(
    "field,value",
    (
        ("athlete_id", ATHLETE),
        ("metric_key", "STRENGTH_1RM"),
        ("metric_unit", "kg"),
        ("planning_authorized", True),
        ("procedure", {}),
    ),
)
def test_http_measurement_body_cannot_override_server_owned_fields(field, value):
    import json

    payload = json.loads(canonical_json(proposal_for()))
    payload[field] = value
    with pytest.raises(ValidationError):
        GoalMeasurementInput.model_validate(payload)


@pytest.mark.parametrize(
    "field,value", (("revision", True), ("revision", "1"), ("athlete_id", ATHLETE))
)
def test_http_plan_body_rejects_coercion_and_owner_override(field, value):
    import json

    payload = json.loads(canonical_json(macro_proposal()))
    payload[field] = value
    with pytest.raises(ValidationError):
        MacrocyclePlanInput.model_validate(payload)


@pytest.mark.parametrize("value", (123, "2030-01-02T09:00:00", "1234567890"))
def test_http_times_require_an_explicit_datetime_offset(value):
    import json

    payload = json.loads(canonical_json(proposal_for()))
    payload["observation"]["started_at"] = value
    with pytest.raises(ValidationError):
        GoalMeasurementInput.model_validate(payload)
