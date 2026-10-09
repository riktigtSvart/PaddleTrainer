"""Offline experiment prepare/check/control; local binding is not fresh source proof."""

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from app.schemas.response_experiment import ResponseExperimentManifest
from app.services.response_experiment_contract import (
    MAX_EXPERIMENT_BYTES,
    build_response_experiment_manifest,
    check_response_experiment_manifest,
    extract_cohort_record,
)

MAX_ARCHIVE_FILE_BYTES = 3 * 1024 * 1024


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("EXPERIMENT_DUPLICATE_JSON_KEY")
        result[name] = value
    return result


def _nonfinite(_):
    raise ValueError("EXPERIMENT_NONFINITE_JSON")


def read_json(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("EXPERIMENT_INPUT_FILE_SIZE_LIMIT")
    return raw, json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=_nonfinite
    )


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_new(path, value):
    path = Path(path)
    raw = encode(value)
    # Exclusive creation preserves both input files and previous outputs.
    with path.open("xb") as output:
        try:
            output.write(raw)
        except BaseException:
            output.close()
            path.unlink(missing_ok=True)
            raise


def _check_expected_pins(record, args):
    for key, expected in (
        ("record_hash", args.expected_record_hash),
        ("cohort_index_hash", args.expected_index_hash),
    ):
        if expected is not None and expected != record[key]:
            raise ValueError("EXPERIMENT_EXPECTED_ARCHIVE_PIN_MISMATCH")


def _prepare(archive, args):
    return build_response_experiment_manifest(
        archive,
        experiment_id=args.experiment_id,
        workload_features=args.workload_feature,
        environment_features=args.environment_feature,
        lookback_windows_ms=args.lookback_ms,
    )


def _expect_rejection(payload, archive):
    try:
        check_response_experiment_manifest(payload, archive)
    except (ValidationError, ValueError, TypeError, KeyError, RecursionError):
        return True
    raise ValueError("EXPERIMENT_NEGATIVE_CONTROL_ACCEPTED")


def _rehash(payload):
    return ResponseExperimentManifest.model_validate(payload).committed_payload()


def _rehash_invalid_control(payload):
    # Controls must have a valid content hash even when their policy is forbidden.
    # Otherwise a hash failure could mask a missing leakage/scope guard.
    body = {
        key: value
        for key, value in payload.items()
        if key != "experiment_manifest_hash"
    }
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    payload["experiment_manifest_hash"] = hashlib.sha256(raw).hexdigest()
    return payload


def run_control(archive, original_raw, args):
    """Exercise the actual pure validator on a supplied archive, without API/DB calls."""
    record = extract_cohort_record(archive)
    _check_expected_pins(record, args)
    before = deepcopy(archive)
    contract = _prepare(archive, args)
    repeated = _prepare(archive, args)
    first_check = check_response_experiment_manifest(contract, archive)
    second_check = check_response_experiment_manifest(contract, archive)
    if encode(contract) != encode(repeated) or encode(first_check) != encode(
        second_check
    ):
        raise ValueError("EXPERIMENT_REPEATED_OUTPUT_CHANGED")
    negative = {}
    changed = deepcopy(contract)
    changed["experiment_manifest_hash"] = (
        "f" * 64 if contract["experiment_manifest_hash"] != "f" * 64 else "0" * 64
    )
    negative["TamperedHashRejected"] = _expect_rejection(changed, archive)
    changed = deepcopy(contract)
    pin = changed["cohort"]["record_hash"]
    changed["cohort"]["record_hash"] = "0" * 64 if pin != "0" * 64 else "1" * 64
    negative["WrongArchivePinRejected"] = _expect_rejection(_rehash(changed), archive)
    changed = deepcopy(contract)
    train = next(m for m in changed["members"] if m["split"] == "TRAIN")
    test = next(m for m in changed["members"] if m["split"] == "TEST")
    train["split"], test["split"] = test["split"], train["split"]
    negative["ChangedSplitRejected"] = _expect_rejection(_rehash(changed), archive)
    for name, section, key, value in (
        ("HRPredictorRejected", "inputs", "workload_features", ["recorded_hr_bpm"]),
        (
            "PFTTargetDerivedPredictorRejected",
            "inputs",
            "workload_features",
            ["HR_P2_MEDIAN"],
        ),
        (
            "AllSplitFittingRejected",
            "evaluation",
            "fitted_preprocessing_scope",
            "ALL_SPLITS",
        ),
        ("FixedShiftRejected", "temporal", "fixed_hr_shift_applied", True),
        ("PhysiologicalLagClaimRejected", "temporal", "physiological_lag_ms", 1663),
        ("CrossSequenceHistoryRejected", "temporal", "history_scope", "ALL_SESSIONS"),
        ("FatigueTargetRejected", "pft", "fitness_or_fatigue_targets_used", True),
        ("WrongModalityRejected", "context", "declared_modality", "RUN_TRACK"),
    ):
        changed = deepcopy(contract)
        changed[section][key] = value
        negative[name] = _expect_rejection(_rehash_invalid_control(changed), archive)
    changed = deepcopy(contract)
    changed["training_authorized"] = True
    negative["ForbiddenAuthorityRejected"] = _expect_rejection(
        _rehash_invalid_control(changed), archive
    )
    if archive != before or Path(args.archive).read_bytes() != original_raw:
        raise ValueError("EXPERIMENT_ARCHIVE_INPUT_CHANGED")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "experiment_contract.json", contract)
    write_new(output / "experiment_contract_repeat.json", repeated)
    write_new(output / "experiment_check.json", first_check)
    summary = {
        "Status": "EXPERIMENT_CONTRACT_LOCAL_CONTROL_VERIFIED",
        "ExperimentManifestHash": contract["experiment_manifest_hash"],
        "ArchivedRecordHash": record["record_hash"],
        "ArchivedIndexHash": record["cohort_index_hash"],
        "Members": first_check["member_count"],
        "RequestedSplitCounts": first_check["requested_split_counts"],
        "ObservationCount": first_check["archived_counts"]["observation_count"],
        "HRSlots": first_check["archived_counts"]["hr_slot_count"],
        "PreparationCandidates": first_check["archived_counts"][
            "preparation_candidate_count"
        ],
        "ContractArchiveBindingVerified": True,
        "RepeatedContractBytesIdentical": True,
        "RepeatedCheckOutputIdentical": True,
        "OriginalArchiveBytesPreserved": True,
        "OriginalArchiveSHA256": hashlib.sha256(original_raw).hexdigest(),
        "SelectedWorkloadFeatures": contract["inputs"]["workload_features"],
        "SelectedEnvironmentFeatures": contract["inputs"]["environment_features"],
        "LookbackWindowsMs": contract["temporal"]["lookback_windows_ms"],
        "EmbeddedHistoricalChronologicalOrderClaim": first_check[
            "embedded_historical_chronological_order_claim"
        ],
        "EmbeddedHistoricalChronologicalSplitClaim": first_check[
            "embedded_historical_chronological_split_claim"
        ],
        **negative,
        "SourceEvidenceVerified": False,
        "CurrentSourceEvidenceVerified": False,
        "OwnerAuthorizationVerified": False,
        "DatabaseRecordPersisted": False,
        "SplitAssignmentPersisted": False,
        "ModelInputArraysChecked": False,
        "ModelInputRowCount": None,
        "FittedPreprocessingPerformed": False,
        "MissingValuesImputed": False,
        "ModelFitPerformed": False,
        "PFTDataUsed": False,
        "FixedHRShiftApplied": False,
        "PhysiologicalLagMs": None,
        "TrainingAuthorized": False,
        "NumericOutputAuthorized": False,
        "PolarProviderCalls": 0,
        "EnvironmentalProviderCalls": 0,
        "DatabaseStorageWrites": 0,
        "LocalFilesWritten": 4,
        "ClaimScope": first_check["claim_scope"],
        "OutputFolder": str(output),
    }
    write_new(output / "experiment_control_summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "control"):
        command = commands.add_parser(name)
        command.add_argument("--archive", type=Path, required=True)
        command.add_argument("--experiment-id", required=True)
        command.add_argument(
            "--output" if name == "prepare" else "--output-dir",
            type=Path,
            required=True,
        )
        command.add_argument("--workload-feature", action="append")
        command.add_argument("--environment-feature", action="append")
        command.add_argument("--lookback-ms", type=int, action="append")
        command.add_argument("--expected-record-hash")
        command.add_argument("--expected-index-hash")
    command = commands.add_parser("check")
    command.add_argument("manifest", type=Path)
    command.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        original_raw, archive = read_json(args.archive, MAX_ARCHIVE_FILE_BYTES)
        if args.command == "check":
            _, payload = read_json(args.manifest, MAX_EXPERIMENT_BYTES)
            result = check_response_experiment_manifest(payload, archive)
        elif args.command == "prepare":
            record = extract_cohort_record(archive)
            _check_expected_pins(record, args)
            payload = _prepare(archive, args)
            result = check_response_experiment_manifest(payload, archive)
            write_new(args.output, payload)
            result["local_contract_file_written"] = True
        else:
            result = run_control(archive, original_raw, args)
    except ValidationError as exc:
        result = {
            "status": "REJECTED",
            "reason": "EXPERIMENT_SCHEMA_REJECTED",
            "error_types": sorted({error["type"] for error in exc.errors()}),
        }
    except FileExistsError:
        result = {"status": "REJECTED", "reason": "EXPERIMENT_OUTPUT_ALREADY_EXISTS"}
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
    ) as exc:
        message = str(exc)
        reason = (
            message
            if re.fullmatch(r"(?:EXPERIMENT|COHORT_RECORD)_[A-Z0-9_]+", message)
            else ("EXPERIMENT_LOCAL_INPUT_REJECTED")
        )
        result = {"status": "REJECTED", "reason": reason}
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 1 if result.get("status") == "REJECTED" else 0


if __name__ == "__main__":
    sys.exit(main())
