"""Owned append-only body observations and independent nutrition intentions.

Legacy profiles remain immutable. Their dated readings join the new ledger on
read; repeated copies of one legacy day/value are collapsed only in the view.
"""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.entities import User
from app.planning.application import register_athlete_setup as intake
from app.planning.domain import athlete_setup as domain
from app.planning.domain.common.serialization import canonical_json, CONTENT_HASH_ALGORITHM
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.body_mass import BodyMassInput, NutritionGoalInput
from app.schemas.athlete_setup import ProfileData, ProfileInput

MASS = Kind.BODY_MASS_MEASUREMENT
GOAL = Kind.NUTRITION_GOAL
LIMIT = 10000
SCHEMA = 'body-and-nutrition-v0.1'


def identity(owner, kind, request_id):
    return ('pt-body:' if kind == MASS else 'pt-nutrition:') + domain.digest({'owner': owner, 'kind': kind.value, 'request_id': request_id})


def checked(record, owner, kind):
    if record is None or record.athlete_id != owner: raise intake.SetupNotFound('BODY_RECORD_NOT_FOUND')
    value = json.loads(record.contract_json)
    proposal = (BodyMassInput if kind == MASS else NutritionGoalInput).model_validate(value['proposal']).model_dump()
    domain.require(value['schema_version'] == SCHEMA and value['athlete_id'] == owner and value['kind'] == kind.value
        and value['artifact_id'] == record.artifact_id == identity(owner, kind, proposal['request_id'])
        and value['proposal'] == proposal and value['planning_authorized'] is False
        and value['workouts_created'] is False and value['diet_created'] is False
        and domain.digest({k: v for k, v in value.items() if k != 'content_hash'}) == value['content_hash'] == record.content_hash
        and record.schema_version == SCHEMA and record.artifact_kind == kind
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM and record.persisted_at is not None
        and datetime.fromisoformat(value['created_at']) == record.created_at,
        'BODY_STORAGE_INVALID')
    return value


async def rows(repository, session, owner, kind, cutoff=None):
    query = select(PlanningAuditArtifactRow.artifact_id).where(PlanningAuditArtifactRow.athlete_id == UUID(owner),
        PlanningAuditArtifactRow.artifact_kind == kind.value)
    if cutoff is not None: query = query.where(PlanningAuditArtifactRow.created_at <= cutoff)
    result = await session.execute(query.order_by(PlanningAuditArtifactRow.created_at, PlanningAuditArtifactRow.artifact_id).limit(LIMIT + 1))
    ids = result.scalars().all()
    domain.require(len(ids) <= LIMIT, 'BODY_HISTORY_LIMIT')
    records = [await repository.get(artifact_kind=kind, artifact_id=key) for key in ids]
    if cutoff is not None:
        domain.require(all(record is not None and record.persisted_at is not None
            and record.persisted_at <= cutoff for record in records), 'BODY_SOURCE_CHANGED_RETRY')
    return records


def ref(value): return {'artifact_id': value['artifact_id'], 'content_hash': value['content_hash']}


def receipt(value, record, reused=False):
    return {'artifact': value, 'committed': True, 'reused': reused, 'durable_available_at': record.persisted_at.isoformat()}


async def put(repository, owner, kind, proposal, *, created_at, source=None):
    key = identity(owner, kind, proposal['request_id'])
    found = await repository.get(artifact_kind=kind, artifact_id=key)
    if found is not None:
        existing = checked(found, owner, kind)
        domain.require(existing['proposal'] == proposal and existing['source'] == source, 'BODY_REQUEST_CONFLICT')
        return existing, found
    artifact = {'schema_version': SCHEMA, 'kind': kind.value, 'athlete_id': owner, 'artifact_id': key,
        'proposal': proposal, 'source': source, 'created_at': created_at,
        'planning_authorized': False, 'workouts_created': False, 'diet_created': False}
    artifact['content_hash'] = domain.digest(artifact)
    await repository.save(AuditArtifactRecord(artifact_kind=kind, artifact_id=key, athlete_id=owner, schema_version=SCHEMA,
        created_at=datetime.fromisoformat(created_at), content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=artifact['content_hash'], contract_json=canonical_json(artifact)))
    record = await repository.get(artifact_kind=kind, artifact_id=key)
    domain.require(checked(record, owner, kind) == artifact, 'BODY_STORAGE_INVALID')
    return artifact, record


def _item(value):
    p = value['proposal']
    return {'measurement_id': value['artifact_id'], 'value_kg': p['value_kg'], 'recorded_on': p['recorded_on'],
        'recorded_at': value['created_at'], 'source': 'profile' if value['source'] else 'manual',
        'source_reference': ref(value), 'note': p['note']}


async def observations(repository, session, owner, cutoff=None):
    modern = [checked(row, owner, MASS) for row in await rows(repository, session, owner, MASS, cutoff)]
    result = [_item(value) for value in modern]
    represented = {(r['recorded_on'], Decimal(r['value_kg'])) for r in result}
    legacy = {}
    for record in await rows(repository, session, owner, Kind.ATHLETE_PROFILE, cutoff):
        artifact = intake.decode(record, owner=owner, kind='profile')
        p = artifact['proposal']['data']
        values = []
        if p.get('body_mass_kg') and (p.get('body_mass_recorded_on') or p.get('body_measurements_recorded_on')):
            values.append((p.get('body_mass_recorded_on') or p['body_measurements_recorded_on'], p['body_mass_kg'], 'profile'))
        for observation in [*p.get('manual_observations', []), *artifact.get('imported_observations', [])]:
            if observation.get('metric') == 'body_mass_kg' and observation.get('start_date') == observation.get('end_date') and observation.get('aggregation', 'single') == 'single':
                values.append((observation['end_date'], observation['value'], 'imported' if observation.get('artifact_id') else 'manual'))
        for day, number, source in values:
            logical = (day, Decimal(number))
            if Decimal(number) <= 0 or logical in represented or logical in legacy: continue
            legacy[logical] = {'measurement_id': 'legacy:' + domain.digest({'owner': owner, 'day': day, 'value': str(Decimal(number))}),
                'value_kg': number, 'recorded_on': day, 'recorded_at': artifact['created_at'], 'source': source,
                'source_reference': domain.reference(artifact), 'note': 'Korábban rögzített mérés'}
    result.extend(legacy.values())
    domain.require(len(result) <= LIMIT, 'BODY_HISTORY_LIMIT')
    return sorted(result, key=lambda v: (v['recorded_on'], v['recorded_at'], v['measurement_id']), reverse=True)


async def projection(repository, session, owner, cutoff=None):
    values = await observations(repository, session, owner, cutoff)
    result = {'schema_version': 'body-mass-projection-v0.1', 'athlete_id': owner, 'current': values[0] if values else None,
        'total': len(values), 'latest_by': 'measurement_day_then_recorded_at'}
    result['content_hash'] = domain.digest(result)
    return result


async def stage_profile(repository, session, artifact, previous):
    owner, p = artifact['athlete_id'], artifact['proposal']['data']
    before = previous['proposal']['data'] if previous else {}
    new = []
    known = {v['observation_id']: v for v in before.get('manual_observations', [])}
    for observation in p.get('manual_observations', []):
        if observation.get('metric') == 'body_mass_kg' and observation['start_date'] == observation['end_date'] and observation.get('aggregation', 'single') == 'single' and known.get(observation['observation_id']) != observation:
            new.append((observation['value'], observation['end_date'], 'manual:' + observation['observation_id']))
    day = p.get('body_mass_recorded_on') or p.get('body_measurements_recorded_on')
    old_day = before.get('body_mass_recorded_on') or before.get('body_measurements_recorded_on')
    if p.get('body_mass_kg') and day and (p['body_mass_kg'], day) != (before.get('body_mass_kg'), old_day) and not any((Decimal(n), d) == (Decimal(p['body_mass_kg']), day) for n, d, _ in new):
        current = await projection(repository, session, owner)
        latest = current['current']
        if latest is None or (Decimal(latest['value_kg']), latest['recorded_on']) != (Decimal(p['body_mass_kg']), day):
            new.append((p['body_mass_kg'], day, 'profile_mass'))
    for number, day, path in new:
        token = str(uuid5(UUID(owner), artifact['artifact_id'] + ':' + path))
        proposal = BodyMassInput(request_id=token, value_kg=number, recorded_on=day).model_dump()
        await put(repository, owner, MASS, proposal, created_at=artifact['created_at'],
            source={'profile_reference': domain.reference(artifact), 'field': path})


async def read_state(*, repository, session, owner, limit=100, offset=0):
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        values = await observations(repository, session, owner)
        goals = [checked(row, owner, GOAL) for row in await rows(repository, session, owner, GOAL)]
        legacy = []
        if not goals:
            programs = await rows(repository, session, owner, Kind.CYCLE_PROGRAM_REGISTRATION)
            artifacts = []
            for record in programs:
                a = json.loads(record.contract_json)
                domain.require(a.get('athlete_id') == owner and a.get('content_hash') == record.content_hash == domain.digest({k: v for k, v in a.items() if k != 'content_hash'}), 'BODY_STORAGE_INVALID')
                artifacts.append(a)
            represented = set()
            for a in reversed(artifacts):
                for goal in a['proposal']['goals']:
                    if goal['key'] in {'weight_loss', 'weight_maintenance'}:
                        logical = (a.get('program_family_id', a['proposal']['program_id']), goal['key'])
                        if logical in represented: continue
                        represented.add(logical)
                        legacy.append({'program_title': a['proposal']['title'], 'program_reference': ref(a), 'goal': goal['key'], 'body_mass': goal.get('body_mass')})
        value = {'schema_version': SCHEMA, 'athlete_id': owner,
            'local_today': intake._now().astimezone(ZoneInfo(user.timezone)).date().isoformat(),
            'current': values[0] if values else None, 'items': values[offset:offset + limit], 'total': len(values),
            'limit': limit, 'offset': offset, 'has_more': offset + limit < len(values),
            'latest_by': 'measurement_day_then_recorded_at', 'nutrition_goal': goals[-1] if goals else None,
            'legacy_goals': legacy, 'diet_planning_available': False}
        value['content_hash'] = domain.digest(value)
        return value
    finally: await intake.rollback(session)


async def save_measurement(*, repository, session, owner, proposal):
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        found = await repository.get(artifact_kind=MASS, artifact_id=identity(owner, MASS, proposal['request_id']))
        if found is not None:
            value = checked(found, owner, MASS); domain.require(value['proposal'] == proposal, 'BODY_REQUEST_CONFLICT')
            await intake.rollback(session); return receipt(value, found, True)
        now = intake._now(); today = now.astimezone(ZoneInfo(user.timezone)).date().isoformat()
        domain.require(proposal['recorded_on'] <= today, 'ATHLETE_OBSERVATION_IN_FUTURE')
        current = await intake.latest(repository, session, owner, 'profile')
        if current: now = max(now, datetime.fromisoformat(current[0]['created_at']) + timedelta(microseconds=1))
        value, record = await put(repository, owner, MASS, proposal, created_at=now.isoformat())
        latest = (await projection(repository, session, owner))['current']
        data = dict(current[0]['proposal']['data']) if current else ProfileData().model_dump()
        if latest and (data.get('body_mass_kg'), data.get('body_mass_recorded_on') or data.get('body_measurements_recorded_on')) != (latest['value_kg'], latest['recorded_on']):
            data.update(body_mass_kg=latest['value_kg'], body_mass_recorded_on=latest['recorded_on'])
            profile_proposal = ProfileInput.model_validate({'request_id': str(uuid5(UUID(owner), 'body-mass-profile:' + proposal['request_id'])),
                'previous_reference': domain.reference(current[0]) if current else None, 'data': data}).model_dump()
            artifact = domain.make_artifact(owner=owner, kind='profile', proposal=profile_proposal, created_at=now.isoformat(),
                timezone_name=user.timezone, previous=current[0] if current else None,
                observations=current[0].get('imported_observations', []) if current else [])
            await intake.persist(repository, session, artifact, 'profile', sync_mass=False)
        else: await intake.commit(session)
        return receipt(value, record)
    except BaseException:
        await intake.rollback(session); raise


async def save_goal(*, repository, session, owner, proposal):
    intake._require_session(repository, session)
    try:
        await intake.lock_owner(session, owner)
        found = await repository.get(artifact_kind=GOAL, artifact_id=identity(owner, GOAL, proposal['request_id']))
        if found is not None:
            value = checked(found, owner, GOAL); domain.require(value['proposal'] == proposal, 'BODY_REQUEST_CONFLICT')
            await intake.rollback(session); return receipt(value, found, True)
        values = [checked(row, owner, GOAL) for row in await rows(repository, session, owner, GOAL)]
        previous = values[-1] if values else None
        domain.require(proposal['previous_reference'] == (ref(previous) if previous else None), 'NUTRITION_GOAL_CHANGED')
        current = (await projection(repository, session, owner))['current']
        if proposal['goal'] in {'weight_loss', 'weight_gain'}:
            domain.require(current is not None, 'NUTRITION_CURRENT_MASS_REQUIRED')
            target, mass = Decimal(proposal['target_kg']), Decimal(current['value_kg'])
            domain.require(target < mass if proposal['goal'] == 'weight_loss' else target > mass, 'NUTRITION_TARGET_DIRECTION')
        now = intake._now()
        if previous: now = max(now, datetime.fromisoformat(previous['created_at']) + timedelta(microseconds=1))
        value, record = await put(repository, owner, GOAL, proposal, created_at=now.isoformat())
        await intake.commit(session)
        return receipt(value, record)
    except BaseException:
        await intake.rollback(session); raise
