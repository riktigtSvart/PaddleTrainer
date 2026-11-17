"""Read saved menus and intake without replanning or changing training data."""
from datetime import date, timedelta
import json
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.planning.application import register_athlete_setup as intake
from app.planning.domain.athlete_setup import digest, require
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow
from app.schemas.nutrition import NutritionWrite
from app.services import nutrition as menus, nutrition_journal as journal
from app.services.nutrition_domain import catalog
from app.services import nutrition_timing

SCHEMA = 'nutrition-calendar-v0.2'


def dates(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    require(first.isoformat() == start and last.isoformat() == end
        and '1900-01-01' <= start <= end <= '2100-12-31'
        and 0 <= (last-first).days < 366, 'NUTRITION_CALENDAR_RANGE_INVALID')
    return [(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]


def project(sources, data, start, end, reported_sources=(), timing_context=None):
    wanted = set(dates(start, end)); selected = {}; bank = catalog()
    titles = {r['id']: r['title'] for r in bank['recipes']}
    for source in sources:  # newest first; replace the entire covered date
        plan = source['proposal']['data']['plan']
        if not plan:
            continue
        for i in range(plan['day_count']):
            day = (date.fromisoformat(plan['start_date'])+timedelta(days=i)).isoformat()
            if day not in wanted or day in selected:
                continue
            schedule = nutrition_timing.day_schedule(data, day, [m['slot'] for m in plan['meals'] if m['date'] == day], timing_context) if timing_context else None
            meals = []
            for m in plan['meals']:
                if m['date'] != day:
                    continue
                ref = menus.reference(source)
                report = next((e for e in data['entries'] if e['source']
                    and e['source']['date'] == day and e['source']['slot'] == m['slot']), None)
                original_source = next((s for s in reported_sources if report and menus.reference(s) == report['source']['reference']), None)
                original_plan = original_source['proposal']['data']['plan'] if original_source else None
                original = next((x for x in (original_plan or {}).get('meals', []) if x['date'] == day and x['slot'] == m['slot']), None)
                same = bool(report and (report['source']['reference'] == ref or original
                    and original['recipe_id'] == m['recipe_id'] and original['portion_factor'] == m['portion_factor']))
                timing = next((t for t in data['timings'] if t['date'] == day and t['slot'] == m['slot']), None)
                meals.append({**m, 'title': titles[m['recipe_id']], 'people': plan['people'], 'source': ref,
                    'planned_time': schedule[m['slot']]['time'] if schedule else timing['time'] if timing is not None else data['default_times'][m['slot']],
                    **({'timing': schedule[m['slot']]} if schedule else {}),
                    'status': report['status'] if same else 'planned',
                    'report_id': report['id'] if report else None, 'different_report': bool(report and not same)})
            selected[day] = meals
    return {'days': [{'date': day, 'meals': selected[day]} for day in sorted(selected)],
        'meal_count': sum(len(v) for v in selected.values()),
        'actual_entries': [e for e in data['entries'] if start <= e['date'] <= end],
        'workouts_changed': False, 'personal_energy_prescribed': False, 'nutrient_adequacy': 'not_evaluated'}


async def read(*, repository, session, owner, start, end):
    wanted = set(dates(start, end))
    intake._require_session(repository, session)
    try:
        user = await intake.lock_owner(session, owner)
        rows = (await session.execute(select(PlanningAuditArtifactRow.artifact_id, PlanningAuditArtifactRow.contract_json)
            .where(PlanningAuditArtifactRow.athlete_id == UUID(owner), PlanningAuditArtifactRow.artifact_kind == menus.KIND.value)
            .order_by(PlanningAuditArtifactRow.created_at.desc(), PlanningAuditArtifactRow.artifact_id.desc()).limit(3001))).all()
        sources = []
        for key, raw in rows[:3000]:
            plan = NutritionWrite.model_validate(json.loads(raw)['proposal']).data.plan
            if plan is None:
                continue
            covered = {(date.fromisoformat(plan.start_date)+timedelta(days=i)).isoformat() for i in range(plan.day_count)} & wanted
            if covered:
                sources.append(menus.checked(await repository.get(artifact_kind=menus.KIND, artifact_id=key), owner))
                wanted -= covered
            if not wanted:
                break
        require(len(rows) <= 3000 or not wanted, 'NUTRITION_CALENDAR_HISTORY_LIMIT')
        saved, journal_sources = await journal.latest(repository, session, owner)
        now = intake._now()
        log = {'schema_version': journal.SCHEMA, 'athlete_id': owner, 'timezone': user.timezone,
            'now': now.isoformat(), 'local_today': now.astimezone(ZoneInfo(user.timezone)).date().isoformat(),
            'saved': saved, 'reference': menus.reference(saved), 'sources': journal_sources, **journal.FLAGS}
        log['content_hash'] = digest(log)
        data = saved['proposal']['data'] if saved else journal.JournalData().model_dump()
        timing_context = await nutrition_timing.context(session, owner, user.timezone, start, end, now)
        value = {'schema_version': SCHEMA, 'athlete_id': owner, 'timezone': user.timezone,
            'start_date': start, 'end_date': end, 'catalog': catalog(), 'sources': sources, 'journal': log,
            'timing_context': timing_context,
            'result': project(sources, data, start, end, journal_sources, timing_context), 'read_only': True}
        value['content_hash'] = digest(value)
        return value
    finally:
        await intake.rollback(session)
