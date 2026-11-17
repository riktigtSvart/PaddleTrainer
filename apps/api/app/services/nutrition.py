"""Owned meal plans and shopping state, saved atomically as append-only snapshots."""
import json
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.planning.application import register_athlete_setup as intake
from app.planning.domain.athlete_setup import digest, require
from app.planning.domain.common.serialization import canonical_json, CONTENT_HASH_ALGORITHM
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition import NutritionWrite
from app.services.nutrition_domain import SCHEMA, catalog, project

KIND = Kind.NUTRITION_WORKSPACE


def identity(owner, request_id):
    return 'pt-meals:' + digest({'owner': owner, 'request_id': request_id})


def reference(artifact):
    return {'artifact_id': artifact['artifact_id'], 'content_hash': artifact['content_hash']} if artifact else None


def checked(record, owner):
    require(record is not None and record.athlete_id == owner and record.artifact_kind == KIND, 'NUTRITION_STORAGE_INVALID')
    value = json.loads(record.contract_json)
    proposal = NutritionWrite.model_validate(value['proposal']).model_dump()
    require(value['schema_version'] == SCHEMA and record.schema_version == SCHEMA
        and value['athlete_id'] == owner and value['kind'] == KIND.value
        and value['artifact_id'] == record.artifact_id == identity(owner, proposal['request_id'])
        and value['proposal'] == proposal and proposal['catalog_hash'] == catalog()['content_hash']
        and value['result'] == project(proposal['data'])
        and value['workouts_changed'] is False and value['actual_intake_changed'] is False
        and value['personal_energy_prescribed'] is False
        and digest({k: v for k, v in value.items() if k != 'content_hash'}) == value['content_hash'] == record.content_hash
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM and record.persisted_at is not None
        and datetime.fromisoformat(value['created_at']) == record.created_at, 'NUTRITION_STORAGE_INVALID')
    return value


async def latest(repository, session, owner):
    result = await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id.desc()).limit(1))
    key = result.scalar_one_or_none()
    return checked(await repository.get(artifact_kind=KIND, artifact_id=key), owner) if key else None


async def read(*, repository, session, owner):
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        saved = await latest(repository, session, owner)
        value = {'schema_version': SCHEMA, 'athlete_id': owner,
            'local_today': intake._now().astimezone(ZoneInfo(user.timezone)).date().isoformat(),
            'catalog': catalog(), 'saved': saved, 'reference': reference(saved),
            'workouts_changed': False, 'actual_intake_changed': False, 'personal_energy_prescribed': False}
        value['content_hash'] = digest(value)
        return value
    finally:
        await intake.rollback(session)


def receipt(artifact, record, reused):
    return {'artifact': artifact, 'committed': True, 'reused': reused, 'durable_available_at': record.persisted_at.isoformat()}


async def save(*, repository, session, owner, proposal):
    intake._require_session(repository, session)
    try:
        await intake.lock_owner(session, owner)
        key = identity(owner, proposal['request_id'])
        found = await repository.get(artifact_kind=KIND, artifact_id=key)
        if found is not None:
            value = checked(found, owner)
            require(value['proposal'] == proposal, 'NUTRITION_REQUEST_CONFLICT')
            await intake.rollback(session)
            return receipt(value, found, True)
        previous = await latest(repository, session, owner)
        require(proposal['previous_reference'] == reference(previous), 'NUTRITION_REVISION_CHANGED')
        require(proposal['catalog_hash'] == catalog()['content_hash'], 'NUTRITION_CATALOG_CHANGED')
        result = project(proposal['data'])
        now = intake._now()
        if previous:
            now = max(now, datetime.fromisoformat(previous['created_at']) + timedelta(microseconds=1))
        value = {'schema_version': SCHEMA, 'kind': KIND.value, 'athlete_id': owner, 'artifact_id': key,
            'created_at': now.isoformat(), 'proposal': proposal, 'result': result,
            'workouts_changed': False, 'actual_intake_changed': False, 'personal_energy_prescribed': False}
        value['content_hash'] = digest(value)
        await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner,
            schema_version=SCHEMA, created_at=now, content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=value['content_hash'], contract_json=canonical_json(value)))
        record = await repository.get(artifact_kind=KIND, artifact_id=key)
        require(checked(record, owner) == value, 'NUTRITION_STORAGE_INVALID')
        await intake.commit(session)
        return receipt(value, record, False)
    except BaseException:
        await intake.rollback(session)
        raise
