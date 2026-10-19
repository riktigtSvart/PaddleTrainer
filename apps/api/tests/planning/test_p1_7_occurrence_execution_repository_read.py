import pytest

from app.planning.infrastructure.repositories.postgres_authoritative_occurrence_execution import (
    SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository,
)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return FakeResult(self.rows)


@pytest.mark.asyncio
async def test_lists_all_occurrence_links_for_plan_execution():
    rows = [object(), object()]
    session = FakeSession(rows)

    repository = (
        SqlAlchemyAuthoritativeOccurrenceExecutionLinkRepository(
            session
        )
    )

    mapped = {
        rows[0]: "first",
        rows[1]: "second",
    }
    repository._from_row = lambda row: mapped[row]

    result = await repository.list_by_plan_execution_link(
        plan_execution_link_id="pt-exec-link:example"
    )

    assert result == ("first", "second")

    statement = str(session.statement)

    assert "planning_occurrence_execution_links" in statement
    assert "plan_execution_link_id" in statement
    assert "ORDER BY" in statement
    assert "authoritative_occurrence_id" in statement
