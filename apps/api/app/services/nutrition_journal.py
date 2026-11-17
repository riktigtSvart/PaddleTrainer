"""Owned append-only journal snapshots; no planner, provider, diagnosis or dosing."""
from collections import Counter
from datetime import datetime, UTC, timedelta
from decimal import Decimal
import json
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from app.planning.application import register_athlete_setup as intake
from app.planning.domain.athlete_setup import digest, require
from app.planning.domain.common.serialization import canonical_json, CONTENT_HASH_ALGORITHM
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition_journal import JournalData, JournalWrite
from app.services import nutrition as menus
from app.services.nutrition_domain import catalog

SCHEMA = 'nutrition-journal-v0.1'
KIND = Kind.NUTRITION_JOURNAL
FLAGS = {'workouts_changed': False, 'personal_energy_prescribed': False, 'lab_based_dose_generated': False}


def identity(owner, token):
    return 'pt-nutrition-journal:' + digest({'owner': owner, 'request_id': token})


def instant(entry):
    """Round-trip civil time to reject DST gaps and require a fold when ambiguous."""
    try:
        zone = ZoneInfo(entry['timezone'])
    except (ZoneInfoNotFoundError, ValueError):
        require(False, 'NUTRITION_JOURNAL_TIMEZONE_INVALID')
    if entry['status'] == 'skipped':
        return None
    wall = datetime.fromisoformat(entry['date'] + 'T' + entry['time'])
    candidates = {}
    for fold in [0, 1]:
        local = wall.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == wall:
            candidates[fold] = utc
    require(candidates, 'NUTRITION_JOURNAL_DST_GAP')
    ambiguous = len(set(candidates.values())) > 1
    require(not ambiguous or entry['fold'] is not None, 'NUTRITION_JOURNAL_DST_FOLD_REQUIRED')
    require(ambiguous or entry['fold'] in {None, 0}, 'NUTRITION_JOURNAL_DST_FOLD_INVALID')
    return candidates[entry['fold'] or 0]


def project(raw, sources, at, timezone='Europe/Budapest'):
    data = JournalData.model_validate(raw).model_dump()
    today = at.astimezone(ZoneInfo(timezone)).date().isoformat()
    require(all(o['sampled_on'] <= today for o in data['observations']) and all(t['assessed_on'] <= today for t in data['targets']), 'NUTRITION_JOURNAL_FUTURE_ASSESSMENT')
    bank = catalog()
    recipes = {r['id']: r for r in bank['recipes']}
    lookup = {s['artifact_id']: s for s in sources}
    needed, entries, counts, times = set(), [], Counter(), {}
    for e in data['entries']:
        when = instant(e)
        require(when is None or when <= at, 'NUTRITION_JOURNAL_FUTURE_INTAKE')
        require(e['date'] <= at.astimezone(ZoneInfo(e['timezone'])).date().isoformat() if e['status'] == 'skipped' else True, 'NUTRITION_JOURNAL_FUTURE_INTAKE')
        if e['recipe_id'] is not None:
            require(e['recipe_id'] in recipes and e['title'] == recipes[e['recipe_id']]['title'], 'NUTRITION_JOURNAL_RECIPE_INVALID')
        if e['source']:
            source = e['source']; ref = source['reference']; saved = lookup.get(ref['artifact_id'])
            require(saved and saved['content_hash'] == ref['content_hash'], 'NUTRITION_JOURNAL_SOURCE_INVALID')
            needed.add(ref['artifact_id'])
            plan = saved['proposal']['data']['plan']
            choice = next((m for m in (plan or {}).get('meals', []) if m['date'] == source['date'] and m['slot'] == source['slot']), None)
            require(choice and choice['recipe_id'] == e['recipe_id'], 'NUTRITION_JOURNAL_SOURCE_INVALID')
            # Amount is a fraction of ONE person's planned serving, never household size.
            factor = str(Decimal(choice['portion_factor']) * Decimal(e['amount']))
        else:
            factor = e['amount'] if e['recipe_id'] and e['unit'] == 'portion' else None
        if e['status'] == 'eaten' and e['recipe_id']:
            counts[e['recipe_id']] += 1
            if e['source']:
                slot = e['source']['slot']; parts = list(map(int, e['time'].split(':')))
                times.setdefault(slot, []).append(parts[0] * 3600 + parts[1] * 60 + parts[2])
        entries.append({'id': e['id'], 'instant': when.isoformat() if when else None, 'recipe_portions': factor})
    require(needed == set(lookup), 'NUTRITION_JOURNAL_SOURCE_INVALID')
    typical = {}
    for slot, values in times.items():
        # An explicit proposal only, with at least three real observations.
        if len(values) >= 3:
            seconds = sorted(values)[len(values)//2]
            typical[slot] = f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'
    return {'entries': entries, 'eaten_count': sum(e['status'] == 'eaten' for e in data['entries']),
        'skipped_count': sum(e['status'] == 'skipped' for e in data['entries']),
        'favourites': [{'recipe_id': k, 'count': counts[k]} for k in sorted(counts, key=lambda k: (-counts[k], k))],
        'suggested_times': typical, 'nutrient_totals': None, 'nutrient_adequacy': 'not_evaluated',
        'assessment_mode': 'reported_targets' if any(t['assessed_on'] <= today and (t['valid_until'] is None or t['valid_until'] >= today) for t in data['targets']) else 'general_guidance'}


async def sources_for(repository, data, owner):
    refs = {e['source']['reference']['artifact_id']: e['source']['reference'] for e in data['entries'] if e['source']}
    require(len(refs) <= 100, 'NUTRITION_JOURNAL_SOURCE_LIMIT')
    result = []
    for key in sorted(refs):
        source = menus.checked(await repository.get(artifact_kind=menus.KIND, artifact_id=key), owner)
        require(source['content_hash'] == refs[key]['content_hash'], 'NUTRITION_JOURNAL_SOURCE_INVALID')
        result.append(source)
    return result


async def checked(repository, record, owner):
    require(record is not None and record.athlete_id == owner and record.artifact_kind == KIND, 'NUTRITION_JOURNAL_STORAGE_INVALID')
    value = json.loads(record.contract_json)
    p = JournalWrite.model_validate(value['proposal']).model_dump()
    sources = await sources_for(repository, p['data'], owner)
    at = datetime.fromisoformat(value['created_at'])
    require(value['schema_version'] == record.schema_version == SCHEMA and value['kind'] == KIND.value
        and value['athlete_id'] == owner and value['proposal'] == p
        and value['artifact_id'] == record.artifact_id == identity(owner, p['request_id'])
        and value['result'] == project(p['data'], sources, at, value['timezone'])
        and all(value.get(k) is v for k, v in FLAGS.items())
        and digest({k: v for k, v in value.items() if k != 'content_hash'}) == value['content_hash'] == record.content_hash
        and record.content_hash_algorithm == CONTENT_HASH_ALGORITHM and record.persisted_at is not None
        and at == record.created_at, 'NUTRITION_JOURNAL_STORAGE_INVALID')
    return value, sources


async def latest(repository, session, owner):
    rows = await session.execute(select(PlanningAuditArtifactRow.artifact_id).where(
        PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == KIND.value
    ).order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id.desc()).limit(1))
    key = rows.scalar_one_or_none()
    return await checked(repository, await repository.get(artifact_kind=KIND, artifact_id=key), owner) if key else (None, [])


async def read(*, repository, session, owner):
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        saved, sources = await latest(repository, session, owner)
        now = intake._now()
        value = {'schema_version': SCHEMA, 'athlete_id': owner, 'timezone': user.timezone, 'now': now.isoformat(),
            'local_today': now.astimezone(ZoneInfo(user.timezone)).date().isoformat(), 'saved': saved,
            'reference': menus.reference(saved), 'sources': sources, **FLAGS}
        value['content_hash'] = digest(value)
        return value
    finally:
        await intake.rollback(session)


async def save(*, repository, session, owner, proposal):
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        key = identity(owner, proposal['request_id'])
        found = await repository.get(artifact_kind=KIND, artifact_id=key)
        if found:
            value, sources = await checked(repository, found, owner)
            require(value['proposal'] == proposal, 'NUTRITION_JOURNAL_REQUEST_CONFLICT')
            await intake.rollback(session)
            return {**menus.receipt(value, found, True), 'sources': sources}
        previous, _ = await latest(repository, session, owner)
        require(proposal['previous_reference'] == menus.reference(previous), 'NUTRITION_JOURNAL_REVISION_CHANGED')
        now = intake._now()
        if previous:
            now = max(now, datetime.fromisoformat(previous['created_at']) + timedelta(microseconds=1))
        today = now.astimezone(ZoneInfo(user.timezone)).date().isoformat()
        data = proposal['data']
        require(all(o['sampled_on'] <= today for o in data['observations']) and all(t['assessed_on'] <= today for t in data['targets']), 'NUTRITION_JOURNAL_FUTURE_ASSESSMENT')
        old_entries = {e['id']: e for e in (previous or {}).get('proposal', {}).get('data', {}).get('entries', [])}
        for e in data['entries']:
            if old_entries.get(e['id']) != e:
                require(e['timezone'] == user.timezone or e['timezone'] == old_entries.get(e['id'], {}).get('timezone'), 'NUTRITION_JOURNAL_TIMEZONE_INVALID')
            require(e['date'] <= today if e['status'] == 'skipped' else True, 'NUTRITION_JOURNAL_FUTURE_INTAKE')
        sources = await sources_for(repository, data, owner)
        value = {'schema_version': SCHEMA, 'kind': KIND.value, 'athlete_id': owner, 'artifact_id': key,
            'created_at': now.isoformat(), 'timezone': user.timezone,
            'proposal': proposal, 'result': project(data, sources, now, user.timezone), **FLAGS}
        value['content_hash'] = digest(value)
        await repository.save(AuditArtifactRecord(artifact_kind=KIND, artifact_id=key, athlete_id=owner,
            schema_version=SCHEMA, created_at=now, content_hash_algorithm=CONTENT_HASH_ALGORITHM,
            content_hash=value['content_hash'], contract_json=canonical_json(value)))
        record = await repository.get(artifact_kind=KIND, artifact_id=key)
        await checked(repository, record, owner)
        await intake.commit(session)
        return {**menus.receipt(value, record, False), 'sources': sources}
    except BaseException:
        await intake.rollback(session)
        raise
