"""Bounded calendar source reads retain exact day-scoped planning evidence."""
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.entities import PlannedWorkout, WorkoutSession
from app.planning.domain.athlete_setup import digest
from app.planning.domain.persistence.audit import AuditArtifactKind as Kind, AuditArtifactRecord
from app.planning.infrastructure.persistence.sqlalchemy_models import PlanningAuditArtifactRow as Row
from app.planning.infrastructure.repositories.postgres_planning_audit import SqlAlchemyPlanningAuditRepository as Repository
from app.services import calendar_training_projection as projection, training_plans as plans
from tests.planning.test_c21_10_9_profile_sources import env, configure, full
from tests.planning.test_c21_10_17_direct_picker import setup, get_options, snapshots
from tests.planning.test_c21_10_15_today_and_variants import feed
from tests.planning.test_p2_4c18_4_training_plan import accept
from tests.planning.test_p2_4c3_goal_workflow_api import ATHLETE, OTHER, count


def calendar(e, path='feed'):
    response = e.client.get(f'/api/v1/planning/calendar/{path}?start_date=2026-10-26&end_date=2026-11-22')
    assert response.status_code == 200, response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Server-Timing'].startswith('calendar;dur=')
    return response.json()


def test_four_week_feed_verifies_each_immutable_source_once_and_writes_nothing(env, monkeypatch):
    configure(env)
    reviewed = full(env)
    accept(env, reviewed, token=21118001)
    before = snapshots(env), count(env, Row), count(env, WorkoutSession)
    verified, queries = Counter(), []
    original = plans.decode

    def decode(record, owner):
        verified[record.artifact_id] += 1
        return original(record, owner)

    def trace(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)

    monkeypatch.setattr(plans, 'decode', decode)
    event.listen(env.engine, 'before_cursor_execute', trace)
    try:
        value = calendar(env)
    finally:
        event.remove(env.engine, 'before_cursor_execute', trace)
    assert len(value['planned']) >= 20
    assert len(verified) == 1 and set(verified.values()) == {1}  # compact acceptance only; no full review tree
    assert len(queries) <= 18  # small indexed projection reads replace historical evidence reads
    assert all(w['planning_context']['accepted_review_reference']['artifact_id'] == reviewed['artifact_id'] for w in value['planned'])
    assert before == (snapshots(env), count(env, Row), count(env, WorkoutSession))
    verified.clear()
    again = calendar(env)
    assert set(verified.values()) == {1}  # no shared cache survives this request
    assert again['planned'] == value['planned']


def test_cycle_context_shares_verification_of_latest_and_accepted_source(env, monkeypatch):
    configure(env)
    reviewed = full(env)
    accept(env, reviewed, token=21118002)
    original, verified = plans.decode, Counter()

    def decode(record, owner):
        verified[record.artifact_id] += 1
        return original(record, owner)

    monkeypatch.setattr(plans, 'decode', decode)
    value = calendar(env, 'cycles')
    assert not verified  # prepared cycle views require no full review verification
    assert all(row['latest_review']['review_reference']['artifact_id'] == reviewed['artifact_id'] for row in value['cycles'])


def test_independent_day_reviews_do_not_hide_each_other_or_replace_the_programme_stream(env):
    target, scope = setup(env)
    first = get_options(env, target, scope)
    before = feed(env)
    later = next(w for w in before['planned'] if w['date'] > target['date'])
    later_scope = {**scope, 'workout_id': later['id'], 'expected_workout_hash': later['planning_context']['workout_hash']}
    second = get_options(env, later, later_scope)
    after = feed(env)
    old = next(w for w in before['planned'] if w['id'] == target['id'])
    current = next(w for w in after['planned'] if w['id'] == target['id'])
    assert current['planning_context'] == old['planning_context']
    assert current['planning_context']['alternatives_checked_at'] == first['created_at']
    selected_later = next(w for w in after['planned'] if w['id'] == later['id'])
    assert selected_later['planning_context']['alternatives_checked_at'] == second['created_at']
    assert all(w['planning_context'] == next(p for p in before['planned'] if p['id'] == w['id'])['planning_context']
               for w in after['planned'] if w['id'] not in {target['id'], later['id']})


def test_next_read_observes_a_new_review_and_does_not_reuse_tampered_storage(env):
    configure(env)
    reviewed = full(env)
    accept(env, reviewed, token=21118003)
    old = calendar(env)
    fresh = full(env)
    updated = calendar(env)
    assert fresh['artifact_id'] != reviewed['artifact_id']
    assert any(w['planning_context']['alternatives_checked_at'] == fresh['created_at'] for w in updated['planned'])
    assert [w['id'] for w in old['planned']] == [w['id'] for w in updated['planned']]
    with Session(env.engine) as db:
        from app.services.training_read_models import identity
        row = db.query(Row).filter_by(artifact_id=identity(fresh['artifact_id'])).one()
        row.contract_json = row.contract_json.replace('"timezone_name":"Europe/Budapest"', '"timezone_name":"UTC"')
        db.commit()
    before = snapshots(env)
    response = env.client.get('/api/v1/planning/calendar/feed?start_date=2026-10-26&end_date=2026-11-22')
    assert response.status_code == 503 and 'STORAGE_INVALID' in response.text
    assert snapshots(env) == before


def record():
    value = {'schema_version': plans.SCHEMA, 'athlete_id': ATHLETE, 'artifact_id': 'calendar-proof-test'}
    value['content_hash'] = digest(value)
    return AuditArtifactRecord(Kind.TRAINING_PLAN_REVIEW, value['artifact_id'], ATHLETE, plans.SCHEMA,
        datetime(2026, 10, 26, tzinfo=UTC), plans.CONTENT_HASH_ALGORITHM, value['content_hash'], plans.canonical_json(value),
        datetime(2026, 10, 26, tzinfo=UTC))


@pytest.mark.parametrize('change', [
    {'athlete_id': OTHER}, {'schema_version': 'future'}, {'content_hash': 'f' * 64},
    {'content_hash_algorithm': 'other'}, {'persisted_at': None}, {'contract_json': '{}'},
])
def test_request_local_cache_revalidates_changed_body_and_metadata(monkeypatch, change):
    original, verified = plans.decode, []

    def decode(source, owner):
        verified.append(source)
        return original(source, owner)

    monkeypatch.setattr(plans, 'decode', decode)
    reader = projection.PlanningRead(Repository(None), ATHLETE)
    source = record()
    reader.decode_record(source)
    reader.decode_record(replace(source))
    assert len(verified) == 1
    with pytest.raises((plans.TrainingPlanError, KeyError)):
        reader.decode_record(replace(source, **change))
    assert len(verified) == 2


def test_equal_payload_with_changed_persistence_metadata_is_reverified(monkeypatch):
    original, verified = plans.decode, []
    monkeypatch.setattr(plans, 'decode', lambda source, owner: (verified.append(source), original(source, owner))[1])
    source = record()
    reader = projection.PlanningRead(Repository(None), ATHLETE)
    assert reader.decode_record(source) == reader.decode_record(replace(source, persisted_at=source.persisted_at + timedelta(seconds=1)))
    assert len(verified) == 2


@pytest.mark.asyncio
async def test_dense_scope_query_is_bounded_and_portable_without_loading_other_owners(monkeypatch):
    from sqlalchemy.dialects import postgresql, sqlite

    class Rows:
        def scalars(self):
            return []

    class Database:
        def __init__(self):
            self.queries = []

        async def execute(self, query):
            self.queries.append(query)
            return Rows()

    database = Database()
    scopes = {str(UUID(int=i)): ('programme', {'schema_version': 'workout-alternatives-request-v0.1',
        'workout_id': str(UUID(int=i)), 'expected_workout_hash': 'a' * 64}) for i in range(1, 206)}
    assert await projection.latest_scoped(database, ATHLETE, scopes, projection.PlanningRead(None, ATHLETE)) == {}
    assert len(database.queries) == 3
    for query in database.queries:
        for dialect in (sqlite.dialect(), postgresql.dialect()):
            sql = str(query.compile(dialect=dialect, compile_kwargs={'literal_binds': True}))
            assert 'row_number() OVER' in sql and 'CASE WHEN' in sql
            assert OTHER.replace('-', '') not in sql and ATHLETE.replace('-', '') in sql.replace('-', '')


def test_http_timing_is_read_only_and_never_added_to_response_contract(env):
    configure(env)
    before = count(env, Row), count(env, PlannedWorkout)
    value = calendar(env)
    assert 'Server-Timing' not in value and 'duration_ms' not in value
    assert before == (count(env, Row), count(env, PlannedWorkout))
