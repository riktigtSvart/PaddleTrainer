"""Build/check bounded interval inputs offline; fetch-control reads explicit local API replays."""

import argparse
import hashlib
import json
import re
import sys
import time
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

# Direct invocation works from the project root without changing PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from pydantic import ValidationError  # noqa: E402

from app.services.environment_replay_snapshot import canonical_hash  # noqa: E402
from app.services.response_experiment_contract import (  # noqa: E402
    MAX_EXPERIMENT_BYTES,
    check_response_experiment_manifest,
    extract_cohort_record,
)
from app.services.response_model_inputs import (  # noqa: E402
    MAX_INPUT_BYTES,
    build_response_model_input_package,
    check_member_dataset_binding,
    check_response_model_input_package,
)

MAX_ARCHIVE_FILE_BYTES = 3 * 1024 * 1024
MAX_REPLAY_FILE_BYTES = 96 * 1024 * 1024
MAX_TOTAL_REPLAY_FILE_BYTES = 256 * 1024 * 1024
MAX_FETCH_SECONDS = 180


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MODEL_INPUT_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("MODEL_INPUT_NONFINITE_JSON")


def decode(raw):
    return json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=_nonfinite
    )


def read_json(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("MODEL_INPUT_FILE_SIZE_LIMIT")
    return raw, decode(raw)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_new_bytes(path, raw):
    path = Path(path)
    with path.open("xb") as output:
        try:
            output.write(raw)
        except BaseException:
            output.close()
            path.unlink(missing_ok=True)
            raise


def write_new(path, value):
    raw = encode(value)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("MODEL_INPUT_OUTPUT_FILE_SIZE_LIMIT")
    write_new_bytes(path, raw)


def _rehash(package):
    package["input_package_hash"] = canonical_hash(
        {k: v for k, v in package.items() if k != "input_package_hash"}
    )
    return package


def _rejected(package, manifest, archive, datasets):
    try:
        check_response_model_input_package(package, manifest, archive, datasets)
    except (
        ValidationError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
    ):
        return True
    raise ValueError("MODEL_INPUT_NEGATIVE_CONTROL_ACCEPTED")


def _negative_controls(package, manifest, archive, datasets):
    controls = {}
    changed = deepcopy(package)
    changed["input_package_hash"] = (
        "f" * 64 if package["input_package_hash"] != "f" * 64 else "0" * 64
    )
    controls["TamperedHashRejected"] = _rejected(changed, manifest, archive, datasets)
    changed = deepcopy(package)
    changed["members"][0]["split"] = (
        "TEST" if changed["members"][0]["split"] != "TEST" else "TRAIN"
    )
    controls["ChangedSplitRejected"] = _rejected(
        _rehash(changed), manifest, archive, datasets
    )
    changed = deepcopy(package)
    changed["training_authorized"] = True
    controls["ForbiddenAuthorityRejected"] = _rejected(
        _rehash(changed), manifest, archive, datasets
    )
    changed = deepcopy(package)
    changed["members"][0]["input_arrays"]["values"][0][0] = 123456.5
    controls["ChangedPredictorValueRejected"] = _rejected(
        _rehash(changed), manifest, archive, datasets
    )
    changed = deepcopy(package)
    changed["columns"].append(
        {"name": "recorded_hr_bpm", "source": "target", "unit": "bpm"}
    )
    controls["HRPredictorColumnRejected"] = _rejected(
        _rehash(changed), manifest, archive, datasets
    )
    target_member = next((m for m in package["members"] if m["targets"]), None)
    if target_member is not None:
        position = package["members"].index(target_member)
        changed = deepcopy(package)
        changed["members"][position]["targets"][0]["recorded_hr_mean_bpm"] += 1
        controls["ChangedHRTargetRejected"] = _rejected(
            _rehash(changed), manifest, archive, datasets
        )
        changed = deepcopy(package)
        window = changed["members"][position]["targets"][0]["history_windows"][0]
        window["stop_input_row_index_exclusive"] += 1
        controls["FutureOrCrossBoundaryWindowRejected"] = _rejected(
            _rehash(changed), manifest, archive, datasets
        )
    else:
        # Absence of targets is a valid diagnosed result, not a fictitious success.
        controls["ChangedHRTargetRejected"] = None
        controls["FutureOrCrossBoundaryWindowRejected"] = None
    changed_sources = deepcopy(datasets)
    changed_sources[0]["observations"][0]["workload_observation"][
        "gps_ground_speed_mps"
    ] = 123456.5
    changed_sources[0]["package_hash"] = canonical_hash(
        {k: v for k, v in changed_sources[0].items() if k != "package_hash"}
    )
    controls["RehashedWrongSourcePinRejected"] = _rejected(
        package, manifest, archive, changed_sources
    )
    controls["MissingMemberRejected"] = _rejected(
        package, manifest, archive, datasets[:-1]
    )
    duplicated = [*datasets[:-1], datasets[0]]
    controls["DuplicateMemberRejected"] = _rejected(
        package, manifest, archive, duplicated
    )
    return controls


def _unchanged(inputs):
    for path, original in inputs:
        with Path(path).open("rb") as source:
            current = source.read(len(original) + 1)
        if current != original:
            raise ValueError("MODEL_INPUT_SOURCE_FILE_CHANGED_DURING_CONTROL")


def run_control(
    manifest,
    archive,
    datasets,
    output,
    original_inputs,
    *,
    output_exists=False,
    api_requests=0,
):
    package = build_response_model_input_package(manifest, archive, datasets)
    repeated = build_response_model_input_package(
        manifest, archive, list(reversed(datasets))
    )
    checked = check_response_model_input_package(package, manifest, archive, datasets)
    if encode(package) != encode(repeated):
        raise ValueError("MODEL_INPUT_REPEATED_PACKAGE_CHANGED")
    negatives = _negative_controls(package, manifest, archive, datasets)
    _unchanged(original_inputs)
    if not output_exists:
        output.mkdir(parents=True, exist_ok=False)
    write_new(output / "model_inputs.json", package)
    write_new(output / "model_inputs_repeat.json", repeated)
    write_new(output / "model_inputs_check.json", checked)
    summary = {
        "Status": "RESPONSE_MODEL_INPUT_LOCAL_CONTROL_VERIFIED",
        "InputPackageHash": package["input_package_hash"],
        "ExperimentManifestHash": package["experiment_manifest_hash"],
        "ArchivedRecordHash": package["cohort_record_hash"],
        "ArchivedIndexHash": package["cohort_index_hash"],
        "Members": len(package["members"]),
        "ObservationCount": package["totals"]["source_observation_count"],
        "HRSlots": package["totals"]["source_hr_slot_count"],
        "PreparationCandidates": package["totals"][
            "source_preparation_candidate_count"
        ],
        "ModelInputRowCount": package["totals"]["model_input_row_count"],
        "ExcludedObservations": package["totals"]["excluded_observation_count"],
        "PerSplitCoverage": package["per_split_coverage"],
        "EmptyInputPartitions": package["empty_input_partitions"],
        "LookbackWindowsMs": package["lookback_windows_ms"],
        "SelectedFeatures": [c["name"] for c in package["columns"]],
        "ModelInputArraysChecked": True,
        "RowLevelHistoryCoverageVerified": True,
        "ReconstructionVerified": True,
        "ContractArchiveBindingVerified": True,
        "ArchivedReplayPackagePinsVerified": True,
        "UnassignedReplayPinsPreserved": True,
        "RepeatedPackageBytesIdentical": True,
        "AllSourceObservationsReferenced": True,
        "UnlabelledWorkloadHistoryRetained": True,
        "SourceMasksPreserved": True,
        "OriginalInputBytesPreserved": True,
        "OriginalInputSHA256": {
            str(path): hashlib.sha256(raw).hexdigest() for path, raw in original_inputs
        },
        "PerMemberCoverage": [
            {
                "SessionId": m["session_external_id"],
                "Split": m["split"],
                **m["coverage"],
            }
            for m in package["members"]
        ],
        **negatives,
        "SourceEvidenceVerified": False,
        "CurrentSourceEvidenceVerified": False,
        "OwnerAuthorizationVerified": False,
        "DatabaseRecordPersisted": False,
        "SplitAssignmentPersisted": False,
        "FittedPreprocessingPerformed": False,
        "MissingValuesImputed": False,
        "ModelFitPerformed": False,
        "PFTDataUsed": False,
        "FixedHRShiftApplied": False,
        "PhysiologicalLagMs": None,
        "TrainingAuthorized": False,
        "NumericOutputAuthorized": False,
        "PolarProviderCallsLocalMaterializer": 0,
        "EnvironmentalProviderCallsLocalMaterializer": 0,
        "DatabaseStorageWritesLocalMaterializer": 0,
        "ReplayAPIRequestsPerformed": api_requests,
        "ReplayAPIReadScope": "EXPLICIT_PINNED_UNASSIGNED_REPLAY_ENDPOINT"
        if api_requests
        else "OFFLINE_FILES_ONLY",
        "ReplayEndpointReportedEnvironmentalProviderCalls": 0 if api_requests else None,
        "ReplayEndpointReportedStorageWrites": 0 if api_requests else None,
        "LocalFilesWritten": 4 + api_requests,
        "ClaimScope": checked["claim_scope"],
        "OutputFolder": str(output),
    }
    write_new(output / "model_inputs_control_summary.json", summary)
    return summary


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("MODEL_INPUT_REPLAY_REDIRECT_REJECTED")


def local_api_base(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/api/v1/integrations/polar"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MODEL_INPUT_LOCAL_API_BASE_REQUIRED")
    # Accessing port also checks malformed/range-invalid port strings.
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("MODEL_INPUT_LOCAL_API_BASE_REQUIRED")
    return value.rstrip("/")


def fetch_control(manifest, archive, args, original_inputs):
    check_response_experiment_manifest(manifest, archive)
    record = extract_cohort_record(archive)
    base = local_api_base(args.api_base)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=False)
    members = record["cohort_index"]["members"]
    requested = {
        (m["athlete_id"], m["session_external_id"]): m
        for m in record["request_manifest"]["members"]
    }
    # A configured HTTP proxy must not route local replay requests elsewhere.
    opener, datasets, total = build_opener(ProxyHandler({}), _NoRedirect()), [], 0
    started = time.monotonic()
    for index, member in enumerate(members):
        remaining = MAX_FETCH_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            raise ValueError("MODEL_INPUT_REPLAY_DEADLINE")
        pin = requested[(member["athlete_id"], member["session_external_id"])]
        uri = (
            base
            + "/sessions/"
            + quote(member["session_external_id"], safe="")
            + "/response-dataset/replay?"
            + urlencode({"route_date": pin["route_date"]})
        )
        request = Request(
            uri,
            data=encode(
                {
                    "replay_snapshot_id": pin["replay_snapshot_id"],
                    "include_payload": True,
                }
            ),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=min(60, remaining)) as response:
                raw = response.read(MAX_REPLAY_FILE_BYTES + 1)
        except HTTPError as exc:
            raise ValueError(f"MODEL_INPUT_REPLAY_HTTP_{exc.code}") from exc
        if len(raw) > MAX_REPLAY_FILE_BYTES:
            raise ValueError("MODEL_INPUT_FILE_SIZE_LIMIT")
        total += len(raw)
        if total > MAX_TOTAL_REPLAY_FILE_BYTES:
            raise ValueError("MODEL_INPUT_TOTAL_REPLAY_FILE_SIZE_LIMIT")
        dataset = decode(raw)
        check_member_dataset_binding(dataset, member)
        if time.monotonic() - started > MAX_FETCH_SECONDS:
            raise ValueError("MODEL_INPUT_REPLAY_DEADLINE")
        destination = output / f"member_{index:03d}_replay.json"
        write_new_bytes(destination, raw)
        original_inputs.append((destination, raw))
        datasets.append(dataset)
    return run_control(
        manifest,
        archive,
        datasets,
        output,
        original_inputs,
        output_exists=True,
        api_requests=len(datasets),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check", "control", "fetch-control"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--archive", type=Path, required=True)
        if name != "fetch-control":
            command.add_argument("--dataset", action="append", type=Path, required=True)
        if name == "check":
            command.add_argument("package", type=Path)
        elif name == "build":
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--output-dir", type=Path, required=True)
        if name == "fetch-control":
            command.add_argument(
                "--api-base", default="http://127.0.0.1:8000/api/v1/integrations/polar"
            )
    args = parser.parse_args(argv)
    try:
        manifest_raw, manifest = read_json(args.manifest, MAX_EXPERIMENT_BYTES)
        archive_raw, archive = read_json(args.archive, MAX_ARCHIVE_FILE_BYTES)
        originals = [(args.manifest, manifest_raw), (args.archive, archive_raw)]
        if args.command == "fetch-control":
            result = fetch_control(manifest, archive, args, originals)
        else:
            # Reject a bad contract or member count before loading large replay files.
            check_response_experiment_manifest(manifest, archive)
            record = extract_cohort_record(archive)
            if len(args.dataset) != len(record["cohort_index"]["members"]):
                raise ValueError("MODEL_INPUT_EXACT_MEMBER_SET_REQUIRED")
            datasets, total = [], 0
            for path in args.dataset:
                raw, dataset = read_json(path, MAX_REPLAY_FILE_BYTES)
                total += len(raw)
                if total > MAX_TOTAL_REPLAY_FILE_BYTES:
                    raise ValueError("MODEL_INPUT_TOTAL_REPLAY_FILE_SIZE_LIMIT")
                originals.append((path, raw))
                datasets.append(dataset)
            if args.command == "build":
                package = build_response_model_input_package(
                    manifest, archive, datasets
                )
                _unchanged(originals)
                write_new(args.output, package)
                result = {
                    "status": package["status"],
                    "input_package_hash": package["input_package_hash"],
                    **package["totals"],
                    "claim_scope": package["claim_scope"],
                }
            elif args.command == "check":
                _, package = read_json(args.package, MAX_INPUT_BYTES)
                result = check_response_model_input_package(
                    package, manifest, archive, datasets
                )
                _unchanged(originals)
            else:
                result = run_control(
                    manifest, archive, datasets, args.output_dir, originals
                )
        print(encode(result).decode(), end="")
        return 0
    except (
        OSError,
        URLError,
        ValueError,
        ValidationError,
        TypeError,
        KeyError,
        IndexError,
        OverflowError,
        RecursionError,
    ) as exc:
        # Do not echo a raw payload, access token, URL or local private path.
        code = (
            "MODEL_INPUT_OUTPUT_ALREADY_EXISTS"
            if isinstance(exc, FileExistsError)
            else "MODEL_INPUT_SOURCE_FILE_NOT_FOUND"
            if isinstance(exc, FileNotFoundError)
            else str(exc)
            if type(exc) is ValueError
            and re.fullmatch(r"MODEL_INPUT_[A-Z0-9_]+|EXPERIMENT_[A-Z0-9_]+", str(exc))
            else "MODEL_INPUT_INVALID_OR_UNAVAILABLE_INPUT"
        )
        print(
            encode(
                {
                    "status": "REJECTED",
                    "reason": code,
                    "model_fit_performed": False,
                    "training_authorized": False,
                }
            ).decode(),
            end="",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
