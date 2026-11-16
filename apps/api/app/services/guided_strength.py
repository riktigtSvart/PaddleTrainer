"""Owner-bound occasion, durable checkpoints, atomic activity + intake publication."""
import json
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.entities import Sport, User, WorkoutSession
from app.planning.application import register_athlete_setup as transactions
from app.planning.domain.athlete_setup import digest
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import (
    AuditArtifactKind,
    AuditArtifactRecord,
    AuditArtifactSaveStatus,
)
from app.planning.infrastructure.adapters.athlete_history import aware
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.planning.infrastructure.repositories.postgres_planning_audit import (
    SqlAlchemyPlanningAuditRepository,
)
from app.schemas.strength_calibration import parse_command, SCHEMA as CALIBRATION_SCHEMA, RULES as CALIBRATION_RULES
from app.services import guided_strength_domain as domain
from app.services import initial_assessment as intake
from app.services import strength_calibration_domain as calibration
from app.services.assessment_source_updates import registry_extension

KIND = AuditArtifactKind.GUIDED_STRENGTH_SESSION
ACTIVITY = AuditArtifactKind.GUIDED_STRENGTH_ACTIVITY
SCHEMA = domain.SCHEMA
LIMIT = 2000


class GuidedError(ValueError):
    pass


def require(value, code):
    if not value:
        raise GuidedError(code)


def _now():
    return datetime.now(UTC)


def identity(owner, token):
    return f'pt-guided-strength:{UUID(owner).hex}:{UUID(token).hex}'


def decode(record, owner):
    value = json.loads(record.contract_json)
    proposal = parse_command(value['proposal'])
    require(record.athlete_id == owner == value['athlete_id'] and record.artifact_kind == KIND
            and record.schema_version == value['schema_version'] == (CALIBRATION_SCHEMA if proposal.get('protocol_version') else SCHEMA)
            and value['rules_version'] == (CALIBRATION_RULES if proposal.get('protocol_version') else domain.RULES)
            and record.artifact_id == value['artifact_id'] == identity(owner, proposal['request_id'])
            and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
            and record.content_hash == value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
            and record.contract_json == canonical_json(value) and proposal == value['proposal']
            and record.persisted_at is not None and record.persisted_at.tzinfo is not None
            and record.created_at == datetime.fromisoformat(value['created_at']) and record.created_at.tzinfo is not None
            and value['planning_authorized'] is False and value['clinical_clearance'] is False,
            'GUIDED_STORAGE_INVALID')
    return value


async def load(repo, owner, key):
    row = await repo.get(artifact_kind=KIND, artifact_id=key)
    require(row is not None and row.athlete_id == owner, 'GUIDED_NOT_FOUND')
    value = decode(row, owner)
    base = value
    if value['base_reference'] is not None:
        base_row = await repo.get(artifact_kind=KIND, artifact_id=value['base_reference']['artifact_id'])
        require(base_row is not None and base_row.athlete_id == owner, 'GUIDED_STORAGE_INVALID')
        base = decode(base_row, owner)
        require(domain.reference(base) == value['base_reference'] and base['revision'] == 1 and base['session_id'] == value['session_id'], 'GUIDED_STORAGE_INVALID')
    if value['proposal']['previous_reference']:
        previous = await repo.get(artifact_kind=KIND, artifact_id=value['proposal']['previous_reference']['artifact_id'])
        require(previous is not None and previous.athlete_id == owner, 'GUIDED_STORAGE_INVALID')
        parent = decode(previous, owner)
        require(domain.reference(parent) == value['proposal']['previous_reference'] and parent['session_id'] == value['session_id']
                and parent['revision'] + 1 == value['revision'] and parent['created_at'] < value['created_at'], 'GUIDED_STORAGE_INVALID')
    return value, row, base


async def heads(repo, session, owner, cutoff=None):
    query = select(PlanningAuditArtifactRow.artifact_id).where(PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value)
    if cutoff:
        query = query.where(PlanningAuditArtifactRow.created_at >= cutoff - timedelta(days=56), PlanningAuditArtifactRow.created_at <= cutoff, PlanningAuditArtifactRow.persisted_at <= cutoff)
    keys = (await session.execute(query.order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(LIMIT + 1))).scalars().all()
    require(len(keys) <= LIMIT, 'GUIDED_HISTORY_LIMIT')
    result, seen = [], set()
    for key in keys:
        row = await repo.get(artifact_kind=KIND, artifact_id=key)
        value = decode(row, owner)
        if value['session_id'] not in seen:
            seen.add(value['session_id'])
            result.append((value, row))
    return result


async def receipt(repo, owner, value, row, base, reused):
    assessment = None
    if value['result'] and value['result'].get('assessment_reference'):
        stored, record = await intake.load(repo, owner, value['result']['assessment_reference']['artifact_id'])
        require(intake.reference(stored) == value['result']['assessment_reference'], 'GUIDED_STORAGE_INVALID')
        assessment = intake.receipt(stored, record, True)
    return {'artifact': value, 'base': base if base['artifact_id'] != value['artifact_id'] else None,
            'committed': True, 'reused': reused, 'durable_available_at': row.persisted_at.isoformat(),
            'assessment_receipt': assessment, 'planning_authorized': False, 'clinical_clearance': False,
            'activity_receipt': await activity_receipt(repo, owner, value['proposal']['request_id'])}


async def persist(repo, owner, value):
    value = domain.freeze(value)
    result = await repo.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=value['artifact_id'], athlete_id=owner,
        schema_version=value['schema_version'], created_at=datetime.fromisoformat(value['created_at']), content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=value['content_hash'], contract_json=canonical_json(value)))
    require(result.status == AuditArtifactSaveStatus.CREATED, 'GUIDED_STORAGE_INVALID')
    loaded = await load(repo, owner, value['artifact_id'])
    require(loaded[0] == value, 'GUIDED_STORAGE_INVALID')
    return loaded


async def capture_intake(session, repo, owner, user, now):
    return await intake.capture_context(session=session, repo=repo, owner=owner, user=user,
                                       today=now.astimezone(ZoneInfo(user.timezone)).date().isoformat())


async def available_recordings(session, owner, today, zone):
    low = datetime.combine(datetime.fromisoformat(today).date() - timedelta(days=7), datetime.min.time(), ZoneInfo(zone))
    rows = (await session.execute(select(WorkoutSession).where(WorkoutSession.user_id == UUID(owner),
        WorkoutSession.sport == Sport.STRENGTH, WorkoutSession.started_at >= low).order_by(WorkoutSession.started_at.desc(), WorkoutSession.id).limit(201))).scalars().all()
    require(len(rows) <= 200, 'GUIDED_WORKOUT_LIMIT')
    return [{'id': str(r.id), 'name': r.name, 'sport': r.sport.value, 'provider': r.external_provider,
             'started_at': aware(r.started_at).isoformat(), 'ended_at': aware(r.ended_at).isoformat() if r.ended_at else None,
             'duration_sec': r.duration_sec} for r in rows]


async def context(*, session, owner):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        now = _now()
        initial = await capture_intake(session, repo, owner, user, now)
        current = await heads(repo, session, owner)
        latest = await load(repo, owner, current[0][0]['artifact_id']) if current else None
        value = {'schema_version': SCHEMA, 'athlete_id': owner, 'local_today': initial['local_today'], 'timezone_name': user.timezone,
                 'server_now': now.isoformat(), 'intake': initial, 'preparation': domain.preparation(initial),
                 'latest': await receipt(repo, owner, *latest, True) if latest else None,
                 'history': [{'session_id': v['session_id'], 'reference': domain.reference(v), 'state': v['state'], 'created_at': v['created_at']} for v, _ in current],
                 'recordings': await available_recordings(session, owner, initial['local_today'], user.timezone),
                 'planning_authorized': False, 'clinical_clearance': False}
        value['calibration_protocols'] = calibration.protocols()
        value['content_hash'] = digest(value)
        return value
    finally:
        await transactions.rollback(session)


def changed_observations(previous, proposal):
    old = previous['proposal']['progress']
    # A completed result is immutable; applying it later only changes its intake binding.
    return canonical_json(old) != canonical_json(proposal['progress'])


async def finish_activity(session, owner, user, base, proposal, now):
    require(proposal['reviewed'], 'GUIDED_REVIEW_REQUIRED')
    progress = proposal['progress']
    require(progress['warmup_completed'] or any(r['observations'] for r in progress['results']), 'GUIDED_NO_OBSERVATIONS')
    require(progress['phase'] == 'review', 'GUIDED_REVIEW_REQUIRED')
    actual = calibration.observed(progress) if proposal.get('protocol_version') else [v for r in progress['results'] for v in r['observations']]
    if proposal['recording_mode'] == 'device':
        require(proposal['workout_session_id'] is not None, 'GUIDED_RECORDING_REQUIRED')
        row = (await session.execute(select(WorkoutSession).where(WorkoutSession.id == UUID(proposal['workout_session_id']), WorkoutSession.user_id == UUID(owner)).with_for_update())).scalar_one_or_none()
        require(row is not None and row.sport == Sport.STRENGTH and row.ended_at is not None
                and aware(row.started_at) <= aware(row.ended_at) <= now
                and aware(row.ended_at) >= datetime.fromisoformat(base['created_at'])
                and (aware(row.ended_at) - aware(row.started_at)).total_seconds() <= 21600
                and row.external_provider != 'PADDLETRAINER_GUIDED', 'GUIDED_RECORDING_INVALID')
        used = await planning_activities(SqlAlchemyPlanningAuditRepository(session), session, owner, now)
        require(not any(v['artifact']['workout_session_id'] == str(row.id) for v in used), 'GUIDED_RECORDING_ALREADY_USED')
        days = {v['performed_on'] for v in actual}
        low = aware(row.started_at).astimezone(ZoneInfo(user.timezone)).date().isoformat()
        high = aware(row.ended_at).astimezone(ZoneInfo(user.timezone)).date().isoformat()
        require(all(low <= day <= high for day in days), 'GUIDED_RECORDING_DATE_MISMATCH')
        return row, False
    require(proposal['no_other_recording_confirmed'] and proposal['workout_session_id'] is None
            and proposal['actual_start_at'] is not None and proposal['actual_end_at'] is not None, 'GUIDED_MANUAL_CLOCK_REQUIRED')
    first, last = datetime.fromisoformat(proposal['actual_start_at']), datetime.fromisoformat(proposal['actual_end_at'])
    require(datetime.fromisoformat(base['created_at']) - timedelta(seconds=60) <= first < last <= now and (last - first).total_seconds() <= 21600, 'GUIDED_MANUAL_CLOCK_INVALID')
    low, high = (d.astimezone(ZoneInfo(user.timezone)).date().isoformat() for d in (first, last))
    require(all(low <= v['performed_on'] <= high for v in actual), 'GUIDED_RECORDING_DATE_MISMATCH')
    key = uuid5(NAMESPACE_URL, 'paddletrainer:guided:' + owner + ':' + base['session_id'])
    require((await session.execute(select(WorkoutSession.id).where(WorkoutSession.id == key))).scalar_one_or_none() is None, 'GUIDED_RECORDING_CONFLICT')
    row = WorkoutSession(id=key, user_id=UUID(owner), external_provider='PADDLETRAINER_GUIDED', external_id=str(key),
        sport=Sport.STRENGTH, name='Kezdő erőfelmérés', started_at=first, ended_at=last,
        duration_sec=int((last - first).total_seconds()), created_at=now,
        raw_data={'paddletrainer_guided_assessment': {'session_id': base['session_id'], 'base_reference': domain.reference(base),
                  'source_kind': 'self_report', 'duration_basis': 'elapsed_including_rests', 'numeric_prediction_authorized': False}})
    session.add(row)
    await session.flush()
    return row, True


async def command(*, session, owner, proposal):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        user = await transactions.lock_owner(session, owner)
        proposal = parse_command(proposal)
        key = identity(owner, proposal['request_id'])
        old = await repo.get(artifact_kind=KIND, artifact_id=key)
        if old:
            loaded = await load(repo, owner, key)
            require(loaded[0]['proposal'] == proposal, 'GUIDED_REQUEST_CONFLICT')
            return await receipt(repo, owner, *loaded, True)
        now = _now()
        initial = await capture_intake(session, repo, owner, user, now)
        current = await heads(repo, session, owner)
        head = current[0][0] if current else None
        action = proposal['action']
        base = None
        if action == 'start':
            require(head is None or head['state'] in {'finished', 'abandoned'}, 'GUIDED_ACTIVE_EXISTS')
            require(head is None or not (head['result'] or {}).get('application_pending'), 'GUIDED_APPLICATION_PENDING')
            prepared = domain.preparation(initial)
            require(not prepared['issues'] and initial['reference'] == proposal['assessment_reference']
                    and initial['sources']['source_hash'] == proposal['source_hash'] and proposal['precheck_confirmed'], 'GUIDED_PREPARATION_CHANGED')
            place = next((v for v in prepared['locations'] if v['location_id'] == proposal['location_id']), None)
            require(place is not None and all(any(e['entry_id'] == key and e['ready'] for e in place['entries']) for key in proposal['selected_entry_ids']), 'GUIDED_SELECTION_INVALID')
            require(not any(r['observations'] or r['state'] != 'pending' for r in proposal['progress']['results'])
                    and not proposal['progress']['warmup_completed'] and proposal['progress']['phase'] == 'warmup', 'GUIDED_START_HAS_RESULTS')
            selected_patterns = {e['pattern'] for e in place['entries'] if e['entry_id'] in proposal['selected_entry_ids']}
            require(len(selected_patterns) == len(proposal['selected_entry_ids']), 'GUIDED_DISTINCT_PATTERNS_REQUIRED')
            session_id = str(uuid5(NAMESPACE_URL, owner + ':guided:' + proposal['request_id']))
            revision, previous_base = 1, None
        else:
            require(head is not None and proposal['previous_reference'] == domain.reference(head), 'GUIDED_REVISION_CONFLICT')
            _, _, base = await load(repo, owner, head['artifact_id'])
            require(head['state'] == 'active' or action == 'apply' and head['state'] == 'finished', 'GUIDED_ALREADY_CLOSED')
            require(proposal['selected_entry_ids'] == base['proposal']['selected_entry_ids']
                    and proposal['location_id'] == base['proposal']['location_id']
                    and proposal['recording_mode'] == base['proposal']['recording_mode'], 'GUIDED_SELECTION_CHANGED')
            require(all(proposal.get(k) == base['proposal'].get(k) for k in ['protocol_version', 'protocol_hash', 'measurement_mode']), 'CALIBRATION_PROTOCOL_CHANGED')
            if action != 'apply':
                require(proposal['assessment_reference'] == base['proposal']['assessment_reference'] and proposal['source_hash'] == base['proposal']['source_hash'], 'GUIDED_BINDING_CHANGED')
            else:
                require(not changed_observations(head, proposal) and all(proposal[k] == head['proposal'][k] for k in ['actual_start_at', 'actual_end_at', 'workout_session_id', 'no_other_recording_confirmed']) and proposal['reviewed'] and head['result']['assessment_reference'] is None, 'GUIDED_CLOSED_RESULTS_CHANGED')
            session_id, revision, previous_base = base['session_id'], head['revision'] + 1, domain.reference(base)
            now = max(now, datetime.fromisoformat(head['created_at']) + timedelta(microseconds=1))
        start_day = datetime.fromisoformat(base['created_at'] if base else now.isoformat()).astimezone(ZoneInfo(user.timezone)).date().isoformat()
        try:
            measurement_protocols = (base['measurement_protocols'] if base else calibration.selected_protocols(initial, proposal['selected_entry_ids'], proposal['measurement_mode'], proposal['protocol_hash'])) if proposal.get('protocol_version') else None
            domain.validate_progress(proposal, start_day, initial['local_today'], measurement_protocols)
        except ValueError as exc:
            raise GuidedError(str(exc)) from None
        state, result, application_context = 'active', None, None
        if action == 'abandon':
            require(not proposal['progress']['warmup_completed'] and not any(r['observations'] for r in proposal['progress']['results']), 'GUIDED_ACTIVITY_MUST_BE_RECORDED')
            state = 'abandoned'
        if action in {'finish', 'apply'}:
            if action == 'finish':
                row, created = await finish_activity(session, owner, user, base, proposal, now)
                result = {'workout_session_id': str(row.id), 'workout_created': created,
                          'workout': {'id': str(row.id), 'athlete_id': owner, 'sport': row.sport.value,
                                      'started_at': aware(row.started_at).isoformat(), 'ended_at': aware(row.ended_at).isoformat(),
                                      'duration_sec': row.duration_sec, 'provider': row.external_provider},
                          'assessment_reference': None, 'stop_required': domain.stop_required(proposal['progress'])}
            else:
                result = dict(head['result'])
            compatible = initial['reference'] == proposal['assessment_reference'] and initial['sources']['source_hash'] == proposal['source_hash'] and (not initial['sources_changed'] or registry_extension(initial))
            if action == 'apply':
                require(compatible, 'GUIDED_PREPARATION_CHANGED')
            if compatible:
                old_entries = {v['id']: v for v in base['intake_context']['data']['exercises']}
                new_entries = {v['id']: v for v in initial['data']['exercises']}
                compatible = all(key in new_entries and new_entries[key]['exercise_id'] == old_entries[key]['exercise_id'] and new_entries[key]['location_id'] == old_entries[key]['location_id'] for key in proposal['selected_entry_ids'])
            if compatible:
                application_context = initial
                projected = domain.project_intake(initial['data'], proposal['progress'], initial['local_today'])
                value, _, _ = await intake.stage(session=session, repo=repo, owner=owner, user=user,
                    proposal={'request_id': proposal['request_id'], 'previous_reference': initial['reference'],
                              'source_hash': initial['sources']['source_hash'], 'data': projected})
                result['assessment_reference'] = intake.reference(value)
                now = max(now, datetime.fromisoformat(value['created_at']) + timedelta(microseconds=1))
            result['application_pending'] = result['assessment_reference'] is None
            state = 'finished'
        value = {'schema_version': CALIBRATION_SCHEMA if proposal.get('protocol_version') else SCHEMA,
                 'rules_version': CALIBRATION_RULES if proposal.get('protocol_version') else domain.RULES, 'artifact_id': key, 'athlete_id': owner,
                 'created_at': now.isoformat(), 'session_id': session_id, 'revision': revision, 'base_reference': previous_base,
                 'state': state, 'proposal': proposal, 'intake_context': initial if action == 'start' else None,
                 'preparation': domain.preparation(initial) if action == 'start' else None,
                 'application_context': application_context, 'result': result,
                 'planning_authorized': False, 'clinical_clearance': False}
        if proposal.get('protocol_version'):
            value['measurement_protocols'] = measurement_protocols if action == 'start' else None
        loaded = await persist(repo, owner, value)
        await persist_activity(repo, owner, loaded[0], head)
        await transactions.commit(session)
        return await receipt(repo, owner, *loaded, False)
    finally:
        await transactions.rollback(session)


def activity_identity(owner, token):
    return f'pt-guided-activity:{UUID(owner).hex}:{UUID(token).hex}'


def decode_activity(record, owner):
    value = json.loads(record.contract_json)
    require(record.athlete_id == value['athlete_id'] == owner and record.artifact_kind == ACTIVITY
            and record.schema_version == value['schema_version'] == ('guided-strength-activity-v0.2' if value.get('measurement_protocol_version') else 'guided-strength-activity-v0.1')
            and value.get('measurement_protocol_version') in {None, 'strength-calibration-v0.3'}
            and record.artifact_id == value['artifact_id'] == activity_identity(owner, value['request_id'])
            and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM and record.persisted_at is not None
            and record.content_hash == value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
            and record.contract_json == canonical_json(value)
            and value['planning_authorized'] is False and value['clinical_clearance'] is False,
            'GUIDED_ACTIVITY_INVALID')
    return value


async def activity_receipt(repo, owner, token):
    record = await repo.get(artifact_kind=ACTIVITY, artifact_id=activity_identity(owner, token))
    require(record is not None, 'GUIDED_ACTIVITY_INVALID')
    return {'artifact': decode_activity(record, owner), 'committed': True, 'durable_available_at': record.persisted_at.isoformat()}


async def persist_activity(repo, owner, value, previous):
    result = value['result'] or {}
    proof = {'schema_version': 'guided-strength-activity-v0.1', 'artifact_id': activity_identity(owner, value['proposal']['request_id']),
             'athlete_id': owner, 'session_id': value['session_id'], 'request_id': value['proposal']['request_id'],
             'created_at': value['created_at'], 'state': value['state'], 'guided_reference': domain.reference(value),
             'previous_reference': domain.reference(decode_activity(await repo.get(artifact_kind=ACTIVITY, artifact_id=activity_identity(owner, previous['proposal']['request_id'])), owner)) if previous and previous['session_id'] == value['session_id'] else None,
             'workout_session_id': result.get('workout_session_id'), 'assessment_reference': result.get('assessment_reference'),
             'stop_required': domain.stop_required(value['proposal']['progress']),
             'planning_authorized': False, 'clinical_clearance': False}
    if value['proposal'].get('protocol_version'):
        proof['schema_version'] = 'guided-strength-activity-v0.2'
        proof['measurement_protocol_version'] = value['proposal']['protocol_version']
    proof['content_hash'] = digest(proof)
    saved = await repo.save(AuditArtifactRecord(artifact_kind=ACTIVITY, artifact_id=proof['artifact_id'], athlete_id=owner,
        schema_version=proof['schema_version'], created_at=datetime.fromisoformat(proof['created_at']), content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash=proof['content_hash'], contract_json=canonical_json(proof)))
    require(saved.status == AuditArtifactSaveStatus.CREATED, 'GUIDED_ACTIVITY_INVALID')


async def planning_activities(repo, session, owner, cutoff):
    keys = (await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == ACTIVITY.value,
        PlanningAuditArtifactRow.created_at >= cutoff - timedelta(days=56), PlanningAuditArtifactRow.created_at <= cutoff,
        PlanningAuditArtifactRow.persisted_at <= cutoff,
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id).limit(LIMIT + 1))).scalars().all()
    require(len(keys) <= LIMIT, 'GUIDED_HISTORY_LIMIT')
    proofs, seen = [], set()
    for key in keys:
        row = await repo.get(artifact_kind=ACTIVITY, artifact_id=key)
        value = decode_activity(row, owner)
        if value['session_id'] not in seen:
            seen.add(value['session_id'])
            proofs.append({'artifact': value, 'committed': True, 'durable_available_at': row.persisted_at.isoformat()})
    return proofs


async def calibration_evidence(repo, session, owner, cutoff):
    values = []
    for value, _ in await heads(repo, session, owner, cutoff):
        if value['schema_version'] == CALIBRATION_SCHEMA and value['state'] == 'finished' and value['result']['assessment_reference']:
            loaded = await load(repo, owner, value['artifact_id'])
            values.append(await receipt(repo, owner, *loaded, True))
    return values


async def read_revision(*, session, owner, token):
    repo = SqlAlchemyPlanningAuditRepository(session)
    transactions._require_session(repo, session)
    try:
        loaded = await load(repo, owner, identity(owner, token))
        return await receipt(repo, owner, *loaded, True)
    finally:
        await transactions.rollback(session)
