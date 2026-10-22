"""Synthetic explicit strategy and measurement-intent contracts, not efficacy tests."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest
from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.goals.catalog import (
    GOAL_CATALOG_HASH,
    GOAL_METRICS,
    CapabilityKey,
    goal_metric,
)
from app.planning.domain.goals.protocol import (
    CapabilityGoalRole,
    ChangeBasis,
    DurableGoalSourceReference,
    EndpointRole,
    GoalChangeRequirement,
    GoalMeasurementEndpoint,
    GoalPeriodType,
    GoalVersionReference,
    LegacyObjectiveSnapshot,
    MacrocycleCapabilityGoal,
    MacrocyclePlanProposal,
    MeasurementProcedure,
    MeasurementWindow,
    MesocycleProtocolProposal,
    MesocycleRoleDirective,
    ProtocolOrigin,
    TrainingGoalSourceSnapshot,
    TrainingPeriodGoalSnapshot,
    build_macrocycle_capability_plan,
    build_mesocycle_goal_protocol,
    decimal_text,
    goal_artifact_id,
)
from app.planning.domain.persistence.audit import AuditArtifactKind
from app.planning.domain.workout_family.builtins import (
    builtin_workout_family_registry_v0_1,
)

ATHLETE = "11111111-1111-4111-8111-111111111111"
SEASON = "22222222-2222-4222-8222-222222222222"
MACRO = "33333333-3333-4333-8333-333333333333"
MESO = "44444444-4444-4444-8444-444444444444"
MESO2 = "55555555-5555-4555-8555-555555555555"
NOW = datetime(2026, 10, 22, 9, tzinfo=UTC)
ROLE = CapabilityGoalRole
CAP = CapabilityKey
KIND = AuditArtifactKind
CAP_ROLES = (
    (CAP.VO2_CAPACITY, ROLE.PRIMARY_DEVELOPMENT, "VO2MAX_RELATIVE", "2", None),
    (CAP.MAX_STRENGTH, ROLE.SECONDARY_DEVELOPMENT, "STRENGTH_REFERENCE_LOAD", "1", None),
    (CAP.TECHNICAL_SKILL, ROLE.MAINTENANCE, "TECHNICAL_ERROR_COUNT", "-1", "1"),
    (CAP.POWER_RFD, ROLE.PERMITTED_DECLINE, "PEAK_POWER", "-5", None),
)


def sources():
    def node(identity, parent, kind, start, end):
        return TrainingPeriodGoalSnapshot(
            identity,
            ATHLETE,
            parent,
            kind,
            f"synthetic {kind}",
            start,
            end,
            (
                LegacyObjectiveSnapshot("ENDURANCE", "0.6"),
                LegacyObjectiveSnapshot("STRENGTH", "0.2"),
                LegacyObjectiveSnapshot("TECHNIQUE", "0.2"),
            ),
        )

    return TrainingGoalSourceSnapshot(
        ATHLETE,
        "Europe/Budapest",
        (
            node(SEASON, None, GoalPeriodType.SEASON, "2030-01-01", "2030-12-31"),
            node(MACRO, SEASON, GoalPeriodType.MACROCYCLE, "2030-01-01", "2030-02-28"),
        ),
        (
            node(MESO, MACRO, GoalPeriodType.MESOCYCLE, "2030-01-01", "2030-01-31"),
            node(MESO2, MACRO, GoalPeriodType.MESOCYCLE, "2030-02-01", "2030-02-28"),
        ),
    )


def macro_proposal():
    return MacrocyclePlanProposal(
        MACRO,
        1,
        None,
        tuple(
            MacrocycleCapabilityGoal(cap, role, "explicit strategic intent")
            for cap, role, *_ in CAP_ROLES
        ),
        tuple(
            MesocycleRoleDirective(period, cap, role, "explicit phase allocation")
            for period in (MESO, MESO2)
            for cap, role, *_ in CAP_ROLES
        ),
        "Synthetic macrocycle strategy; no empirical efficacy claim.",
    )


def macro_plan(proposal=None, source=None, previous=None, created=NOW):
    return build_macrocycle_capability_plan(
        athlete_id=ATHLETE,
        proposal=proposal or macro_proposal(),
        sources=source or sources(),
        previous_source=previous,
        created_at=created,
    )


def macro_ref(plan):
    from hashlib import sha256

    return DurableGoalSourceReference(
        KIND.MACROCYCLE_CAPABILITY_PLAN,
        plan.artifact_id,
        plan.content_hash,
        sha256(canonical_json(plan).encode()).hexdigest(),
        NOW + timedelta(seconds=1),
    )


def endpoint(cap, metric_key, minimum, maximum):
    return GoalMeasurementEndpoint(
        f"primary:{metric_key}",
        cap,
        metric_key,
        EndpointRole.PRIMARY,
        MeasurementProcedure(
            f"synthetic:{metric_key}",
            "1",
            ProtocolOrigin.EXPLICIT_CUSTOM,
            "synthetic:explicit-test-definition-v1",
            "KAYAK" if cap != CAP.MAX_STRENGTH else "STRENGTH",
            "Fixed synthetic exercise/task and dose",
            "Repeat the fixed synthetic task",
            "Same calibrated synthetic equipment and algorithm",
            ("same task, equipment, conditions and processing", "record fatigue and body mass"),
        ),
        MeasurementWindow(datetime(2030, 1, 2, 9, tzinfo=UTC), datetime(2030, 1, 3, 9, tzinfo=UTC)),
        MeasurementWindow(
            datetime(2030, 1, 25, 9, tzinfo=UTC), datetime(2030, 1, 26, 9, tzinfo=UTC)
        ),
        GoalChangeRequirement(ChangeBasis.FAVOURABLE_ABSOLUTE_CHANGE, minimum, maximum, None, None),
    )


def meso_proposal(plan=None):
    plan = plan or macro_plan()
    return MesocycleProtocolProposal(
        MESO,
        1,
        None,
        GoalVersionReference(plan.artifact_id, plan.content_hash),
        tuple(endpoint(cap, metric, low, high) for cap, _, metric, low, high in CAP_ROLES),
        "Prospective synthetic endpoints, no selected observed outcomes.",
    )


def meso_protocol(proposal=None, plan=None, source=None):
    plan = plan or macro_plan()
    return build_mesocycle_goal_protocol(
        athlete_id=ATHLETE,
        proposal=proposal or meso_proposal(plan),
        macrocycle_plan=plan,
        macrocycle_source=macro_ref(plan),
        sources=source or sources(),
        previous_source=None,
        created_at=NOW + timedelta(seconds=2),
    )


def test_catalog_covers_existing_families_and_three_accepted_additions():
    family_keys = {
        key
        for family in builtin_workout_family_registry_v0_1().families
        for key in family.primary_capability_keys + family.secondary_capability_keys
    }
    assert family_keys <= set(CAP)
    assert len(CAP) == 13
    assert {
        CAP.SPRINT_SPEED_AND_START,
        CAP.MUSCULAR_ENDURANCE,
        CAP.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
    } <= set(CAP)
    assert len({m.metric_key for m in GOAL_METRICS}) == len(GOAL_METRICS)
    assert len(GOAL_CATALOG_HASH) == 64


def test_macrocycle_explicitly_assigns_all_four_roles_without_inferring_weights():
    plan = macro_plan()
    assert {d.role for d in plan.proposal.mesocycle_directives} == set(ROLE)
    assert plan.unassigned_capability_keys == tuple(
        k for k in CAP if k not in {c[0] for c in CAP_ROLES}
    )
    assert plan.sources.mesocycles[0].legacy_objectives[0].weight == "0.6"
    assert plan.verify_content_hash()
    assert plan.authority.shadow_only
    assert not plan.authority.planning_authorized
    with pytest.raises(FrozenInstanceError):
        plan.proposal.revision = 2


def test_mesocycle_roles_are_derived_from_macrocycle_not_supplied_as_weights():
    protocol = meso_protocol()
    assert protocol.capability_roles == tuple(
        d for d in macro_proposal().mesocycle_directives if d.mesocycle_period_id == MESO
    )
    assert protocol.verify_content_hash()
    assert protocol.combination_rule == "ALL_PRIMARY_ENDPOINTS_REQUIRED_NO_COMPOSITE_SCORE"
    assert protocol.uncertainty_rule == "WITHHOLD_IF_UNQUANTIFIED_OR_INCONCLUSIVE"
    assert protocol.authority.comparative_utility_endpoint_preregistered is False
    assert protocol.authority.physiological_adaptation_established is False


def test_macrocycle_can_plan_a_temporary_decline_then_development():
    proposal = macro_proposal()
    directives = tuple(
        replace(d, role=ROLE.PRIMARY_DEVELOPMENT)
        if d.mesocycle_period_id == MESO2 and d.capability_key == CAP.POWER_RFD
        else d
        for d in proposal.mesocycle_directives
    )
    plan = macro_plan(replace(proposal, mesocycle_directives=directives))
    assert [
        d.role for d in plan.proposal.mesocycle_directives if d.capability_key == CAP.POWER_RFD
    ] == [ROLE.PERMITTED_DECLINE, ROLE.PRIMARY_DEVELOPMENT]


@pytest.mark.parametrize(
    "change",
    [
        lambda p: replace(p, goals=()),
        lambda p: replace(p, goals=p.goals + (p.goals[0],)),
        lambda p: replace(p, mesocycle_directives=p.mesocycle_directives[:-1]),
        lambda p: replace(
            p, mesocycle_directives=p.mesocycle_directives + (p.mesocycle_directives[0],)
        ),
        lambda p: replace(p, goals=list(p.goals)),
        lambda p: replace(p, revision=True),
        lambda p: replace(p, revision=2),
        lambda p: replace(p, rationale=" "),
        lambda p: replace(
            p, goals=(replace(p.goals[0], role="primary_development"),) + p.goals[1:]
        ),
    ],
)
def test_invalid_or_incomplete_macrocycle_intent_is_rejected(change):
    with pytest.raises(ValueError):
        macro_plan(change(macro_proposal()))


@pytest.mark.parametrize(
    "change",
    [
        lambda s: replace(s, mesocycles=()),
        lambda s: replace(s, hierarchy=s.hierarchy[1:]),
        lambda s: replace(s, athlete_id=SEASON),
        lambda s: replace(s, mesocycles=tuple(reversed(s.mesocycles))),
        lambda s: replace(
            s, mesocycles=(replace(s.mesocycles[0], parent_id=SEASON), s.mesocycles[1])
        ),
        lambda s: replace(
            s, mesocycles=(replace(s.mesocycles[0], end_date="2030-02-02"), s.mesocycles[1])
        ),
        lambda s: replace(
            s, mesocycles=(replace(s.mesocycles[0], athlete_id=SEASON), s.mesocycles[1])
        ),
        lambda s: replace(
            s,
            mesocycles=(
                replace(s.mesocycles[0], period_type=GoalPeriodType.SEASON),
                s.mesocycles[1],
            ),
        ),
        lambda s: replace(
            s, hierarchy=(replace(s.hierarchy[0], end_date="2029-12-31"), s.hierarchy[1])
        ),
        lambda s: replace(
            s,
            mesocycles=(
                replace(
                    s.mesocycles[0],
                    legacy_objectives=(
                        LegacyObjectiveSnapshot("ENDURANCE", "1"),
                        LegacyObjectiveSnapshot("STRENGTH", "0.2"),
                    ),
                ),
                s.mesocycles[1],
            ),
        ),
    ],
)
def test_invalid_goal_hierarchy_or_census_is_rejected(change):
    with pytest.raises(ValueError):
        macro_plan(source=change(sources()))


@pytest.mark.parametrize(
    "text",
    [
        "NaN",
        "Infinity",
        "-Infinity",
        "1e2",
        "1.0",
        "-0",
        "01",
        ".2",
        " 1",
        "1 ",
        "",
        "9" * 81,
        1,
        True,
    ],
)
def test_decimal_thresholds_are_finite_canonical_and_typed(text):
    with pytest.raises(ValueError):
        decimal_text(text)


def test_version_identity_is_stable_but_content_changes_with_goal_intent():
    first = macro_plan()
    later = macro_plan(created=NOW + timedelta(seconds=1))
    assert first.artifact_id == later.artifact_id
    assert first.content_hash == later.content_hash
    changed = macro_plan(replace(macro_proposal(), rationale="different intent"))
    assert changed.artifact_id == first.artifact_id
    assert changed.content_hash != first.content_hash


def test_second_version_requires_exact_previous_slot_and_hash():
    first = macro_plan()
    previous = macro_ref(first)
    proposal = replace(
        macro_proposal(),
        revision=2,
        supersedes=GoalVersionReference(first.artifact_id, first.content_hash),
    )
    second = macro_plan(proposal, previous=previous, created=NOW + timedelta(seconds=2))
    assert second.artifact_id != first.artifact_id
    with pytest.raises(ValueError):
        macro_plan(proposal, previous=replace(previous, content_hash="a" * 64))
    assert goal_artifact_id(KIND.MACROCYCLE_CAPABILITY_PLAN, ATHLETE, MACRO, 1) == first.artifact_id


@pytest.mark.parametrize(
    "change",
    [
        lambda e: replace(e, metric_key="NOT_A_METRIC"),
        lambda e: replace(e, capability_key=CAP.POWER_RFD),
        lambda e: replace(e, baseline_window=MeasurementWindow(NOW, NOW + timedelta(hours=1))),
        lambda e: replace(e, followup_window=e.baseline_window),
        lambda e: replace(
            e,
            followup_window=MeasurementWindow(
                datetime(2030, 1, 31, 23, 30, tzinfo=UTC), datetime(2030, 1, 31, 23, 31, tzinfo=UTC)
            ),
        ),
        lambda e: replace(e, procedure=replace(e.procedure, comparability_conditions=())),
        lambda e: replace(e, procedure=replace(e.procedure, procedure="")),
        lambda e: replace(e, change_requirement=replace(e.change_requirement, minimum="0")),
        lambda e: replace(e, change_requirement=replace(e.change_requirement, maximum="1")),
        lambda e: replace(
            e, change_requirement=replace(e.change_requirement, measurement_error_estimate="1")
        ),
        lambda e: replace(
            e,
            change_requirement=replace(
                e.change_requirement,
                measurement_error_estimate="-1",
                measurement_error_source="source",
            ),
        ),
        lambda e: replace(e, role=EndpointRole.SUPPORTING),
    ],
)
def test_invalid_endpoint_selection_comparability_and_chronology_are_rejected(change):
    proposal = meso_proposal()
    with pytest.raises(ValueError):
        meso_protocol(
            replace(proposal, endpoints=(change(proposal.endpoints[0]),) + proposal.endpoints[1:])
        )


@pytest.mark.parametrize(
    "index,low,high",
    [
        (1, "-1", None),
        (2, "1", "2"),
        (2, "-1", None),
        (2, "-2", "-1"),
        (3, "0", None),
        (3, "-5", "-1"),
    ],
)
def test_role_specific_acceptance_ranges(index, low, high):
    proposal = meso_proposal()
    rows = list(proposal.endpoints)
    rows[index] = replace(
        rows[index],
        change_requirement=replace(rows[index].change_requirement, minimum=low, maximum=high),
    )
    with pytest.raises(ValueError):
        meso_protocol(replace(proposal, endpoints=tuple(rows)))


def test_context_and_estimates_cannot_be_promoted_to_measured_capability():
    assert goal_metric("VO2MAX_ESTIMATED_RELATIVE").evidence_kind.value == "estimate"
    assert goal_metric("SUBMAXIMAL_OUTPUT").evidence_kind.value == "indirect_indicator"
    assert goal_metric("PAIN_RATING").primary_endpoint_eligible is False
    protocol = meso_protocol()
    assert protocol.standardization_validated is False
    assert protocol.authority.capability_change_established is False


def test_percentage_change_is_restricted_to_ratio_metrics():
    plan = macro_plan()
    proposal = meso_proposal(plan)
    first = replace(
        proposal.endpoints[0],
        change_requirement=replace(
            proposal.endpoints[0].change_requirement, basis=ChangeBasis.FAVOURABLE_PERCENT_CHANGE
        ),
    )
    assert meso_protocol(
        replace(proposal, endpoints=(first,) + proposal.endpoints[1:])
    ).verify_content_hash()
    altered_goal = MacrocycleCapabilityGoal(
        CAP.TECHNICAL_STABILITY_UNDER_FATIGUE, ROLE.PRIMARY_DEVELOPMENT, "technical stability"
    )
    changed = replace(
        macro_proposal(),
        goals=(altered_goal,),
        mesocycle_directives=tuple(
            MesocycleRoleDirective(p, altered_goal.capability_key, altered_goal.role, "explicit")
            for p in (MESO, MESO2)
        ),
    )
    plan = macro_plan(changed)
    trial = endpoint(altered_goal.capability_key, "TECHNICAL_ERROR_INCREASE", "1", None)
    trial = replace(
        trial,
        change_requirement=replace(
            trial.change_requirement, basis=ChangeBasis.FAVOURABLE_PERCENT_CHANGE
        ),
    )
    with pytest.raises(ValueError):
        meso_protocol(replace(meso_proposal(plan), endpoints=(trial,)), plan=plan)


def test_changed_mutable_sources_do_not_redefine_the_macrocycle_intent():
    changed = replace(
        sources(),
        hierarchy=(sources().hierarchy[0], replace(sources().hierarchy[1], title="edited later")),
    )
    with pytest.raises(ValueError):
        meso_protocol(source=changed)


def test_external_reference_is_not_a_claim_of_validated_standardization():
    proposal = meso_proposal()
    first = replace(
        proposal.endpoints[0],
        procedure=replace(
            proposal.endpoints[0].procedure,
            origin=ProtocolOrigin.EXTERNAL_REFERENCE,
            source_reference="https://example.invalid/synthetic-standard-reference",
        ),
    )
    artifact = meso_protocol(replace(proposal, endpoints=(first,) + proposal.endpoints[1:]))
    assert artifact.standardization_validated is False


def test_endpoint_omission_and_duplicate_keys_cannot_change_the_primary_family():
    proposal = meso_proposal()
    for endpoints in (proposal.endpoints[:-1], proposal.endpoints + (proposal.endpoints[0],)):
        with pytest.raises(ValueError):
            meso_protocol(replace(proposal, endpoints=endpoints))


def test_supporting_results_do_not_replace_a_missing_primary_endpoint():
    proposal = meso_proposal()
    first = replace(proposal.endpoints[0], role=EndpointRole.SUPPORTING, change_requirement=None)
    with pytest.raises(ValueError, match="Every assigned capability"):
        meso_protocol(replace(proposal, endpoints=(first,) + proposal.endpoints[1:]))


def test_one_procedure_version_cannot_mean_two_different_procedures():
    proposal = meso_proposal()
    extra = replace(
        proposal.endpoints[0],
        endpoint_key="supporting:conflict",
        role=EndpointRole.SUPPORTING,
        change_requirement=None,
        procedure=replace(proposal.endpoints[0].procedure, procedure="different"),
    )
    with pytest.raises(ValueError, match="conflicting procedure"):
        meso_protocol(replace(proposal, endpoints=proposal.endpoints + (extra,)))


def test_measurement_selection_and_nonpositive_baseline_rules_are_frozen():
    protocol = meso_protocol()
    assert protocol.measurement_selection_rule == (
        "EXACTLY_ONE_ELIGIBLE_COMPLETE_RESULT_PER_WINDOW_OTHERWISE_WITHHOLD"
    )
    assert protocol.nonpositive_baseline_rule == "WITHHOLD_PERCENT_CHANGE_IF_BASELINE_NOT_POSITIVE"


def test_subjective_state_can_be_recorded_as_context_only():
    goal = MacrocycleCapabilityGoal(
        CAP.MUSCULOSKELETAL_ROBUSTNESS, ROLE.PRIMARY_DEVELOPMENT, "task tolerance"
    )
    plan = macro_plan(
        replace(
            macro_proposal(),
            goals=(goal,),
            mesocycle_directives=tuple(
                MesocycleRoleDirective(p, goal.capability_key, goal.role, "explicit")
                for p in (MESO, MESO2)
            ),
        )
    )
    primary = endpoint(goal.capability_key, "FUNCTIONAL_TASK_REPETITIONS", "1", None)
    context = replace(
        endpoint(goal.capability_key, "PAIN_RATING", "1", None),
        role=EndpointRole.CONTEXT,
        change_requirement=None,
    )
    protocol = meso_protocol(replace(meso_proposal(plan), endpoints=(primary, context)), plan=plan)
    assert protocol.authority.physiological_adaptation_established is False
    with pytest.raises(ValueError, match="context only"):
        meso_protocol(
            replace(
                meso_proposal(plan),
                endpoints=(primary, replace(context, role=EndpointRole.SUPPORTING)),
            ),
            plan=plan,
        )
