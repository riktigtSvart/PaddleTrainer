"""Owned, read-only cycle goals and accepted time-budget waves.

Never runs a review or retroactively invents a load stage for a missing block.
"""
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.entities import TrainingPeriod, User
from app.planning.application import calendar_workspace as calendar
from app.planning.application import register_athlete_setup as setup
from app.planning.application import register_goal_protocol as goals
from app.planning.domain.athlete_setup import digest, reference
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
from app.services import planning_inputs
from app.services import training_read_models
from app.services.calendar_training_projection import latest_record, PlanningRead


def period_wire(p):
    return {'id': str(p.id), 'parent_id': str(p.parent_id) if p.parent_id else None,
            'title': p.title, 'period_type': p.period_type.value,
            'start_date': p.start_date.isoformat(), 'end_date': p.end_date.isoformat()}


async def context(*, owner, start, end, repository, session):
    setup._require_session(repository, session)
    try:
        now = calendar._now()
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        calendar.require(date(1900, 1, 1) <= first <= last <= date(2100, 12, 31) and (last - first).days < 366,
                         'CALENDAR_DATE_RANGE_INVALID')
        user = (await session.execute(select(User).where(User.id == UUID(owner)))).scalar_one()
        periods = list((await session.execute(select(TrainingPeriod).where(
            TrainingPeriod.user_id == UUID(owner), TrainingPeriod.period_type == 'MESOCYCLE',
            TrainingPeriod.start_date <= last, TrainingPeriod.end_date >= first,
        ).order_by(TrainingPeriod.start_date, TrainingPeriod.id).limit(101))).scalars())
        calendar.require(len(periods) <= 100, 'CALENDAR_RANGE_TOO_DENSE')
        parent_ids = {p.parent_id for p in periods if p.parent_id}
        parents = list((await session.execute(select(TrainingPeriod).where(
            TrainingPeriod.user_id == UUID(owner), TrainingPeriod.id.in_(parent_ids),
        ))).scalars()) if parent_ids else []
        versions = await planning_inputs.goal_versions(repository, session, owner,
            [period_wire(p) for p in periods + parents], now) if periods else []
        programs, rows, reader = {}, [], PlanningRead(repository, owner)
        for p in periods:
            wire = period_wire(p)
            macro = next((v for v in versions if v['kind'] == goals.MACRO_KIND.value and v['period_id'] == wire['parent_id']), None)
            directives = [d for d in macro['artifact']['proposal']['mesocycle_directives']
                if d['mesocycle_period_id'] == wire['id']] if macro else []
            program_id = (p.extra_data or {}).get('cycle_program_artifact_id')
            if program_id and program_id not in programs:
                acceptance = await latest_record(repository, session, owner, Kind.TRAINING_PLAN_ACCEPTANCE, program_id, reader=reader)
                reviewed = await latest_record(repository, session, owner, Kind.TRAINING_PLAN_REVIEW, program_id, reader=reader)
                accepted = None
                if acceptance:
                    source_id = acceptance['review_reference']['artifact_id']
                    accepted = (await training_read_models.load_many(repository, session, owner,
                        Kind.TRAINING_PLAN_REVIEW, [source_id])).get(source_id)
                    calendar.require(accepted is not None, 'CALENDAR_CYCLE_STORAGE_INVALID')
                    calendar.require(reference(accepted) == acceptance['review_reference'] and
                        accepted['program_id'] == program_id == acceptance['program_id'] and
                        datetime.fromisoformat(accepted['created_at']) <= datetime.fromisoformat(acceptance['created_at']) <= now,
                        'CALENDAR_CYCLE_STORAGE_INVALID')
                programs[program_id] = acceptance, accepted, reviewed
            acceptance, accepted, reviewed = programs.get(program_id, (None, None, None))
            blocks, wave_source, wave_status = [], None, 'not_accepted'
            if accepted:
                saved = next((v for v in accepted['inputs']['periods'] if v['id'] == wire['id']), None)
                coordination = accepted['result'].get('mesocycle_coordination') or {}
                if not saved or (saved['start_date'], saved['end_date']) != (wire['start_date'], wire['end_date']):
                    wave_status = 'dates_changed'
                elif coordination.get('mode') != 'coordinated':
                    wave_status = 'short_review'
                else:
                    blocks = [b for b in coordination['blocks'] if b['mesocycle_id'] == wire['id']]
                    wave_status = 'accepted' if blocks else 'outside_accepted_range'
                    if blocks:
                        wave_source = {'review_reference': reference(accepted), 'acceptance_reference': reference(acceptance),
                            'accepted_at': acceptance['created_at'], 'rules_version': coordination['rules_version']}
            report = None
            if reviewed:
                saved = next((v for v in reviewed['inputs']['periods'] if v['id'] == wire['id']), None)
                if saved and (saved['start_date'], saved['end_date']) == (wire['start_date'], wire['end_date']):
                    availability = reviewed['result'].get('preparation', {}).get('sport_availability') or {}
                    report = {'review_reference': reference(reviewed), 'created_at': reviewed['created_at'],
                        'goal_coverage': [v for v in availability.get('goal_coverage', []) if v['mesocycle_id'] == wire['id']],
                        'sports': availability.get('sports', [])}
                    comparison = reviewed['inputs'].get('strength_assessment', {}).get('source_comparison')
                    if comparison and not comparison['reusable']:
                        report['source_changes'] = comparison['changes']
                    profile = reviewed['inputs'].get('strength_assessment', {}).get('profile_comparison')
                    if profile and (profile['changed_fields'] or profile['source_reference_changed']):
                        report['profile_comparison'] = profile
            rows.append({'period': wire, 'goal_reference': reference(macro['artifact']) if macro else None,
                'goals': [{'capability_key': d['capability_key'], 'role': d['role'], 'rationale': d['rationale']} for d in directives],
                'wave_status': wave_status, 'wave_source': wave_source, 'blocks': blocks, 'latest_review': report})
        result = {'schema_version': 'calendar-cycle-context-v0.1', 'athlete_id': owner,
            'timezone_name': user.timezone, 'start_date': start, 'end_date': end,
            'retrieved_at': now.isoformat(), 'cycles': rows, 'has_more': False,
            'planning_authorized': False, 'workouts_changed': False, 'adaptation_measured': False}
        result['content_hash'] = digest(result)
        return result
    finally:
        await setup.rollback(session)
