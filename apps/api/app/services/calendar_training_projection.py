"""Read-only calendar purpose and choices, bound to accepted own prescriptions.

No inference from a workout title/sport, no new review, no dose or goal writes.
Existing rows obtain their purpose from the immutable accepted source too.
"""
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select

from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row
from app.services import training_plan_policy as policy, training_plans as plans
from app.services import training_read_models as views

SCHEMA = "calendar-training-plan-v0.1"


class PlanningRead:
    """Owner-bound, request-local verification; never a cross-request cache.

    Equality covers the complete immutable record, including persistence and
    owner metadata. A changed body or metadata must be verified again.
    """
    def __init__(self, repository, owner):
        self.repository, self.owner, self.records = repository, owner, {}

    def decode(self, row):
        if row.artifact_kind == views.KIND.value:
            return views.decode(self.repository._from_row(row), self.owner)
        return self.decode_record(self.repository._from_row(row))

    def decode_record(self, record):
        key = (record.artifact_kind, record.artifact_id)
        previous = self.records.get(key)
        if previous is None or previous[0] != record:
            previous = (record, plans.decode(record, self.owner))
            self.records[key] = previous
        return previous[1]

    def review_order(self, value):
        return policy.at(value['created_at']), value['artifact_id']


async def latest_record(repository, session, owner, kind, program_id, *, alternatives_for=None, accepted_review_id=None, reader=None):
    # Day pickers have their own review stream; they must not replace the
    # programme-wide planning/calibration history or its accepted date range.
    regular = ~Row.contract_json.contains('"alternatives_for":')
    scope = or_(regular, Row.contract_json.contains('"alternatives_for":' + plans.canonical_json(alternatives_for)),
                Row.artifact_id == accepted_review_id) if alternatives_for else regular
    if reader is not None:
        row = (await session.execute(select(Row).where(
            Row.athlete_id == UUID(owner), Row.artifact_kind == views.KIND.value,
            Row.schema_version == views.INDEX_SCHEMA,
            Row.contract_json.contains('"source_kind":' + json.dumps(kind.value)),
            Row.contract_json.contains('"program_id":' + json.dumps(program_id)), scope,
        ).order_by(Row.created_at.desc(), Row.artifact_id.desc()).limit(1))).scalar_one_or_none()
        if row is not None:
            plans.require(reader.owner == owner, 'TRAINING_PLAN_STORAGE_INVALID')
            index = views.decode_index(repository._from_row(row), owner)
            value = (await views.load_many(repository, session, owner, kind, [index['source_reference']['artifact_id']])).get(index['source_reference']['artifact_id'])
            plans.require(value is not None and reference(value) == index['source_reference'], 'TRAINING_PLAN_STORAGE_INVALID')
            plans.require(value['program_id'] == program_id, 'TRAINING_PLAN_STORAGE_INVALID')
            return value
    row = (await session.execute(select(Row).where(
        Row.athlete_id == UUID(owner), Row.artifact_kind == kind.value,
        Row.contract_json.contains('"program_id":' + json.dumps(program_id)),
        scope,
    ).order_by(Row.created_at.desc(), Row.artifact_id.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        return None
    plans.require(reader is None or reader.owner == owner, 'TRAINING_PLAN_STORAGE_INVALID')
    value = reader.decode(row) if reader else plans.decode(repository._from_row(row), owner)
    plans.require(value['program_id'] == program_id, 'TRAINING_PLAN_STORAGE_INVALID')
    return value


async def latest_scoped(session, owner, requests, reader):
    """One latest row per exact workout/hash scope in one bounded SQL query."""
    plans.require(reader.owner == owner, 'TRAINING_PLAN_STORAGE_INVALID')
    if not requests:
        return {}
    # Bound SQL expression depth and parameter count for dense year views too.
    if len(requests) > 100:
        items, result = list(requests.items()), {}
        for offset in range(0, len(items), 100):
            result.update(await latest_scoped(session, owner, dict(items[offset:offset + 100]), reader))
        return result
    matches = [(and_(Row.contract_json.contains('"program_id":' + json.dumps(program)),
                     Row.contract_json.contains('"alternatives_for":' + plans.canonical_json(scope))), key)
               for key, (program, scope) in requests.items()]
    ranked = select(Row.artifact_id, func.row_number().over(
        partition_by=case(*matches), order_by=(Row.created_at.desc(), Row.artifact_id.desc())).label('position')).where(
            Row.athlete_id == UUID(owner), Row.artifact_kind == views.KIND.value,
            Row.schema_version == views.INDEX_SCHEMA,
            Row.contract_json.contains('"source_kind":"training_plan_review"'),
            or_(*(condition for condition, _ in matches))).subquery()
    rows = list((await session.execute(select(Row).where(
        Row.athlete_id == UUID(owner), Row.artifact_kind == views.KIND.value,
        Row.artifact_id.in_(select(ranked.c.artifact_id).where(ranked.c.position == 1)),
    ))).scalars())
    plans.require(len(rows) <= len(requests), 'TRAINING_PLAN_HISTORY_LIMIT')
    indices = [views.decode_index(reader.repository._from_row(row), owner) for row in rows]
    loaded = await views.load_many(reader.repository, session, owner, Kind.TRAINING_PLAN_REVIEW,
        [i['source_reference']['artifact_id'] for i in indices])
    result = {}
    for index in indices:
        value = loaded.get(index['source_reference']['artifact_id'])
        plans.require(value is not None and reference(value) == index['source_reference'], 'TRAINING_PLAN_STORAGE_INVALID')
        scope = value.get('alternatives_for')
        key = (scope or {}).get('workout_id')
        plans.require(key in requests and value['program_id'] == requests[key][0]
                      and scope == requests[key][1] == value['inputs'].get('alternatives_for'),
                      'TRAINING_PLAN_STORAGE_INVALID')
        result[key] = value
    return result


async def project(*, owner, workouts, repository, session, now, executed=(), approved=(), local_today=None):
    own = [w for w in workouts if w.source == policy.SOURCE and w.polar_target_id is None
           and isinstance((w.raw_data or {}).get(policy.MARKER), dict)]
    if not own:
        return {}
    markers = {str(w.id): w.raw_data[policy.MARKER] for w in own}
    review_ids = {m.get('review_id') for m in markers.values() if isinstance(m.get('review_id'), str)}
    if not review_ids:
        return {}
    rows = list((await session.execute(select(Row).where(
        Row.athlete_id == UUID(owner), Row.artifact_kind == Kind.TRAINING_PLAN_ACCEPTANCE.value,
        or_(*(Row.contract_json.contains(json.dumps(key)) for key in sorted(review_ids))),
    ).limit(plans.LIMIT + 1))).scalars())
    plans.require(len(rows) <= plans.LIMIT, 'TRAINING_PLAN_HISTORY_LIMIT')
    reader, accepted = PlanningRead(repository, owner), {}
    for row in rows:
        value = reader.decode(row)
        for key, captured in value['created_workouts'].items():
            if key in markers and captured['marker'] == markers[key]:
                accepted[key] = (value, captured)
    source_ids = {markers[key].get('review_id') for key in accepted}
    sources = await views.load_many(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, source_ids)
    snapshots = {str(w.id): plans.snapshot(w) for w in own if str(w.id) in accepted}
    requests = {key: (value['program_id'], {'schema_version': 'workout-alternatives-request-v0.1',
        'workout_id': key, 'expected_workout_hash': snapshots[key][1]}) for key, (value, _) in accepted.items()}
    scoped = await latest_scoped(session, owner, requests, reader)
    regular = {program: await latest_record(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, program, reader=reader)
               for program in sorted({program for program, _ in requests.values()})}
    projected = {}
    for w in own:
        key = str(w.id)
        if key not in accepted:
            continue
        acceptance, captured = accepted[key]
        marker = markers[key]
        rid = marker.get('review_id')
        plans.require(rid in sources, 'TRAINING_PLAN_STORAGE_INVALID')
        source = sources[rid]
        plans.require(reference(source) == acceptance['review_reference'] and
                      source['program_id'] == acceptance['program_id'] == marker.get('program_id'),
                      'TRAINING_PLAN_STORAGE_INVALID')
        candidate = next((c for c in source['result']['create'] if c['candidate_key'] == captured['candidate_key']), None)
        plans.require(candidate is not None and captured['candidate_key'] == marker.get('candidate_key'),
                      'TRAINING_PLAN_STORAGE_INVALID')
        workout, actual_hash = snapshots[key]
        raw = plans.planning_inputs.wire({k: v for k, v in (w.raw_data or {}).items() if k != policy.MARKER})
        # A completion status does not change the original intended purpose.
        normalized_hash = digest({'workout': {**workout, 'status': 'PLANNED'}, 'raw_data': raw})
        if normalized_hash != captured['workout_hash']:
            continue  # A changed prescription must not acquire a false purpose.
        eligible = (actual_hash == captured['workout_hash'] and w.status.value in {'PLANNED', 'DRAFT', 'SCHEDULED'}
                    and w.planned_start_time is not None and (plans.aware(w.planned_start_time) > now
                        or w.date.isoformat() == (local_today or now.astimezone(ZoneInfo(source["timezone_name"])).date().isoformat()))
                    and w.id not in executed and w.id not in approved)
        program_id = source['program_id']
        current = max((v for v in (source, regular.get(program_id), scoped.get(key)) if v is not None), key=reader.review_order)
        group = next((g for g in (current or {}).get('result', {}).get('alternatives', []) if g['date'] == workout['date']), None)
        timing = (current or {}).get('result', {}).get('alternative_availability', {}).get('by_candidate', {})
        from app.services.training_alternative_availability import live
        live_candidates = [c for c in (group or {}).get('candidates', [])
                           if c['candidate_key'] not in timing or live(timing[c['candidate_key']], now)]
        count, checked = None, None
        if eligible and current:
            unchanged = next((p for p in current['plan_snapshots'] if p['workout']['id'] == key
                              and p['workout_hash'] == actual_hash and p['replaceable']), None)
            group = next((g for g in current['result'].get('alternatives', []) if g['date'] == workout['date']), None)
            if unchanged and current['start_date'] <= workout['date'] <= current['end_date']:
                count = sum(c['candidate_key'] != candidate['candidate_key'] for c in live_candidates) if group else 0
                checked = current['created_at']
            elif current['artifact_id'] == source['artifact_id'] and group:
                # Immediately after acceptance the review predates the new row.
                # Its choices remain a labelled last-review indicator, not a
                # permission to write without checking the current snapshot.
                count = sum(c['candidate_key'] != candidate['candidate_key'] for c in live_candidates)
                checked = current['created_at']
        projected[key] = {'schema_version': SCHEMA, 'source_kind': 'accepted_training_plan',
            'program_reference': source['program_reference'], 'accepted_review_reference': reference(source),
            'candidate_key': candidate['candidate_key'], 'primary_goal': candidate['capability_key'],
            'role': candidate['role'], 'mesocycle_id': candidate['training_period_id'], 'date': workout['date'],
            'workout_hash': actual_hash, 'replaceable': eligible,
            'same_day_confirmation_required': eligible and w.date.isoformat() == (local_today or now.astimezone(ZoneInfo(source['timezone_name'])).date().isoformat()),
            'alternatives_count': count, 'alternatives_checked_at': checked}
        metadata = source['result'].get('prescription_context', {}).get('by_candidate', {}).get(candidate['candidate_key'])
        from app.services.training_alternative_variants import summary
        group = next((g for g in (current or {}).get('result',{}).get('alternatives',[]) if g['date'] == workout['date']),None)
        projected[key]['alternative_kinds'] = summary(candidate,metadata,live_candidates,
            (current or {}).get('result',{}).get('prescription_context',{}).get('by_candidate',{}), checked is not None)
        if metadata and candidate.get('blocks') and candidate['sport'] in {'KAYAK','RUNNING','SWIMMING','STRENGTH'}:
            if source.get('_read_model'):
                instructions = source['result']['instruction_context']['by_candidate'].get(candidate['candidate_key'])
                if instructions:
                    projected[key]['instructions'] = instructions
                continue
            from app.services.training_instructions import derive, matches_stored
            instructions = derive(candidate, metadata)
            stored = source['result'].get('instruction_context')
            if stored:
                plans.require(matches_stored(stored['by_candidate'].get(candidate['candidate_key']), candidate, metadata), 'TRAINING_PLAN_STORAGE_INVALID')
            projected[key]['instructions'] = instructions
    return projected
