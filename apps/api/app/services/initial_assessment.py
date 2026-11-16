"""Owner-bound initial assessments, immutable revisions and exact idempotent saves."""
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import User
from app.planning.application import create_cycle_program as cycles
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain import athlete_setup
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
from app.schemas.initial_assessment import AssessmentInput
from app.services import initial_assessment_domain as domain
from app.services import strength_catalog, training_options

SCHEMA = 'initial-assessment-v0.1'
KIND = AuditArtifactKind.INITIAL_ASSESSMENT


def _now():
    return datetime.now(UTC)


def identity(owner, token):
    return 'pt-initial-assessment:' + UUID(owner).hex + ':' + UUID(token).hex


def reference(artifact):
    return {'artifact_id': artifact['artifact_id'], 'content_hash': artifact['content_hash']}


def source_body(snapshot):
    return {'timezone_name': snapshot['timezone_name'], 'profile_reference': snapshot['profile_reference'],
                   'options_reference': snapshot['options_reference'], 'catalog_hash': snapshot['catalog']['content_hash'],
                   'registry_hash': snapshot['registry']['content_hash'], 'programs': snapshot['programs']}


def source_hash(snapshot):
    return digest(source_body(snapshot))


def profile_content(data):
    # Biography, current observations, selected data and available equipment
    # are consumed live. They do not alter a recorded movement or set. Named
    # venue equipment is checked separately. Health, movement constraints,
    # participation and body values remain part of this comparison.
    ignored = {'sport_history', 'sport_history_status', 'competition_category', 'target_sport',
               'typical_days_per_week', 'typical_minutes_per_week', 'last_training_date',
               'resources', 'duration_doubling_slowdown_pct', 'manual_observations',
               'source_window', 'source_selections'}
    return {key: value for key, value in data.items() if key not in ignored}


async def assessment_profile(repo, session, owner, preferred_reference):
    current = await transactions.latest(repo, session, owner, 'profile')
    if not current or not preferred_reference:
        return current
    original = current
    content = profile_content(current[0]['proposal']['data'])
    for _ in range(1024):
        if reference(current[0]) == preferred_reference:
            return current
        parent = current[0]['proposal']['previous_reference']
        if parent is None:
            return original
        previous = await transactions.load(repo, owner, 'profile', parent['artifact_id'])
        if profile_content(previous[0]['proposal']['data']) != content:
            return original
        current = previous
    require(False, 'INITIAL_ASSESSMENT_PROFILE_HISTORY_LIMIT')


async def sources(repo, session, owner, user, today):
    previous = await latest(repo, session, owner)
    profile = await assessment_profile(repo, session, owner,
        previous[0]['snapshot']['profile_reference'] if previous else None)
    options = await training_options.assessment_options(repo, session, owner,
        preferred_reference=previous[0]['snapshot']['options_reference'] if previous else None)
    keys = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == cycles.PROGRAM.value,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(101))).scalars().all()
    require(len(keys) <= 100, 'INITIAL_ASSESSMENT_PROGRAM_LIMIT')
    programs = []
    cache = {}
    for key in keys:
        value, _ = await cycles._load(repo, owner, cycles.PROGRAM, key, cache=cache)
        proposal = value['proposal']
        programs.append({'reference': reference(value), 'title': proposal['title'], 'sport': proposal['sport'],
                         'start_date': proposal['start_date'], 'end_date': proposal['end_date']})
    snapshot = {'athlete_id': owner, 'timezone_name': user.timezone,
                'profile_reference': reference(profile[0]) if profile else None,
                'profile_receipt': transactions.receipt(*profile, True) if profile else None,
                'profile_review': athlete_setup.review_profile(profile[0]['proposal']['data'], today) if profile else None,
                'options_reference': reference(options[0]) if options else None,
                'options_receipt': training_options.receipt(*options, True) if options else None,
                'locations': options[0]['proposal']['data']['locations'] if options else [],
                'catalog': strength_catalog.catalog(), 'registry': domain.registry(), 'programs': programs}
    snapshot['source_hash'] = source_hash(snapshot)
    return snapshot


def decode(record, owner):
    value = json.loads(record.contract_json)
    proposal = AssessmentInput.model_validate(value['proposal']).model_dump(mode='json')
    require(record.athlete_id == owner == value['athlete_id'] == value['snapshot']['athlete_id']
            and record.artifact_kind == KIND and record.schema_version == value['schema_version'] == SCHEMA
            and value['artifact_id'] == record.artifact_id == identity(owner, proposal['request_id'])
            and value['proposal'] == proposal and record.contract_json == canonical_json(value)
            and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
            and record.content_hash == value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
            and record.created_at == datetime.fromisoformat(value['created_at'])
            and record.created_at.tzinfo is not None and record.persisted_at is not None and record.persisted_at.tzinfo is not None
            and type(value['revision']) is int and value['revision'] >= 1
            and (value['revision'] == 1) == (proposal['previous_reference'] is None)
            and value['planning_authorized'] is False and value['workouts_changed'] is False and value['clinical_clearance'] is False
            and source_hash(value['snapshot']) == value['snapshot']['source_hash'] == proposal['source_hash'],
            'INITIAL_ASSESSMENT_STORAGE_INVALID')
    domain.validate_sources(proposal['data'], value['snapshot'])
    require(value['summary'] == domain.summary(proposal['data'], value['snapshot'], value['summary']['evaluated_on']), 'INITIAL_ASSESSMENT_STORAGE_INVALID')
    return value


async def load(repo, owner, key):
    record = await repo.get(artifact_kind=KIND, artifact_id=key)
    require(record is not None and record.athlete_id == owner, 'INITIAL_ASSESSMENT_NOT_FOUND')
    value = decode(record, owner)
    parent = value['proposal']['previous_reference']
    if parent:
        previous = await repo.get(artifact_kind=KIND, artifact_id=parent['artifact_id'])
        require(previous is not None and previous.athlete_id == owner, 'INITIAL_ASSESSMENT_STORAGE_INVALID')
        a = decode(previous, owner)
        require(reference(a) == parent and a['revision'] + 1 == value['revision'] and a['created_at'] < value['created_at'], 'INITIAL_ASSESSMENT_STORAGE_INVALID')
    return value, record


async def latest(repo, session, owner):
    key = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(1))).scalar_one_or_none()
    return await load(repo, owner, key) if key else None


def receipt(artifact, record, reused):
    return {'identity_scope': 'APPLICATION_DEMO_USER', 'artifact': artifact, 'committed': True, 'reused': reused,
            'durable_available_at': record.persisted_at.isoformat(), 'planning_authorized': False, 'workouts_changed': False, 'clinical_clearance': False}


async def stage(*, session, repo, owner, user, proposal):
    """Prepare a revision inside the caller's owner-locked transaction."""
    proposal = AssessmentInput.model_validate(proposal).model_dump(mode='json')
    key = identity(owner, proposal['request_id'])
    found = await repo.get(artifact_kind=KIND, artifact_id=key)
    if found:
        value, stored = await load(repo, owner, key)
        require(value['proposal'] == proposal, 'INITIAL_ASSESSMENT_REQUEST_CONFLICT')
        return value, stored, True
    current = await latest(repo, session, owner)
    parent = current[0] if current else None
    require(proposal['previous_reference'] == (reference(parent) if parent else None), 'INITIAL_ASSESSMENT_REVISION_CONFLICT')
    today = _now().astimezone(ZoneInfo(user.timezone)).date().isoformat()
    snapshot = await sources(repo, session, owner, user, today)
    require(snapshot['source_hash'] == proposal['source_hash'], 'INITIAL_ASSESSMENT_SOURCES_CHANGED')
    require(proposal['data']['timezone_name'] == user.timezone and proposal['data']['assessment_date'] <= today, 'INITIAL_ASSESSMENT_DATE_OR_ZONE_INVALID')
    domain.validate_sources(proposal['data'], snapshot)
    created = _now()
    if parent:
        created = max(created, datetime.fromisoformat(parent['created_at']) + timedelta(microseconds=1))
    value = {'schema_version': SCHEMA, 'artifact_id': key, 'athlete_id': owner, 'created_at': created.isoformat(),
             'revision': parent['revision'] + 1 if parent else 1, 'proposal': proposal, 'snapshot': snapshot,
             'summary': domain.summary(proposal['data'], snapshot, today),
             'planning_authorized': False, 'workouts_changed': False, 'clinical_clearance': False}
    value['content_hash'] = digest(value)
    result = await repo.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner, schema_version=SCHEMA,
                            created_at=created, content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=value['content_hash'], contract_json=canonical_json(value)))
    require(result.status == AuditArtifactSaveStatus.CREATED, 'INITIAL_ASSESSMENT_STORAGE_INVALID')
    verified, stored = await load(repo, owner, key)
    require(verified == value, 'INITIAL_ASSESSMENT_STORAGE_INVALID')
    return verified, stored, False


async def save(*, session, owner, proposal):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        user = await transactions.lock_owner(session, owner)
        value, record, reused = await stage(session=session, repo=repo, owner=owner, user=user, proposal=proposal)
        if not reused:
            await transactions.commit(session)
        return receipt(value, record, reused)
    finally:
        await transactions.rollback(session)


async def capture_context(*, session, repo, owner, user, today):
    current = await latest(repo, session, owner)
    snapshot = await sources(repo, session, owner, user, today)
    data = current[0]['proposal']['data'] if current else None
    value = {'schema_version': SCHEMA, 'athlete_id': owner, 'timezone_name': user.timezone, 'local_today': today,
             'sources': snapshot, 'saved': receipt(*current, True) if current else None,
             'reference': reference(current[0]) if current else None, 'data': data,
             'sources_changed': current is not None and current[0]['proposal']['source_hash'] != snapshot['source_hash'],
             'summary': domain.summary(data, current[0]['snapshot'], today) if data else None,
             'planning_authorized': False, 'workouts_changed': False, 'clinical_clearance': False}
    value['content_hash'] = digest(value)
    return value


async def context(*, session, owner):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        today = _now().astimezone(ZoneInfo(user.timezone)).date().isoformat()
        return await capture_context(session=session, repo=repo, owner=owner, user=user, today=today)
    finally:
        await transactions.rollback(session)


async def read_revision(*, session, owner, token):
    """Read an exact owned revision without retrying or creating a write."""
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        value, stored = await load(repo, owner, identity(owner, token))
        return receipt(value, stored, True)
    finally:
        await transactions.rollback(session)
