"""Prepare compact calendar reads once. Original plans and evidence stay intact."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))


async def prepare(session, owner):
    from uuid import UUID
    from sqlalchemy import select
    from app.models.entities import PlannedWorkout
    from app.planning.domain.persistence.audit import AuditArtifactKind as Kind
    from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row
    from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository as Repository
    from app.services import training_plans as plans, training_read_models as views
    repository = Repository(session)
    existing = set((await session.execute(select(Row.artifact_id).where(Row.athlete_id == UUID(owner),
        Row.artifact_kind == views.KIND.value))).scalars())
    sources = list((await session.execute(select(Row.artifact_kind, Row.artifact_id).where(Row.athlete_id == UUID(owner),
        Row.artifact_kind.in_([Kind.TRAINING_PLAN_REVIEW.value, Kind.TRAINING_PLAN_ACCEPTANCE.value]))
        .order_by(Row.created_at, Row.artifact_id))).all())
    await session.rollback()
    prepared, skipped = 0, []
    for kind, source_id in sources:
        key = views.identity(source_id)
        if key in existing and key.replace('pt-training-view:', 'pt-training-view-index:') in existing:
            continue
        try:
            record = await repository.get(artifact_kind=Kind(kind), artifact_id=source_id)
            value = plans.decode(record, owner)
            await views.save(repository, owner, Kind(kind), value)
            await session.commit()
            prepared += 1
        except (ValueError, KeyError, TypeError):
            await session.rollback()
            skipped.append(source_id)
    active = list((await session.execute(select(PlannedWorkout.raw_data).where(PlannedWorkout.user_id == UUID(owner),
        PlannedWorkout.source == plans.policy.SOURCE, PlannedWorkout.status != 'CANCELLED'))).scalars())
    needed = {raw[plans.policy.MARKER]['review_id'] for raw in active if isinstance(raw, dict) and plans.policy.MARKER in raw}
    if needed & set(skipped):
        raise ValueError('Egy jelenlegi edzés eredeti forrása hibás; az előkészítés nem teljes. A tervek nem változtak.')
    await session.rollback()
    return {'prepared_sources': prepared, 'existing_sources': len(sources)-prepared-len(skipped),
            'unused_invalid_sources_skipped': len(skipped), 'workouts_changed': False, 'original_sources_changed': False}


async def main():
    import json
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.db.session import SessionLocal, engine
    from app.models.entities import User
    try:
        async with SessionLocal() as session:
            user = (await session.execute(select(User).where(User.email == get_settings().demo_user_email))).scalar_one()
            owner = str(user.id)
            await session.rollback()
            print(json.dumps(await prepare(session, owner), ensure_ascii=False), flush=True)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
