from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .enums import SnapshotStatus
from .serialization import (
    CONTENT_HASH_ALGORITHM,
    compute_content_hash,
    deep_freeze,
    to_contract_primitive,
)
from .time import to_utc


SNAPSHOT_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "snapshot_id", "created_at"}
)


@dataclass(frozen=True)
class ImmutableDomainSnapshot:
    snapshot_id: str
    athlete_id: str
    domain_type: str
    schema_version: str
    as_of: datetime
    information_cutoff_at: datetime
    created_at: datetime
    payload: Mapping[str, object]
    status: SnapshotStatus
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=SNAPSHOT_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def create_domain_snapshot(
    *,
    snapshot_id: str,
    athlete_id: str,
    domain_type: str,
    schema_version: str,
    as_of: datetime,
    information_cutoff_at: datetime,
    created_at: datetime,
    payload: Mapping[str, object],
    status: SnapshotStatus = SnapshotStatus.FROZEN,
) -> ImmutableDomainSnapshot:
    for field_name, value in (
        ("snapshot_id", snapshot_id),
        ("athlete_id", athlete_id),
        ("domain_type", domain_type),
        ("schema_version", schema_version),
    ):
        if not value or not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    as_of_utc = to_utc(as_of, field_name="as_of")
    cutoff_utc = to_utc(
        information_cutoff_at,
        field_name="information_cutoff_at",
    )
    created_utc = to_utc(created_at, field_name="created_at")

    if cutoff_utc > as_of_utc:
        raise ValueError(
            "information_cutoff_at must not be after as_of."
        )

    frozen_payload = deep_freeze(payload)
    to_contract_primitive(frozen_payload)

    provisional = ImmutableDomainSnapshot(
        snapshot_id=snapshot_id,
        athlete_id=athlete_id,
        domain_type=domain_type,
        schema_version=schema_version,
        as_of=as_of_utc,
        information_cutoff_at=cutoff_utc,
        created_at=created_utc,
        payload=frozen_payload,
        status=status,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=SNAPSHOT_HASH_EXCLUDE_FIELDS,
    )
    return ImmutableDomainSnapshot(
        snapshot_id=provisional.snapshot_id,
        athlete_id=provisional.athlete_id,
        domain_type=provisional.domain_type,
        schema_version=provisional.schema_version,
        as_of=provisional.as_of,
        information_cutoff_at=provisional.information_cutoff_at,
        created_at=provisional.created_at,
        payload=provisional.payload,
        status=provisional.status,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
