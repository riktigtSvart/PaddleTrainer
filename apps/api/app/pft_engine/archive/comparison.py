from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureDelta:
    name: str
    unit: str | None

    reference_value: float | None
    current_value: float | None

    delta: float | None
    relative_change_pct: float | None

    reference_quality_grade: str
    current_quality_grade: str

    reference_baseline_eligible: bool
    current_baseline_eligible: bool


@dataclass(frozen=True)
class RhriDelta:
    method: str
    stage: str

    reference_value_bpm_per_s: float
    current_value_bpm_per_s: float

    delta_bpm_per_s: float
    relative_change_pct: float | None


@dataclass(frozen=True)
class PftArchiveComparison:
    reference_started_at: str
    current_started_at: str

    protocol_name: str
    protocol_version: str

    output_schema_version: str

    reference_processor_version: str
    current_processor_version: str

    reference_session_quality_grade: str
    current_session_quality_grade: str

    features: tuple[FeatureDelta, ...]
    rhri: tuple[RhriDelta, ...]


class PftComparisonIncompatible(
    ValueError
):
    def __init__(
        self,
        issues: tuple[str, ...],
    ) -> None:
        self.issues = issues

        super().__init__(
            "PFT results are not comparable: "
            + "; ".join(issues)
        )


def _relative_change_pct(
    reference: float,
    current: float,
) -> float | None:

    if reference == 0.0:
        return None

    return (
        (current - reference)
        / abs(reference)
        * 100.0
    )


def _compatibility_issues(
    reference: dict[str, Any],
    current: dict[str, Any],
) -> tuple[str, ...]:

    issues: list[str] = []

    reference_schema = reference.get(
        "schema_version"
    )
    current_schema = current.get(
        "schema_version"
    )

    if reference_schema != current_schema:
        issues.append(
            "output schema differs: "
            f"{reference_schema!r} != "
            f"{current_schema!r}"
        )

    reference_protocol = reference.get(
        "protocol",
        {},
    )
    current_protocol = current.get(
        "protocol",
        {},
    )

    for field in (
        "name",
        "version",
    ):
        reference_value = (
            reference_protocol.get(field)
        )

        current_value = (
            current_protocol.get(field)
        )

        if reference_value != current_value:
            issues.append(
                f"protocol {field} differs: "
                f"{reference_value!r} != "
                f"{current_value!r}"
            )

    reference_lineage = reference.get(
        "algorithm_lineage",
        {},
    )

    current_lineage = current.get(
        "algorithm_lineage",
        {},
    )

    # Processor itself is intentionally not included.
    # Component algorithms define scientific comparability.
    comparable_algorithms = (
        "stage_quality",
        "transition_detection",
        "feature_extraction",
        "feature_quality",
        "rhri_local",
        "rhri_sig",
        "rhri_diagnostics",
    )

    for algorithm in comparable_algorithms:
        reference_version = (
            reference_lineage.get(
                algorithm
            )
        )

        current_version = (
            current_lineage.get(
                algorithm
            )
        )

        if (
            reference_version
            != current_version
        ):
            issues.append(
                f"{algorithm} differs: "
                f"{reference_version!r} != "
                f"{current_version!r}"
            )

    return tuple(issues)


def _features_by_name(
    document: dict[str, Any],
) -> dict[str, dict[str, Any]]:

    result: dict[
        str,
        dict[str, Any],
    ] = {}

    for feature in document.get(
        "features",
        [],
    ):
        name = feature.get("name")

        if isinstance(name, str):
            result[name] = feature

    return result


def _calculate_feature_deltas(
    reference: dict[str, Any],
    current: dict[str, Any],
) -> tuple[FeatureDelta, ...]:

    reference_features = (
        _features_by_name(
            reference
        )
    )

    current_features = (
        _features_by_name(
            current
        )
    )

    # Preserve reference document order.
    names = [
        feature["name"]
        for feature in reference.get(
            "features",
            [],
        )
        if (
            feature.get("name")
            in current_features
        )
    ]

    deltas: list[FeatureDelta] = []

    for name in names:
        old = reference_features[name]
        new = current_features[name]

        old_value = old.get("value")
        new_value = new.get("value")

        if (
            old_value is None
            or new_value is None
        ):
            delta = None
            relative = None
        else:
            old_float = float(
                old_value
            )
            new_float = float(
                new_value
            )

            delta = (
                new_float
                - old_float
            )

            relative = (
                _relative_change_pct(
                    old_float,
                    new_float,
                )
            )

        deltas.append(
            FeatureDelta(
                name=name,
                unit=new.get("unit"),
                reference_value=(
                    None
                    if old_value is None
                    else float(old_value)
                ),
                current_value=(
                    None
                    if new_value is None
                    else float(new_value)
                ),
                delta=delta,
                relative_change_pct=(
                    relative
                ),
                reference_quality_grade=(
                    str(
                        old.get(
                            "quality_grade",
                            "",
                        )
                    )
                ),
                current_quality_grade=(
                    str(
                        new.get(
                            "quality_grade",
                            "",
                        )
                    )
                ),
                reference_baseline_eligible=(
                    bool(
                        old.get(
                            "baseline_eligible",
                            False,
                        )
                    )
                ),
                current_baseline_eligible=(
                    bool(
                        new.get(
                            "baseline_eligible",
                            False,
                        )
                    )
                ),
            )
        )

    return tuple(deltas)


def _rhri_values(
    document: dict[str, Any],
    method: str,
) -> dict[str, float]:

    experimental = document.get(
        "experimental",
        {},
    )

    values = experimental.get(
        method,
        [],
    )

    result: dict[str, float] = {}

    for item in values:
        stage = item.get("stage")
        value = item.get(
            "value_bpm_per_s"
        )

        if (
            isinstance(stage, str)
            and value is not None
        ):
            result[stage] = float(
                value
            )

    return result


def _calculate_rhri_deltas(
    reference: dict[str, Any],
    current: dict[str, Any],
) -> tuple[RhriDelta, ...]:

    output: list[RhriDelta] = []

    for json_key, label in (
        ("rhri_local", "RHRI_LOCAL"),
        ("rhri_sig", "RHRI_SIG"),
    ):
        reference_values = _rhri_values(
            reference,
            json_key,
        )

        current_values = _rhri_values(
            current,
            json_key,
        )

        for stage in (
            "p1",
            "p2",
        ):
            if (
                stage not in reference_values
                or stage not in current_values
            ):
                continue

            old = reference_values[
                stage
            ]

            new = current_values[
                stage
            ]

            output.append(
                RhriDelta(
                    method=label,
                    stage=stage,
                    reference_value_bpm_per_s=old,
                    current_value_bpm_per_s=new,
                    delta_bpm_per_s=(
                        new - old
                    ),
                    relative_change_pct=(
                        _relative_change_pct(
                            old,
                            new,
                        )
                    ),
                )
            )

    return tuple(output)


def compare_pft_documents(
    *,
    reference: dict[str, Any],
    current: dict[str, Any],
) -> PftArchiveComparison:

    issues = _compatibility_issues(
        reference,
        current,
    )

    if issues:
        raise PftComparisonIncompatible(
            issues
        )

    protocol = reference[
        "protocol"
    ]

    reference_lineage = reference[
        "algorithm_lineage"
    ]

    current_lineage = current[
        "algorithm_lineage"
    ]

    return PftArchiveComparison(
        reference_started_at=(
            reference["session"]
            ["started_at"]
        ),
        current_started_at=(
            current["session"]
            ["started_at"]
        ),
        protocol_name=protocol[
            "name"
        ],
        protocol_version=protocol[
            "version"
        ],
        output_schema_version=(
            reference[
                "schema_version"
            ]
        ),
        reference_processor_version=(
            reference_lineage[
                "processor"
            ]
        ),
        current_processor_version=(
            current_lineage[
                "processor"
            ]
        ),
        reference_session_quality_grade=(
            reference[
                "session_quality_grade"
            ]
        ),
        current_session_quality_grade=(
            current[
                "session_quality_grade"
            ]
        ),
        features=(
            _calculate_feature_deltas(
                reference,
                current,
            )
        ),
        rhri=(
            _calculate_rhri_deltas(
                reference,
                current,
            )
        ),
    )