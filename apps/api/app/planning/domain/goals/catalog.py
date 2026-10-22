"""Versioned measurement vocabulary, without scientific or dose defaults.

A method family is not a standardized or validated test protocol. Each use
must freeze its exact procedure, comparability conditions and source.
"""

from dataclasses import dataclass
from enum import StrEnum

from ..common.serialization import compute_content_hash

GOAL_CATALOG_VERSION = "capability-measurement-catalog-v0.1"


class CapabilityKey(StrEnum):
    VO2_CAPACITY = "VO2_CAPACITY"
    PERIPHERAL_OXIDATIVE_CAPACITY = "PERIPHERAL_OXIDATIVE_CAPACITY"
    PADDLING_ECONOMY = "PADDLING_ECONOMY"
    MAX_STRENGTH = "MAX_STRENGTH"
    POWER_RFD = "POWER_RFD"
    MUSCULOSKELETAL_ROBUSTNESS = "MUSCULOSKELETAL_ROBUSTNESS"
    TECHNICAL_SKILL = "TECHNICAL_SKILL"
    TECHNICAL_STABILITY_UNDER_FATIGUE = "TECHNICAL_STABILITY_UNDER_FATIGUE"
    LONG_DURATION_DURABILITY = "LONG_DURATION_DURABILITY"
    PACING_COMPETENCE = "PACING_COMPETENCE"
    SPRINT_SPEED_AND_START = "SPRINT_SPEED_AND_START"
    MUSCULAR_ENDURANCE = "MUSCULAR_ENDURANCE"
    HIGH_INTENSITY_AND_ANAEROBIC_PROFILE = "HIGH_INTENSITY_AND_ANAEROBIC_PROFILE"


class MeasurementEvidenceKind(StrEnum):
    PHYSIOLOGICAL_MEASUREMENT = "physiological_measurement"
    TASK_PERFORMANCE = "task_performance"
    ESTIMATE = "estimate"
    INDIRECT_INDICATOR = "indirect_indicator"
    SUBJECTIVE_CONTEXT = "subjective_context"


class MeasurementScale(StrEnum):
    RATIO = "ratio"
    INTERVAL = "interval"
    ORDINAL = "ordinal"


class ImprovementDirection(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"


@dataclass(frozen=True)
class GoalMetricDefinition:
    metric_key: str
    capability_key: CapabilityKey
    unit: str
    evidence_kind: MeasurementEvidenceKind
    scale: MeasurementScale
    favourable_direction: ImprovementDirection
    method_family: str
    primary_endpoint_eligible: bool
    interpretation_limit: str


def _metric(key, capability, unit, kind, direction, method, limit, *, scale=None, primary=True):
    return GoalMetricDefinition(
        key,
        capability,
        unit,
        kind,
        scale or MeasurementScale.RATIO,
        direction,
        method,
        primary,
        limit,
    )


C = CapabilityKey
E = MeasurementEvidenceKind
D = ImprovementDirection
S = MeasurementScale

# The supported metric keys deliberately separate measured and estimated VO2,
# standing/flying starts, power and RFD, and different threshold constructs.
GOAL_METRICS = (
    _metric(
        "VO2MAX_ABSOLUTE",
        C.VO2_CAPACITY,
        "L/min",
        E.PHYSIOLOGICAL_MEASUREMENT,
        D.HIGHER,
        "gas_exchange",
        "Protocol- and modality-specific oxygen uptake.",
    ),
    _metric(
        "VO2MAX_RELATIVE",
        C.VO2_CAPACITY,
        "mL/kg/min",
        E.PHYSIOLOGICAL_MEASUREMENT,
        D.HIGHER,
        "gas_exchange",
        "Body mass must also be retained.",
    ),
    _metric(
        "VO2MAX_ESTIMATED_RELATIVE",
        C.VO2_CAPACITY,
        "mL/kg/min",
        E.ESTIMATE,
        D.HIGHER,
        "vo2_estimator",
        "Not interchangeable with measured VO2max.",
    ),
    _metric(
        "SUBMAXIMAL_OUTPUT",
        C.PERIPHERAL_OXIDATIVE_CAPACITY,
        "W",
        E.INDIRECT_INDICATOR,
        D.HIGHER,
        "submaximal_task",
        "Does not isolate muscular oxidative adaptation.",
    ),
    _metric(
        "PADDLING_OXYGEN_COST",
        C.PADDLING_ECONOMY,
        "L/min",
        E.PHYSIOLOGICAL_MEASUREMENT,
        D.LOWER,
        "fixed_output_gas_exchange",
        "Requires matched external output and modality.",
    ),
    _metric(
        "STRENGTH_1RM",
        C.MAX_STRENGTH,
        "kg",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "direct_1rm",
        "Exercise/equipment/range of motion must match.",
    ),
    _metric(
        "STRENGTH_REFERENCE_LOAD",
        C.MAX_STRENGTH,
        "kg",
        E.INDIRECT_INDICATOR,
        D.HIGHER,
        "submaximal_strength_reference",
        "Repetitions, reserve and technique must match.",
    ),
    _metric(
        "STRENGTH_ESTIMATED_1RM",
        C.MAX_STRENGTH,
        "kg",
        E.ESTIMATE,
        D.HIGHER,
        "estimated_1rm",
        "Estimator version is part of the protocol.",
    ),
    _metric(
        "PEAK_POWER",
        C.POWER_RFD,
        "W",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "power_test",
        "Does not measure rate of force development.",
    ),
    _metric(
        "RATE_OF_FORCE_DEVELOPMENT",
        C.POWER_RFD,
        "N/s",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "force_time_test",
        "Requires force-time acquisition and fixed processing.",
    ),
    _metric(
        "FUNCTIONAL_TASK_REPETITIONS",
        C.MUSCULOSKELETAL_ROBUSTNESS,
        "repetition",
        E.INDIRECT_INDICATOR,
        D.HIGHER,
        "functional_task",
        "Task tolerance does not establish injury resistance.",
    ),
    _metric(
        "PAIN_RATING",
        C.MUSCULOSKELETAL_ROBUSTNESS,
        "score_0_10",
        E.SUBJECTIVE_CONTEXT,
        D.LOWER,
        "subjective_rating",
        "Context only; not a capability or diagnostic endpoint.",
        scale=S.ORDINAL,
        primary=False,
    ),
    _metric(
        "TECHNICAL_ERROR_COUNT",
        C.TECHNICAL_SKILL,
        "error",
        E.INDIRECT_INDICATOR,
        D.LOWER,
        "fixed_rubric_observation",
        "Fixed observation duration and rubric required.",
    ),
    _metric(
        "TECHNICAL_ERROR_INCREASE",
        C.TECHNICAL_STABILITY_UNDER_FATIGUE,
        "error",
        E.INDIRECT_INDICATOR,
        D.LOWER,
        "fresh_loaded_technical_task",
        "Fixed loading and matched fresh/loaded observations required.",
        scale=S.INTERVAL,
    ),
    _metric(
        "POWER_RETENTION",
        C.LONG_DURATION_DURABILITY,
        "percent",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "prolonged_task",
        "Fresh/loaded tasks and preceding load must match.",
    ),
    _metric(
        "HEART_RATE_DRIFT",
        C.LONG_DURATION_DURABILITY,
        "percentage_point",
        E.INDIRECT_INDICATOR,
        D.LOWER,
        "fixed_output_drift",
        "Affected by conditions; does not diagnose fatigue.",
        scale=S.INTERVAL,
    ),
    _metric(
        "PACING_PROFILE_ERROR",
        C.PACING_COMPETENCE,
        "percent",
        E.TASK_PERFORMANCE,
        D.LOWER,
        "target_profile_tracking",
        "Evaluate against the prescribed strategy.",
    ),
    _metric(
        "STANDING_START_TIME",
        C.SPRINT_SPEED_AND_START,
        "s",
        E.TASK_PERFORMANCE,
        D.LOWER,
        "standing_start_sprint",
        "Fixed distance, start and timing method required.",
    ),
    _metric(
        "FLYING_START_SPEED",
        C.SPRINT_SPEED_AND_START,
        "m/s",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "flying_start_sprint",
        "Not interchangeable with standing-start results.",
    ),
    _metric(
        "FIXED_LOAD_REPETITIONS",
        C.MUSCULAR_ENDURANCE,
        "repetition",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "fixed_load_endurance",
        "Fixed load, movement and termination rule required.",
    ),
    _metric(
        "LACTATE_THRESHOLD_POWER",
        C.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
        "W",
        E.INDIRECT_INDICATOR,
        D.HIGHER,
        "lactate_threshold",
        "Threshold definition must be frozen; not an anaerobic capacity measure.",
    ),
    _metric(
        "VENTILATORY_THRESHOLD_POWER",
        C.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
        "W",
        E.INDIRECT_INDICATOR,
        D.HIGHER,
        "ventilatory_threshold",
        "Not interchangeable with lactate threshold or critical power.",
    ),
    _metric(
        "CRITICAL_POWER",
        C.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
        "W",
        E.ESTIMATE,
        D.HIGHER,
        "critical_power_model",
        "Model, trials and fitting procedure must be frozen.",
    ),
    _metric(
        "SPRINT_MEAN_POWER",
        C.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
        "W",
        E.TASK_PERFORMANCE,
        D.HIGHER,
        "fixed_duration_sprint",
        "Mixed energy-system performance; not a pure anaerobic capacity measure.",
    ),
    _metric(
        "ANAEROBIC_CAPACITY_ESTIMATE",
        C.HIGH_INTENSITY_AND_ANAEROBIC_PROFILE,
        "J",
        E.ESTIMATE,
        D.HIGHER,
        "anaerobic_capacity_estimator",
        "Method-dependent estimate; cannot be inferred from sprint power alone.",
    ),
)

GOAL_CATALOG_HASH = compute_content_hash(
    {"version": GOAL_CATALOG_VERSION, "capabilities": tuple(CapabilityKey), "metrics": GOAL_METRICS}
)


def goal_metric(metric_key: str) -> GoalMetricDefinition:
    for metric in GOAL_METRICS:
        if metric.metric_key == metric_key:
            return metric
    raise ValueError("Unsupported goal metric key.")
