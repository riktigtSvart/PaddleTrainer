"""Prepare/run/check a fixed offline development baseline; TEST is integrity-only."""

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from pydantic import ValidationError  # noqa: E402

from app.services.environment_replay_snapshot import canonical_hash  # noqa: E402
from app.services.response_baseline_experiment import (  # noqa: E402
    MAX_ARTIFACT_BYTES,
    build_response_baseline_plan,
    check_response_baseline_experiment,
    run_response_baseline_experiment,
)
from app.services.response_model_inputs import MAX_INPUT_BYTES  # noqa: E402

MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 3 * 1024 * 1024
MAX_DATASET_BYTES = 96 * 1024 * 1024
MAX_TOTAL_DATASET_BYTES = 256 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("BASELINE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("BASELINE_NONFINITE_JSON")


def read_json(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("BASELINE_FILE_SIZE_LIMIT")
    return raw, json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=_nonfinite
    )


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_new(path, value):
    raw = encode(value)
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise ValueError("BASELINE_OUTPUT_FILE_SIZE_LIMIT")
    destination = Path(path)
    with destination.open("xb") as output:
        try:
            output.write(raw)
        except BaseException:
            output.close()
            destination.unlink(missing_ok=True)
            raise


def _sources(args):
    original, data = [], []
    paths = [
        (args.manifest, MAX_MANIFEST_BYTES),
        (args.archive, MAX_ARCHIVE_BYTES),
        (args.inputs, MAX_INPUT_BYTES),
    ]
    paths.extend((p, MAX_DATASET_BYTES) for p in args.dataset)
    if len(args.dataset) > 20:
        raise ValueError("BASELINE_DATASET_COUNT_LIMIT")
    total = 0
    for index, (path, limit) in enumerate(paths):
        raw, value = read_json(path, limit)
        if index >= 3:
            total += len(raw)
            if total > MAX_TOTAL_DATASET_BYTES:
                raise ValueError("BASELINE_TOTAL_DATASET_SIZE_LIMIT")
        original.append((Path(path), raw))
        data.append(value)
    return data[0], data[1], data[2], data[3:], original


def _unchanged(original):
    for path, raw in original:
        with path.open("rb") as source:
            if source.read(len(raw) + 1) != raw:
                raise ValueError("BASELINE_SOURCE_CHANGED_DURING_CONTROL")


def _rehash(run):
    run["run_hash"] = canonical_hash({k: v for k, v in run.items() if k != "run_hash"})
    return run


def _rejected(run, plan, package, manifest, archive, datasets):
    try:
        check_response_baseline_experiment(
            run, plan, package, manifest, archive, datasets
        )
    except (
        ValidationError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
    ):
        return True
    raise ValueError("BASELINE_NEGATIVE_CONTROL_ACCEPTED")


def _negative_controls(run, plan, package, manifest, archive, datasets):
    controls = {}
    changed = deepcopy(run)
    changed["run_hash"] = "f" * 64 if run["run_hash"] != "f" * 64 else "0" * 64
    controls["TamperedHashRejected"] = _rejected(
        changed, plan, package, manifest, archive, datasets
    )
    changed = deepcopy(run)
    changed["parameters"]["constant_hr_mean_bpm"] += 1
    changed["parameters"]["parameter_hash"] = canonical_hash(
        {k: v for k, v in changed["parameters"].items() if k != "parameter_hash"}
    )
    controls["RehashedChangedTrainParameterRejected"] = _rejected(
        _rehash(changed), plan, package, manifest, archive, datasets
    )
    changed = deepcopy(run)
    scored = next(
        s for s in changed["development_report"]["sessions"] if s["metrics"] is not None
    )
    scored["metrics"]["constant"]["MAE_BPM"] += 1
    controls["RehashedChangedMetricRejected"] = _rejected(
        _rehash(changed), plan, package, manifest, archive, datasets
    )
    changed = deepcopy(run)
    changed["training_authorized"] = True
    controls["RehashedAuthorityClaimRejected"] = _rejected(
        _rehash(changed), plan, package, manifest, archive, datasets
    )
    for key, value, name in (
        ("fit_scope", "ALL_SPLITS", "AllSplitFittingRejected"),
        ("test_role", "FINAL_SCORING", "TestScoringPolicyRejected"),
        ("ridge_alpha", 1.0, "ChangedRegularizationRejected"),
        ("ridge_min_nonempty_train_sessions", 1, "SingleTrainRidgeOptInRejected"),
        ("physiological_lag_ms", 30000, "PhysiologicalLagClaimRejected"),
    ):
        changed = {**plan, key: value}
        changed["plan_hash"] = canonical_hash(
            {k: v for k, v in changed.items() if k != "plan_hash"}
        )
        controls[name] = _rejected(run, changed, package, manifest, archive, datasets)
    changed = {**plan, "input_package_hash": "0" * 64}
    changed["plan_hash"] = canonical_hash(
        {k: v for k, v in changed.items() if k != "plan_hash"}
    )
    controls["WrongInputPinRejected"] = _rejected(
        run, changed, package, manifest, archive, datasets
    )
    return controls


def control(manifest, archive, package, datasets, original, output, run_id):
    plan = build_response_baseline_plan(
        package, manifest, archive, datasets, run_id=run_id
    )
    _unchanged(original)
    output.mkdir(parents=True, exist_ok=False)
    # Record fixed policy before any development metric is calculated.
    write_new(output / "baseline_plan.json", plan)
    run = run_response_baseline_experiment(plan, package, manifest, archive, datasets)
    repeated = run_response_baseline_experiment(
        plan, package, manifest, archive, list(reversed(datasets))
    )
    if encode(run) != encode(repeated):
        raise ValueError("BASELINE_REPEATED_RUN_CHANGED")
    checked = check_response_baseline_experiment(
        run, plan, package, manifest, archive, datasets
    )
    negatives = _negative_controls(run, plan, package, manifest, archive, datasets)
    _unchanged(original)
    write_new(output / "baseline_run.json", run)
    write_new(output / "baseline_run_repeat.json", repeated)
    write_new(output / "baseline_check.json", checked)
    write_new(output / "development_report.json", run["development_report"])
    write_new(output / "train_parameters.json", run["parameters"])
    summary = {
        "Status": "RESPONSE_BASELINE_LOCAL_CONTROL_VERIFIED",
        "RunStatus": run["status"],
        "RunHash": run["run_hash"],
        "PlanHash": plan["plan_hash"],
        "InputPackageHash": package["input_package_hash"],
        "ExperimentManifestHash": package["experiment_manifest_hash"],
        "ArchivedRecordHash": package["cohort_record_hash"],
        "ArchivedIndexHash": package["cohort_index_hash"],
        "ParameterHash": run["parameters"]["parameter_hash"],
        "PlanWrittenBeforeDevelopmentScoring": True,
        "FullBInputReconstructionVerified": True,
        "OriginalInputBytesPreserved": True,
        "OriginalInputSHA256": {
            str(p): hashlib.sha256(raw).hexdigest() for p, raw in original
        },
        "RepeatedRunBytesIdentical": True,
        "ReconstructionVerified": True,
        "SourceObservationCount": package["totals"]["source_observation_count"],
        "BModelInputRowCount": package["totals"]["model_input_row_count"],
        "AdapterColumns": len(run["adapter"]["columns"]),
        "DevelopmentRows": run["adapter"]["development_row_count"],
        "TrainSessions": run["parameters"]["train_session_count"],
        "TrainRows": run["parameters"]["train_row_count"],
        "ValidationRows": sum(
            len(m["rows"])
            for m in run["adapter"]["members"]
            if m["split"] == "VALIDATION"
        ),
        "ReservedTestRows": run["reserved_test_coverage"]["model_input_row_count"],
        "TestPayloadReadForIntegrityOnly": True,
        "TestAdaptedRows": 0,
        "TestScoringPerformed": False,
        "ConstantBaselineFitPerformed": True,
        "TrainPreprocessingFitPerformed": True,
        "RidgeFitPerformed": run["ridge_fit_performed"],
        "RidgeStatus": run["parameters"]["ridge"]["status"],
        "RidgeAlpha": plan["ridge_alpha"],
        "DroppedTrainConstantColumns": [
            run["adapter"]["columns"][i]["name"]
            for i in run["parameters"]["preprocessing"][
                "dropped_numerical_constant_column_indices"
            ]
        ],
        "ExperimentalNumericCalculationsPerformed": True,
        "HyperparameterSearchPerformed": False,
        "ModelSelectionPerformed": False,
        "GeneralizationEvidenceVerified": False,
        "CurrentSourceEvidenceVerified": False,
        "OwnerAuthorizationVerified": False,
        "SplitAssignmentPersisted": False,
        "PolarProviderCalls": 0,
        "EnvironmentalProviderCalls": 0,
        "DatabaseStorageWrites": 0,
        "MissingValuesImputed": False,
        "FixedHRShiftApplied": False,
        "PhysiologicalLagMs": None,
        "PFTDataUsed": False,
        "TrainingAuthorized": False,
        "NumericOutputAuthorized": False,
        "ClaimScope": run["claim_scope"],
        "LocalFilesWritten": 7,
        "OutputFolder": str(output),
        **negatives,
    }
    write_new(output / "baseline_control_summary.json", summary)
    return summary


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run", "check", "control"):
        sub = commands.add_parser(command)
        sub.add_argument("--manifest", required=True)
        sub.add_argument("--archive", required=True)
        sub.add_argument("--inputs", required=True)
        sub.add_argument("--dataset", action="append", required=True)
        if command in ("run", "check"):
            sub.add_argument("--plan", required=True)
        if command == "check":
            sub.add_argument("artifact")
        elif command == "control":
            sub.add_argument("--run-id", default="v24-11-c-development-control")
            sub.add_argument("--output-dir", required=True)
        else:
            sub.add_argument("--output", required=True)
            if command == "prepare":
                sub.add_argument("--run-id", default="v24-11-c-development-control")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        manifest, archive, package, datasets, original = _sources(args)
        if args.command == "control":
            value = control(
                manifest,
                archive,
                package,
                datasets,
                original,
                Path(args.output_dir),
                args.run_id,
            )
        elif args.command == "prepare":
            value = build_response_baseline_plan(
                package, manifest, archive, datasets, run_id=args.run_id
            )
            _unchanged(original)
            write_new(args.output, value)
            value = {
                "status": "FIXED_DEVELOPMENT_PLAN_PREPARED",
                "plan_hash": value["plan_hash"],
                "test_scoring_performed": False,
            }
        else:
            raw, plan = read_json(args.plan, MAX_MANIFEST_BYTES)
            original.append((Path(args.plan), raw))
            if args.command == "run":
                run = run_response_baseline_experiment(
                    plan, package, manifest, archive, datasets
                )
                _unchanged(original)
                write_new(args.output, run)
                value = {
                    "status": run["status"],
                    "run_hash": run["run_hash"],
                    "ridge_fit_performed": run["ridge_fit_performed"],
                    "test_scoring_performed": False,
                }
            else:
                raw, run = read_json(args.artifact, MAX_ARTIFACT_BYTES)
                original.append((Path(args.artifact), raw))
                value = check_response_baseline_experiment(
                    run, plan, package, manifest, archive, datasets
                )
                _unchanged(original)
        print(encode(value).decode(), end="")
        return 0
    except (
        OSError,
        ValidationError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        RecursionError,
    ) as error:
        reason = str(error)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,120}", reason):
            reason = "BASELINE_INVALID_INPUT_OR_OUTPUT"
        print(
            encode(
                {
                    "status": "REJECTED",
                    "reason": reason,
                    "error_type": type(error).__name__,
                }
            ).decode(),
            end="",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
