from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.planning.infrastructure.adapters import (
    current_phase_occurrence_candidate as adapter,
)
from app.planning.infrastructure.adapters.current_phase_occurrence_candidate import (
    CurrentAppPhaseOccurrenceCandidateProvider,
    CurrentPhaseOccurrenceCandidateNotFound,
)


ATHLETE_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"
HYPOTHESIS_ID = "phase_path_1"
STABLE_ID = "phase-source-occurrence_1"


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.scalar_calls = 0

    @property
    def no_autoflush(self):
        return nullcontext()

    async def scalar(self, statement):
        self.scalar_calls += 1
        return self.row


@pytest.mark.asyncio
async def test_provider_derives_candidate_from_owned_server_read(
    monkeypatch,
):
    row = SimpleNamespace()
    db = FakeDB(row)
    reconciliation = {"server": "reconciliation"}
    candidate = object()
    calls = {}

    async def read(
        passed_db,
        passed_row,
        owner_id,
        *,
        include_source,
    ):
        calls["read"] = (
            passed_db,
            passed_row,
            str(owner_id),
            include_source,
        )
        return reconciliation

    def capture(
        value,
        *,
        hypothesis_id,
        stable_source_occurrence_id,
    ):
        calls["capture"] = (
            value,
            hypothesis_id,
            stable_source_occurrence_id,
        )
        return candidate

    monkeypatch.setattr(
        adapter,
        "read_owned_phase_reconciliation",
        read,
    )
    monkeypatch.setattr(
        adapter,
        "capture_occurrence_execution_candidate",
        capture,
    )

    provider = CurrentAppPhaseOccurrenceCandidateProvider(
        db,
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
    )

    result = await provider(
        hypothesis_id=HYPOTHESIS_ID,
        stable_source_occurrence_id=STABLE_ID,
    )

    assert result is candidate
    assert db.scalar_calls == 1
    assert calls["read"] == (
        db,
        row,
        ATHLETE_ID,
        False,
    )
    assert calls["capture"] == (
        reconciliation,
        HYPOTHESIS_ID,
        STABLE_ID,
    )


@pytest.mark.asyncio
async def test_provider_hides_missing_or_cross_owner_session():
    provider = CurrentAppPhaseOccurrenceCandidateProvider(
        FakeDB(None),
        athlete_id=ATHLETE_ID,
        workout_session_id=SESSION_ID,
    )

    with pytest.raises(CurrentPhaseOccurrenceCandidateNotFound):
        await provider(
            hypothesis_id=HYPOTHESIS_ID,
            stable_source_occurrence_id=STABLE_ID,
        )


def test_provider_accepts_no_client_evidence_fields():
    import inspect

    signature = inspect.signature(
        CurrentAppPhaseOccurrenceCandidateProvider.__call__
    )

    assert set(signature.parameters) == {
        "self",
        "hypothesis_id",
        "stable_source_occurrence_id",
    }

    for forbidden in (
        "session_source_content_hash",
        "plan_source_content_hash",
        "candidate_start_window_s",
        "candidate_completion_window_s",
        "captured_contract_occurrence_id",
        "clock_domain",
        "provider_event_verified",
    ):
        assert forbidden not in signature.parameters
