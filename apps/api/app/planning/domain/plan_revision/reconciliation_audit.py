from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

from ..common.serialization import (
    CONTENT_HASH_ALGORITHM,
    canonical_json,
    compute_content_hash,
)
from ..common.time import to_utc
from ..integration.polar_reconciliation import (
    FutureBaselineAdoptionSupport,
    PolarReconciliationStatus,
    PolarSourceReconciliationArtifact,
)
from .persistence_contract import (
    AuthoritativePlanRevision,
    CurrentStateAdoptionBinding,
    PlanRevisionOrigin,
)


POLAR_RECONCILIATION_AUDIT_SCHEMA_VERSION = "0.1"
POLAR_RECONCILIATION_AUDIT_HASH_EXCLUDE_FIELDS = frozenset({"content_hash"})


@dataclass(frozen=True)
class PolarReconciliationAuditRecord:
    audit_schema_version: str
    revision_id: str
    logical_plan_id: str
    athlete_id: str
    source_workout_id: str
    capture_id: str
    reconciliation_schema_version: str
    reconciliation_rules_version: str
    reconciliation_content_hash_algorithm: str
    reconciliation_content_hash: str
    reconciliation_canonical_json: str
    reconciliation_captured_at: datetime
    source_content_sha256: str
    source_read_content_hash: str
    timezone_context_name: str
    timezone_context_source: str
    reconciliation_status: str
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_reconciliation_artifact_hash(self) -> bool:
        parsed = json.loads(self.reconciliation_canonical_json)
        return (
            compute_content_hash(parsed, exclude_fields=frozenset({"content_hash"}))
            == self.reconciliation_content_hash
        )

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=POLAR_RECONCILIATION_AUDIT_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def _validate_hex_sha256(value: str, *, field_name: str) -> None:
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")


def finalize_polar_reconciliation_audit(
    *,
    binding: CurrentStateAdoptionBinding,
    revision: AuthoritativePlanRevision,
    artifact: PolarSourceReconciliationArtifact,
    created_at: datetime,
) -> PolarReconciliationAuditRecord:
    """Bind one verified Polar reconciliation artifact to revision 1.

    The audit is separate from the immutable revision payload so introducing
    this lineage does not change hashes of pre-existing authoritative revisions.
    """
    if revision.origin != PlanRevisionOrigin.ADOPTED_CURRENT_STATE:
        raise ValueError("Polar reconciliation audit only applies to adoption baseline.")
    if revision.revision_number != 1:
        raise ValueError("Polar reconciliation audit requires revision 1.")
    if revision.revision_id != binding.adopted_revision_id:
        raise ValueError("Audit binding revision does not match adoption binding.")
    if revision.logical_plan_id != binding.logical_plan_id:
        raise ValueError("Audit logical plan does not match adoption binding.")
    if revision.adoption_source is None:
        raise ValueError("Polar reconciliation audit requires adoption source provenance.")
    if not artifact.verify_content_hash():
        raise ValueError("Polar reconciliation artifact content hash does not verify.")
    if artifact.status != PolarReconciliationStatus.SYNC_PROJECTION_MATCH:
        raise ValueError("Only sync-projection matches may authorize Polar adoption.")
    if (
        artifact.future_baseline_adoption_support
        != FutureBaselineAdoptionSupport.SUPPORTED_BY_RECONCILIATION
        or artifact.current_orm_edit_detected is not False
        or artifact.provider_snapshot_selected_as_future_authority_candidate is not True
        or artifact.blockers
    ):
        raise ValueError("Polar reconciliation artifact does not support baseline adoption.")

    source = revision.adoption_source
    exact_binding = (
        artifact.capture_id == source.capture_id
        and artifact.logical_plan_id == revision.logical_plan_id
        and artifact.athlete_id == revision.athlete_id
        and artifact.source_workout_id == binding.source_workout_id
        and artifact.source_content_sha256 == source.source_content_sha256
        and artifact.source_content_sha256 == binding.expected_source_content_sha256
        and artifact.source_read_content_hash == source.source_read_content_hash
        and artifact.external_contract_plan_id == source.external_contract_plan_id
        and artifact.external_contract_plan_revision
        == source.external_contract_plan_revision
    )
    if not exact_binding:
        raise ValueError("Polar reconciliation artifact is stale or bound to another source.")
    if not artifact.timezone_context_name or not artifact.timezone_context_source:
        raise ValueError("Polar reconciliation audit requires explicit timezone context.")

    _validate_hex_sha256(
        artifact.content_hash,
        field_name="reconciliation_content_hash",
    )
    _validate_hex_sha256(
        artifact.source_content_sha256,
        field_name="source_content_sha256",
    )
    _validate_hex_sha256(
        artifact.source_read_content_hash,
        field_name="source_read_content_hash",
    )

    created = to_utc(created_at, field_name="created_at")
    captured = to_utc(artifact.captured_at, field_name="reconciliation_captured_at")
    reconciliation_json = canonical_json(artifact)

    provisional = PolarReconciliationAuditRecord(
        audit_schema_version=POLAR_RECONCILIATION_AUDIT_SCHEMA_VERSION,
        revision_id=revision.revision_id,
        logical_plan_id=revision.logical_plan_id,
        athlete_id=revision.athlete_id,
        source_workout_id=binding.source_workout_id,
        capture_id=artifact.capture_id,
        reconciliation_schema_version=artifact.schema_version,
        reconciliation_rules_version=artifact.rules_version,
        reconciliation_content_hash_algorithm=artifact.content_hash_algorithm,
        reconciliation_content_hash=artifact.content_hash,
        reconciliation_canonical_json=reconciliation_json,
        reconciliation_captured_at=captured,
        source_content_sha256=artifact.source_content_sha256,
        source_read_content_hash=artifact.source_read_content_hash,
        timezone_context_name=artifact.timezone_context_name,
        timezone_context_source=artifact.timezone_context_source,
        reconciliation_status=artifact.status.value,
        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    return PolarReconciliationAuditRecord(
        **{
            **provisional.__dict__,
            "content_hash": compute_content_hash(
                provisional,
                exclude_fields=POLAR_RECONCILIATION_AUDIT_HASH_EXCLUDE_FIELDS,
            ),
        }
    )


def load_polar_reconciliation_audit_record(
    *,
    audit_schema_version: str,
    revision_id: str,
    logical_plan_id: str,
    athlete_id: str,
    source_workout_id: str,
    capture_id: str,
    reconciliation_schema_version: str,
    reconciliation_rules_version: str,
    reconciliation_content_hash_algorithm: str,
    reconciliation_content_hash: str,
    reconciliation_canonical_json: str,
    reconciliation_captured_at: datetime,
    source_content_sha256: str,
    source_read_content_hash: str,
    timezone_context_name: str,
    timezone_context_source: str,
    reconciliation_status: str,
    created_at: datetime,
    content_hash_algorithm: str,
    content_hash: str,
) -> PolarReconciliationAuditRecord:
    record = PolarReconciliationAuditRecord(
        audit_schema_version=audit_schema_version,
        revision_id=revision_id,
        logical_plan_id=logical_plan_id,
        athlete_id=athlete_id,
        source_workout_id=source_workout_id,
        capture_id=capture_id,
        reconciliation_schema_version=reconciliation_schema_version,
        reconciliation_rules_version=reconciliation_rules_version,
        reconciliation_content_hash_algorithm=reconciliation_content_hash_algorithm,
        reconciliation_content_hash=reconciliation_content_hash,
        reconciliation_canonical_json=canonical_json(json.loads(reconciliation_canonical_json)),
        reconciliation_captured_at=to_utc(
            reconciliation_captured_at,
            field_name="reconciliation_captured_at",
        ),
        source_content_sha256=source_content_sha256,
        source_read_content_hash=source_read_content_hash,
        timezone_context_name=timezone_context_name,
        timezone_context_source=timezone_context_source,
        reconciliation_status=reconciliation_status,
        created_at=to_utc(created_at, field_name="created_at"),
        content_hash_algorithm=content_hash_algorithm,
        content_hash=content_hash,
    )
    if record.reconciliation_status != PolarReconciliationStatus.SYNC_PROJECTION_MATCH.value:
        raise ValueError("Stored Polar reconciliation audit has unsupported status.")
    if not record.verify_reconciliation_artifact_hash():
        raise ValueError("Stored reconciliation artifact hash does not verify.")
    if not record.verify_content_hash():
        raise ValueError("Stored reconciliation audit record hash does not verify.")
    return record
