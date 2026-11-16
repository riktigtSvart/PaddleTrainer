"""Append-only owned actual strength logs; plans never imply completion."""
import json
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.entities import User
from app.planning.application import register_athlete_setup as setup
from app.planning.application.calendar_workspace import digest, require
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord, AuditArtifactSaveStatus
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.strength_workout import StrengthWorkoutInput
from app.services import session_feedback, strength_catalog, training_options, initial_assessment_domain

SCHEMA = 'strength-workout-log-v0.1'
KIND = Kind.STRENGTH_WORKOUT_LOG
LIMIT = 200

def _now():
    return datetime.now(UTC)

def identity(owner, request):
    return 'pt-strength-workout:' + digest({'athlete_id': owner, 'request_id': request})

def snapshot(row):
    return {'id': str(row.id), 'sport': row.sport.value, 'started_at': aware(row.started_at).isoformat(),
            'ended_at': aware(row.ended_at).isoformat() if row.ended_at else None, 'duration_sec': row.duration_sec}

def decode(record, owner):
    require(record is not None, 'CALENDAR_STRENGTH_LOG_STORAGE_INVALID')
    a = json.loads(record.contract_json)
    p = StrengthWorkoutInput.model_validate(a['proposal']).model_dump(mode='json')
    require(record.athlete_id == a['athlete_id'] == owner and record.artifact_kind == KIND
        and record.schema_version == a['schema_version'] == SCHEMA
        and record.artifact_id == a['artifact_id'] == identity(owner, p['request_id'])
        and a['proposal'] == p and a['revision'] == p['expected_revision'] + 1
        and record.persisted_at is not None and record.created_at == datetime.fromisoformat(a['submitted_at'])
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == a['content_hash'] == digest({k:v for k,v in a.items() if k != 'content_hash'})
        and record.contract_json == canonical_json(a), 'CALENDAR_STRENGTH_LOG_STORAGE_INVALID')
    return a

async def history(repo, session, owner, session_id, cutoff=None):
    keys = list((await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
        PlanningAuditArtifactRow.contract_json.contains('"session_id":"' + session_id + '"')
    ).limit(LIMIT + 1))).scalars().all())
    require(len(keys) <= LIMIT, 'CALENDAR_STRENGTH_LOG_HISTORY_LIMIT')
    result = []
    for key in keys:
        r = await repo.get(artifact_kind=KIND, artifact_id=key)
        a = decode(r, owner)
        if cutoff is None or r.persisted_at <= cutoff and r.created_at <= cutoff:
            result.append({'artifact': a, 'durable_available_at': r.persisted_at.isoformat()})
    result.sort(key=lambda r: r['artifact']['revision'])
    previous = None
    for index, r in enumerate(result, 1):
        a = r['artifact']
        require(a['session_id'] == session_id and a['revision'] == index and a['previous_hash'] == previous,
                'CALENDAR_STRENGTH_LOG_STORAGE_INVALID')
        previous = a['content_hash']
    return result

async def context(*, owner, session_id, repository, session):
    setup._require_session(repository, session)
    try:
        workout = await session_feedback.owned(session, owner, session_id)
        require(workout.sport.value == 'STRENGTH', 'CALENDAR_STRENGTH_LOG_SPORT_REQUIRED')
        records = await history(repository, session, owner, session_id)
        options = await training_options.latest(repository, session, owner)
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        return {'schema_version': SCHEMA, 'athlete_id': owner, 'session_id': session_id,
                'timezone_name': user.timezone, 'session': snapshot(workout), 'current': records[-1] if records else None,
                'catalog': strength_catalog.catalog(), 'patterns': initial_assessment_domain.registry()['patterns'],
                'locations': options[0]['proposal']['data']['locations'] if options else []}
    finally:
        await setup.rollback(session)

async def save(*, owner, session_id, proposal, repository, session):
    setup._require_session(repository, session)
    try:
        user = await setup.lock_owner(session, owner)
        row = await session_feedback.owned(session, owner, session_id)
        require(row.sport.value == 'STRENGTH' and row.ended_at is not None and aware(row.started_at) <= aware(row.ended_at) <= _now()
                and (row.duration_sec is None or 0 <= row.duration_sec <= (aware(row.ended_at)-aware(row.started_at)).total_seconds()),
                'CALENDAR_STRENGTH_LOG_COMPLETED_REQUIRED')
        key = identity(owner, proposal['request_id'])
        existing = await repository.get(artifact_kind=KIND, artifact_id=key)
        if existing:
            a = decode(existing, owner)
            require(a['proposal'] == proposal and a['session_id'] == session_id, 'CALENDAR_STRENGTH_LOG_REQUEST_CONFLICT')
            await setup.rollback(session)
            return {'committed': True, 'reused': True, 'artifact': a, 'durable_available_at': existing.persisted_at.isoformat()}
        records = await history(repository, session, owner, session_id)
        previous = records[-1]['artifact'] if records else None
        require(proposal['expected_revision'] == (previous['revision'] if previous else 0), 'CALENDAR_STRENGTH_LOG_REVISION_CONFLICT')
        require(len(records) < LIMIT, 'CALENDAR_STRENGTH_LOG_HISTORY_LIMIT')
        options = await training_options.latest(repository, session, owner)
        locations = options[0]['proposal']['data']['locations'] if options else []
        patterns = {p['key']:p['exercise_ids'] for p in initial_assessment_domain.registry()['patterns']}
        day = aware(row.started_at).astimezone(ZoneInfo(user.timezone)).date().isoformat()
        for e in proposal['exercises']:
            require(e['performed_on'] == day, 'CALENDAR_STRENGTH_LOG_DAY_MISMATCH')
            require(e['exercise_id'] in patterns[e['pattern']], 'CALENDAR_STRENGTH_LOG_EXERCISE_INVALID')
            require(any(p['id'] == e['location_id'] for p in locations), 'CALENDAR_STRENGTH_LOG_LOCATION_INVALID')
        now = _now()
        a = {'schema_version': SCHEMA, 'artifact_id': key, 'athlete_id': owner, 'session_id': session_id,
             'session': snapshot(row), 'timezone_name': user.timezone, 'proposal': proposal,
             'revision': proposal['expected_revision'] + 1, 'previous_hash': previous['content_hash'] if previous else None,
             'submitted_at': now.isoformat()}
        a['content_hash'] = digest(a)
        saved = await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner,
            schema_version=SCHEMA, created_at=now, content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=a['content_hash'], contract_json=canonical_json(a)))
        require(saved.status == AuditArtifactSaveStatus.CREATED, 'CALENDAR_STRENGTH_LOG_STORAGE_INVALID')
        r = await repository.get(artifact_kind=KIND, artifact_id=key)
        require(decode(r, owner) == a, 'CALENDAR_STRENGTH_LOG_STORAGE_INVALID')
        await setup.commit(session)
        return {'committed': True, 'reused': False, 'artifact': a, 'durable_available_at': r.persisted_at.isoformat()}
    except BaseException:
        await setup.rollback(session)
        raise

async def capture(repo, session, owner, data):
    cutoff = datetime.fromisoformat(data['captured_at'])
    result = []
    present = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value,
    ).limit(1))).scalar_one_or_none()
    if present is None:
        return {'schema_version': 'strength-workout-context-v0.1', 'athlete_id': owner, 'logs': []}
    assessment_ids = {v['artifact']['workout_session_id'] for v in data['strength_assessment'].get('guided_activities', []) if v['artifact']['state'] == 'finished'}
    for row in data['recent_sessions']:
        if row['sport'] != 'STRENGTH' or row['id'] in assessment_ids or row.get('reference_occasion') or not row['ended_at']:
            continue
        items = await history(repo, session, owner, row['id'], cutoff)
        if not items:
            continue
        latest = items[-1]
        a = latest['artifact']
        expected = {k: row[k] for k in ('id', 'sport', 'started_at', 'ended_at', 'duration_sec')}
        if a['session'] != expected or a['proposal']['purpose'] != 'training':
            continue
        feedback = []
        for f in await session_feedback.history(repo, session, owner, row['id']):
            r = await repo.get(artifact_kind=Kind.SESSION_FEEDBACK, artifact_id=f['artifact_id'])
            if r.created_at <= cutoff and r.persisted_at <= cutoff:
                feedback.append({'artifact': f, 'durable_available_at': r.persisted_at.isoformat()})
        latest_feedback = [next((f for f in reversed(feedback) if f['artifact']['proposal']['timing'] == t), None) for t in ('IMMEDIATE', 'NEXT_MORNING')]
        result.append({'log': latest, 'feedback': [f for f in latest_feedback if f]})
    return {'schema_version': 'strength-workout-context-v0.1', 'athlete_id': owner, 'logs': result}
