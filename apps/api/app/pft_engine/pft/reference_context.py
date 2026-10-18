"""Observed load and end-stage HR context, separate from physiological labels."""

from datetime import timezone
import hashlib
import json
import math
from statistics import fmean, median, pstdev

from app.pft_engine.contracts.input import ImportedSession
from app.pft_engine.pft.protocol import PftProtocol, PftStage


REFERENCE_CONTEXT_VERSION = "pft_reference_context_v0.1"


def _finite(value):
    return value is not None and math.isfinite(value)


def _window(session, start_s, end_s, target_w):
    selected = [s for s in session.samples if start_s <= s.elapsed_s < end_s]
    hr_samples = [s for s in selected if _finite(s.hr_bpm)]
    hr = [s.hr_bpm for s in hr_samples]
    power = [s.power_w for s in selected if _finite(s.power_w)]
    hr_mean = fmean(hr) if hr else None
    power_mean = fmean(power) if power else None
    hr_trend = None
    if len(hr_samples) >= 2:
        t_mean = fmean(s.elapsed_s for s in hr_samples)
        denominator = sum((s.elapsed_s - t_mean)**2 for s in hr_samples)
        if denominator > 0:
            hr_trend = 60.0 * sum(
                (s.elapsed_s - t_mean) * (s.hr_bpm - hr_mean)
                for s in hr_samples
            ) / denominator
    gaps = [
        b.elapsed_s - a.elapsed_s
        for a, b in zip(selected, selected[1:])
    ]
    return {
        "start_s": start_s,
        "end_s_exclusive": end_s,
        "sample_count": len(selected),
        "observed_first_sample_s": selected[0].elapsed_s if selected else None,
        "observed_last_sample_s": selected[-1].elapsed_s if selected else None,
        "maximum_sample_gap_s": max(gaps) if gaps else None,
        "finite_hr_sample_count": len(hr),
        "finite_power_sample_count": len(power),
        "hr_mean_bpm": hr_mean,
        "hr_median_bpm": median(hr) if hr else None,
        "hr_linear_trend_bpm_per_min": hr_trend,
        "power_mean_w": power_mean,
        "power_cv_pct": (
            100.0 * pstdev(power) / power_mean
            if power and power_mean is not None and power_mean > 0
            else None
        ),
        "mean_power_minus_target_w": power_mean - target_w if power_mean is not None else None,
        "mean_power_minus_target_pct": (
            100.0 * (power_mean - target_w) / target_w
            if power_mean is not None else None
        ),
        "steady_state_confirmed": None,
        "baseline_eligible": None,
    }


def build_pft_reference_context(
    *,
    session: ImportedSession,
    protocol: PftProtocol,
    profile: dict,
    raw_source_sha256: str | None = None,
) -> dict:
    """Describe actual samples under explicit, separately stored power targets.

    Counts and trends describe the signal. They do not assign acquisition
    accuracy, state, target-adherence thresholds or baseline eligibility.
    """
    if profile.get("schema_version") != "0.1":
        raise ValueError("Unsupported target profile schema.")
    if profile.get("protocol") != {"name": protocol.name, "version": protocol.version}:
        raise ValueError("Target profile protocol differs from the processed protocol.")
    if not isinstance(profile.get("profile_id"), str) or not profile["profile_id"].strip():
        raise ValueError("Target profile requires a nonempty profile_id.")
    targets = profile.get("target_power_w")
    if not isinstance(targets, dict) or set(targets) != {"p0", "p1", "p2"}:
        raise ValueError("Target profile requires p0, p1 and p2 power targets.")
    for value in targets.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Power targets must be finite positive watts.")
    times = [s.elapsed_s for s in session.samples]
    if any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Reference context requires finite, strictly increasing sample times.")
    expected_stages = {PftStage.P0, PftStage.P1, PftStage.P2}
    stages = [w for w in protocol.stages if w.stage in expected_stages]
    if {w.stage for w in stages} != expected_stages or len(stages) != 3:
        raise ValueError("Protocol requires one P0, P1 and P2 stage.")
    if any(w.duration_s < 60.0 for w in stages):
        raise ValueError("Protocol stages must cover the declared 60-second end window.")
    signature_input = {
        "profile": profile,
        "stage_windows": [
            {"stage": w.stage.value, "start_s": w.start_s, "end_s": w.end_s}
            for w in protocol.stages
        ],
    }
    signature = hashlib.sha256(json.dumps(
        signature_input, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    observations = []
    for stage in stages:
        target = targets[stage.stage.value]
        observations.append({
            "stage": stage.stage.value,
            "intended_target_w": target,
            "whole_stage": _window(session, stage.start_s, stage.end_s, target),
            "end_windows": {
                str(seconds): _window(session, stage.end_s - seconds, stage.end_s, target)
                for seconds in (30, 45, 60)
            },
        })
    return {
        "schema_version": REFERENCE_CONTEXT_VERSION,
        "status": "OBSERVED_LOAD_AND_END_HR_CONTEXT_WITH_LIMITATIONS",
        "raw_source_sha256": raw_source_sha256,
        "started_at_utc": session.started_at.astimezone(timezone.utc).isoformat(),
        "last_observed_sample_at_utc": (
            session.samples[-1].timestamp.astimezone(timezone.utc).isoformat()
            if session.samples else None
        ),
        "target_profile": profile,
        "stimulus_context_sha256": signature,
        "primary_p2_end_window_seconds": 60,
        "primary_p2_statistic": "MEAN",
        "primary_p2_feature_id": "HR_P2_END60_MEAN",
        "secondary_p2_end_window_seconds": [30, 45],
        "window_anchor": "NOMINAL_STAGE_END; OBSERVED_TRANSITIONS_REMAIN_IN_PROCESSING_OUTPUT",
        "stages": observations,
        "unmeasured_context": {
            "air_temperature_c": None,
            "hydration_state": None,
            "illness_status": None,
            "preparation_and_warmup": None,
            "recovery_posture_and_movement": None,
            "device_body_weight_setting_kg": None,
            "independent_hr_acquisition_accuracy": None,
            "preceding_28_day_history_coverage": None,
        },
        "automatic_baseline_update_authorized": False,
        "fitness_or_fatigue_state_estimated": False,
        "training_load_increase_authorized": False,
        "limitations": [
            "USE_OF_PRESCRIBED_TARGETS_DURING_THIS_RECORD_NOT_INDEPENDENTLY_VERIFIED",
            "TARGET_ADHERENCE_THRESHOLDS_NOT_VALIDATED",
            "END_WINDOW_DOES_NOT_ESTABLISH_STEADY_STATE",
            "PROFILE_CONTEXT_NOT_AUTOMATICALLY_ENFORCED_BY_LEGACY_ARCHIVE_COMPARISON",
            "WRIST_HR_KINETICS_ACCURACY_NOT_INDEPENDENTLY_VERIFIED",
            "UNKNOWN_CONTEXT_IS_NOT_A_HEALTHY_OR_RECOVERED_LABEL",
        ],
    }
