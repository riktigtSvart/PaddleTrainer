"""Read-only timings on the configured local database; no Polar calls or planning."""
import asyncio
from datetime import datetime, timedelta, UTC
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))


async def measure(session, owner, today):
    from app.planning.application import calendar_workspace, calendar_constraints
    from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository as Repository
    from app.services import calendar_cycles, calendar_saved_options
    first = today - timedelta(days=today.weekday())
    result = {'database_writes': 0, 'provider_calls': 0, 'planning_runs': 0, 'reads': {}}
    feed = None
    for label, operation in [('week', calendar_workspace.feed), ('four_weeks', calendar_workspace.feed), ('schedule', calendar_constraints.projected), ('cycles', calendar_cycles.context)]:
        end = first + timedelta(days=6 if label == 'week' else 27)
        times = []
        for _ in range(3):
            started = perf_counter()
            args = {'owner': owner, 'session': session, 'repository': Repository(session)}
            value = await operation(**args, **({'first': first.isoformat(), 'last': end.isoformat()} if label == 'schedule' else {'start': first.isoformat(), 'end': end.isoformat()}))
            times.append(perf_counter() - started)
            if label == 'four_weeks': feed = value
        result['reads'][label] = {'median_ms': round(median(times) * 1000, 1), 'response_bytes': len(json.dumps(value, ensure_ascii=False).encode())}
    target = next((p for p in (feed or {}).get('planned', []) if p.get('planning_context', {}).get('replaceable')), None)
    if target:
        times = []
        for _ in range(3):
            started = perf_counter()
            value = await calendar_saved_options.read(session=session, owner=owner, workout_id=target['id'])
            times.append(perf_counter() - started)
        result['reads']['alternatives'] = {'median_ms': round(median(times) * 1000, 1), 'candidates': len(value['candidates']), 'response_bytes': len(json.dumps(value, ensure_ascii=False).encode())}
    return result


async def main():
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models.entities import User
    try:
        async with SessionLocal() as session:
            user = (await session.execute(select(User).where(User.email == get_settings().demo_user_email))).scalar_one()
            owner, zone = str(user.id), user.timezone
            await session.rollback()
            print(json.dumps(await measure(session, owner, datetime.now(UTC).astimezone(ZoneInfo(zone)).date()), ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
