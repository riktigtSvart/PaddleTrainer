from __future__ import annotations

from ..domain.integration.models import ExistingWorkoutPlanCapture
from ..domain.integration.polar_reconciliation import (
    PolarSourceReconciliationArtifact,
    reconcile_polar_source_capture,
)


def build_polar_source_reconciliation(
    *,
    capture: ExistingWorkoutPlanCapture,
    athlete_timezone: str | None,
) -> PolarSourceReconciliationArtifact:
    """Build a transient, read-only reconciliation artifact for one capture."""
    return reconcile_polar_source_capture(
        capture,
        athlete_timezone=athlete_timezone,
    )
