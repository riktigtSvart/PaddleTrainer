"""Bounded, pure metadata checks. Received JSON cannot establish source ownership.

The assembly service may bind these checks to sources it actually verified.
Reported wall-clock bounds do not prove device accuracy or session independence.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta, timezone
from itertools import combinations, pairwise

from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_dataset_split import SPLITS

MAX_TEMPORAL_EXERCISES = 256
MAX_TEMPORAL_MEMBERS = 20
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?")
_MISSING = object()
SUPPORTED_INTERVAL = "SUPPORTED_DECLARED_SOURCE_INTERVAL_WITH_LIMITATIONS"
LIMITATIONS = [
    "DECLARED_POLAR_WALL_CLOCK_BOUNDS_ONLY",
    "DEVICE_CLOCK_ACCURACY_AND_SERIALIZATION_UNCERTAINTY_NOT_VERIFIED",
    "DURATION_MILLIS_NOT_USED_TO_INFER_MISSING_STOP",
    "PAUSE_AND_NATIVE_HR_CLOCK_SEMANTICS_NOT_VERIFIED",
    "PUBLISHED_EXERCISE_SET_ONLY_HIDDEN_PROVIDER_RECORDS_NOT_EXAMINED",
]


class TemporalMetadataError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise TemporalMetadataError(code)


def declared_utc(value, offset=_MISSING, fallback=_MISSING):
    """Strict calendar timestamp, explicit offset, no host-timezone assumption."""
    _require(isinstance(value, str) and _ISO.fullmatch(value), "COHORT_TIME_FORMAT_INVALID")
    _require(not value.endswith("-00:00"), "COHORT_TIMEZONE_UNRESOLVED")
    if re.search(r"[+-]\d{2}:\d{2}$", value):
        _require(int(value[-2:]) < 60, "COHORT_TIMEZONE_OFFSET_INVALID")
    if offset is not _MISSING:
        _require(
            type(offset) is int and -840 <= offset <= 840,
            "COHORT_TIMEZONE_OFFSET_INVALID",
        )
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            effective = fallback if offset is _MISSING else offset
            _require(effective is not _MISSING, "COHORT_TIMEZONE_UNRESOLVED")
            _require(
                type(effective) is int and -840 <= effective <= 840,
                "COHORT_TIMEZONE_OFFSET_INVALID",
            )
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=effective)))
        elif offset is not _MISSING:
            _require(
                parsed.utcoffset() == timedelta(minutes=offset),
                "COHORT_TIMEZONE_OFFSET_CONFLICT",
            )
        _require(abs(parsed.utcoffset()) <= timedelta(hours=14), "COHORT_TIMEZONE_OFFSET_INVALID")
        return parsed.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, TemporalMetadataError):
            raise
        raise TemporalMetadataError("COHORT_TIME_FORMAT_INVALID") from None


def _utc_text(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _bounds(obj, fallback=_MISSING):
    _require(isinstance(obj, dict), "COHORT_TEMPORAL_SOURCE_SHAPE_INVALID")
    _require(
        obj.get("startTime") is not None and obj.get("stopTime") is not None,
        "COHORT_EXPLICIT_START_OR_STOP_MISSING",
    )
    offset = obj.get("timezoneOffsetMinutes", _MISSING)
    start = declared_utc(obj["startTime"], offset, fallback)
    stop = declared_utc(obj["stopTime"], offset, fallback)
    _require(start < stop, "COHORT_INTERVAL_NOT_POSITIVE")
    return start, stop


def _identifier(exercise):
    identifier = exercise.get("identifier")
    if identifier is None:
        return None
    _require(isinstance(identifier, dict), "COHORT_EXERCISE_IDENTITY_INVALID")
    value = identifier.get("id")
    _require(
        type(value) in (str, int)
        and 1 <= len(str(value)) <= 200
        and str(value).strip() == str(value),
        "COHORT_EXERCISE_IDENTITY_INVALID",
    )
    return str(value)


def _duration_difference(obj, start, stop):
    duration = obj.get("durationMillis")
    if type(duration) is not int or duration < 0:
        return None
    wall_us = (stop - start) // timedelta(microseconds=1)
    return wall_us - duration * 1000


def _source_intervals(source):
    start, stop = _bounds(source)
    exercises = source.get("exercises")
    _require(
        isinstance(exercises, list) and 1 <= len(exercises) <= MAX_TEMPORAL_EXERCISES,
        "COHORT_PUBLISHED_EXERCISE_SET_MISSING_OR_LIMIT",
    )
    items, identities = [], set()
    for position, exercise in enumerate(exercises):
        first, last = _bounds(exercise, source.get("timezoneOffsetMinutes", _MISSING))
        _require(start <= first < last <= stop, "COHORT_EXERCISE_OUTSIDE_SESSION_INTERVAL")
        identifier = _identifier(exercise)
        if identifier is None:
            sport = exercise.get("sport")
            _require(
                isinstance(sport, dict)
                and type(sport.get("id")) in (str, int)
                and bool(str(sport["id"]).strip())
                and type(exercise.get("durationMillis")) is int
                and exercise["durationMillis"] >= 0,
                "COHORT_ANONYMOUS_EXERCISE_METADATA_INCOMPLETE",
            )
        metadata = {
            "start_utc": _utc_text(first),
            "stop_utc": _utc_text(last),
            "sport": exercise.get("sport"),
            "duration_millis": exercise.get("durationMillis"),
        }
        identity = (
            ("ID", identifier) if identifier is not None else ("METADATA", canonical_hash(metadata))
        )
        _require(identity not in identities, "COHORT_EXERCISE_IDENTITY_AMBIGUOUS")
        identities.add(identity)
        items.append(
            {
                "source_exercise_index": position,
                "provider_exercise_id": identifier,
                "metadata": metadata,
                "identity": identity,
                "wall_clock_minus_duration_us": _duration_difference(exercise, first, last),
            }
        )
    return start, stop, items


def _fingerprints(route, sample):
    # Raw feature hashes omit identity/header time so renamed or shifted imports
    # can still be flagged. Coordinates and labels never escape this function.
    content = (
        canonical_hash(
            {
                "sport": sample.get("sport"),
                "durationMillis": sample.get("durationMillis"),
                "routes": route.get("routes"),
                "samples": sample.get("samples"),
            }
        )
        if route.get("routes") or sample.get("samples")
        else None
    )
    container = sample.get("samples")
    series = container.get("samples") if isinstance(container, dict) else None
    hr_hashes = set()
    if isinstance(series, list):
        for item in series:
            if not isinstance(item, dict) or item.get("type") != "HEART_RATE":
                continue
            values = item.get("values")
            if isinstance(values, list) and any(
                type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values
            ):
                hr_hashes.add(
                    canonical_hash(
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": item.get("intervalMillis"),
                            "values": values,
                        }
                    )
                )
    return content, sorted(hr_hashes)


def build_session_temporal_evidence(route_session, sample_session):
    """Metadata consistency only. No caller flags, dates or stored JSON grant authority."""
    result = {
        "schema_version": "0.1",
        "session_interval_status": "WITHHELD",
        "claim_scope": "DECLARED_WALL_CLOCK_METADATA_CONSISTENCY_ONLY",
        "metadata_consistent": False,
        "start_utc": None,
        "stop_utc": None,
        "published_exercise_count": None,
        "exercises": [],
        "route_date_used_as_chronological_evidence": False,
        "stop_inferred_from_duration": False,
        "limitations": LIMITATIONS.copy(),
        "blocking_reasons": [],
    }
    try:
        a, b, routes = _source_intervals(route_session)
        c, d, samples = _source_intervals(sample_session)
        _require((a, b) == (c, d), "COHORT_SESSION_TIME_METADATA_MISMATCH")
        route_map = {r["identity"]: r for r in routes}
        sample_map = {s["identity"]: s for s in samples}
        _require(route_map.keys() == sample_map.keys(), "COHORT_PUBLISHED_EXERCISE_SET_MISMATCH")
        exercises = []
        for identity, item in sorted(route_map.items()):
            paired = sample_map[identity]
            _require(
                canonical_hash(item["metadata"]) == canonical_hash(paired["metadata"]),
                "COHORT_EXERCISE_TIME_METADATA_MISMATCH",
            )
            content, hr_hashes = _fingerprints(
                route_session["exercises"][item["source_exercise_index"]],
                sample_session["exercises"][paired["source_exercise_index"]],
            )
            exercises.append(
                {
                    "route_source_exercise_index": item["source_exercise_index"],
                    "sample_source_exercise_index": paired["source_exercise_index"],
                    "provider_exercise_id": item["provider_exercise_id"],
                    "identity_basis": identity[0],
                    **item["metadata"],
                    "wall_clock_minus_duration_us": item["wall_clock_minus_duration_us"],
                    "anonymous_feature_content_hash": content,
                    "hr_sequence_hashes": hr_hashes,
                }
            )
        result.update(
            session_interval_status=SUPPORTED_INTERVAL,
            metadata_consistent=True,
            start_utc=_utc_text(a),
            stop_utc=_utc_text(b),
            published_exercise_count=len(exercises),
            exercises=exercises,
            session_wall_clock_minus_duration_us={
                "routes": _duration_difference(route_session, a, b),
                "samples": _duration_difference(sample_session, c, d),
            },
        )
    except TemporalMetadataError as exc:
        result["blocking_reasons"] = [str(exc)]
    except (ValueError, TypeError, KeyError, OverflowError):
        result["blocking_reasons"] = ["COHORT_TEMPORAL_SOURCE_SHAPE_INVALID"]
    result["temporal_evidence_hash"] = canonical_hash(result)
    return result


def audit_cohort_temporal_metadata(members):
    """Pure audit of supplied metadata, never source/DB verification or training permission."""
    _require(
        isinstance(members, list) and 1 <= len(members) <= MAX_TEMPORAL_MEMBERS,
        "COHORT_TEMPORAL_MEMBER_LIMIT",
    )
    supported, intervals, unsupported = [], {}, []
    duplicates = defaultdict(set)
    for position, member in enumerate(members):
        _require(
            member["requested_split"]["split"] in (*SPLITS, None), "COHORT_REQUESTED_SPLIT_INVALID"
        )
        evidence = member["temporal_evidence"]
        if evidence["session_interval_status"] != SUPPORTED_INTERVAL:
            unsupported.append(position)
            continue
        start = declared_utc(evidence["start_utc"])
        stop = declared_utc(evidence["stop_utc"])
        _require(start < stop, "COHORT_INTERVAL_NOT_POSITIVE")
        supported.append(position)
        intervals[position] = (start, stop)
        _require(
            len(evidence["exercises"]) <= MAX_TEMPORAL_EXERCISES,
            "COHORT_PUBLISHED_EXERCISE_SET_MISSING_OR_LIMIT",
        )
        for exercise in evidence["exercises"]:
            for field, reason in (
                ("provider_exercise_id", "COHORT_PROVIDER_EXERCISE_ID_REUSED"),
                ("anonymous_feature_content_hash", "COHORT_EXACT_FEATURE_CONTENT_REUSED"),
            ):
                if exercise[field] is not None:
                    duplicates[(reason, exercise[field])].add(position)
            for fingerprint in exercise["hr_sequence_hashes"]:
                duplicates[("COHORT_EXACT_HR_SEQUENCE_REUSED", fingerprint)].add(position)
    possible_copies = defaultdict(set)
    for (reason, _), positions in duplicates.items():
        for pair in combinations(sorted(positions), 2):
            possible_copies[pair].add(reason)
    conflicts = []
    for first, second in combinations(supported, 2):
        a, b = intervals[first]
        c, d = intervals[second]
        if not (b < c or d < a):
            conflicts.append(
                {
                    "member_canonical_indices": [first, second],
                    "reason": "COHORT_SESSION_BOUNDARIES_TOUCH"
                    if b == c or d == a
                    else "COHORT_SESSION_INTERVALS_OVERLAP",
                    "same_requested_split": members[first]["requested_split"]["split"]
                    == members[second]["requested_split"]["split"],
                }
            )
    order = sorted(supported, key=lambda i: (*intervals[i], i))
    chronology_reasons = []
    if unsupported:
        chronology_reasons.append("COHORT_SESSION_INTERVAL_NOT_SUPPORTED")
    if len(members) < 2:
        chronology_reasons.append("COHORT_RELATIVE_ORDER_REQUIRES_MULTIPLE_SESSIONS")
    if conflicts:
        chronology_reasons.append("COHORT_STRICT_SESSION_SEPARATION_NOT_SUPPORTED")
    if possible_copies:
        chronology_reasons.append("COHORT_POSSIBLE_DUPLICATE_SOURCE")
    split_counts = Counter(m["requested_split"]["split"] or "UNASSIGNED" for m in members)
    split_reasons = []
    if split_counts["UNASSIGNED"]:
        split_reasons.append("COHORT_SPLIT_ASSIGNMENT_INCOMPLETE")
    missing_splits = [split for split in SPLITS if not split_counts[split]]
    if missing_splits:
        split_reasons.append("COHORT_EVALUATION_PARTITION_EMPTY")
    boundaries = {}
    if not unsupported:
        for split in SPLITS:
            positions = [i for i, m in enumerate(members) if m["requested_split"]["split"] == split]
            if positions:
                boundaries[split] = {
                    "first_start_utc": _utc_text(min(intervals[i][0] for i in positions)),
                    "last_stop_utc": _utc_text(max(intervals[i][1] for i in positions)),
                    "member_count": len(positions),
                }
        for early, late in pairwise(SPLITS):
            if (
                early in boundaries
                and late in boundaries
                and boundaries[early]["last_stop_utc"] >= boundaries[late]["first_start_utc"]
            ):
                split_reasons.append(f"COHORT_{early}_NOT_STRICTLY_BEFORE_{late}")
    split_reasons = sorted(set(chronology_reasons + split_reasons))
    return {
        "schema_version": "0.1",
        "status": "DECLARED_INTERVAL_ORDER_SUPPORTED_WITH_LIMITATIONS"
        if not chronology_reasons
        else "SINGLE_SESSION_TIME_BOUNDS_ONLY"
        if len(members) == len(supported) == 1
        else "WITHHELD",
        "claim_scope": "SUPPLIED_TEMPORAL_METADATA_AND_REQUESTED_SPLIT_ONLY",
        "source_verification_performed": False,
        "chronological_order_supported": not chronology_reasons,
        "chronological_split_supported": not split_reasons,
        "supported_interval_count": len(supported),
        "unsupported_member_canonical_indices": unsupported,
        "compared_interval_pair_count": len(supported) * (len(supported) - 1) // 2,
        "ordered_member_canonical_indices": order if not unsupported else [],
        "interval_conflicts": conflicts,
        "possible_duplicate_pairs": [
            {"member_canonical_indices": list(pair), "reasons": sorted(reasons)}
            for pair, reasons in sorted(possible_copies.items())
        ],
        "duplicate_check_complete_for_supported_members": not unsupported,
        "duplicate_check_scope": "PROVIDER_EXERCISE_ID_AND_EXACT_FEATURE_OR_HR_SEQUENCE_REUSE_ONLY",
        "all_possible_duplicates_ruled_out": False,
        "missing_evaluation_partitions": missing_splits,
        "split_boundaries_utc": boundaries,
        "chronology_blocking_reasons": chronology_reasons,
        "split_blocking_reasons": split_reasons,
        "policy": {
            "all_published_exercises_included_in_session_bounds": True,
            "all_session_pairs_checked": True,
            "touching_boundaries_strictly_separated": False,
            "same_split_overlap_permitted_for_evaluation": False,
            "statistical_independence_established": False,
            "washout_gap_inferred": False,
            "whole_session_split_required": True,
            "split_assignment_persisted": False,
            "preprocessing_fit_scope_required": "TRAIN_ONLY",
            "feature_fit_performed": False,
            "training_authorized": False,
        },
    }
