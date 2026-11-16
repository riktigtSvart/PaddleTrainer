"""Durable, revocable authority for the existing bounded application planner."""
import json
from datetime import datetime, timedelta
from uuid import UUID, NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.planning.application import create_cycle_program as cycles
from app.planning.application import revise_cycle_boundary as boundaries
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository
from app.schemas.automatic_planning import AutomaticSettingInput
from app.services import training_plans as plans

SCHEMA = 'automatic-planning-v0.1'
POLICY = Kind.AUTOMATIC_PLANNING_POLICY
RUN = Kind.AUTOMATIC_PLANNING_RUN
LIMIT = 2000


class AutomaticPlanningError(ValueError):
    pass


def require(value, code):
    if not value:
        raise AutomaticPlanningError(code)


def identity(owner, value):
    return 'pt-automatic:' + digest({'owner': owner, 'key': value})


def decode(record, owner):
    value = json.loads(record.contract_json)
    require(record.athlete_id == owner == value['athlete_id'] and record.persisted_at is not None
            and value['schema_version'] == record.schema_version == SCHEMA
            and value['artifact_id'] == record.artifact_id
            and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
            and value['content_hash'] == record.content_hash == digest({k: v for k, v in value.items() if k != 'content_hash'})
            and canonical_json(value) == record.contract_json, 'AUTOMATIC_PLANNING_STORAGE_INVALID')
    return value


async def records(repo, session, owner, kind):
    keys = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == kind.value,
    ).order_by(PlanningAuditArtifactRow.created_at, PlanningAuditArtifactRow.artifact_id).limit(LIMIT + 1))).scalars().all()
    require(len(keys) <= LIMIT, 'AUTOMATIC_PLANNING_HISTORY_LIMIT')
    return [decode(await repo.get(artifact_kind=kind, artifact_id=key), owner) for key in keys]


async def persist(repo, owner, kind, body):
    value = {**body, 'schema_version': SCHEMA, 'athlete_id': owner}
    value['content_hash'] = digest(value)
    await repo.save(AuditArtifactRecord(artifact_kind=kind, artifact_id=value['artifact_id'], athlete_id=owner,
        schema_version=SCHEMA, created_at=datetime.fromisoformat(value['created_at']), content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=value['content_hash'], contract_json=canonical_json(value)))
    require(decode(await repo.get(artifact_kind=kind, artifact_id=value['artifact_id']), owner) == value, 'AUTOMATIC_PLANNING_STORAGE_INVALID')
    return value


async def program_info(repo, owner, requested):
    program, _ = await cycles._load(repo, owner, cycles.PROGRAM, requested['artifact_id'])
    require(reference(program) == requested, 'AUTOMATIC_PLANNING_PROGRAM_CHANGED')
    changed = await boundaries.head(repo, owner, program)
    return {'reference': reference(program), 'title': program['proposal']['title'], 'start_date': program['proposal']['start_date'],
            'end_date': program['proposal']['end_date'], 'timezone_name': program['timezone_name'],
            'periods': changed[-1]['artifact']['periods'] if changed else program['periods']}


async def require_current(repo, session, owner, program_id, requested):
    values = await records(repo, session, owner, POLICY)
    current = values[-1] if values else None
    require(current and reference(current) == requested and current['proposal']['enabled']
            and current['proposal']['onboarding_completed'] and current['proposal']['program_reference']['artifact_id'] == program_id,
            'AUTOMATIC_PLANNING_AUTHORITY_CHANGED')
    await program_info(repo, owner, current['proposal']['program_reference'])
    require(await repo.get(artifact_kind=cycles.PROGRAM, artifact_id=cycles.domain.replacement_slot(owner, program_id)) is None,
            'AUTOMATIC_PLANNING_PROGRAM_SUPERSEDED')
    return current


async def save(*, session, owner, proposal):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    proposal = AutomaticSettingInput.model_validate(proposal).model_dump(mode='json')
    try:
        await transactions.lock_owner(session, owner)
        key = identity(owner, {'setting': proposal['request_id']})
        old = await repo.get(artifact_kind=POLICY, artifact_id=key)
        if old:
            value = decode(old, owner)
            require(value['proposal'] == proposal, 'AUTOMATIC_PLANNING_REQUEST_CONFLICT')
            return {'artifact': value, 'committed': True, 'reused': True}
        values = await records(repo, session, owner, POLICY)
        previous = values[-1] if values else None
        require(proposal['previous_reference'] == (reference(previous) if previous else None), 'AUTOMATIC_PLANNING_REVISION_CONFLICT')
        if proposal['program_reference']:
            await program_info(repo, owner, proposal['program_reference'])
            if proposal['enabled']:
                require(await repo.get(artifact_kind=cycles.PROGRAM, artifact_id=cycles.domain.replacement_slot(owner, proposal['program_reference']['artifact_id'])) is None,
                        'AUTOMATIC_PLANNING_PROGRAM_SUPERSEDED')
        now = plans._now()
        if previous:
            now = max(now, datetime.fromisoformat(previous['created_at']) + timedelta(microseconds=1))
        value = await persist(repo, owner, POLICY, {'artifact_id': key, 'created_at': now.isoformat(),
            'revision': len(values) + 1, 'proposal': proposal,
            'authority_scope': 'bounded_application_training_plans' if proposal['enabled'] else 'disabled',
            'provider_writeback': False, 'nutrition_planning': False, 'personal_response_model_applied': False})
        await transactions.commit(session)
        return {'artifact': value, 'committed': True, 'reused': False}
    finally:
        await transactions.rollback(session)


async def context(*, session, owner):
    repo = SqlAlchemyPlanningAuditRepository(session)
    try:
        values = await records(repo, session, owner, POLICY)
        policy = values[-1] if values else None
        program = await program_info(repo, owner, policy['proposal']['program_reference']) if policy and policy['proposal']['program_reference'] else None
        runs = await records(repo, session, owner, RUN) if policy else []
        latest = next((v for v in reversed(runs) if v['policy_reference'] == reference(policy)), None)
        zone = program['timezone_name'] if program else await cycles.timezone_for(session, owner)
        value = {'schema_version': SCHEMA, 'athlete_id': owner, 'timezone_name': zone,
                 'policy': policy, 'program': program, 'last_run': latest,
                 'automatic_review_interval_seconds': 60,
                 'supported_training_sports': ['KAYAK', 'RUNNING', 'STRENGTH', 'SWIMMING'],
                 'nutrition_planning_available': False, 'fatigue_prediction_available': False}
        value['content_hash'] = digest(value)
        return value
    finally:
        await transactions.rollback(session)


async def remember_run(session, owner, policy, result):
    repo = SqlAlchemyPlanningAuditRepository(session)
    try:
        await transactions.lock_owner(session, owner)
        values = await records(repo, session, owner, RUN)
        previous = values[-1] if values else None
        key = {'policy_reference': reference(policy), **result}
        if previous and previous['result_key'] == digest(key):
            return previous
        now = plans._now()
        if previous:
            now = max(now, datetime.fromisoformat(previous['created_at']) + timedelta(microseconds=1))
        value = await persist(repo, owner, RUN, {'artifact_id': identity(owner, {'run': digest(key), 'previous': reference(previous) if previous else None}),
            'created_at': now.isoformat(), 'policy_reference': reference(policy), 'result_key': digest(key), **result})
        await transactions.commit(session)
        return value
    finally:
        await transactions.rollback(session)


async def run_once(session, owner):
    current = await context(session=session, owner=owner)
    policy, program = current['policy'], current['program']
    if not policy or not policy['proposal']['enabled']:
        return None
    repo = SqlAlchemyPlanningAuditRepository(session)
    superseded = await repo.get(artifact_kind=cycles.PROGRAM,
        artifact_id=cycles.domain.replacement_slot(owner, program['reference']['artifact_id']))
    await transactions.rollback(session)
    if superseded is not None:
        return await remember_run(session, owner, policy, {'state': 'blocked', 'blockers': ['AUTOMATIC_PLANNING_PROGRAM_SUPERSEDED'],
            'start_date': None, 'end_date': None, 'review_reference': None, 'application_reference': None, 'created_count': 0, 'cancelled_count': 0})
    today = plans._now().astimezone(ZoneInfo(program['timezone_name'])).date().isoformat()
    first = max(today, program['start_date'])
    future = sorted((p for p in program['periods'] if p['period_type'] == 'MESOCYCLE' and p['end_date'] >= first), key=lambda p: (p['start_date'], p['id']))[:2]
    if program['end_date'] and today > program['end_date']:
        return await remember_run(session, owner, policy, {'state': 'completed', 'blockers': [], 'start_date': None, 'end_date': None, 'review_reference': None, 'application_reference': None, 'created_count': 0, 'cancelled_count': 0})
    if not future:
        return await remember_run(session, owner, policy, {'state': 'blocked', 'blockers': ['AUTOMATIC_PLANNING_CYCLE_EXTENSION_REQUIRED'], 'start_date': None, 'end_date': None, 'review_reference': None, 'application_reference': None, 'created_count': 0, 'cancelled_count': 0})
    last = min(future[-1]['end_date'], (datetime.fromisoformat(first).date() + timedelta(days=365)).isoformat())
    if program['end_date']:
        last = min(last, program['end_date'])
    result = {'state': 'blocked', 'blockers': [], 'start_date': first, 'end_date': last, 'review_reference': None, 'application_reference': None, 'created_count': 0, 'cancelled_count': 0}
    try:
        viewed = (await plans.review(session=session, owner=owner, program_id=program['reference']['artifact_id'], first=first, last=last, coordinate_mesocycles=True))['review']
        result.update(review_reference=reference(viewed), blockers=viewed['result']['blockers'])
        if 'sport_availability' in viewed['result']['preparation']:
            result['sport_availability'] = viewed['result']['preparation']['sport_availability']
        if not result['blockers']:
            if viewed['result']['create'] or viewed['result']['cancel']:
                token = str(uuid5(NAMESPACE_URL, 'paddletrainer:auto:' + owner + ':' + policy['artifact_id'] + ':' + viewed['artifact_id']))
                accepted = await plans.accept(session=session, owner=owner, program_id=program['reference']['artifact_id'],
                    proposal={'request_id': token, 'review_reference': reference(viewed)}, automation_reference=reference(policy))
                artifact = accepted['artifact']
                result.update(state='applied', application_reference=reference(artifact), created_count=len(artifact['created_workouts']), cancelled_count=len(artifact['cancelled_workout_ids']))
            elif viewed['result']['keep']:
                result['state'] = 'current'
            else:
                result.update(state='blocked', blockers=['AUTOMATIC_PLANNING_NO_USABLE_WORKOUTS'])
    except (plans.TrainingPlanError, AutomaticPlanningError) as exc:
        result.update(state='blocked', blockers=[str(exc)])
    return await remember_run(session, owner, policy, result)
