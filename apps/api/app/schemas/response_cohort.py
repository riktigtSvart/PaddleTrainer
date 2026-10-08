"""V24.10-A: pinned request structure; no source, chronology or training proof."""

import hashlib
import json
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.response_dataset import DatasetSplitManifest
from app.services.response_dataset_split import validate_split_manifest

MAX_COHORT_MEMBERS = 100


def _trimmed(value: str) -> str:
    if value != value.strip() or not value.strip():
        raise ValueError("Identifier must be nonempty and trimmed")
    return value


Identifier = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_trimmed)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CanonicalUuid = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]


class ResponseCohortMember(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    provider: Literal["POLAR"]
    athlete_id: Identifier
    session_external_id: Identifier
    route_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    replay_snapshot_id: CanonicalUuid
    expected_snapshot_hash: Sha256
    expected_evidence_set_id: CanonicalUuid
    expected_evidence_hash: Sha256
    expected_unassigned_replay_package_hash: Sha256
    expected_dataset_version: Literal["0.1.0"] = "0.1.0"
    expected_snapshot_schema_version: Literal["0.1"] = "0.1"

    @field_validator("route_date")
    @classmethod
    def valid_replay_query_date(cls, value: str) -> str:
        parsed = date.fromisoformat(value)
        if parsed == date.max:
            raise ValueError("route_date cannot be the maximum date")
        return value


class ResponseCohortManifest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["0.1"]
    manifest_id: Identifier
    task: Literal["RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE"] = (
        "RETROSPECTIVE_HR_RESPONSE_WITHIN_ATHLETE"
    )
    members: list[ResponseCohortMember] = Field(min_length=1, max_length=MAX_COHORT_MEMBERS)
    split_manifest: DatasetSplitManifest | None = None

    @model_validator(mode="after")
    def validate_selected_groups(self) -> Self:
        if len({member.athlete_id for member in self.members}) != 1:
            raise ValueError("Cohort contract supports one athlete only")
        groups = {
            (member.provider, member.athlete_id, member.session_external_id)
            for member in self.members
        }
        if len(groups) != len(self.members):
            raise ValueError("Duplicate session group in cohort")
        if len({member.replay_snapshot_id for member in self.members}) != len(self.members):
            raise ValueError("One replay snapshot cannot select different sessions")
        if self.split_manifest is not None:
            for entry in self.split_manifest.assignments:
                if (entry.provider, entry.athlete_id, entry.session_external_id) not in groups:
                    raise ValueError("Split assignment selects a session outside this cohort")
        return self

    def canonical_payload(self) -> dict:
        """Normalize request defaults and membership order, not observation chronology."""
        payload = self.model_dump(mode="json")
        payload["members"].sort(
            key=lambda member: (
                member["provider"],
                member["athlete_id"],
                member["session_external_id"],
            )
        )
        if payload["split_manifest"] is not None:
            payload["split_manifest"] = validate_split_manifest(payload["split_manifest"])
        return payload

    def request_manifest_hash(self) -> str:
        """Commit the normalized request; this is never a cohort-evidence hash."""
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
