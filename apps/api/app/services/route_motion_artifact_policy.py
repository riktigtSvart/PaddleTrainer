from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


ACTION_OBSERVE = "OBSERVE"
ACTION_SUPPRESS = "SUPPRESS"
ACTION_EXCLUDE = "EXCLUDE"
ACTION_RECONSTRUCT = "RECONSTRUCT"
ACTION_REVIEW = "REVIEW"

PROFILE_SENSITIVE = "SENSITIVE"
PROFILE_BALANCED = "BALANCED"
PROFILE_CONSERVATIVE = "CONSERVATIVE"
PROFILE_CUSTOM = "CUSTOM"

SUPPORTED_ACTIONS = (
    ACTION_OBSERVE,
    ACTION_SUPPRESS,
    ACTION_EXCLUDE,
    ACTION_RECONSTRUCT,
    ACTION_REVIEW,
)

POLICY_VERSION = "0.4"


SUPPORTED_PROFILES = (
    PROFILE_SENSITIVE,
    PROFILE_BALANCED,
    PROFILE_CONSERVATIVE,
    PROFILE_CUSTOM,
)


# v0.1 thresholds are intentionally provisional and configurable.
# The balanced profile is anchored to the first-route-window evidence
# collected from the April-September 2026 kayak sample. These thresholds
# are policy parameters, not physiological or physical truths.
_PROFILE_THRESHOLDS: dict[str, dict[str, Any]] = {
    PROFILE_SENSITIVE: {
        "late_route_start_ms": 10_000,
        "geometry_cross_track_m": 0.35,
        "geometry_path_minus_net_m": 0.20,
        "temporal_min_speed_range_mps": 0.75,
        "temporal_peak_to_last_drop_fraction": 0.50,
        "temporal_min_sign_reversals": 1,
        "temporal_residual_cancellation_fraction": 0.75,
        "temporal_min_trigger_count": 2,
        "cross_source_max_abs_difference_mps": 1.50,
        "material_cross_track_m": 0.35,
        "material_path_minus_net_m": 0.20,
        "material_speed_range_mps": 1.25,
        "material_cross_source_difference_mps": 1.50,
        "review_min_supporting_dimensions": 2,
        "intervention_min_supporting_dimensions": 3,
        "reconstruction_requires_backward_anchor": True,
        "reconstruction_requires_forward_anchor": True,
    },
    PROFILE_BALANCED: {
        "late_route_start_ms": 30_000,
        "geometry_cross_track_m": 0.75,
        "geometry_path_minus_net_m": 0.50,
        "temporal_min_speed_range_mps": 1.00,
        "temporal_peak_to_last_drop_fraction": 0.75,
        "temporal_min_sign_reversals": 2,
        "temporal_residual_cancellation_fraction": 0.85,
        "temporal_min_trigger_count": 2,
        "cross_source_max_abs_difference_mps": 3.00,
        "material_cross_track_m": 0.75,
        "material_path_minus_net_m": 0.50,
        "material_speed_range_mps": 2.00,
        "material_cross_source_difference_mps": 3.00,
        "review_min_supporting_dimensions": 2,
        "intervention_min_supporting_dimensions": 3,
        "reconstruction_requires_backward_anchor": True,
        "reconstruction_requires_forward_anchor": True,
    },
    PROFILE_CONSERVATIVE: {
        "late_route_start_ms": 60_000,
        "geometry_cross_track_m": 1.50,
        "geometry_path_minus_net_m": 1.00,
        "temporal_min_speed_range_mps": 2.00,
        "temporal_peak_to_last_drop_fraction": 0.90,
        "temporal_min_sign_reversals": 2,
        "temporal_residual_cancellation_fraction": 0.90,
        "temporal_min_trigger_count": 2,
        "cross_source_max_abs_difference_mps": 5.00,
        "material_cross_track_m": 1.50,
        "material_path_minus_net_m": 1.00,
        "material_speed_range_mps": 4.00,
        "material_cross_source_difference_mps": 5.00,
        "review_min_supporting_dimensions": 2,
        "intervention_min_supporting_dimensions": 3,
        "reconstruction_requires_backward_anchor": True,
        "reconstruction_requires_forward_anchor": True,
    },
}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if not isinstance(value, (int, float)):
        return None

    result = float(value)

    if not math.isfinite(result):
        return None

    return result


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
    ):
        return int(value)

    return None


def _thresholds(
    profile: str,
    custom_thresholds: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_profile = profile.upper()

    if normalized_profile not in SUPPORTED_PROFILES:
        raise ValueError(
            "profile must be one of: "
            + ", ".join(SUPPORTED_PROFILES)
        )

    if normalized_profile == PROFILE_CUSTOM:
        if custom_thresholds is None:
            raise ValueError(
                "custom_thresholds is required for CUSTOM profile"
            )

        base = deepcopy(
            _PROFILE_THRESHOLDS[PROFILE_BALANCED]
        )
        base.update(custom_thresholds)
        return base

    result = deepcopy(
        _PROFILE_THRESHOLDS[normalized_profile]
    )

    if custom_thresholds:
        result.update(custom_thresholds)

    return result


def _value_at_least(
    value: Any,
    threshold: Any,
) -> bool:
    numeric_value = _finite_number(value)
    numeric_threshold = _finite_number(threshold)

    return (
        numeric_value is not None
        and numeric_threshold is not None
        and numeric_value >= numeric_threshold
    )


def _route_policy(
    route: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    reconstruction_context: dict[str, Any] | None,
) -> dict[str, Any]:
    available = route.get("available") is True

    trajectory_summary = route.get("trajectory_summary")
    if not isinstance(trajectory_summary, dict):
        trajectory_summary = {}

    geometry = route.get("geometry")
    if not isinstance(geometry, dict):
        geometry = {}

    temporal = route.get("temporal_residual")
    if not isinstance(temporal, dict):
        temporal = {}

    cross_source = route.get("cross_source_speed")
    if not isinstance(cross_source, dict):
        cross_source = {}

    first_waypoint_ms = _integer(
        route.get("first_route_waypoint_exercise_elapsed_ms")
    )
    speed_range_mps = _finite_number(
        trajectory_summary.get("gps_ground_speed_range_mps")
    )
    peak_drop_fraction = _finite_number(
        trajectory_summary.get(
            "peak_to_last_drop_fraction_of_speed_range"
        )
    )
    sign_reversals = _integer(
        trajectory_summary.get(
            "speed_change_sign_reversal_count"
        )
    )
    cross_track_m = _finite_number(
        geometry.get(
            "maximum_middle_point_cross_track_deviation_m"
        )
    )
    path_minus_net_m = _finite_number(
        geometry.get(
            "path_minus_net_displacement_sum_m"
        )
    )
    residual_cancellation = _finite_number(
        temporal.get(
            "window_residual_cancellation_fraction"
        )
    )
    max_cross_source_difference_mps = _finite_number(
        cross_source.get(
            "maximum_absolute_gps_polar_speed_difference_mps"
        )
    )

    late_route_start_context = (
        first_waypoint_ms is not None
        and first_waypoint_ms
        >= thresholds["late_route_start_ms"]
    )

    geometry_cross_track_trigger = _value_at_least(
        cross_track_m,
        thresholds["geometry_cross_track_m"],
    )
    geometry_path_trigger = _value_at_least(
        path_minus_net_m,
        thresholds["geometry_path_minus_net_m"],
    )
    geometry_support = (
        geometry_cross_track_trigger
        or geometry_path_trigger
    )

    temporal_speed_range_gate = _value_at_least(
        speed_range_mps,
        thresholds["temporal_min_speed_range_mps"],
    )
    temporal_peak_drop_trigger = _value_at_least(
        peak_drop_fraction,
        thresholds[
            "temporal_peak_to_last_drop_fraction"
        ],
    )
    temporal_sign_reversal_trigger = (
        sign_reversals is not None
        and sign_reversals
        >= thresholds["temporal_min_sign_reversals"]
    )
    temporal_cancellation_trigger = _value_at_least(
        residual_cancellation,
        thresholds[
            "temporal_residual_cancellation_fraction"
        ],
    )
    temporal_trigger_count = sum(
        1
        for triggered in (
            temporal_peak_drop_trigger,
            temporal_sign_reversal_trigger,
            temporal_cancellation_trigger,
        )
        if triggered
    )
    temporal_support = (
        temporal_speed_range_gate
        and temporal_trigger_count
        >= thresholds["temporal_min_trigger_count"]
    )

    cross_source_support = _value_at_least(
        max_cross_source_difference_mps,
        thresholds[
            "cross_source_max_abs_difference_mps"
        ],
    )

    supporting_dimensions = [
        dimension
        for dimension, supported in (
            ("GEOMETRY", geometry_support),
            ("TEMPORAL", temporal_support),
            ("CROSS_SOURCE", cross_source_support),
        )
        if supported
    ]

    materiality_triggers = {
        "cross_track": _value_at_least(
            cross_track_m,
            thresholds["material_cross_track_m"],
        ),
        "path_minus_net": _value_at_least(
            path_minus_net_m,
            thresholds["material_path_minus_net_m"],
        ),
        "speed_range": _value_at_least(
            speed_range_mps,
            thresholds["material_speed_range_mps"],
        ),
        "cross_source_difference": _value_at_least(
            max_cross_source_difference_mps,
            thresholds[
                "material_cross_source_difference_mps"
            ],
        ),
    }
    materiality_supported = any(
        materiality_triggers.values()
    )

    reconstruction_context = (
        reconstruction_context
        if isinstance(reconstruction_context, dict)
        else {}
    )

    expected_segment_indices = route.get(
        "expected_segment_indices"
    )
    if not isinstance(
        expected_segment_indices,
        list,
    ):
        expected_segment_indices = []

    first_expected_segment_index = (
        expected_segment_indices[0]
        if expected_segment_indices
        else None
    )

    if (
        "backward_anchor_available"
        in reconstruction_context
    ):
        backward_anchor_available = (
            reconstruction_context.get(
                "backward_anchor_available"
            )
            is True
        )
    elif first_expected_segment_index == 0:
        backward_anchor_available = False
    else:
        backward_anchor_available = None

    if (
        "forward_anchor_available"
        in reconstruction_context
    ):
        forward_anchor_available = (
            reconstruction_context.get(
                "forward_anchor_available"
            )
            is True
        )
    else:
        forward_anchor_available = None

    backward_ok = (
        not thresholds[
            "reconstruction_requires_backward_anchor"
        ]
        or backward_anchor_available is True
    )
    forward_ok = (
        not thresholds[
            "reconstruction_requires_forward_anchor"
        ]
        or forward_anchor_available is True
    )
    reconstruction_eligible = (
        backward_ok
        and forward_ok
    )

    supporting_dimension_count = len(
        supporting_dimensions
    )

    if not available:
        action = ACTION_OBSERVE
        reason = "EVIDENCE_UNAVAILABLE"
    elif supporting_dimension_count == 0:
        action = ACTION_OBSERVE
        reason = "NO_POLICY_EVIDENCE_DIMENSION_TRIGGERED"
    elif (
        supporting_dimension_count
        < thresholds["review_min_supporting_dimensions"]
    ):
        if materiality_supported:
            action = ACTION_REVIEW
            reason = "SINGLE_DIMENSION_WITH_MATERIALITY_EVIDENCE"
        else:
            action = ACTION_SUPPRESS
            reason = "SINGLE_DIMENSION_LOW_MATERIALITY_EVIDENCE"
    elif (
        supporting_dimension_count
        < thresholds[
            "intervention_min_supporting_dimensions"
        ]
    ):
        action = ACTION_REVIEW
        reason = "MULTI_DIMENSION_EVIDENCE_BELOW_INTERVENTION_REQUIREMENT"
    elif not materiality_supported:
        action = ACTION_REVIEW
        reason = "MULTI_DIMENSION_EVIDENCE_WITHOUT_MATERIALITY_SUPPORT"
    elif reconstruction_eligible:
        action = ACTION_RECONSTRUCT
        reason = "MULTI_DIMENSION_MATERIAL_EVIDENCE_WITH_REQUIRED_ANCHORS"
    else:
        action = ACTION_EXCLUDE
        reason = "MULTI_DIMENSION_MATERIAL_EVIDENCE_WITHOUT_REQUIRED_ANCHORS"

    return {
        "route_index": route.get("route_index"),
        "exercise_index": route.get("exercise_index"),
        "available": available,
        "action": action,
        "reason": reason,
        "supporting_dimensions": supporting_dimensions,
        "supporting_dimension_count": supporting_dimension_count,
        "context": {
            "late_route_start": late_route_start_context,
            "first_route_waypoint_exercise_elapsed_ms": (
                first_waypoint_ms
            ),
            "trust_boundary": {
                "status": (
                    reconstruction_context.get(
                        "trust_boundary_status"
                    )
                ),
                "geometry_supported_usable_from_exercise_elapsed_ms": (
                    reconstruction_context.get(
                        "geometry_supported_usable_from_exercise_elapsed_ms"
                    )
                ),
                "time_to_validated_forward_anchor_ms": (
                    reconstruction_context.get(
                        "time_to_validated_forward_anchor_ms"
                    )
                ),
                "segments_to_validated_forward_anchor": (
                    reconstruction_context.get(
                        "segments_to_validated_forward_anchor"
                    )
                ),
            },
        },
        "evidence": {
            "geometry": {
                "supported": geometry_support,
                "maximum_middle_point_cross_track_deviation_m": (
                    cross_track_m
                ),
                "cross_track_triggered": (
                    geometry_cross_track_trigger
                ),
                "path_minus_net_displacement_sum_m": (
                    path_minus_net_m
                ),
                "path_minus_net_triggered": (
                    geometry_path_trigger
                ),
            },
            "temporal": {
                "supported": temporal_support,
                "speed_range_mps": speed_range_mps,
                "speed_range_gate_passed": (
                    temporal_speed_range_gate
                ),
                "peak_to_last_drop_fraction_of_speed_range": (
                    peak_drop_fraction
                ),
                "peak_drop_triggered": (
                    temporal_peak_drop_trigger
                ),
                "speed_change_sign_reversal_count": (
                    sign_reversals
                ),
                "sign_reversal_triggered": (
                    temporal_sign_reversal_trigger
                ),
                "window_residual_cancellation_fraction": (
                    residual_cancellation
                ),
                "residual_cancellation_triggered": (
                    temporal_cancellation_trigger
                ),
                "trigger_count": temporal_trigger_count,
            },
            "cross_source": {
                "supported": cross_source_support,
                "maximum_absolute_gps_polar_speed_difference_mps": (
                    max_cross_source_difference_mps
                ),
                "difference_triggered": (
                    cross_source_support
                ),
            },
        },
        "materiality": {
            "supported": materiality_supported,
            "triggers": materiality_triggers,
        },
        "scope": {
            "type": "FIRST_ROUTE_WINDOW",
            "expected_segment_indices": (
                expected_segment_indices
            ),
            "window_start_exercise_elapsed_ms": (
                route.get(
                    "startup_window_start_exercise_elapsed_ms"
                )
            ),
            "window_end_exercise_elapsed_ms": (
                route.get(
                    "startup_window_end_exercise_elapsed_ms"
                )
            ),
            "directive_applies_to_entire_route": False,
        },
        "reconstruction_eligibility": {
            "eligible": reconstruction_eligible,
            "backward_anchor_available": (
                backward_anchor_available
            ),
            "forward_anchor_available": (
                forward_anchor_available
            ),
            "forward_anchor_exercise_elapsed_ms": (
                reconstruction_context.get(
                    "forward_anchor_exercise_elapsed_ms"
                )
            ),
            "requires_backward_anchor": thresholds[
                "reconstruction_requires_backward_anchor"
            ],
            "requires_forward_anchor": thresholds[
                "reconstruction_requires_forward_anchor"
            ],
            "anchor_state_semantics": (
                "true=validated available, "
                "false=known unavailable, "
                "null=not yet validated"
            ),
        },
    }


def build_route_motion_artifact_policy(
    startup_evidence: dict[str, Any],
    *,
    profile: str = PROFILE_BALANCED,
    custom_thresholds: dict[str, Any] | None = None,
    reconstruction_context_by_route_index: (
        dict[int, dict[str, Any]] | None
    ) = None,
) -> dict[str, Any]:
    """Build a non-mutating policy decision over first-route-window evidence.

    v0.4 deliberately separates evidence from action. It does not smooth,
    delete, exclude, or reconstruct route data. It only emits the policy
    action that downstream processing may choose to apply.
    """
    normalized_profile = profile.upper()
    thresholds = _thresholds(
        normalized_profile,
        custom_thresholds,
    )

    route_results = []

    for route_position, route in enumerate(
        startup_evidence.get("routes") or []
    ):
        if not isinstance(route, dict):
            continue

        route_index = _integer(
            route.get("route_index")
        )
        if route_index is None:
            route_index = route_position

        reconstruction_context = None
        if reconstruction_context_by_route_index:
            reconstruction_context = (
                reconstruction_context_by_route_index.get(
                    route_index
                )
            )

        route_results.append(
            _route_policy(
                route,
                thresholds=thresholds,
                reconstruction_context=reconstruction_context,
            )
        )

    action_counts = {
        action: sum(
            1
            for route in route_results
            if route.get("action") == action
        )
        for action in SUPPORTED_ACTIONS
    }

    return {
        "provider": startup_evidence.get("provider"),
        "policy_version": POLICY_VERSION,
        "profile": normalized_profile,
        "available": bool(route_results),
        "route_count": len(route_results),
        "thresholds": thresholds,
        "action_counts": action_counts,
        "routes": route_results,
    }
