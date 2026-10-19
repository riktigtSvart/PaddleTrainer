from __future__ import annotations

from app.planning.domain.occurrence_execution import (
    OccurrenceExecutionCandidateEvidence,
)
from app.planning_contracts.phase_reconciliation import (
    RULES_VERSION,
)


class PhaseOccurrenceCandidateAdapterError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhaseOccurrenceCandidateAdapterError(message)


def _window(value, *, field_name: str) -> tuple[float, float]:
    _require(
        isinstance(value, list) and len(value) == 2,
        f"{field_name} must be a two-value list.",
    )
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhaseOccurrenceCandidateAdapterError(
            f"{field_name} contains invalid numeric values."
        ) from exc


def capture_occurrence_execution_candidate(
    phase_reconciliation_read: dict,
    *,
    hypothesis_id: str,
    stable_source_occurrence_id: str,
) -> OccurrenceExecutionCandidateEvidence:
    """Extract one bounded occurrence candidate from server state.

    The caller identifies only an existing hypothesis and stable
    source occurrence. Hashes, windows, provider-verification flags,
    clock domain, and captured contract occurrence identity are
    derived from the server-produced reconciliation artifact.

    Only hypotheses still consistent after clarification are eligible.
    """
    _require(
        isinstance(phase_reconciliation_read, dict),
        "Phase reconciliation read is unavailable.",
    )
    _require(
        isinstance(hypothesis_id, str)
        and hypothesis_id.startswith("phase_path_"),
        "Invalid phase hypothesis identity.",
    )
    _require(
        isinstance(stable_source_occurrence_id, str)
        and stable_source_occurrence_id.startswith(
            "phase-source-occurrence_"
        ),
        "Invalid stable source occurrence identity.",
    )

    # Fail closed if future reconciliation code starts making a
    # stronger alignment claim. P1.6C1 must be reviewed before
    # consuming stronger semantics.
    _require(
        phase_reconciliation_read.get(
            "actual_phase_alignment_verified"
        )
        is False,
        "Unexpected phase-alignment authority.",
    )

    rules_version = phase_reconciliation_read.get(
        "rules_version"
    )
    _require(
        rules_version == RULES_VERSION,
        "Unsupported phase reconciliation rules version.",
    )

    result = phase_reconciliation_read.get("result")
    _require(
        isinstance(result, dict),
        "Phase reconciliation result is unavailable.",
    )

    artifact_id = phase_reconciliation_read.get(
        "stable_artifact_id"
    )
    _require(
        isinstance(artifact_id, str)
        and result.get("artifact_id") == artifact_id,
        "Phase reconciliation artifact identity differs.",
    )
    _require(
        result.get("rules_version") == rules_version,
        "Phase reconciliation rules binding differs.",
    )
    _require(
        result.get("actual_phase_alignment_verified")
        is False,
        "Reconciliation result changed phase-alignment authority.",
    )

    binding = result.get("binding")
    _require(
        isinstance(binding, dict),
        "Phase reconciliation source binding is unavailable.",
    )

    session_id = phase_reconciliation_read.get("session_id")
    session_hash = phase_reconciliation_read.get(
        "source_content_sha256"
    )
    plan_hash = phase_reconciliation_read.get(
        "plan_source_content_sha256"
    )

    _require(
        binding.get("session_id") == session_id,
        "Session identity differs from reconciliation binding.",
    )
    _require(
        binding.get("source_sha256") == session_hash,
        "Session source hash differs from reconciliation binding.",
    )
    _require(
        binding.get("plan_sha256") == plan_hash,
        "Plan source hash differs from reconciliation binding.",
    )

    mappings = phase_reconciliation_read.get(
        "source_capture_occurrence_mapping"
    )
    _require(
        isinstance(mappings, list),
        "Source occurrence mapping is unavailable.",
    )

    matching_mappings = [
        item
        for item in mappings
        if isinstance(item, dict)
        and item.get("stable_source_occurrence_id")
        == stable_source_occurrence_id
    ]
    _require(
        len(matching_mappings) == 1,
        "Stable source occurrence mapping is not unique.",
    )

    captured_contract_occurrence_id = (
        matching_mappings[0].get(
            "captured_contract_occurrence_id"
        )
    )
    _require(
        isinstance(captured_contract_occurrence_id, str)
        and captured_contract_occurrence_id,
        "Captured contract occurrence identity is unavailable.",
    )

    hypotheses = result.get(
        "consistent_hypotheses_after_clarification"
    )
    _require(
        isinstance(hypotheses, list),
        "Consistent phase hypotheses are unavailable.",
    )

    matching_hypotheses = [
        item
        for item in hypotheses
        if isinstance(item, dict)
        and item.get("hypothesis_id") == hypothesis_id
    ]
    _require(
        len(matching_hypotheses) == 1,
        "Requested hypothesis is not uniquely eligible.",
    )

    hypothesis = matching_hypotheses[0]
    _require(
        hypothesis.get("scope")
        == (
            "INCOMPLETE_MOTION_HYPOTHESIS_"
            "NOT_ACTUAL_EXECUTION_PROOF"
        ),
        "Unexpected phase hypothesis authority.",
    )

    phase_windows = hypothesis.get("phase_windows")
    _require(
        isinstance(phase_windows, list),
        "Hypothesis phase windows are unavailable.",
    )

    matching_windows = [
        item
        for item in phase_windows
        if isinstance(item, dict)
        and item.get("occurrence_id")
        == stable_source_occurrence_id
    ]
    _require(
        len(matching_windows) == 1,
        "Requested occurrence window is not uniquely eligible.",
    )

    phase_window = matching_windows[0]

    start_window = _window(
        phase_window.get("start_window_s"),
        field_name="start_window_s",
    )
    completion_window = _window(
        phase_window.get("goal_completion_window_s"),
        field_name="goal_completion_window_s",
    )

    _require(
        phase_window.get("provider_event_verified") is False,
        "Candidate unexpectedly claims provider verification.",
    )

    clock_domain = phase_window.get("clock_domain")
    _require(
        isinstance(clock_domain, str) and clock_domain,
        "Candidate clock domain is unavailable.",
    )

    return OccurrenceExecutionCandidateEvidence(
        phase_reconciliation_artifact_id=artifact_id,
        phase_reconciliation_rules_version=rules_version,
        session_source_content_hash=session_hash,
        plan_source_content_hash=plan_hash,
        stable_source_occurrence_id=(
            stable_source_occurrence_id
        ),
        captured_contract_occurrence_id=(
            captured_contract_occurrence_id
        ),
        hypothesis_id=hypothesis_id,
        candidate_start_window_s=start_window,
        candidate_completion_window_s=completion_window,
        clock_domain=clock_domain,

        # Existing reconciliation explicitly provides only
        # candidate interpretations.
        provider_event_verified=False,
        clock_alignment_verified=False,
        actual_boundary_verified=False,
    )
