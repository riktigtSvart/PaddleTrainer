"""Owner-locked append-only intake/calendar revisions and explicit Polar history imports."""

import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.security import decrypt_secret, encrypt_secret
from app.integrations.polar.client import PolarClient
from app.models.entities import (
    ExternalConnection,
    PeriodType,
    ProviderDataRecord,
    TrainingPeriod,
    User,
)
from app.planning.domain import athlete_setup as domain
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from app.planning.infrastructure.adapters.athlete_history import aware, historical_candidates
from app.schemas.athlete_setup import AvailabilityInput, PolarImportInput, ProfileInput

KINDS = {
    "profile": AuditArtifactKind.ATHLETE_PROFILE,
    "availability": AuditArtifactKind.ATHLETE_AVAILABILITY,
    "polar_import": AuditArtifactKind.ATHLETE_POLAR_IMPORT,
}
INPUTS = {
    "profile": ProfileInput,
    "availability": AvailabilityInput,
    "polar_import": PolarImportInput,
}
SCOPES = {
    "sessions": "training_sessions:read",
    "sleep": "sleep:read",
    "nightly_recharge": "nightly_recharge:read",
    "continuous_hr": "continuous_samples:read",
    "activity": "activity:read",
    "tests": "tests:read",
}


def _now():
    return datetime.now(UTC)


class SetupNotFound(LookupError):
    pass


class SetupStorageError(RuntimeError):
    pass


def _require_session(repository, session):
    if session is None or getattr(repository, "session", None) is not session:
        raise SetupStorageError("Athlete registration requires the exact audit repository session.")
    inspect = getattr(session, "in_transaction", None)
    if not callable(inspect) or inspect() is not False:
        raise SetupStorageError("Athlete registration requires a known fresh session.")


async def rollback(session):
    await session.rollback()
    if session.in_transaction() is not False:
        raise SetupStorageError("Athlete transaction did not close.")


async def commit(session):
    await session.commit()
    if session.in_transaction() is not False:
        raise SetupStorageError("Athlete commit did not close.")


async def lock_owner(session, owner):
    result = await session.execute(select(User).where(User.id == UUID(owner)).with_for_update())
    user = result.scalar_one_or_none()
    if user is None:
        raise SetupNotFound("ATHLETE_OWNER_NOT_FOUND")
    return user


def decode(record, *, owner, kind):
    artifact = json.loads(record.contract_json)
    raw = {k: v for k, v in artifact.items() if k != "content_hash"}
    if not (
        record.athlete_id == owner
        and artifact["athlete_id"] == owner
        and artifact["kind"] == kind
        and artifact["schema_version"] == domain.SCHEMA
        and record.schema_version == domain.SCHEMA
        and record.artifact_kind == KINDS[kind]
        and record.artifact_id == artifact["artifact_id"]
        and domain.identity(owner, kind, artifact["proposal"]["request_id"])
        == artifact["artifact_id"]
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == artifact["content_hash"] == domain.digest(raw)
        and record.created_at == datetime.fromisoformat(artifact["created_at"])
        and record.persisted_at is not None
        and record.persisted_at.tzinfo is not None
        and canonical_json(artifact) == record.contract_json
        and artifact["planning_authorized"] is False
        and artifact["workouts_created"] is False
        and INPUTS[kind].model_validate(artifact["proposal"]).model_dump() == artifact["proposal"]
    ):
        raise SetupStorageError("Athlete artifact metadata differs.")
    if kind != "polar_import":
        previous = artifact["proposal"]["previous_reference"]
        if (artifact["revision"] == 1) != (previous is None):
            raise SetupStorageError("Athlete revision chain differs.")
        stub = {"revision": artifact["revision"] - 1} if previous else None
        replay = domain.make_artifact(
            owner=owner,
            kind=kind,
            proposal=artifact["proposal"],
            created_at=artifact["created_at"],
            timezone_name=artifact["timezone_name"],
            previous=stub,
            observations=artifact.get("imported_observations"),
        )
        if replay != artifact:
            raise SetupStorageError("Athlete artifact replay differs.")
    return artifact


async def load(repository, owner, kind, identity):
    record = await repository.get(artifact_kind=KINDS[kind], artifact_id=identity)
    if record is None or record.athlete_id != owner:
        raise SetupNotFound("ATHLETE_RECORD_NOT_FOUND")
    artifact = decode(record, owner=owner, kind=kind)
    if kind in {"profile", "availability"} and artifact["proposal"]["previous_reference"]:
        ref = artifact["proposal"]["previous_reference"]
        parent = await repository.get(artifact_kind=KINDS[kind], artifact_id=ref["artifact_id"])
        if parent is None or parent.athlete_id != owner:
            raise SetupStorageError("Athlete revision parent is unavailable.")
        previous = decode(parent, owner=owner, kind=kind)
        if (
            domain.reference(previous) != ref
            or previous["revision"] + 1 != artifact["revision"]
            or previous["created_at"] >= artifact["created_at"]
        ):
            raise SetupStorageError("Athlete revision parent differs.")
    if kind == "polar_import":
        row = (
            await repository.session.execute(
                select(ProviderDataRecord).where(
                    ProviderDataRecord.id == UUID(artifact["provider_record_id"]),
                    ProviderDataRecord.user_id == UUID(owner),
                    ProviderDataRecord.provider == "POLAR",
                    ProviderDataRecord.data_type
                    == "ATHLETE_INTAKE_" + artifact["proposal"]["domain"].upper(),
                )
            )
        ).scalar_one_or_none()
        if (
            row is None
            or domain.digest(row.raw_data) != artifact["raw_content_hash"]
            or aware(row.fetched_at).isoformat() != artifact["fetched_at"]
        ):
            raise SetupStorageError("The imported raw evidence is unavailable or changed.")
    return artifact, record


async def latest(repository, session, owner, kind):
    from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow

    result = await session.execute(
        select(PlanningAuditArtifactRow.artifact_id)
        .where(
            PlanningAuditArtifactRow.athlete_id == UUID(owner),
            PlanningAuditArtifactRow.artifact_kind == KINDS[kind].value,
        )
        .order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id)
        .limit(1)
    )
    identity = result.scalar_one_or_none()
    return None if identity is None else await load(repository, owner, kind, identity)


def receipt(artifact, record, reused):
    return {
        "identity_scope": "APPLICATION_DEMO_USER",
        "artifact": artifact,
        "durable_available_at": record.persisted_at.isoformat(),
        "committed": True,
        "reused": reused,
        "planning_authorized": False,
        "workouts_created": False,
    }


async def persist(repository, session, artifact, kind):
    record = AuditArtifactRecord(
        artifact_kind=KINDS[kind],
        artifact_id=artifact["artifact_id"],
        athlete_id=artifact["athlete_id"],
        schema_version=domain.SCHEMA,
        created_at=datetime.fromisoformat(artifact["created_at"]),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=artifact["content_hash"],
        contract_json=canonical_json(artifact),
    )
    saved = await repository.save(record)
    if (
        saved.status != AuditArtifactSaveStatus.CREATED
        or saved.content_hash != artifact["content_hash"]
    ):
        raise SetupStorageError("Athlete insertion was not confirmed.")
    verified, stored = await load(repository, artifact["athlete_id"], kind, artifact["artifact_id"])
    if verified != artifact:
        raise SetupStorageError("Athlete read-back differs.")
    await commit(session)
    return receipt(verified, stored, False)


async def resolve_sources(session, owner, data, previous, timezone_name):
    known = {o["artifact_id"]: o for o in (previous or {}).get("imported_observations", [])}
    need = [r for r in data["source_selections"] if r["artifact_id"] not in known]
    if need:
        domain.require(data["source_window"] is not None, "ATHLETE_SOURCE_WINDOW_REQUIRED")
        window = data["source_window"]
        candidates = await historical_candidates(
            session,
            owner,
            first=window["start_date"],
            last=window["end_date"],
            timezone_name=timezone_name,
        )
        known.update({c["artifact_id"]: c for c in candidates})
    selected = []
    for ref in data["source_selections"]:
        value = known.get(ref["artifact_id"])
        domain.require(
            value is not None and domain.reference(value) == ref,
            "ATHLETE_SOURCE_CHANGED_OR_NOT_FOUND",
        )
        selected.append(value)
    # Alternative devices / repeated imports must be chosen explicitly, never summed.
    logical = [o["logical_key"] for o in selected]
    domain.require(len(set(logical)) == len(logical), "ATHLETE_SOURCE_DUPLICATE_CHOOSE_ONE")
    for manual in data["manual_observations"]:
        if manual["supersedes_candidate_id"]:
            target = next(
                o for o in selected if o["artifact_id"] == manual["supersedes_candidate_id"]
            )
            domain.require(
                target["metric"] == manual["metric"]
                and target["aggregation"] == manual["aggregation"]
                and target["start_date"] == manual["start_date"]
                and target["end_date"] == manual["end_date"],
                "ATHLETE_CORRECTION_MEASURE_DIFFERS",
            )
    return selected


async def save(*, owner, kind, proposal, repository, session):
    _require_session(repository, session)
    domain.require(kind in {"profile", "availability"}, "ATHLETE_KIND_INVALID")
    try:
        user = await lock_owner(session, owner)
        identity = domain.identity(owner, kind, proposal["request_id"])
        found = await repository.get(artifact_kind=KINDS[kind], artifact_id=identity)
        if found is not None:
            artifact, record = await load(repository, owner, kind, identity)
            domain.require(artifact["proposal"] == proposal, "ATHLETE_REQUEST_IDENTITY_CONFLICT")
            await rollback(session)
            return receipt(artifact, record, True)
        current = await latest(repository, session, owner, kind)
        previous = current[0] if current else None
        domain.require(
            proposal["previous_reference"] == (domain.reference(previous) if previous else None),
            "ATHLETE_REVISION_CONFLICT_RELOAD",
        )
        data, observations = proposal["data"], None
        if kind == "profile":
            observations = await resolve_sources(session, owner, data, previous, user.timezone)
        elif data["mesocycle_id"]:
            result = await session.execute(
                select(TrainingPeriod).where(
                    TrainingPeriod.id == UUID(data["mesocycle_id"]),
                    TrainingPeriod.user_id == UUID(owner),
                    TrainingPeriod.period_type == PeriodType.MESOCYCLE,
                )
            )
            period = result.scalar_one_or_none()
            if period is None:
                raise SetupNotFound("ATHLETE_MESOCYCLE_NOT_FOUND")
            domain.require(
                period.start_date.isoformat() == data["start_date"]
                and period.end_date.isoformat() == data["end_date"],
                "ATHLETE_MESOCYCLE_DATES_CHANGED",
            )
        created = _now()
        if previous:
            created = max(
                created, datetime.fromisoformat(previous["created_at"]) + timedelta(microseconds=1)
            )
        artifact = domain.make_artifact(
            owner=owner,
            kind=kind,
            proposal=proposal,
            created_at=created.isoformat(),
            timezone_name=user.timezone,
            previous=previous,
            observations=observations,
        )
        return await persist(repository, session, artifact, kind)
    except BaseException:
        await rollback(session)
        raise


async def get_context(*, owner, repository, session, start=None, end=None):
    _require_session(repository, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        today = _now().astimezone(ZoneInfo(user.timezone)).date().isoformat()
        profile = await latest(repository, session, owner, "profile")
        calendar = await latest(repository, session, owner, "availability")
        result = {
            "schema_version": domain.SCHEMA,
            "athlete_id": owner,
            "timezone_name": user.timezone,
            "local_today": today,
            "profile": receipt(*profile, True) if profile else None,
            "availability": receipt(*calendar, True) if calendar else None,
            "current_review": domain.review_profile(profile[0]["proposal"]["data"], today)
            if profile
            else None,
            "planning_authorized": False,
            "workouts_created": False,
        }
        if start is not None:
            result["calendar_context"] = domain.calendar_context(
                calendar[0] if calendar else None, start=start, end=end
            )
        result["references"] = {
            "profile_reference": domain.reference(profile[0]) if profile else None,
            "availability_reference": domain.reference(calendar[0]) if calendar else None,
        }
        connection = (
            await session.execute(
                select(ExternalConnection).where(
                    ExternalConnection.user_id == UUID(owner),
                    ExternalConnection.provider == "POLAR",
                )
            )
        ).scalar_one_or_none()
        result["polar"] = {
            "connected": connection is not None,
            "domains": {
                key: connection is not None and scope in (connection.scopes or [])
                for key, scope in SCOPES.items()
            },
            "source_documentation": "https://www.polar.com/polar-api-v4/",
        }
        return result
    finally:
        await rollback(session)


async def pin_context(repository, session, owner, requested):
    """Validate exact owned references. Save may declare goals, never authorize a dose."""
    result = {}
    for kind in ("profile", "availability"):
        ref = requested[kind + "_reference"]
        if ref is None:
            result[kind] = None
            continue
        artifact, _ = await load(repository, owner, kind, ref["artifact_id"])
        domain.require(domain.reference(artifact) == ref, "ATHLETE_REFERENCE_DIFFERS")
        head = await latest(repository, session, owner, kind)
        domain.require(
            head is not None and domain.reference(head[0]) == ref,
            "ATHLETE_CONTEXT_CHANGED_REVIEW_AGAIN",
        )
        result[kind] = artifact
    domain.require(result["profile"] is not None, "ATHLETE_PROFILE_REQUIRED")
    return result


async def polar_import(*, owner, proposal, repository, session):
    """One domain and one day per request: bounded network work and exact resumable retry."""
    _require_session(repository, session)
    try:
        user = await lock_owner(session, owner)
        identity = domain.identity(owner, "polar_import", proposal["request_id"])
        found = await repository.get(artifact_kind=KINDS["polar_import"], artifact_id=identity)
        if found is not None:
            artifact, record = await load(repository, owner, "polar_import", identity)
            domain.require(artifact["proposal"] == proposal, "ATHLETE_REQUEST_IDENTITY_CONFLICT")
            await rollback(session)
            return receipt(artifact, record, True)
        day, category = date.fromisoformat(proposal["day"]), proposal["domain"]
        now = _now()
        domain.require(
            day <= now.astimezone(ZoneInfo(user.timezone)).date(), "ATHLETE_IMPORT_DAY_IN_FUTURE"
        )
        connection = (
            await session.execute(
                select(ExternalConnection)
                .where(
                    ExternalConnection.user_id == UUID(owner),
                    ExternalConnection.provider == "POLAR",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        domain.require(connection is not None, "ATHLETE_POLAR_NOT_CONNECTED")
        domain.require(SCOPES[category] in connection.scopes, "ATHLETE_POLAR_SCOPE_MISSING")
        token = decrypt_secret(connection.access_token_encrypted)
        domain.require(bool(token), "ATHLETE_POLAR_RECONNECT_REQUIRED")
        client = PolarClient()
        if aware(connection.expires_at) <= now + timedelta(minutes=2):
            refresh = decrypt_secret(connection.refresh_token_encrypted)
            domain.require(bool(refresh), "ATHLETE_POLAR_RECONNECT_REQUIRED")
            renewed = await client.refresh_token(refresh)
            connection.access_token_encrypted = encrypt_secret(renewed["access_token"])
            if renewed.get("refresh_token"):
                connection.refresh_token_encrypted = encrypt_secret(renewed["refresh_token"])
            connection.expires_at = now + timedelta(seconds=int(renewed.get("expires_in", 43199)))
            connection.scopes = renewed.get("scope", "").split() or connection.scopes
            connection.updated_at = now
            # Persist a rotated refresh token before any later provider request can fail.
            await commit(session)
            user = await lock_owner(session, owner)
            connection = (
                await session.execute(
                    select(ExternalConnection)
                    .where(
                        ExternalConnection.user_id == UUID(owner),
                        ExternalConnection.provider == "POLAR",
                    )
                    .with_for_update()
                )
            ).scalar_one()
            domain.require(SCOPES[category] in connection.scopes, "ATHLETE_POLAR_SCOPE_MISSING")
            token = decrypt_secret(connection.access_token_encrypted)
            # Another tab may have completed this identical request during token refresh.
            found = await repository.get(artifact_kind=KINDS["polar_import"], artifact_id=identity)
            if found is not None:
                artifact, record = await load(repository, owner, "polar_import", identity)
                domain.require(
                    artifact["proposal"] == proposal, "ATHLETE_REQUEST_IDENTITY_CONFLICT"
                )
                await rollback(session)
                return receipt(artifact, record, True)
        last = day + timedelta(days=1)
        if category == "sessions":
            payload = await client.list_training_sessions(
                token, day, last, features=["test-results", "statistics"]
            )
        elif category == "sleep":
            payload = await client.list_sleeps(
                token, day, last, features=["sleep-result", "sleep-evaluation", "sleep-score"]
            )
        elif category == "nightly_recharge":
            payload = await client.list_nightly_recharge_results(token, day, last)
        elif category == "continuous_hr":
            payload = await client.list_continuous_samples(
                token, day, last, features=["heart-rate-samples"]
            )
        elif category == "activity":
            payload = await client.list_daily_activity(token, day, last)
        else:
            payload = await client.list_tests(token, day, last)
        domain.require(isinstance(payload, dict), "ATHLETE_PROVIDER_PAYLOAD_INVALID")
        # Preserve the exact decoded provider payload, including fields not mapped yet.
        raw_hash = domain.digest(payload)
        datatype = "ATHLETE_INTAKE_" + category.upper()
        provider_id = proposal["day"] + ":" + raw_hash
        row = (
            await session.execute(
                select(ProviderDataRecord).where(
                    ProviderDataRecord.user_id == UUID(owner),
                    ProviderDataRecord.provider == "POLAR",
                    ProviderDataRecord.data_type == datatype,
                    ProviderDataRecord.provider_record_id == provider_id,
                )
            )
        ).scalar_one_or_none()
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo(user.timezone)).astimezone(UTC)
        if row is None:
            row = ProviderDataRecord(
                user_id=UUID(owner),
                provider="POLAR",
                data_type=datatype,
                provider_record_id=provider_id,
                period_start=start,
                period_end=datetime.combine(
                    last, time.min, tzinfo=ZoneInfo(user.timezone)
                ).astimezone(UTC),
                occurred_at=start,
                raw_data=payload,
                fetched_at=_now(),
            )
            session.add(row)
            await session.flush()
        else:
            domain.require(
                domain.digest(row.raw_data) == raw_hash, "ATHLETE_PROVIDER_RECORD_CHANGED"
            )
        artifact = {
            "schema_version": domain.SCHEMA,
            "artifact_id": identity,
            "athlete_id": owner,
            "kind": "polar_import",
            "created_at": _now().isoformat(),
            "timezone_name": user.timezone,
            "proposal": proposal,
            "provider_record_id": str(row.id),
            "raw_content_hash": raw_hash,
            "fetched_at": aware(row.fetched_at).isoformat(),
            "planning_authorized": False,
            "workouts_created": False,
            "profile_changed": False,
        }
        artifact["content_hash"] = domain.digest(artifact)
        return await persist(repository, session, artifact, "polar_import")
    except BaseException:
        await rollback(session)
        raise
