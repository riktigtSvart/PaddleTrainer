"""Small immutable presentation records, prepared on writes, never a planner on GET.

The full original evidence stays in its original artifact. This is a verified
projection with its own hash and an explicit reference to that original.
"""
from copy import deepcopy
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.common.serialization import CONTENT_HASH_ALGORITHM, canonical_json
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row

SCHEMA = 'training-read-model-v0.1'
INDEX_SCHEMA = 'training-read-index-v0.1'
KIND = Kind.TRAINING_PLAN_READ_MODEL


def identity(source_id):
    return 'pt-training-view:' + source_id.removeprefix('pt-training-plan:')


def summarize(value, kind):
    """Project an already verified source once; no copied historical input tree."""
    if kind == Kind.TRAINING_PLAN_ACCEPTANCE:
        return deepcopy(value)
    from app.services.training_instructions import derive, matches_stored, library
    result = value['result']
    candidates = {c['candidate_key']: c for c in [*result['proposals'],
        *(c for g in result.get('alternatives', []) for c in g['candidates'])]}
    metadata = result.get('prescription_context', {}).get('by_candidate', {})
    prepared, compact_meta = {}, {}
    for key, candidate in candidates.items():
        meta = metadata.get(key)
        if not meta:
            continue
        compact_meta[key] = {k: deepcopy(meta[k]) for k in ('strength', 'introductory_strength', 'rpe', 'running', 'swimming') if k in meta}
        if candidate.get('blocks') and candidate['sport'] in {'KAYAK', 'RUNNING', 'SWIMMING', 'STRENGTH'}:
            stored = result.get('instruction_context', {}).get('by_candidate', {}).get(key)
            if stored is not None and not matches_stored(stored, candidate, meta):
                raise ValueError('TRAINING_PLAN_STORAGE_INVALID')
            prepared[key] = derive(candidate, meta)
    return {**{k: deepcopy(value[k]) for k in ('artifact_id', 'athlete_id', 'program_id', 'program_reference',
        'created_at', 'start_date', 'end_date', 'timezone_name', 'content_hash')},
        **({'alternatives_for': deepcopy(value['alternatives_for'])} if value.get('alternatives_for') else {}),
        'inputs': {'periods': deepcopy(value['inputs']['periods']),
            'strength_assessment': {k: deepcopy(value['inputs'].get('strength_assessment', {}).get(k))
                for k in ('source_comparison', 'profile_comparison')},
            **({'alternatives_for': deepcopy(value['alternatives_for'])} if value.get('alternatives_for') else {})},
        'plan_snapshots': [{'workout': {k: p['workout'][k] for k in ('id', 'date')},
            **{k: deepcopy(p.get(k)) for k in ('workout_hash', 'replaceable', 'candidate_key')}} for p in value['plan_snapshots']],
        'result': {**{k: deepcopy(result.get(k)) for k in ('proposals', 'create', 'alternatives', 'alternative_availability',
            'mesocycle_coordination', 'policy')},
            'prescription_context': {'by_candidate': compact_meta},
            'instruction_context': {'by_candidate': prepared},
            'preparation': {'sport_availability': deepcopy(result.get('preparation', {}).get('sport_availability'))}},
        '_read_model': True, '_routine_library_hash': digest(library())}


async def save(repository, owner, kind, value):
    if kind not in {Kind.TRAINING_PLAN_REVIEW, Kind.TRAINING_PLAN_ACCEPTANCE}:
        return
    key = identity(value['artifact_id'])
    existing = await repository.get(artifact_kind=KIND, artifact_id=key)
    if existing:
        decode(existing, owner)
    else:
        body = {'schema_version': SCHEMA, 'artifact_id': key, 'athlete_id': owner,
            'source_kind': kind.value, 'source_reference': reference(value), 'program_id': value['program_id'],
            'created_at': value['created_at'], 'summary': summarize(value, kind)}
        await _save(repository, body)
    # Search these small catalogue entries, not historical multi-megabyte
    # evidence documents or the prepared exercise lists themselves.
    index = {'schema_version': INDEX_SCHEMA, 'artifact_id': key.replace('pt-training-view:', 'pt-training-view-index:'),
        'athlete_id': owner, 'source_kind': kind.value, 'source_reference': reference(value),
        'program_id': value['program_id'], 'created_at': value['created_at'],
        **({'alternatives_for': value['alternatives_for']} if value.get('alternatives_for') else {})}
    await _save(repository, index)


async def _save(repository, body):
    body['content_hash'] = digest(body)
    await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=body['artifact_id'], athlete_id=body['athlete_id'],
        schema_version=body['schema_version'], created_at=datetime.fromisoformat(body['created_at']),
        content_hash_algorithm=CONTENT_HASH_ALGORITHM, content_hash=body['content_hash'], contract_json=canonical_json(body)))


def decode_index(record, owner):
    import json
    from app.services.training_plans import require
    value = json.loads(record.contract_json)
    require(record.artifact_kind == KIND and record.athlete_id == value['athlete_id'] == owner
        and record.schema_version == value['schema_version'] == INDEX_SCHEMA and record.persisted_at is not None
        and record.artifact_id == value['artifact_id'] == identity(value['source_reference']['artifact_id']).replace('pt-training-view:', 'pt-training-view-index:')
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
        and canonical_json(value) == record.contract_json, 'TRAINING_PLAN_STORAGE_INVALID')
    return value


def decode(record, owner):
    import json
    from app.services.training_plans import require
    value = json.loads(record.contract_json)
    require(record.artifact_kind == KIND and record.athlete_id == value['athlete_id'] == owner
        and record.schema_version == value['schema_version'] == SCHEMA and record.persisted_at is not None
        and record.artifact_id == value['artifact_id'] == identity(value['source_reference']['artifact_id'])
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM
        and record.content_hash == value['content_hash'] == digest({k: v for k, v in value.items() if k != 'content_hash'})
        and canonical_json(value) == record.contract_json
        and reference(value['summary']) == value['source_reference']
        and value['summary']['athlete_id'] == owner and value['summary']['program_id'] == value['program_id'],
        'TRAINING_PLAN_STORAGE_INVALID')
    summary = value['summary']
    if summary.get('_read_model'):
        from app.services.training_instructions import library, derive, matches_stored
        current_library_hash = digest(library())
        if summary.get('_routine_library_hash') != current_library_hash:
            # Compatibility is confined to the two known historical Windows
            # interpretations. Never rewrite a captured dose or arbitrary text.
            summary = deepcopy(summary)
            candidates = {c['candidate_key']: c for c in [*summary['result']['proposals'],
                *(c for g in summary['result'].get('alternatives', []) for c in g['candidates'])]}
            meta = summary['result']['prescription_context']['by_candidate']
            prepared = summary['result']['instruction_context']['by_candidate']
            for key, stored in prepared.items():
                require(matches_stored(stored, candidates[key], meta[key]), 'TRAINING_PLAN_STORAGE_INVALID')
                prepared[key] = derive(candidates[key], meta[key])
            summary['_routine_library_hash'] = current_library_hash
    return summary


async def load_many(repository, session, owner, kind, ids):
    """Primary-key reads. Legacy fallback is bounded to specifically needed sources."""
    if not ids:
        return {}
    rows = list((await session.execute(select(Row).where(Row.athlete_id == UUID(owner),
        Row.artifact_kind == KIND.value, Row.artifact_id.in_([identity(i) for i in ids])))).scalars())
    result = {}
    for row in rows:
        value = decode(repository._from_row(row), owner)
        result[value['artifact_id']] = value
    missing = set(ids) - set(result)
    if missing:
        from app.services.training_plans import decode as full_decode
        rows = (await session.execute(select(Row).where(Row.athlete_id == UUID(owner),
            Row.artifact_kind == kind.value, Row.artifact_id.in_(missing)))).scalars()
        for row in rows:
            value = full_decode(repository._from_row(row), owner)
            result[row.artifact_id] = summarize(value, kind)
    return result
