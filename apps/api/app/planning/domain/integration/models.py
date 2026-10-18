from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import json

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from ..common.time import to_utc


EXISTING_PLAN_CAPTURE_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})


class ExistingPlanCaptureIdentitySemantics(StrEnum):
    """Identity meaning of the current application plan-read API.

    The inspected API intentionally creates a fresh server capture on each
    read. Its exported contract plan_id and expanded occurrence IDs therefore
    identify the capture, not a persisted logical plan revision.
    """

    CAPTURE_SCOPED = "capture_scoped"


@dataclass(frozen=True)
class ExistingWorkoutPlanCapture:
    """Lossless planning-side capture of the current app's read-only plan export.

    This object is an integration boundary, not an authoritative plan revision.
    The entire source read is retained as canonical JSON so adapter extraction
    can always be audited against the exact source payload.
    """

    api_rules_version: str
    contract_release: str

    capture_id: str
    captured_at: datetime
    source_workout_id: str
    athlete_id: str
    source_kind: str
    source_content_sha256: str

    # Stable application identity derived from PlannedWorkout.id. This is a
    # binding key only; it does not rewrite/promote the external contract.
    planning_logical_plan_id: str

    external_contract_plan_id: str
    external_contract_plan_revision: int
    external_contract_schema_version: str
    external_plan_content_hash: str
    external_contract_snapshot_sha256: str
    external_adapter_version: str

    contract_block_ids: tuple[str, ...]
    external_occurrence_ids: tuple[str, ...]

    external_plan_identity_semantics: ExistingPlanCaptureIdentitySemantics
    external_occurrence_identity_semantics: ExistingPlanCaptureIdentitySemantics

    historical_plan_content_verified: bool
    actual_phase_alignment_verified: bool
    numeric_output_authorized: bool
    capability_update_performed: bool
    authoritative_revision_promotion_allowed: bool
    promotion_blockers: tuple[str, ...]

    source_limitations: tuple[str, ...]
    provider_orm_basic_field_differences: tuple[str, ...]

    # Exact lossless boundary copy of the current API/service result.
    source_read_json: str
    source_read_content_hash: str

    content_hash_algorithm: str
    content_hash: str

    def verify_source_read_hash(self) -> bool:
        parsed = json.loads(self.source_read_json)
        return (
            compute_content_hash(parsed, exclude_fields=frozenset())
            == self.source_read_content_hash
        )

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=EXISTING_PLAN_CAPTURE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_existing_workout_plan_capture(
    *,
    api_rules_version: str,
    contract_release: str,
    capture_id: str,
    captured_at: datetime,
    source_workout_id: str,
    athlete_id: str,
    source_kind: str,
    source_content_sha256: str,
    planning_logical_plan_id: str,
    external_contract_plan_id: str,
    external_contract_plan_revision: int,
    external_contract_schema_version: str,
    external_plan_content_hash: str,
    external_contract_snapshot_sha256: str,
    external_adapter_version: str,
    contract_block_ids: tuple[str, ...],
    external_occurrence_ids: tuple[str, ...],
    source_limitations: tuple[str, ...],
    provider_orm_basic_field_differences: tuple[str, ...],
    source_read_json: str,
    source_read_content_hash: str,
) -> ExistingWorkoutPlanCapture:
    for field_name, value in (
        ("api_rules_version", api_rules_version),
        ("contract_release", contract_release),
        ("capture_id", capture_id),
        ("source_workout_id", source_workout_id),
        ("athlete_id", athlete_id),
        ("source_kind", source_kind),
        ("source_content_sha256", source_content_sha256),
        ("planning_logical_plan_id", planning_logical_plan_id),
        ("external_contract_plan_id", external_contract_plan_id),
        ("external_contract_schema_version", external_contract_schema_version),
        ("external_plan_content_hash", external_plan_content_hash),
        ("external_contract_snapshot_sha256", external_contract_snapshot_sha256),
        ("external_adapter_version", external_adapter_version),
        ("source_read_json", source_read_json),
        ("source_read_content_hash", source_read_content_hash),
    ):
        if not value or not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    if external_contract_plan_revision < 1:
        raise ValueError("external_contract_plan_revision must be >= 1.")
    if len(contract_block_ids) != len(set(contract_block_ids)):
        raise ValueError("contract_block_ids must be unique.")
    if len(external_occurrence_ids) != len(set(external_occurrence_ids)):
        raise ValueError("external_occurrence_ids must be unique.")

    captured = to_utc(captured_at, field_name="captured_at")
    canonical_source = canonical_json(json.loads(source_read_json))
    if canonical_source != source_read_json:
        raise ValueError("source_read_json must already be canonical JSON.")
    expected_source_hash = compute_content_hash(
        json.loads(source_read_json),
        exclude_fields=frozenset(),
    )
    if expected_source_hash != source_read_content_hash:
        raise ValueError("source_read_content_hash does not verify.")

    blockers = (
        "STATELESS_READ_CAPTURE_NOT_A_PERSISTED_PLAN_REVISION",
        "HISTORICAL_PLAN_CONTENT_UNVERIFIED",
        "CAPTURE_SCOPED_EXTERNAL_PLAN_ID",
        "CAPTURE_SCOPED_EXTERNAL_OCCURRENCE_IDS",
    )

    provisional = ExistingWorkoutPlanCapture(
        api_rules_version=api_rules_version,
        contract_release=contract_release,
        capture_id=capture_id,
        captured_at=captured,
        source_workout_id=source_workout_id,
        athlete_id=athlete_id,
        source_kind=source_kind,
        source_content_sha256=source_content_sha256,
        planning_logical_plan_id=planning_logical_plan_id,
        external_contract_plan_id=external_contract_plan_id,
        external_contract_plan_revision=external_contract_plan_revision,
        external_contract_schema_version=external_contract_schema_version,
        external_plan_content_hash=external_plan_content_hash,
        external_contract_snapshot_sha256=external_contract_snapshot_sha256,
        external_adapter_version=external_adapter_version,
        contract_block_ids=tuple(contract_block_ids),
        external_occurrence_ids=tuple(external_occurrence_ids),
        external_plan_identity_semantics=(
            ExistingPlanCaptureIdentitySemantics.CAPTURE_SCOPED
        ),
        external_occurrence_identity_semantics=(
            ExistingPlanCaptureIdentitySemantics.CAPTURE_SCOPED
        ),
        historical_plan_content_verified=False,
        actual_phase_alignment_verified=False,
        numeric_output_authorized=False,
        capability_update_performed=False,
        authoritative_revision_promotion_allowed=False,
        promotion_blockers=blockers,
        source_limitations=tuple(source_limitations),
        provider_orm_basic_field_differences=tuple(
            provider_orm_basic_field_differences
        ),
        source_read_json=source_read_json,
        source_read_content_hash=source_read_content_hash,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=EXISTING_PLAN_CAPTURE_HASH_EXCLUDE_FIELDS,
    )
    return ExistingWorkoutPlanCapture(
        **{
            **provisional.__dict__,
            "content_hash": digest,
        }
    )
