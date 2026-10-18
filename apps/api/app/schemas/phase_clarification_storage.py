"""A full replacement answer set and an explicit optimistic concurrency token."""
from pydantic import Field
from app.schemas.phase_reconciliation import PhaseClarificationInspectionRequest


class PhaseClarificationSaveRequest(PhaseClarificationInspectionRequest):
    expected_revision_id: str | None = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
