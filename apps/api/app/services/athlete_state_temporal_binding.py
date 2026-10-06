from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"

STATUS_BOUND = "BOUND"
STATUS_NOT_BOUND = "NOT_BOUND"
STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE = "INSUFFICIENT_TEMPORAL_EVIDENCE"
STATUS_AMBIGUOUS = "AMBIGUOUS"

CANDIDATE_ELIGIBLE = "ELIGIBLE"
CANDIDATE_FUTURE = "FUTURE"
CANDIDATE_TOO_OLD = "TOO_OLD"
CANDIDATE_INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
CANDIDATE_CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"

DEFAULT_MAX_CARRY_FORWARD_SECONDS = 24 * 60 * 60

_TIMESTAMP_KEYS = (
    "state_timestamp",
    "effective_at",
    "snapshot_timestamp",
    "observed_at",
)


def build_athlete_state_temporal_binding(
    target_timestamp: Any,
    candidate_snapshots: Sequence[Mapping[str, Any]] | None,
    *,
    max_carry_forward_seconds: int = DEFAULT_MAX_CARRY_FORWARD_SECONDS,
) -> dict[str, Any]:
    """Bind one AthleteState snapshot to a target instant conservatively.

    This service is a temporal selection layer only.  It does not build an
    AthleteState, does not synthesize readiness into AthleteState, and does not
    decide whether individual state components are physiologically current.

    Candidate contract (provider-independent):
    - a timezone-aware timestamp under one of ``_TIMESTAMP_KEYS``;
    - ``context`` containing the AthleteState/scientific-state payload;
    - optional ``available`` (False rejects the candidate);
    - optional snapshot/provenance/traceability metadata.

    Selection policy:
    - never use future state;
    - never use a candidate older than ``max_carry_forward_seconds``;
    - latest eligible non-future state wins;
    - distinct candidates at the same latest timestamp are ambiguous;
    - exact semantic duplicates at that timestamp are collapsed.

    The carry-forward window is an explicit binding policy, not a claim that
    every component of AthleteState remains physiologically valid for that
    duration.  Component-specific recency remains downstream evidence.
    """
    if isinstance(max_carry_forward_seconds, bool) or max_carry_forward_seconds < 0:
        raise ValueError("max_carry_forward_seconds must be non-negative")

    target = _parse_aware_datetime(target_timestamp)
    candidates = _sequence_of_mappings(candidate_snapshots)

    evaluated: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []

    for position, candidate in enumerate(candidates):
        row = _evaluate_candidate(
            candidate,
            position=position,
            target=target,
            max_carry_forward_seconds=int(max_carry_forward_seconds),
        )
        evaluated.append(row)
        if row["eligibility_status"] == CANDIDATE_ELIGIBLE:
            eligible.append(row)

    base = {
        "schema_version": SCHEMA_VERSION,
        "target_timestamp": target.isoformat() if target is not None else None,
        "candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "policy": {
            "max_carry_forward_seconds": int(max_carry_forward_seconds),
            "future_state_allowed": False,
            "latest_eligible_state_wins": True,
            "same_timestamp_distinct_candidates_are_ambiguous": True,
            "exact_semantic_duplicates_are_collapsed": True,
            "timezone_aware_timestamp_required": True,
        },
        "scope": {
            "domain": "ATHLETE_STATE_TEMPORAL_BINDING",
            "builds_athlete_state": False,
            "synthesizes_readiness_into_athlete_state": False,
            "establishes_component_specific_recency": False,
            "establishes_component_specific_validity": False,
            "uses_future_state": False,
            "infers_physiological_response": False,
            "recommends_training_dose": False,
            "promotes_evidence_quality": False,
            "mutates_candidate_state": False,
        },
        "evaluated_candidates": evaluated,
    }

    if target is None:
        return {
            **base,
            "status": STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE,
            "bound": False,
            "selected_snapshot": None,
            "athlete_state_context": None,
            "binding_basis": ["TARGET_TIMESTAMP_INVALID_OR_TIMEZONE_UNAWARE"],
            "limitations": ["TARGET_TIMESTAMP_NOT_TIMEZONE_AWARE"],
        }

    if not candidates:
        return {
            **base,
            "status": STATUS_NOT_BOUND,
            "bound": False,
            "selected_snapshot": None,
            "athlete_state_context": None,
            "binding_basis": ["NO_ATHLETE_STATE_CANDIDATES"],
            "limitations": ["ATHLETE_STATE_CANDIDATE_UNAVAILABLE"],
        }

    if not eligible:
        return {
            **base,
            "status": STATUS_INSUFFICIENT_TEMPORAL_EVIDENCE,
            "bound": False,
            "selected_snapshot": None,
            "athlete_state_context": None,
            "binding_basis": [
                "NO_NON_FUTURE_ATHLETE_STATE_WITHIN_CARRY_FORWARD_POLICY"
            ],
            "limitations": ["ATHLETE_STATE_TEMPORAL_SUPPORT_INSUFFICIENT"],
        }

    latest_timestamp = max(row["parsed_timestamp"] for row in eligible)
    latest_rows = [row for row in eligible if row["parsed_timestamp"] == latest_timestamp]

    unique_by_hash: dict[str, dict[str, Any]] = {}
    for row in latest_rows:
        unique_by_hash.setdefault(row["semantic_hash"], row)

    if len(unique_by_hash) > 1:
        return {
            **base,
            "status": STATUS_AMBIGUOUS,
            "bound": False,
            "selected_snapshot": None,
            "athlete_state_context": None,
            "binding_basis": [
                "MULTIPLE_DISTINCT_ATHLETE_STATE_CANDIDATES_AT_LATEST_TIMESTAMP"
            ],
            "limitations": ["ATHLETE_STATE_TEMPORAL_BINDING_AMBIGUOUS"],
        }

    selected = next(iter(unique_by_hash.values()))
    selected_candidate = selected["candidate"]
    selected_context = selected_candidate.get("context")
    age_seconds = float(selected["age_seconds"])

    limitations = _unique_strings(
        [
            *_string_list(selected_candidate.get("limitations")),
            *_string_list(selected_candidate.get("traceability_gaps")),
            *(
                ["ATHLETE_STATE_CARRIED_FORWARD_WITHIN_BINDING_POLICY"]
                if age_seconds > 0.0
                else []
            ),
            "ATHLETE_STATE_COMPONENT_SPECIFIC_RECENCY_NOT_ESTABLISHED",
        ]
    )

    selected_snapshot = {
        "snapshot_id": _scalar_id(selected_candidate.get("snapshot_id")),
        "state_timestamp": latest_timestamp.isoformat(),
        "age_seconds": age_seconds,
        "carried_forward": age_seconds > 0.0,
        "schema_version": _string(selected_candidate.get("schema_version")),
        "source": deepcopy(selected_candidate.get("source")),
        "semantic_hash": selected["semantic_hash"],
    }

    return {
        **base,
        "status": STATUS_BOUND,
        "bound": True,
        "selected_snapshot": selected_snapshot,
        "athlete_state_context": deepcopy(dict(selected_context)),
        "binding_basis": [
            "LATEST_ELIGIBLE_NON_FUTURE_ATHLETE_STATE",
            "CANDIDATE_WITHIN_CARRY_FORWARD_POLICY",
        ],
        "limitations": limitations,
    }


def athlete_state_context_from_binding(
    binding: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a defensive copy of the bound context, otherwise ``None``."""
    if not isinstance(binding, Mapping) or binding.get("status") != STATUS_BOUND:
        return None
    context = binding.get("athlete_state_context")
    if not isinstance(context, Mapping):
        return None
    return deepcopy(dict(context))


def build_athlete_state_temporal_binding_summary(
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(binding))
    result.pop("athlete_state_context", None)
    result["athlete_state_context_included"] = False
    return result


def _evaluate_candidate(
    candidate: Mapping[str, Any],
    *,
    position: int,
    target: datetime | None,
    max_carry_forward_seconds: int,
) -> dict[str, Any]:
    timestamp_value = None
    timestamp_field = None
    for key in _TIMESTAMP_KEYS:
        if candidate.get(key) is not None:
            timestamp_value = candidate.get(key)
            timestamp_field = key
            break

    parsed = _parse_aware_datetime(timestamp_value)
    context = candidate.get("context")

    status = CANDIDATE_ELIGIBLE
    age_seconds: float | None = None

    if candidate.get("available") is False or not isinstance(context, Mapping):
        status = CANDIDATE_CONTEXT_UNAVAILABLE
    elif parsed is None:
        status = CANDIDATE_INVALID_TIMESTAMP
    elif target is not None:
        age_seconds = (target - parsed).total_seconds()
        if age_seconds < 0.0:
            status = CANDIDATE_FUTURE
        elif age_seconds > max_carry_forward_seconds:
            status = CANDIDATE_TOO_OLD
    else:
        status = CANDIDATE_INVALID_TIMESTAMP

    semantic_hash = _candidate_semantic_hash(candidate, parsed)

    return {
        "position": position,
        "snapshot_id": _scalar_id(candidate.get("snapshot_id")),
        "timestamp_field": timestamp_field,
        "state_timestamp": parsed.isoformat() if parsed is not None else None,
        "age_seconds": age_seconds,
        "eligibility_status": status,
        "semantic_hash": semantic_hash,
        "candidate": deepcopy(dict(candidate)),
        "parsed_timestamp": parsed,
    }


def _candidate_semantic_hash(
    candidate: Mapping[str, Any],
    parsed: datetime | None,
) -> str:
    payload = {
        "state_timestamp": parsed.isoformat() if parsed is not None else None,
        "context": candidate.get("context"),
        "schema_version": candidate.get("schema_version"),
        "source": candidate.get("source"),
        "traceability_gaps": candidate.get("traceability_gaps"),
        "limitations": candidate.get("limitations"),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_aware_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value:
        text = _string(item)
        if text is not None:
            result.append(text)
    return result


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _string(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _scalar_id(value: Any) -> str | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        return value
    return str(value)
