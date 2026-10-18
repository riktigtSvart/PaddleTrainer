from dataclasses import dataclass
from datetime import datetime

from ..context.models import AthletePlanningContextAggregate
from ..entry_gate.models import EntryMode, GlobalEntryGate
from ..workout_family.models import (
    FamilyEntryGateStatus,
    FamilyRef,
    WorkoutFamilyRegistry,
)
from .models import (
    DayPart,
    MicrocycleItemKind,
    MicrocycleItemRole,
    MicrocyclePlanItem,
    MicrocyclePlanningResolution,
    StrengthFrequencyGroup,
    finalize_microcycle_plan,
)


REANCHOR_MICROCYCLE_POLICY_VERSION = 'reanchor_microcycle_policy_v0.1'
PFT_EASY_KAYAK_COMPOSITION_KEY = 'PFT_WITH_EASY_KAYAK_V0.1'


@dataclass(frozen=True)
class FamilySlot:
    slot_id: str
    date_iso: str
    day_part: DayPart
    family_ref: FamilyRef
    role: MicrocycleItemRole
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FallbackFamilySlot:
    slot_id: str
    date_iso: str
    day_part: DayPart
    primary_family_ref: FamilyRef
    fallback_family_ref: FamilyRef
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PftCompositionSlot:
    slot_id: str
    date_iso: str
    day_part: DayPart
    paired_family_ref: FamilyRef
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ExternalLoadSlot:
    slot_id: str
    date_iso: str
    day_part: DayPart
    external_load_key: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RestDaySlot:
    slot_id: str
    date_iso: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReanchorMicrocycleRequest:
    window_start_date: str
    window_end_date: str
    family_slots: tuple[FamilySlot, ...]
    fallback_slots: tuple[FallbackFamilySlot, ...]
    pft_slots: tuple[PftCompositionSlot, ...]
    external_load_slots: tuple[ExternalLoadSlot, ...]
    rest_slots: tuple[RestDaySlot, ...]
    strength_candidate_slot_ids: tuple[str, ...]
    strength_fallback_slot_ids: tuple[str, ...]
    strength_minimum_count: int
    strength_preferred_count: int
    strength_maximum_count: int


def _family_space(context: AthletePlanningContextAggregate) -> dict[tuple[str, str], object]:
    if context.runtime_projection is None:
        raise ValueError('Reanchor microcycle requires runtime projection.')
    return {
        (item.family_key, item.family_version): item
        for item in context.runtime_projection.training_space.families
    }


def _validate_family(
    *,
    family_ref: FamilyRef,
    registry: WorkoutFamilyRegistry,
    context: AthletePlanningContextAggregate,
) -> None:
    registry.get(family_ref.family_key, family_ref.family_version)
    space = _family_space(context)
    item = space.get((family_ref.family_key, family_ref.family_version))
    if item is None:
        raise ValueError(
            f'Family absent from runtime training space: '
            f'{family_ref.family_key}@{family_ref.family_version}'
        )
    if item.entry_gate_status in {
        FamilyEntryGateStatus.NOT_ELIGIBLE,
        FamilyEntryGateStatus.DEFERRED_BY_GLOBAL_GATE,
        FamilyEntryGateStatus.REVIEW_REQUIRED,
    }:
        raise ValueError(
            f'Family is not reanchor-eligible: '
            f'{family_ref.family_key}@{family_ref.family_version}'
        )


def _validate_date(date_iso: str, start: str, end: str) -> None:
    if not (start <= date_iso <= end):
        raise ValueError(f'Plan slot date outside microcycle window: {date_iso}')


def build_reanchor_microcycle_plan(
    *,
    context: AthletePlanningContextAggregate,
    resolution: MicrocyclePlanningResolution,
    registry: WorkoutFamilyRegistry,
    request: ReanchorMicrocycleRequest,
    plan_id: str,
    created_at: datetime,
):
    if not context.verify_content_hash():
        raise ValueError('Planning context hash does not verify.')
    if not resolution.verify_content_hash():
        raise ValueError('MicrocyclePlanningResolution hash does not verify.')
    if not registry.verify_content_hash():
        raise ValueError('WorkoutFamilyRegistry hash does not verify.')
    if resolution.base_context_hash != context.content_hash:
        raise ValueError('Resolution/base context hash mismatch.')
    if context.runtime_projection is None:
        raise ValueError('Reanchor microcycle requires runtime projection.')

    gate = context.runtime_projection.entry_gate
    if gate.global_gate != GlobalEntryGate.OPEN_WITH_CONSTRAINTS:
        raise ValueError(
            'Reanchor policy requires OPEN_WITH_CONSTRAINTS global gate.'
        )
    if gate.entry_mode != EntryMode.CONSERVATIVE_REANCHOR:
        raise ValueError(
            'Reanchor policy requires CONSERVATIVE_REANCHOR entry mode.'
        )
    if resolution.policy_version != REANCHOR_MICROCYCLE_POLICY_VERSION:
        raise ValueError('Unsupported reanchor microcycle policy version.')

    items: list[MicrocyclePlanItem] = []

    for slot in request.family_slots:
        _validate_date(
            slot.date_iso,
            request.window_start_date,
            request.window_end_date,
        )
        _validate_family(
            family_ref=slot.family_ref,
            registry=registry,
            context=context,
        )
        items.append(
            MicrocyclePlanItem(
                item_id=slot.slot_id,
                date_iso=slot.date_iso,
                day_part=slot.day_part,
                kind=MicrocycleItemKind.WORKOUT_FAMILY,
                role=slot.role,
                family_ref=slot.family_ref,
                reason_codes=slot.reason_codes,
            )
        )

    for slot in request.fallback_slots:
        _validate_date(
            slot.date_iso,
            request.window_start_date,
            request.window_end_date,
        )
        _validate_family(
            family_ref=slot.primary_family_ref,
            registry=registry,
            context=context,
        )
        _validate_family(
            family_ref=slot.fallback_family_ref,
            registry=registry,
            context=context,
        )
        items.append(
            MicrocyclePlanItem(
                item_id=slot.slot_id,
                date_iso=slot.date_iso,
                day_part=slot.day_part,
                kind=MicrocycleItemKind.WORKOUT_FAMILY,
                role=MicrocycleItemRole.PLANNED,
                family_ref=slot.primary_family_ref,
                fallback_family_ref=slot.fallback_family_ref,
                reason_codes=slot.reason_codes,
            )
        )

    for slot in request.pft_slots:
        _validate_date(
            slot.date_iso,
            request.window_start_date,
            request.window_end_date,
        )
        _validate_family(
            family_ref=slot.paired_family_ref,
            registry=registry,
            context=context,
        )
        items.append(
            MicrocyclePlanItem(
                item_id=slot.slot_id,
                date_iso=slot.date_iso,
                day_part=slot.day_part,
                kind=MicrocycleItemKind.MEASUREMENT_COMPOSITION,
                role=MicrocycleItemRole.PLANNED,
                family_ref=slot.paired_family_ref,
                composition_key=PFT_EASY_KAYAK_COMPOSITION_KEY,
                reason_codes=slot.reason_codes,
            )
        )

    for slot in request.external_load_slots:
        _validate_date(
            slot.date_iso,
            request.window_start_date,
            request.window_end_date,
        )
        items.append(
            MicrocyclePlanItem(
                item_id=slot.slot_id,
                date_iso=slot.date_iso,
                day_part=slot.day_part,
                kind=MicrocycleItemKind.EXTERNAL_LOAD_OBSERVATION,
                role=MicrocycleItemRole.EXTERNAL,
                external_load_key=slot.external_load_key,
                reason_codes=slot.reason_codes,
            )
        )

    for slot in request.rest_slots:
        _validate_date(
            slot.date_iso,
            request.window_start_date,
            request.window_end_date,
        )
        items.append(
            MicrocyclePlanItem(
                item_id=slot.slot_id,
                date_iso=slot.date_iso,
                day_part=DayPart.ALL_DAY,
                kind=MicrocycleItemKind.PLANNED_REST,
                role=MicrocycleItemRole.REST,
                reason_codes=slot.reason_codes,
            )
        )

    item_ids = {item.item_id for item in items}
    for item_id in (
        *request.strength_candidate_slot_ids,
        *request.strength_fallback_slot_ids,
    ):
        if item_id not in item_ids:
            raise ValueError(
                f'Strength frequency group references unknown item: {item_id}'
            )

    group = StrengthFrequencyGroup(
        group_key='STRENGTH_FREQUENCY_REANCHOR',
        candidate_item_ids=request.strength_candidate_slot_ids,
        fallback_item_ids=request.strength_fallback_slot_ids,
        minimum_count=request.strength_minimum_count,
        preferred_count=request.strength_preferred_count,
        maximum_count=request.strength_maximum_count,
    )

    return finalize_microcycle_plan(
        plan_id=plan_id,
        schema_version='reanchor_microcycle_plan_v0.1',
        base_context_hash=context.content_hash,
        resolution_hash=resolution.content_hash,
        policy_version=REANCHOR_MICROCYCLE_POLICY_VERSION,
        window_start_date=request.window_start_date,
        window_end_date=request.window_end_date,
        items=tuple(items),
        strength_frequency_group=group,
        protected_elements=(
            'RECOVERY_RESERVE',
            'KAYAK_TECHNICAL_QUALITY',
            'NO_MAJOR_PROGRESSION',
            'NO_MAXIMAL_TESTING',
        ),
        review_triggers=(
            'PAIN_OR_UNUSUAL_ISSUE',
            'BROAD_RESPONSE_DETERIORATION',
            'MATERIAL_AVAILABILITY_CHANGE',
            'MISSED_KEY_SESSION',
        ),
        created_at=created_at,
    )
