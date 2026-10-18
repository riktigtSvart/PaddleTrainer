from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
)
from ..common.time import to_utc
from ..context.models import UnresolvedPlanningDimension
from ..workout_family.models import FamilyRef


MICROCYCLE_RESOLUTION_HASH_EXCLUDE_FIELDS = frozenset(
    {'content_hash', 'resolution_id', 'created_at'}
)
MICROCYCLE_PLAN_HASH_EXCLUDE_FIELDS = frozenset(
    {'content_hash', 'plan_id', 'created_at'}
)


class ResolutionStatus(StrEnum):
    RESOLVED = 'resolved'
    NOT_APPLICABLE = 'not_applicable'


@dataclass(frozen=True)
class PlanningDimensionResolution:
    dimension: UnresolvedPlanningDimension
    status: ResolutionStatus
    source_ref: str
    summary_code: str

    def __post_init__(self) -> None:
        if not self.source_ref.strip():
            raise ValueError('source_ref must be non-empty.')
        if not self.summary_code.strip():
            raise ValueError('summary_code must be non-empty.')


@dataclass(frozen=True)
class MicrocyclePlanningResolution:
    resolution_id: str
    base_context_hash: str
    resolutions: tuple[PlanningDimensionResolution, ...]
    objective_regime_code: str
    planning_authority_code: str
    policy_version: str
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=MICROCYCLE_RESOLUTION_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_microcycle_planning_resolution(
    *,
    resolution_id: str,
    base_context_hash: str,
    resolutions: tuple[PlanningDimensionResolution, ...],
    objective_regime_code: str,
    planning_authority_code: str,
    policy_version: str,
    created_at: datetime,
) -> MicrocyclePlanningResolution:
    required = set(UnresolvedPlanningDimension)
    provided = {item.dimension for item in resolutions}
    if provided != required:
        missing = sorted(item.value for item in required - provided)
        extra = sorted(item.value for item in provided - required)
        raise ValueError(
            f'Planning dimension resolution must be complete; '
            f'missing={missing}, extra={extra}.'
        )
    if len(resolutions) != len(provided):
        raise ValueError('Planning dimensions must be unique.')
    for name, value in (
        ('resolution_id', resolution_id),
        ('base_context_hash', base_context_hash),
        ('objective_regime_code', objective_regime_code),
        ('planning_authority_code', planning_authority_code),
        ('policy_version', policy_version),
    ):
        if not value.strip():
            raise ValueError(f'{name} must be non-empty.')

    ordered = tuple(sorted(resolutions, key=lambda item: item.dimension.value))
    provisional = MicrocyclePlanningResolution(
        resolution_id=resolution_id,
        base_context_hash=base_context_hash,
        resolutions=ordered,
        objective_regime_code=objective_regime_code,
        planning_authority_code=planning_authority_code,
        policy_version=policy_version,
        created_at=to_utc(created_at, field_name='created_at'),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash='',
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=MICROCYCLE_RESOLUTION_HASH_EXCLUDE_FIELDS,
    )
    return MicrocyclePlanningResolution(
        resolution_id=provisional.resolution_id,
        base_context_hash=provisional.base_context_hash,
        resolutions=provisional.resolutions,
        objective_regime_code=provisional.objective_regime_code,
        planning_authority_code=provisional.planning_authority_code,
        policy_version=provisional.policy_version,
        created_at=provisional.created_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )


class DayPart(StrEnum):
    DAWN = 'dawn'
    AM = 'am'
    DAYTIME = 'daytime'
    AFTERNOON = 'afternoon'
    PM = 'pm'
    EVENING = 'evening'
    ALL_DAY = 'all_day'


_DAY_PART_ORDER = {
    DayPart.DAWN: 0,
    DayPart.AM: 1,
    DayPart.DAYTIME: 2,
    DayPart.AFTERNOON: 3,
    DayPart.PM: 4,
    DayPart.EVENING: 5,
    DayPart.ALL_DAY: 6,
}


def day_part_order(value: DayPart) -> int:
    return _DAY_PART_ORDER[value]


class MicrocycleItemKind(StrEnum):
    WORKOUT_FAMILY = 'workout_family'
    MEASUREMENT_COMPOSITION = 'measurement_composition'
    PLANNED_REST = 'planned_rest'
    EXTERNAL_LOAD_OBSERVATION = 'external_load_observation'


class MicrocycleItemRole(StrEnum):
    PLANNED = 'planned'
    PREFERRED = 'preferred'
    OPTIONAL = 'optional'
    FALLBACK = 'fallback'
    EXTERNAL = 'external'
    REST = 'rest'


@dataclass(frozen=True)
class MicrocyclePlanItem:
    item_id: str
    date_iso: str
    day_part: DayPart
    kind: MicrocycleItemKind
    role: MicrocycleItemRole
    family_ref: FamilyRef | None = None
    fallback_family_ref: FamilyRef | None = None
    composition_key: str | None = None
    external_load_key: str | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError('item_id must be non-empty.')
        if len(self.date_iso) != 10:
            raise ValueError('date_iso must be YYYY-MM-DD.')

        if self.kind == MicrocycleItemKind.WORKOUT_FAMILY:
            if self.family_ref is None:
                raise ValueError('WORKOUT_FAMILY requires family_ref.')
            if self.composition_key is not None or self.external_load_key is not None:
                raise ValueError('WORKOUT_FAMILY cannot carry composition/external keys.')
        elif self.kind == MicrocycleItemKind.MEASUREMENT_COMPOSITION:
            if not self.composition_key:
                raise ValueError('MEASUREMENT_COMPOSITION requires composition_key.')
            if self.external_load_key is not None:
                raise ValueError('Measurement composition cannot be external load.')
        elif self.kind == MicrocycleItemKind.EXTERNAL_LOAD_OBSERVATION:
            if not self.external_load_key:
                raise ValueError('EXTERNAL_LOAD_OBSERVATION requires external_load_key.')
            if self.family_ref is not None:
                raise ValueError('External load must not masquerade as workout family.')
        elif self.kind == MicrocycleItemKind.PLANNED_REST:
            if any((self.family_ref, self.fallback_family_ref, self.composition_key, self.external_load_key)):
                raise ValueError('PLANNED_REST cannot carry training content.')


@dataclass(frozen=True)
class StrengthFrequencyGroup:
    group_key: str
    candidate_item_ids: tuple[str, ...]
    fallback_item_ids: tuple[str, ...]
    minimum_count: int
    preferred_count: int
    maximum_count: int

    def __post_init__(self) -> None:
        if not (
            0 <= self.minimum_count <= self.preferred_count <= self.maximum_count
        ):
            raise ValueError('Strength frequency counts must satisfy min <= preferred <= max.')
        if self.maximum_count > len(self.candidate_item_ids) + len(self.fallback_item_ids):
            raise ValueError('maximum_count exceeds available strength candidates.')


@dataclass(frozen=True)
class MicrocyclePlan:
    plan_id: str
    schema_version: str
    base_context_hash: str
    resolution_hash: str
    policy_version: str
    window_start_date: str
    window_end_date: str
    items: tuple[MicrocyclePlanItem, ...]
    strength_frequency_group: StrengthFrequencyGroup | None
    protected_elements: tuple[str, ...]
    review_triggers: tuple[str, ...]
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=MICROCYCLE_PLAN_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_microcycle_plan(
    *,
    plan_id: str,
    schema_version: str,
    base_context_hash: str,
    resolution_hash: str,
    policy_version: str,
    window_start_date: str,
    window_end_date: str,
    items: tuple[MicrocyclePlanItem, ...],
    strength_frequency_group: StrengthFrequencyGroup | None,
    protected_elements: tuple[str, ...],
    review_triggers: tuple[str, ...],
    created_at: datetime,
) -> MicrocyclePlan:
    ids = tuple(item.item_id for item in items)
    if len(ids) != len(set(ids)):
        raise ValueError('Microcycle plan item IDs must be unique.')

    ordered = tuple(
        sorted(
            items,
            key=lambda item: (
                item.date_iso,
                day_part_order(item.day_part),
                item.item_id,
            ),
        )
    )

    rest_dates = {
        item.date_iso
        for item in ordered
        if item.kind == MicrocycleItemKind.PLANNED_REST
    }
    for item in ordered:
        if (
            item.date_iso in rest_dates
            and item.kind not in {
                MicrocycleItemKind.PLANNED_REST,
                MicrocycleItemKind.EXTERNAL_LOAD_OBSERVATION,
            }
        ):
            raise ValueError('Planned-rest date cannot contain planned training.')

    provisional = MicrocyclePlan(
        plan_id=plan_id,
        schema_version=schema_version,
        base_context_hash=base_context_hash,
        resolution_hash=resolution_hash,
        policy_version=policy_version,
        window_start_date=window_start_date,
        window_end_date=window_end_date,
        items=ordered,
        strength_frequency_group=strength_frequency_group,
        protected_elements=tuple(protected_elements),
        review_triggers=tuple(review_triggers),
        created_at=to_utc(created_at, field_name='created_at'),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash='',
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=MICROCYCLE_PLAN_HASH_EXCLUDE_FIELDS,
    )
    return MicrocyclePlan(
        plan_id=provisional.plan_id,
        schema_version=provisional.schema_version,
        base_context_hash=provisional.base_context_hash,
        resolution_hash=provisional.resolution_hash,
        policy_version=provisional.policy_version,
        window_start_date=provisional.window_start_date,
        window_end_date=provisional.window_end_date,
        items=provisional.items,
        strength_frequency_group=provisional.strength_frequency_group,
        protected_elements=provisional.protected_elements,
        review_triggers=provisional.review_triggers,
        created_at=provisional.created_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
