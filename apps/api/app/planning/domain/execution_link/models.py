from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from ..common.serialization import canonical_json


CONTENT_HASH_ALGORITHM = "sha256"
LINK_SCHEMA_VERSION = "authoritative-plan-execution-link-v0.1"


class ExecutionLinkBasis(StrEnum):
    EXACT_PROVIDER_ID = "exact_provider_id"
    MANUAL_CONFIRMED = "manual_confirmed"


class AuthoritativeExecutionLinkNotEligible(ValueError):
    pass


class AuthoritativeExecutionLinkConflictError(RuntimeError):
    pass


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be offset-aware.")
    return value.astimezone(timezone.utc)


def _uuid_text(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be a UUID string."
        ) from exc


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _require_sha256(value: str, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(
            f"{field_name} must be a lowercase SHA-256 hex digest."
        )
    return value


def snapshot_content_hash(snapshot: dict) -> str:
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a dict.")
    return _sha256(canonical_json(snapshot))


def resolve_execution_link_basis(
    *,
    session_snapshot: dict,
    source_workout_snapshot: dict,
) -> tuple[ExecutionLinkBasis, str | None]:
    """Resolve only explicit execution-to-plan identity evidence.

    Clock proximity is deliberately not inspected here.
    """
    if not isinstance(session_snapshot, dict):
        raise AuthoritativeExecutionLinkNotEligible(
            "Execution session snapshot is unavailable."
        )
    if not isinstance(source_workout_snapshot, dict):
        raise AuthoritativeExecutionLinkNotEligible(
            "Source workout snapshot is unavailable."
        )

    athlete_id = str(session_snapshot.get("user_id") or "")
    source_athlete_id = str(
        source_workout_snapshot.get("user_id") or ""
    )
    if not athlete_id or athlete_id != source_athlete_id:
        raise AuthoritativeExecutionLinkNotEligible(
            "Execution and planned workout athlete differ."
        )

    source_workout_id = str(
        source_workout_snapshot.get("id") or ""
    )
    if not source_workout_id:
        raise AuthoritativeExecutionLinkNotEligible(
            "Source workout identity is missing."
        )

    stored_plan_id = session_snapshot.get("planned_workout_id")
    if (
        stored_plan_id is not None
        and str(stored_plan_id) != source_workout_id
    ):
        raise AuthoritativeExecutionLinkNotEligible(
            "Stored execution link points to another workout."
        )

    if (
        session_snapshot.get("sport")
        != source_workout_snapshot.get("sport")
    ):
        raise AuthoritativeExecutionLinkNotEligible(
            "Execution and planned workout sport differ."
        )

    raw = session_snapshot.get("raw_data")
    raw = raw if isinstance(raw, dict) else {}

    training_target = raw.get("trainingTarget")
    training_target = (
        training_target
        if isinstance(training_target, dict)
        else {}
    )
    raw_target_id = training_target.get("id")
    raw_target_id = (
        None
        if raw_target_id in (None, "")
        else str(raw_target_id)
    )

    source_target_id = source_workout_snapshot.get(
        "polar_target_id"
    )
    source_target_id = (
        None
        if source_target_id in (None, "")
        else str(source_target_id)
    )

    polar_pair = (
        session_snapshot.get("external_provider") == "POLAR"
        and source_workout_snapshot.get("source") == "POLAR"
    )

    if (
        polar_pair
        and raw_target_id is not None
        and source_target_id is not None
    ):
        if raw_target_id != source_target_id:
            raise AuthoritativeExecutionLinkNotEligible(
                "Provider target identity conflicts with "
                "the authoritative plan source."
            )
        return (
            ExecutionLinkBasis.EXACT_PROVIDER_ID,
            raw_target_id,
        )

    if (
        stored_plan_id is not None
        and str(stored_plan_id) == source_workout_id
        and session_snapshot.get("planned_workout_link_source")
        == "MANUAL_CONFIRMED"
    ):
        return ExecutionLinkBasis.MANUAL_CONFIRMED, None

    raise AuthoritativeExecutionLinkNotEligible(
        "Execution has no exact provider identity or explicit "
        "manual confirmation for this plan."
    )


@dataclass(frozen=True)
class AuthoritativePlanExecutionLink:
    link_id: str
    schema_version: str
    athlete_id: str
    logical_plan_id: str
    observed_revision_id: str
    workout_session_id: str
    source_workout_id: str
    link_basis: ExecutionLinkBasis
    provider_target_id: str | None
    source_workout_content_hash: str
    session_source_content_hash: str
    observed_revision_content_hash: str
    plan_content_at_execution_status: str
    temporal_match_used: bool
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return _link_content_hash(self) == self.content_hash


def _link_payload(
    link: AuthoritativePlanExecutionLink,
) -> dict:
    return {
        "link_id": link.link_id,
        "schema_version": link.schema_version,
        "athlete_id": link.athlete_id,
        "logical_plan_id": link.logical_plan_id,
        "observed_revision_id": link.observed_revision_id,
        "workout_session_id": link.workout_session_id,
        "source_workout_id": link.source_workout_id,
        "link_basis": link.link_basis.value,
        "provider_target_id": link.provider_target_id,
        "source_workout_content_hash":
            link.source_workout_content_hash,
        "session_source_content_hash":
            link.session_source_content_hash,
        "observed_revision_content_hash":
            link.observed_revision_content_hash,
        "plan_content_at_execution_status":
            link.plan_content_at_execution_status,
        "temporal_match_used": link.temporal_match_used,
        "created_at": link.created_at.isoformat(),
        "content_hash_algorithm": link.content_hash_algorithm,
    }


def _link_content_hash(
    link: AuthoritativePlanExecutionLink,
) -> str:
    return _sha256(canonical_json(_link_payload(link)))


def finalize_authoritative_plan_execution_link(
    *,
    link_id: str,
    athlete_id: str,
    logical_plan_id: str,
    observed_revision_id: str,
    workout_session_id: str,
    source_workout_id: str,
    link_basis: ExecutionLinkBasis,
    provider_target_id: str | None,
    source_workout_content_hash: str,
    session_source_content_hash: str,
    observed_revision_content_hash: str,
    created_at: datetime,
) -> AuthoritativePlanExecutionLink:
    if not link_id.startswith("pt-exec-link:"):
        raise ValueError(
            "link_id must use pt-exec-link: namespace."
        )
    if not logical_plan_id.strip():
        raise ValueError("logical_plan_id must be non-empty.")
    if not observed_revision_id.startswith("pt-plan-rev:"):
        raise ValueError(
            "observed_revision_id must use pt-plan-rev: namespace."
        )

    athlete_id = _uuid_text(
        athlete_id,
        field_name="athlete_id",
    )
    workout_session_id = _uuid_text(
        workout_session_id,
        field_name="workout_session_id",
    )
    source_workout_id = _uuid_text(
        source_workout_id,
        field_name="source_workout_id",
    )

    if link_basis == ExecutionLinkBasis.EXACT_PROVIDER_ID:
        if provider_target_id is None or not provider_target_id.strip():
            raise ValueError(
                "Exact provider link requires provider_target_id."
            )
        provider_target_id = provider_target_id.strip()
    elif link_basis == ExecutionLinkBasis.MANUAL_CONFIRMED:
        if provider_target_id is not None:
            raise ValueError(
                "Manual-confirmed link cannot claim provider target proof."
            )
    else:
        raise ValueError("Unsupported execution link basis.")

    source_workout_content_hash = _require_sha256(
        source_workout_content_hash,
        field_name="source_workout_content_hash",
    )
    session_source_content_hash = _require_sha256(
        session_source_content_hash,
        field_name="session_source_content_hash",
    )
    observed_revision_content_hash = _require_sha256(
        observed_revision_content_hash,
        field_name="observed_revision_content_hash",
    )

    provisional = AuthoritativePlanExecutionLink(
        link_id=link_id,
        schema_version=LINK_SCHEMA_VERSION,
        athlete_id=athlete_id,
        logical_plan_id=logical_plan_id,
        observed_revision_id=observed_revision_id,
        workout_session_id=workout_session_id,
        source_workout_id=source_workout_id,
        link_basis=link_basis,
        provider_target_id=provider_target_id,
        source_workout_content_hash=source_workout_content_hash,
        session_source_content_hash=session_source_content_hash,
        observed_revision_content_hash=
            observed_revision_content_hash,
        # This link proves plan identity, not historical plan content.
        plan_content_at_execution_status="unverified",
        # Time proximity is explicitly excluded from link establishment.
        temporal_match_used=False,
        created_at=_utc(created_at, field_name="created_at"),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )

    return AuthoritativePlanExecutionLink(
        **{
            **provisional.__dict__,
            "content_hash": _link_content_hash(provisional),
        }
    )
