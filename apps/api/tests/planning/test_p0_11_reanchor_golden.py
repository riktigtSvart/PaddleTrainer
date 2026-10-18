from dataclasses import replace

import pytest

from app.planning.domain.common.serialization import canonical_json
from app.planning.domain.entry_gate.models import EntryMode, GlobalEntryGate
from app.planning.domain.microcycle.models import (
    MicrocycleItemKind,
    MicrocycleItemRole,
)
from app.planning.domain.microcycle.reanchor import (
    PFT_EASY_KAYAK_COMPOSITION_KEY,
    build_reanchor_microcycle_plan,
)
from app.planning.domain.workout_family.builtins import (
    KAYAK_EASY_TECHNICAL_KEY,
    KAYAK_LONG_AEROBIC_KEY,
    RUN_EASY_AEROBIC_FALLBACK_KEY,
    STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY,
)
from .golden_scenarios.reanchor_2026_10_16 import (
    _dt,
    build_golden_reanchor_inputs,
)


def _plan(plan_id='golden-plan', created_hour=6):
    state, gate, registry, context, resolution, request = (
        build_golden_reanchor_inputs()
    )
    plan = build_reanchor_microcycle_plan(
        context=context,
        resolution=resolution,
        registry=registry,
        request=request,
        plan_id=plan_id,
        created_at=_dt(16, created_hour),
    )
    return state, gate, registry, context, resolution, request, plan


def test_golden_fixture_enters_conservative_reanchor() -> None:
    _, gate, _, _, _, _, _ = _plan()
    assert gate.global_gate == GlobalEntryGate.OPEN_WITH_CONSTRAINTS
    assert gate.entry_mode == EntryMode.CONSERVATIVE_REANCHOR


def test_golden_plan_exact_structural_signature() -> None:
    *_, plan = _plan()
    signature = tuple(
        (
            item.date_iso,
            item.day_part.value,
            item.kind.value,
            item.role.value,
            None if item.family_ref is None else item.family_ref.family_key,
            None if item.fallback_family_ref is None else item.fallback_family_ref.family_key,
            item.composition_key,
            item.external_load_key,
        )
        for item in plan.items
    )
    assert signature == (
        ('2026-10-16', 'am', 'workout_family', 'planned', KAYAK_EASY_TECHNICAL_KEY, None, None, None),
        ('2026-10-16', 'pm', 'workout_family', 'preferred', STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY, None, None, None),
        ('2026-10-17', 'am', 'workout_family', 'planned', KAYAK_LONG_AEROBIC_KEY, None, None, None),
        ('2026-10-18', 'am', 'workout_family', 'planned', KAYAK_EASY_TECHNICAL_KEY, None, None, None),
        ('2026-10-18', 'daytime', 'external_load_observation', 'external', None, None, None, 'FAMILY_HIKE'),
        ('2026-10-18', 'pm', 'workout_family', 'fallback', STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY, None, None, None),
        ('2026-10-19', 'all_day', 'planned_rest', 'rest', None, None, None, None),
        ('2026-10-20', 'dawn', 'measurement_composition', 'planned', KAYAK_EASY_TECHNICAL_KEY, None, PFT_EASY_KAYAK_COMPOSITION_KEY, None),
        ('2026-10-21', 'afternoon', 'workout_family', 'preferred', STRENGTH_REFERENCE_AND_DEVELOPMENT_KEY, None, None, None),
        ('2026-10-22', 'dawn', 'workout_family', 'planned', KAYAK_EASY_TECHNICAL_KEY, RUN_EASY_AEROBIC_FALLBACK_KEY, None, None),
    )


def test_strength_frequency_contract_matches_accepted_reanchor() -> None:
    *_, plan = _plan()
    group = plan.strength_frequency_group
    assert group is not None
    assert group.minimum_count == 1
    assert group.preferred_count == 2
    assert group.maximum_count == 2
    assert group.candidate_item_ids == ('fri_strength', 'wed_strength')
    assert group.fallback_item_ids == ('sun_strength_fallback',)


def test_pft_is_composition_not_workout_family() -> None:
    *_, plan = _plan()
    pft = next(item for item in plan.items if item.item_id == 'tue_pft_easy_kayak')
    assert pft.kind == MicrocycleItemKind.MEASUREMENT_COMPOSITION
    assert pft.family_ref.family_key == KAYAK_EASY_TECHNICAL_KEY
    assert pft.composition_key == PFT_EASY_KAYAK_COMPOSITION_KEY


def test_hike_is_external_load_not_training_family() -> None:
    *_, plan = _plan()
    hike = next(item for item in plan.items if item.item_id == 'sun_family_hike')
    assert hike.kind == MicrocycleItemKind.EXTERNAL_LOAD_OBSERVATION
    assert hike.family_ref is None


def test_monday_is_true_planned_rest() -> None:
    *_, plan = _plan()
    monday = [item for item in plan.items if item.date_iso == '2026-10-19']
    assert len(monday) == 1
    assert monday[0].kind == MicrocycleItemKind.PLANNED_REST


def test_plan_protects_reanchor_guardrails() -> None:
    *_, plan = _plan()
    assert 'RECOVERY_RESERVE' in plan.protected_elements
    assert 'NO_MAJOR_PROGRESSION' in plan.protected_elements
    assert 'NO_MAXIMAL_TESTING' in plan.protected_elements


def test_plan_hash_is_semantic_not_generated_identity() -> None:
    *_, first = _plan(plan_id='plan-a', created_hour=6)
    *_, second = _plan(plan_id='plan-b', created_hour=7)
    assert first.content_hash == second.content_hash
    assert first.verify_content_hash()
    assert second.verify_content_hash()


def test_resolution_is_bound_to_exact_context() -> None:
    _, _, registry, context, resolution, request = build_golden_reanchor_inputs()
    from app.planning.domain.microcycle.models import (
        finalize_microcycle_planning_resolution,
    )
    wrong = finalize_microcycle_planning_resolution(
        resolution_id='wrong-resolution',
        base_context_hash='x' * 64,
        resolutions=resolution.resolutions,
        objective_regime_code=resolution.objective_regime_code,
        planning_authority_code=resolution.planning_authority_code,
        policy_version=resolution.policy_version,
        created_at=resolution.created_at,
    )
    with pytest.raises(ValueError, match='hash mismatch'):
        build_reanchor_microcycle_plan(
            context=context,
            resolution=wrong,
            registry=registry,
            request=request,
            plan_id='bad',
            created_at=_dt(16, 6),
        )


def test_reanchor_builder_refuses_non_reanchor_entry_mode() -> None:
    _, _, registry, context, resolution, request = build_golden_reanchor_inputs()
    projection = context.runtime_projection
    changed_gate = replace(
        projection.entry_gate,
        entry_mode=EntryMode.DATA_LIMITED,
    )
    changed_projection = replace(projection, entry_gate=changed_gate)
    # Rebuild a valid-hash context with altered runtime projection.
    from app.planning.domain.context.models import create_planning_context
    changed_context = create_planning_context(
        context_id='changed',
        athlete_id=context.athlete_id,
        schema_version=context.schema_version,
        as_of=context.as_of,
        information_cutoff_at=context.information_cutoff_at,
        created_at=context.created_at,
        planning_scope=context.planning_scope,
        decision_purpose=context.decision_purpose,
        source_snapshot_refs=context.source_snapshot_refs,
        engine_version=context.engine_version,
        rules_version=context.rules_version,
        evidence_pack_version=context.evidence_pack_version,
        sport_profile_versions=context.sport_profile_versions,
        policy_versions=context.policy_versions,
        critical_unknowns=context.critical_unknowns,
        runtime_projection=changed_projection,
    )
    changed_resolution = replace(
        resolution,
        base_context_hash=changed_context.content_hash,
    )
    # Re-finalize to maintain a valid semantic hash.
    from app.planning.domain.microcycle.models import finalize_microcycle_planning_resolution
    changed_resolution = finalize_microcycle_planning_resolution(
        resolution_id='changed-resolution',
        base_context_hash=changed_context.content_hash,
        resolutions=resolution.resolutions,
        objective_regime_code=resolution.objective_regime_code,
        planning_authority_code=resolution.planning_authority_code,
        policy_version=resolution.policy_version,
        created_at=resolution.created_at,
    )
    with pytest.raises(ValueError, match='CONSERVATIVE_REANCHOR'):
        build_reanchor_microcycle_plan(
            context=changed_context,
            resolution=changed_resolution,
            registry=registry,
            request=request,
            plan_id='bad',
            created_at=_dt(16, 6),
        )


def test_golden_plan_canonical_json_is_stable() -> None:
    *_, first = _plan(plan_id='plan-a', created_hour=6)
    *_, second = _plan(plan_id='plan-b', created_hour=7)
    # IDs/timestamps differ in raw contracts, but the verified semantic hash
    # remains stable. The content itself is still canonicalizable/auditable.
    assert canonical_json(first)
    assert canonical_json(second)
    assert first.content_hash == second.content_hash
