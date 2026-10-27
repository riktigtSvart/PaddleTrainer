"""Durable, explicit provider imports with owned retries and bounded execution.

The immutable start reservation survives token-refresh and importer commits.
GETs only read local state. No provider job is launched by opening the app.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select

from app.core.security import decrypt_secret
from app.integrations.polar.client import PolarAPIError
from app.models.entities import ExternalConnection, User, WorkoutSession
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json, compute_content_hash
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.schemas.data_connections import DataSyncInput
from app.services.data_provider_registry import DATASET_SCOPES, PROVIDERS, REGISTRY
from app.services.polar_sync import sync_recent_sessions
from app.services.polar_targets import sync_training_targets
from app.services.polar_matching import link_exact_polar_sessions_after_import

SCHEMA = "data-connections-v0.1"
RUN_SCHEMA = "data-sync-run-v0.1"
TIMEOUT_SECONDS = 180
LEASE_SECONDS = 240
TERMINAL = (Kind.DATA_SYNC_SUCCEEDED, Kind.DATA_SYNC_FAILED)
PAIRING_COUNTS = ("linked", "already_linked", "unmatched", "missing_reference", "conflicts", "ambiguous")


class SyncRuleError(ValueError):
    pass


def require(value, code):
    if not value:
        raise SyncRuleError(code)


def _now():
    return datetime.now(UTC)


def digest(value):
    return compute_content_hash(value, exclude_fields=frozenset())


def scope(owner, provider):
    return "pt-data-sync:" + UUID(owner).hex + ":" + provider + ":"


def identity(owner, proposal):
    return scope(owner, proposal["provider"]) + UUID(proposal["request_id"]).hex


def reference(artifact):
    return {key: artifact[key] for key in ("artifact_id", "content_hash")}


def decode(record, owner):
    artifact = json.loads(record.contract_json)
    proposal = DataSyncInput.model_validate(artifact["proposal"]).model_dump(mode="json")
    require(
        record.athlete_id == artifact["athlete_id"] == owner
        and record.schema_version == artifact["schema_version"] == RUN_SCHEMA
        and record.artifact_id == artifact["artifact_id"] == identity(owner, proposal)
        and artifact["proposal"] == proposal
        and artifact["request_hash"] == digest(proposal)
        and artifact["content_hash"] == record.content_hash
        == digest({k: v for k, v in artifact.items() if k != "content_hash"})
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and canonical_json(artifact) == record.contract_json
        and record.persisted_at is not None
        and record.created_at == datetime.fromisoformat(artifact["created_at"])
        and artifact["planning_authorized"] is False,
        "DATA_SYNC_STORAGE_INVALID",
    )
    if record.artifact_kind == Kind.DATA_SYNC_STARTED:
        require(artifact["stage"] == "started" and datetime.fromisoformat(artifact["deadline_at"]) > record.created_at, "DATA_SYNC_STORAGE_INVALID")
    else:
        require(
            record.artifact_kind in TERMINAL and artifact["stage"] == "finished"
            and artifact["outcome"] in ("succeeded", "partial", "failed", "interrupted")
            and (record.artifact_kind == Kind.DATA_SYNC_SUCCEEDED) == (artifact["outcome"] == "succeeded")
            and [item["dataset"] for item in artifact["datasets"]] == proposal["datasets"],
            "DATA_SYNC_STORAGE_INVALID",
        )
        for item in artifact["datasets"]:
            require(item["state"] in ("succeeded", "failed", "not_attempted"), "DATA_SYNC_STORAGE_INVALID")
            require(all(item[key] is None or type(item[key]) is int and item[key] >= 0 for key in ("imported", "updated", "skipped")), "DATA_SYNC_STORAGE_INVALID")
            validate_details(item, "DATA_SYNC_STORAGE_INVALID")
    return artifact


def validate_details(item, code):
    if "details" in item:
        data = item["details"]
        require(item["dataset"] == "session_details" and isinstance(data, dict) and set(data) == {
            "requested_sessions", "already_complete", "fetched_sessions", "with_samples", "without_samples",
            "pending_sessions", "processed_days", "pending_days"}, code)
        require(all(type(n) is int and n >= 0 for n in data.values()), code)
        require(data["already_complete"] + data["fetched_sessions"] + data["pending_sessions"] == data["requested_sessions"]
            and data["with_samples"] + data["without_samples"] == data["fetched_sessions"]
            and data["fetched_sessions"] == item["updated"] and data["pending_sessions"] == item["skipped"], code)
    if "pairing" in item:
        require(isinstance(item["pairing"], dict) and set(item["pairing"]) == set(PAIRING_COUNTS), code)
        require(all(type(n) is int and n >= 0 for n in item["pairing"].values()), code)
    if "skip_reasons" in item:
        require(isinstance(item["skip_reasons"], dict), code)
        require(all(type(k) is str and k and type(n) is int and n >= 0
                    for k, n in item["skip_reasons"].items()), code)
        require(sum(item["skip_reasons"].values()) == item["skipped"], code)


async def load(repository, owner, artifact_id, kind):
    record = await repository.get(artifact_kind=kind, artifact_id=artifact_id)
    if record is None:
        return None
    return decode(record, owner)


async def end_for(repository, owner, start):
    ends = [await load(repository, owner, start["artifact_id"], kind) for kind in TERMINAL]
    ends = [item for item in ends if item is not None]
    require(len(ends) <= 1, "DATA_SYNC_STORAGE_INVALID")
    end = ends[0] if ends else None
    if end:
        require(end["start_reference"] == reference(start) and end["proposal"] == start["proposal"] and end["created_at"] >= start["created_at"], "DATA_SYNC_STORAGE_INVALID")
    return end


async def latest(session, repository, owner, provider, kind):
    artifact_id = (await session.execute(select(Row.artifact_id).where(
        Row.athlete_id == UUID(owner), Row.artifact_kind == kind.value,
        Row.artifact_id.startswith(scope(owner, provider)),
    ).order_by(Row.created_at.desc(), Row.artifact_id.desc()).limit(1))).scalar_one_or_none()
    return await load(repository, owner, artifact_id, kind) if artifact_id else None


def run_state(start, end, now):
    return end["outcome"] if end else "running" if now < datetime.fromisoformat(start["deadline_at"]) else "interrupted"


def run_summary(start, end, now):
    return {
        "request_id": start["proposal"]["request_id"],
        "provider": start["proposal"]["provider"],
        "state": run_state(start, end, now),
        "started_at": start["created_at"], "deadline_at": start["deadline_at"],
        "finished_at": end["created_at"] if end else None,
        "window": start["window"], "datasets": end["datasets"] if end else [],
        "requested_datasets": start["proposal"]["datasets"],
        "error_code": end["error_code"] if end else "DATA_SYNC_INTERRUPTED" if now >= datetime.fromisoformat(start["deadline_at"]) else None,
        "may_have_saved_data": end["may_have_saved_data"] if end else True,
    }


async def write(session, repository, owner, artifact, kind):
    artifact["content_hash"] = digest(artifact)
    saved = await repository.save(AuditArtifactRecord(
        artifact_kind=kind, artifact_id=artifact["artifact_id"], athlete_id=owner,
        schema_version=RUN_SCHEMA, created_at=datetime.fromisoformat(artifact["created_at"]),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=artifact["content_hash"], contract_json=canonical_json(artifact),
    ))
    require(saved.status == AuditArtifactSaveStatus.CREATED, "DATA_SYNC_STORAGE_INVALID")
    verified = await load(repository, owner, artifact["artifact_id"], kind)
    require(verified == artifact, "DATA_SYNC_STORAGE_INVALID")
    await transactions.commit(session)


async def find_request(session, repository, owner, request_id):
    artifact_id = (await session.execute(select(Row.artifact_id).where(
        Row.athlete_id == UUID(owner), Row.artifact_kind == Kind.DATA_SYNC_STARTED.value,
        Row.artifact_id.endswith(":" + UUID(request_id).hex),
    ))).scalar_one_or_none()
    return await load(repository, owner, artifact_id, Kind.DATA_SYNC_STARTED) if artifact_id else None


async def receipt(session, owner, request_id, *, reused=True):
    repository = SqlAlchemyPlanningAuditRepository(session)
    try:
        start = await find_request(session, repository, owner, request_id)
        require(start is not None, "DATA_SYNC_REQUEST_NOT_FOUND")
        end = await end_for(repository, owner, start)
        return {
            "schema_version": "data-sync-receipt-v0.1", "athlete_id": owner,
            "committed": True, "reused": reused, "start": start, "result": end,
            "run": run_summary(start, end, _now()), "planning_authorized": False,
        }
    finally:
        await transactions.rollback(session)


def connection_state(connection, configured, now):
    if not configured:
        return "configuration_required"
    if connection is None:
        return "not_connected"
    if not connection.access_token_encrypted:
        return "reconnect_required"
    try:
        if not decrypt_secret(connection.access_token_encrypted):
            return "reconnect_required"
    except Exception:
        return "reconnect_required"
    if aware(connection.expires_at) <= now and not connection.refresh_token_encrypted:
        return "reconnect_required"
    return "connected"


async def status(session, owner, *, configured):
    repository = SqlAlchemyPlanningAuditRepository(session)
    try:
        now = _now()
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        connections = (await session.execute(select(ExternalConnection).where(ExternalConnection.user_id == UUID(owner)))).scalars().all()
        by_provider = {item.provider: item for item in connections}
        providers = []
        for definition in PROVIDERS:
            connection = by_provider.get(definition.key)
            state = connection_state(connection, configured, now) if definition.implemented else "unavailable"
            allowed = [dataset for dataset in definition.datasets if connection is not None and set(DATASET_SCOPES[dataset]) <= set(connection.scopes)]
            start = await latest(session, repository, owner, definition.key, Kind.DATA_SYNC_STARTED)
            end = await end_for(repository, owner, start) if start else None
            successful = await latest(session, repository, owner, definition.key, Kind.DATA_SYNC_SUCCEEDED)
            if successful:
                original = await load(repository, owner, successful["artifact_id"], Kind.DATA_SYNC_STARTED)
                require(original is not None and await end_for(repository, owner, original) == successful, "DATA_SYNC_STORAGE_INVALID")
            newest = (await session.execute(select(func.max(WorkoutSession.started_at)).where(
                WorkoutSession.user_id == UUID(owner), WorkoutSession.external_provider == definition.key,
            ))).scalar_one_or_none()
            providers.append({
                "key": definition.key, "label": definition.label,
                "implemented": definition.implemented, "delivery": definition.delivery,
                "connection_state": state, "manual_sync_supported": definition.implemented,
                "datasets": list(definition.datasets), "allowed_datasets": allowed,
                "last_run": run_summary(start, end, now) if start else None,
                "last_success_at": successful["created_at"] if successful else None,
                "last_success_datasets": successful["proposal"]["datasets"] if successful else [],
                "latest_session_at": aware(newest).isoformat() if newest else None,
            })
        return {"schema_version": SCHEMA, "athlete_id": owner, "timezone_name": user.timezone,
                "retrieved_at": now.isoformat(), "providers": providers,
                "has_more": False, "planning_authorized": False}
    finally:
        await transactions.rollback(session)


async def reserve(session, owner, proposal, *, configured):
    repository = SqlAlchemyPlanningAuditRepository(session)
    try:
        user = await transactions.lock_owner(session, owner)
        require(user is not None, "DATA_SYNC_OWNER_NOT_FOUND")
        found = await find_request(session, repository, owner, proposal["request_id"])
        if found:
            require(found["proposal"] == proposal, "DATA_SYNC_REQUEST_IDENTITY_CONFLICT")
            await transactions.rollback(session)
            return False
        definition = REGISTRY[proposal["provider"]]
        require(definition.implemented, "DATA_SYNC_PROVIDER_UNAVAILABLE")
        connection = (await session.execute(select(ExternalConnection).where(
            ExternalConnection.user_id == UUID(owner), ExternalConnection.provider == definition.key,
        ))).scalar_one_or_none()
        state = connection_state(connection, configured, _now())
        require(state == "connected", "DATA_SYNC_" + state.upper())
        require(all(set(DATASET_SCOPES[d]) <= set(connection.scopes) for d in proposal["datasets"]), "DATA_SYNC_PERMISSION_MISSING")
        require(bool(decrypt_secret(connection.access_token_encrypted)), "DATA_SYNC_RECONNECT_REQUIRED")
        previous = await latest(session, repository, owner, definition.key, Kind.DATA_SYNC_STARTED)
        if previous:
            previous_end = await end_for(repository, owner, previous)
            require(run_state(previous, previous_end, _now()) != "running", "DATA_SYNC_ALREADY_RUNNING")
        now = _now()
        today = now.astimezone(ZoneInfo(user.timezone)).date()
        if previous:
            now = max(now, datetime.fromisoformat(previous["created_at"]) + timedelta(microseconds=1))
        start = {
            "schema_version": RUN_SCHEMA, "artifact_id": identity(owner, proposal),
            "athlete_id": owner, "proposal": proposal, "request_hash": digest(proposal),
            "stage": "started", "created_at": now.isoformat(),
            "deadline_at": (now + timedelta(seconds=LEASE_SECONDS)).isoformat(),
            "window": {"from_date": (today - timedelta(days=proposal["past_days"] - 1)).isoformat(),
                       "sessions_to_exclusive": (today + timedelta(days=1)).isoformat(),
                       "targets_to_exclusive": (today + timedelta(days=proposal["future_days"] + 1)).isoformat(),
                       "timezone_name": user.timezone},
            "planning_authorized": False,
        }
        await write(session, repository, owner, start, Kind.DATA_SYNC_STARTED)
        return True
    except BaseException:
        await transactions.rollback(session)
        raise


def failure_code(exc):
    if isinstance(exc, TimeoutError):
        return "DATA_SYNC_TIMEOUT"
    if isinstance(exc, PolarAPIError):
        code = getattr(exc, "status_code", None)
        known = {401: "DATA_SYNC_RECONNECT_REQUIRED", 403: "DATA_SYNC_PERMISSION_MISSING", 429: "DATA_SYNC_RATE_LIMITED"}
        if type(code) is int and code in known:
            return known[code]
        if type(code) is int and 400 <= code <= 599:
            return f"DATA_SYNC_PROVIDER_HTTP_{code}"
        return "DATA_SYNC_PROVIDER_REJECTED"
    if isinstance(exc, httpx.HTTPError):
        return "DATA_SYNC_PROVIDER_NETWORK_UNAVAILABLE"
    return "DATA_SYNC_IMPORT_FAILED"


async def import_dataset(session, user, dataset, window, report):
    """Only this adapter knows Polar. New providers implement this same operation."""
    from datetime import date
    first = date.fromisoformat(window["from_date"])
    if dataset == "sessions":
        await sync_recent_sessions(session, user, first=first,
            last=date.fromisoformat(window["sessions_to_exclusive"]),
            include_enrichment=False, report=report)
    elif dataset == "session_details":
        from app.services.polar_session_details import synchronize_details
        await synchronize_details(session, user, first=first,
            last=date.fromisoformat(window["sessions_to_exclusive"]), report=report)
    else:
        await sync_training_targets(session, user, first=first,
            last=date.fromisoformat(window["targets_to_exclusive"]),
            protect_tracked_plans=True, report=report)
    if report["skipped"] and not report.get("error_code"):
        report["error_code"] = (
            "DATA_SYNC_PROTECTED_PLANS_SKIPPED"
            if set(report.get("skip_reasons", {})) == {"protected_plan"}
            else "DATA_SYNC_SOURCE_RECORDS_SKIPPED"
        )


async def execute(session, owner, start):
    results = []
    pairing_report = None
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            for dataset in start["proposal"]["datasets"]:
                report = {"dataset": dataset, "state": "failed", "imported": None,
                          "updated": None, "skipped": None, "error_code": None}
                results.append(report)
                try:
                    user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
                    await import_dataset(session, user, dataset, start["window"], report)
                    report["state"] = "succeeded"
                except Exception as exc:
                    await transactions.rollback(session)
                    report["error_code"] = failure_code(exc)
            # One pass after all requested imports, so new targets are already
            # available and the final report has no transient missing-plan count.
            pairing_report = next((item for item in reversed(results) if item["state"] == "succeeded"), None)
            if pairing_report is not None:
                try:
                    user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
                    pairing_report["pairing"] = await link_exact_polar_sessions_after_import(session, user)
                    if pairing_report["pairing"]["conflicts"] or pairing_report["pairing"]["ambiguous"]:
                        pairing_report["error_code"] = "DATA_SYNC_PAIRING_REVIEW_REQUIRED"
                except Exception:
                    await transactions.rollback(session)
                    pairing_report["error_code"] = "DATA_SYNC_PAIRING_FAILED"
    except TimeoutError:
        await transactions.rollback(session)
        if pairing_report is not None:
            pairing_report["error_code"] = "DATA_SYNC_TIMEOUT"
        elif results and results[-1]["state"] != "succeeded":
            results[-1]["error_code"] = "DATA_SYNC_TIMEOUT"
    for dataset in start["proposal"]["datasets"][len(results):]:
        results.append({"dataset": dataset, "state": "not_attempted", "imported": None,
                        "updated": None, "skipped": None, "error_code": "DATA_SYNC_TIMEOUT"})
    require(all(item["state"] != "succeeded" or all(type(item[key]) is int and item[key] >= 0 for key in ("imported", "updated", "skipped")) for item in results), "DATA_SYNC_IMPORT_REPORT_INVALID")
    for item in results:
        validate_details(item, "DATA_SYNC_IMPORT_REPORT_INVALID")
    return results


async def finish(session, owner, start, results):
    await transactions.rollback(session)
    repository = SqlAlchemyPlanningAuditRepository(session)
    await transactions.lock_owner(session, owner)
    require(await end_for(repository, owner, start) is None, "DATA_SYNC_STORAGE_INVALID")
    complete = all(item["state"] == "succeeded" and item["skipped"] == 0 and item["error_code"] is None for item in results)
    outcome = "succeeded" if complete else "partial" if any(item["state"] == "succeeded" for item in results) else "failed"
    error_code = next((item["error_code"] for item in results if item["error_code"]), None)
    if not complete and error_code is None:
        error_code = "DATA_SYNC_SOURCE_RECORDS_SKIPPED"
    artifact = {
        "schema_version": RUN_SCHEMA, "artifact_id": start["artifact_id"],
        "athlete_id": owner, "proposal": start["proposal"], "request_hash": start["request_hash"],
        "stage": "finished", "created_at": max(_now(), datetime.fromisoformat(start["created_at"])).isoformat(),
        "start_reference": reference(start), "outcome": outcome, "datasets": results,
        "error_code": error_code, "may_have_saved_data": True, "planning_authorized": False,
    }
    await write(session, repository, owner, artifact, Kind.DATA_SYNC_SUCCEEDED if complete else Kind.DATA_SYNC_FAILED)


async def synchronize(session, owner, proposal, *, configured):
    try:
        created = await reserve(session, owner, proposal, configured=configured)
        if created:
            saved = await receipt(session, owner, proposal["request_id"], reused=False)
            results = await execute(session, owner, saved["start"])
            await finish(session, owner, saved["start"], results)
        return await receipt(session, owner, proposal["request_id"], reused=not created)
    except BaseException:
        await transactions.rollback(session)
        raise
