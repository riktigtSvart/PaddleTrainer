from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping, Sequence

from app.services.athlete_state_temporal_binding import (
    DEFAULT_MAX_CARRY_FORWARD_SECONDS,
    build_athlete_state_temporal_binding,
)


SCHEMA_VERSION = "0.1"

SOURCE_VIEW = "ATHLETE_STATE_SCIENTIFIC_VIEW"

_TIMESTAMP_KEYS = (
    "state_timestamp",
    "effective_at",
    "snapshot_timestamp",
    "as_of_timestamp",
    "as_of",
)


def build_athlete_state_candidate_from_scientific_view(
    scientific_view: Mapping[str, Any] | None,
    *,
    state_timestamp: Any = None,
    snapshot_id: Any = None,
    source_reference: Any = None,
) -> dict[str, Any] | None:
    """Adapt one already-built scientific AthleteState view to the V22 contract.

    The adapter is intentionally semantic-light.  It does not build an
    AthleteState, does not derive readiness, does not score the state, and does
    not infer a timestamp from component observations.  A whole-view temporal
    anchor must be explicit either in ``state_timestamp`` or in a recognized
    top-level view field.

    If caller metadata and the source view both provide timezone-aware temporal
    anchors and they disagree, the candidate is retained as evidence but marked
    unavailable so V22 cannot silently bind it.
    """
    if not isinstance(scientific_view, Mapping):
        return None

    view = deepcopy(dict(scientific_view))
    source_timestamp_field, source_timestamp = _source_timestamp(view)

    explicit_timestamp = state_timestamp
    resolved_timestamp = (
        explicit_timestamp
        if explicit_timestamp is not None
        else source_timestamp
    )

    timestamp_conflict = _timestamps_conflict(
        explicit_timestamp,
        source_timestamp,
    )

    evidence_inventory = (
        view.get("evidence_inventory")
        if isinstance(view.get("evidence_inventory"), Mapping)
        else {}
    )

    traceability_gaps = _unique_strings(
        [
            *_string_list(view.get("traceability_gaps")),
            *_string_list(evidence_inventory.get("gaps")),
        ]
    )

    limitations = _unique_strings(
        [
            *_string_list(view.get("limitations")),
            *(
                ["ATHLETE_STATE_TIMESTAMP_CONFLICT"]
                if timestamp_conflict
                else []
            ),
            *(
                ["ATHLETE_STATE_VIEW_TEMPORAL_ANCHOR_UNAVAILABLE"]
                if resolved_timestamp is None
                else []
            ),
            "ATHLETE_STATE_SCIENTIFIC_VIEW_ADAPTED_WITHOUT_COMPONENT_RECENCY_PROMOTION",
        ]
    )

    source = {
        "provider": "PADDLETRAINER",
        "view": SOURCE_VIEW,
        "adapter_schema_version": SCHEMA_VERSION,
        "scientific_view_schema_version": _string(view.get("schema_version")),
        "timestamp_source": (
            "EXPLICIT_ADAPTER_METADATA"
            if explicit_timestamp is not None
            else source_timestamp_field
        ),
        "source_view_timestamp_field": source_timestamp_field,
        "source_view_timestamp": deepcopy(source_timestamp),
        "source_reference": deepcopy(source_reference),
    }

    available = (
        view.get("available") is not False
        and resolved_timestamp is not None
        and not timestamp_conflict
    )

    return {
        "snapshot_id": _scalar_id(
            snapshot_id
            if snapshot_id is not None
            else view.get("snapshot_id")
        ),
        "schema_version": SCHEMA_VERSION,
        "state_timestamp": deepcopy(resolved_timestamp),
        "available": available,
        "source": source,
        "traceability_gaps": traceability_gaps,
        "limitations": limitations,
        "context": view,
        "adapter_provenance": {
            "timestamp_conflict": timestamp_conflict,
            "explicit_state_timestamp": deepcopy(explicit_timestamp),
            "source_view_timestamp": deepcopy(source_timestamp),
            "source_view_timestamp_field": source_timestamp_field,
            "whole_view_timestamp_inferred_from_components": False,
            "scientific_evidence_inventory_gaps_preserved": bool(
                _string_list(evidence_inventory.get("gaps"))
            ),
        },
    }


def build_athlete_state_candidates_from_scientific_views(
    scientific_view_snapshots: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Adapt timestamped scientific-view wrappers to V22 candidates.

    Wrapper contract::

        {
            "scientific_view": {...},
            "state_timestamp": "...",       # optional if view has top-level anchor
            "snapshot_id": "...",           # optional
            "source_reference": {...},       # optional
        }

    Invalid/non-mapping wrappers are ignored.  A mapping with a scientific view
    but insufficient temporal evidence is retained as an unavailable candidate
    so the binding result remains evidence-aware rather than silently dropping
    the problem.
    """
    if not isinstance(scientific_view_snapshots, Sequence) or isinstance(
        scientific_view_snapshots, (str, bytes, bytearray)
    ):
        return []

    result: list[dict[str, Any]] = []
    for item in scientific_view_snapshots:
        if not isinstance(item, Mapping):
            continue
        candidate = build_athlete_state_candidate_from_scientific_view(
            item.get("scientific_view"),
            state_timestamp=item.get("state_timestamp"),
            snapshot_id=item.get("snapshot_id"),
            source_reference=item.get("source_reference"),
        )
        if candidate is not None:
            result.append(candidate)
    return result


def build_athlete_state_temporal_binding_from_scientific_views(
    target_timestamp: Any,
    scientific_view_snapshots: Sequence[Mapping[str, Any]] | None,
    *,
    max_carry_forward_seconds: int = DEFAULT_MAX_CARRY_FORWARD_SECONDS,
) -> dict[str, Any]:
    """Adapt scientific-state snapshots and run the V22 temporal policy."""
    candidates = build_athlete_state_candidates_from_scientific_views(
        scientific_view_snapshots
    )
    binding = build_athlete_state_temporal_binding(
        target_timestamp,
        candidates,
        max_carry_forward_seconds=max_carry_forward_seconds,
    )
    return {
        **binding,
        "source_adapter": {
            "schema_version": SCHEMA_VERSION,
            "source_view": SOURCE_VIEW,
            "candidate_count": len(candidates),
            "builds_athlete_state": False,
            "synthesizes_readiness_into_athlete_state": False,
            "infers_whole_view_timestamp_from_components": False,
        },
    }


def _source_timestamp(view: Mapping[str, Any]) -> tuple[str | None, Any]:
    for key in _TIMESTAMP_KEYS:
        if view.get(key) is not None:
            return key, view.get(key)
    return None, None


def _parse_aware_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _timestamps_conflict(explicit: Any, source: Any) -> bool:
    if explicit is None or source is None:
        return False
    explicit_dt = _parse_aware_datetime(explicit)
    source_dt = _parse_aware_datetime(source)
    if explicit_dt is None or source_dt is None:
        # The binding layer will independently reject invalid timestamps.  Do
        # not invent a conflict solely from unparsable formatting.
        return False
    return explicit_dt != source_dt


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [text for item in value if (text := _string(item)) is not None]


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _scalar_id(value: Any) -> str | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)):
        return value
    return None
