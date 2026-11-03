"""Owned, revisioned training opportunities with idempotent, explicit saves."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.planning.application import register_athlete_setup as transactions
from app.planning.domain import training_options as domain
from app.planning.domain.athlete_setup import digest
from app.planning.domain.calendar_constraints import require
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.training_options import OptionsInput

SCHEMA = "training-options-v0.1"
KIND = AuditArtifactKind.TRAINING_OPTIONS


def _now():
    return datetime.now(UTC)


def identity(owner, token):
    return "pt-training-options:" + UUID(owner).hex + ":" + UUID(token).hex


def reference(artifact):
    return {"artifact_id": artifact["artifact_id"], "content_hash": artifact["content_hash"]}


def decode(record, owner):
    value = json.loads(record.contract_json)
    normalized = OptionsInput.model_validate(value["proposal"]).model_dump(mode="json")
    require(record.athlete_id == owner == value["athlete_id"] and record.artifact_kind == KIND
        and record.schema_version == value["schema_version"] == SCHEMA
        and record.artifact_id == value["artifact_id"] == identity(owner, normalized["request_id"])
        and value["proposal"] == normalized and record.contract_json == canonical_json(value)
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == value["content_hash"] == digest({k: v for k, v in value.items() if k != "content_hash"})
        and record.created_at == datetime.fromisoformat(value["created_at"])
        and record.created_at.tzinfo is not None and record.persisted_at is not None
        and record.persisted_at.tzinfo is not None and type(value["revision"]) is int and value["revision"] >= 1
        and (value["revision"] == 1) == (normalized["previous_reference"] is None)
        and value["workouts_changed"] is False and value["planning_authorized"] is False,
        "TRAINING_OPTIONS_STORAGE_INVALID")
    return value


async def load(repo, owner, key):
    record = await repo.get(artifact_kind=KIND, artifact_id=key)
    require(record is not None and record.athlete_id == owner, "TRAINING_OPTIONS_NOT_FOUND")
    artifact = decode(record, owner)
    parent_ref = artifact["proposal"]["previous_reference"]
    if parent_ref:
        parent = await repo.get(artifact_kind=KIND, artifact_id=parent_ref["artifact_id"])
        require(parent is not None and parent.athlete_id == owner, "TRAINING_OPTIONS_STORAGE_INVALID")
        previous = decode(parent, owner)
        require(reference(previous) == parent_ref and previous["revision"] + 1 == artifact["revision"]
            and previous["created_at"] < artifact["created_at"], "TRAINING_OPTIONS_STORAGE_INVALID")
    return artifact, record


async def latest(repo, session, owner):
    key = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(1))).scalar_one_or_none()
    return await load(repo, owner, key) if key else None


def receipt(artifact, record, reused):
    return {"identity_scope": "APPLICATION_DEMO_USER", "artifact": artifact, "committed": True, "reused": reused,
        "durable_available_at": record.persisted_at.isoformat(), "planning_authorized": False, "workouts_changed": False}


async def save(*, session, owner, proposal):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        user = await transactions.lock_owner(session, owner)
        proposal = OptionsInput.model_validate(proposal).model_dump(mode="json")
        key = identity(owner, proposal["request_id"])
        found = await repo.get(artifact_kind=KIND, artifact_id=key)
        if found:
            value, stored = await load(repo, owner, key)
            require(value["proposal"] == proposal, "TRAINING_OPTIONS_REQUEST_CONFLICT")
            return receipt(value, stored, True)
        current = await latest(repo, session, owner)
        parent = current[0] if current else None
        require(proposal["previous_reference"] == (reference(parent) if parent else None), "TRAINING_OPTIONS_REVISION_CONFLICT")
        require(proposal["data"]["timezone_name"] == user.timezone, "TRAINING_OPTIONS_TIMEZONE_CHANGED")
        # Resolve dated exceptions now; impossible or ambiguous civil times are not guessed.
        for item in proposal["data"]["exceptions"]:
            if item["replacement"] is not None:
                from app.planning.domain.athlete_setup import local_instant
                details = item["replacement"]
                day = domain.calendar.calendar_day(item["date"])
                a = local_instant(item["date"], details["start_time"], user.timezone, details["start_fold"])
                b = local_instant((day + timedelta(days=int(details["ends_next_day"]))).isoformat(), details["end_time"], user.timezone, details["end_fold"])
                require(0 < (b - a).total_seconds() / 60 <= 1500 and details["max_minutes"] <= (b - a).total_seconds() / 60, "TRAINING_OPTIONS_TIME_WINDOW_INVALID")
        created = _now()
        if parent:
            created = max(created, datetime.fromisoformat(parent["created_at"]) + timedelta(microseconds=1))
        value = {"schema_version": SCHEMA, "artifact_id": key, "athlete_id": owner, "created_at": created.isoformat(),
            "revision": parent["revision"] + 1 if parent else 1, "proposal": proposal, "planning_authorized": False, "workouts_changed": False}
        value["content_hash"] = digest(value)
        result = await repo.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner, schema_version=SCHEMA,
            created_at=created, content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=value["content_hash"], contract_json=canonical_json(value)))
        require(result.status == AuditArtifactSaveStatus.CREATED, "TRAINING_OPTIONS_STORAGE_INVALID")
        verified, stored = await load(repo, owner, key)
        require(verified == value, "TRAINING_OPTIONS_STORAGE_INVALID")
        await transactions.commit(session)
        return receipt(verified, stored, False)
    finally:
        await transactions.rollback(session)


async def context(*, session, owner, first=None, last=None):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        from app.models.entities import User
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        today = _now().astimezone(ZoneInfo(user.timezone)).date()
        first, last = first or today.isoformat(), last or (today + timedelta(days=6)).isoformat()
        domain.calendar.bounded_range(first, last)
        current = await latest(repo, session, owner)
        data = current[0]["proposal"]["data"] if current else domain.empty(user.timezone)
        projection = domain.expand(data, first, last, user.timezone)
        return {"schema_version": SCHEMA, "athlete_id": owner, "timezone_name": user.timezone, "local_today": today.isoformat(),
            "start_date": first, "end_date": last, "data": data, "saved": receipt(*current, True) if current else None,
            "reference": reference(current[0]) if current else None, "groups": projection["groups"],
            "override_days": projection["override_days"],
            "timezone_review_required": data["timezone_name"] != user.timezone, "workouts_changed": False, "planning_authorized": False}
    finally:
        await transactions.rollback(session)
