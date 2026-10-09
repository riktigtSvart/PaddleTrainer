"""Inventory older recorded kayaking sessions through existing local GET endpoints."""

import argparse
import hashlib
import json
import math
import re
import sys
import time
from copy import deepcopy
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from pydantic import ValidationError  # noqa: E402

from app.services.environment_replay_snapshot import canonical_hash  # noqa: E402
from app.services.response_session_inventory import (  # noqa: E402
    MAX_ARTIFACT_BYTES,
    build_session_inventory,
    check_session_inventory,
    prepare_session_inventory,
    provider_date,
    request_path,
    require,
    seal,
)

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_RESPONSE_BYTES = 256 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 180
MAX_SECONDS = 900
FAILURES = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    IndexError,
    OverflowError,
    RecursionError,
)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVENTORY_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("INVENTORY_NONFINITE_JSON")


def decode(raw):
    return json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique, parse_constant=_nonfinite
    )


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def read_json(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    require(len(raw) <= limit, "INVENTORY_FILE_LIMIT")
    return raw, decode(raw)


def write_bytes(path, raw):
    with Path(path).open("xb") as output:
        try:
            output.write(raw)
        except BaseException:
            output.close()
            Path(path).unlink(missing_ok=True)
            raise


def write_json(path, value):
    raw = encode(value)
    require(len(raw) <= MAX_ARTIFACT_BYTES, "INVENTORY_ARTIFACT_LIMIT")
    write_bytes(path, raw)


def reason(error):
    message = str(error)
    return (
        message
        if re.fullmatch(r"INVENTORY_[A-Z0-9_]{1,160}", message)
        else "INVENTORY_INVALID_SOURCE_OR_OUTPUT"
    )


def local_base(value):
    parsed = urlsplit(value)
    require(
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.username is None
        and parsed.password is None
        and parsed.path.rstrip("/") == "/api/v1"
        and not parsed.query
        and not parsed.fragment,
        "INVENTORY_LOCAL_API_BASE_REQUIRED",
    )
    require(
        parsed.port is None or 1 <= parsed.port <= 65535,
        "INVENTORY_LOCAL_API_BASE_REQUIRED",
    )
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def execution_limits(request_seconds, batch_seconds):
    require(
        type(request_seconds) is int and 1 <= request_seconds <= 300,
        "INVENTORY_REQUEST_TIMEOUT_LIMIT",
    )
    require(
        type(batch_seconds) is int and 1 <= batch_seconds <= 1800,
        "INVENTORY_BATCH_TIMEOUT_LIMIT",
    )
    return {
        "request_timeout_seconds": request_seconds,
        "batch_timeout_seconds": batch_seconds,
    }


class Reader:
    def __init__(self, base, folder, request_seconds=None, batch_seconds=None):
        self.base, self.folder = local_base(base), folder
        self.limits = execution_limits(
            REQUEST_TIMEOUT_SECONDS if request_seconds is None else request_seconds,
            MAX_SECONDS if batch_seconds is None else batch_seconds,
        )
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.started, self.total, self.requests = time.monotonic(), 0, []

    def get(self, kind, session=None, day=None):
        started = time.monotonic()
        path = request_path(kind, session, day)
        entry = {
            "kind": kind,
            "session_external_id": session["external_id"] if session else None,
            "method": "GET",
            "path": path,
            "http_status": None,
            "body_file": None,
            "body_sha256": None,
            "elapsed_seconds": None,
            "request_timeout_seconds": None,
        }
        self.requests.append(entry)
        try:
            remaining = self.limits["batch_timeout_seconds"] - (started - self.started)
            require(remaining > 0, "INVENTORY_BATCH_DEADLINE")
            entry["request_timeout_seconds"] = min(
                self.limits["request_timeout_seconds"], remaining
            )
            with self.opener.open(
                Request(self.base + path, method="GET"),
                timeout=entry["request_timeout_seconds"],
            ) as response:
                entry["http_status"] = response.status
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            entry["http_status"] = error.code
            raise ValueError(f"INVENTORY_HTTP_{error.code}") from None
        except TimeoutError:
            raise ValueError("INVENTORY_LOCAL_API_TIMEOUT") from None
        except URLError as error:
            code = (
                "INVENTORY_LOCAL_API_TIMEOUT"
                if isinstance(error.reason, TimeoutError)
                else "INVENTORY_LOCAL_API_CONNECTION_FAILED"
            )
            raise ValueError(code) from None
        except (OSError, HTTPException):
            raise ValueError("INVENTORY_LOCAL_API_CONNECTION_FAILED") from None
        finally:
            entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        require(entry["http_status"] == 200, "INVENTORY_UNEXPECTED_HTTP_STATUS")
        require(len(raw) <= MAX_RESPONSE_BYTES, "INVENTORY_RESPONSE_SIZE_LIMIT")
        self.total += len(raw)
        require(
            self.total <= MAX_TOTAL_RESPONSE_BYTES,
            "INVENTORY_TOTAL_RESPONSE_SIZE_LIMIT",
        )
        filename = f"response_{len(self.requests) - 1:03d}.json"
        value = decode(raw)
        # Invalid JSON is an unavailable response, never a successful capture.
        canonical_hash(value)
        write_bytes(self.folder / filename, raw)
        entry.update(body_file=filename, body_sha256=hashlib.sha256(raw).hexdigest())
        require(
            time.monotonic() - self.started <= self.limits["batch_timeout_seconds"],
            "INVENTORY_BATCH_DEADLINE",
        )
        return value


def capture_value(plan, reader, outcomes):
    return seal(
        {
            "schema_version": "0.2",
            "plan": plan,
            "execution_limits": reader.limits,
            "requests": deepcopy(reader.requests),
            "outcomes": deepcopy(outcomes),
        },
        "capture_hash",
    )


def load_capture(capture, folder, manifest, archive):
    timed = capture.get("schema_version") == "0.2"
    keys = {"schema_version", "plan", "requests", "outcomes", "capture_hash"}
    require(
        set(capture) == (keys | {"execution_limits"} if timed else keys)
        and capture["schema_version"] in {"0.1", "0.2"},
        "INVENTORY_CAPTURE_SHAPE",
    )
    if timed:
        limits = capture["execution_limits"]
        require(
            isinstance(limits, dict)
            and set(limits) == {"request_timeout_seconds", "batch_timeout_seconds"},
            "INVENTORY_EXECUTION_LIMITS_SHAPE",
        )
        execution_limits(
            limits["request_timeout_seconds"], limits["batch_timeout_seconds"]
        )
    require(
        capture["capture_hash"]
        == canonical_hash({k: v for k, v in capture.items() if k != "capture_hash"}),
        "INVENTORY_CAPTURE_HASH_MISMATCH",
    )
    plan, requests, outcomes = capture["plan"], capture["requests"], capture["outcomes"]
    require(
        isinstance(requests, list) and 1 <= len(requests) <= 1 + 3 * plan["batch_size"],
        "INVENTORY_REQUEST_COUNT_LIMIT",
    )
    payloads, total = [], 0
    for i, entry in enumerate(requests):
        request_keys = {
            "kind",
            "session_external_id",
            "method",
            "path",
            "http_status",
            "body_file",
            "body_sha256",
        }
        require(
            set(entry)
            == (
                request_keys | {"elapsed_seconds", "request_timeout_seconds"}
                if timed
                else request_keys
            )
            and entry["method"] == "GET",
            "INVENTORY_CAPTURE_METHOD_OR_SHAPE",
        )
        if timed:
            elapsed, timeout = (
                entry["elapsed_seconds"],
                entry["request_timeout_seconds"],
            )
            require(
                type(elapsed) in (int, float)
                and math.isfinite(elapsed)
                and elapsed >= 0
                and (
                    timeout is None
                    or type(timeout) in (int, float)
                    and math.isfinite(timeout)
                    and 0 < timeout <= limits["request_timeout_seconds"]
                    and timeout <= limits["batch_timeout_seconds"]
                ),
                "INVENTORY_REQUEST_TIMING_INVALID",
            )
            require(
                timeout is not None or entry["http_status"] is None,
                "INVENTORY_REQUEST_TIMING_INVALID",
            )
        require(
            entry["http_status"] is None
            or type(entry["http_status"]) is int
            and 100 <= entry["http_status"] <= 599,
            "INVENTORY_CAPTURE_HTTP_STATUS_INVALID",
        )
        if entry["body_file"] is None:
            require(entry["body_sha256"] is None, "INVENTORY_CAPTURE_FILE_BINDING")
            payloads.append(None)
            continue
        require(
            entry["body_file"] == f"response_{i:03d}.json"
            and entry["http_status"] == 200,
            "INVENTORY_CAPTURE_FILE_BINDING",
        )
        path = folder / entry["body_file"]
        require(
            path.resolve().is_relative_to(folder.resolve()),
            "INVENTORY_CAPTURE_PATH_ESCAPE",
        )
        raw, value = read_json(path, MAX_RESPONSE_BYTES)
        require(
            hashlib.sha256(raw).hexdigest() == entry["body_sha256"],
            "INVENTORY_CAPTURE_BYTES_CHANGED",
        )
        total += len(raw)
        require(
            total <= MAX_TOTAL_RESPONSE_BYTES, "INVENTORY_TOTAL_RESPONSE_SIZE_LIMIT"
        )
        canonical_hash(value)
        payloads.append(value)
    require(
        requests[0]["kind"] == "sessions"
        and requests[0]["session_external_id"] is None
        and requests[0]["path"] == request_path("sessions")
        and requests[0]["http_status"] == 200,
        "INVENTORY_SESSION_LIST_REQUEST_BINDING",
    )
    sessions = payloads[0]
    expected_plan = prepare_session_inventory(
        manifest,
        archive,
        sessions,
        batch_size=plan["batch_size"],
        skip_ids=plan["operator_skip_session_ids"],
    )
    require(
        canonical_hash(plan) == canonical_hash(expected_plan),
        "INVENTORY_PLAN_BINDING_MISMATCH",
    )
    require(
        isinstance(outcomes, list)
        and len(outcomes) <= len(plan["selected_session_ids"]),
        "INVENTORY_OUTCOME_COUNT",
    )
    lookup = {
        s["external_id"]: s for s in sessions if s["external_provider"] == "POLAR"
    }
    observations, used = [], [0]
    for position, outcome in enumerate(outcomes):
        sid = plan["selected_session_ids"][position]
        require(
            outcome["session_external_id"] == sid
            and isinstance(outcome["request_indices"], list),
            "INVENTORY_OUTCOME_IDENTITY",
        )
        indices = outcome["request_indices"]
        require(
            1 <= len(indices) <= 3
            and all(type(i) is int and 1 <= i < len(requests) for i in indices),
            "INVENTORY_REQUEST_INDICES_INVALID",
        )
        require(
            indices == list(range(used[-1] + 1, used[-1] + 1 + len(indices))),
            "INVENTORY_REQUEST_ORDER_INVALID",
        )
        used.extend(indices)
        session, day = lookup[sid], None
        for offset, index in enumerate(indices):
            kind = ("detail", "inspection", "replays")[offset]
            entry = requests[index]
            if offset == 1:
                day = provider_date(session, payloads[indices[0]])
            require(
                entry["kind"] == kind
                and entry["session_external_id"] == sid
                and entry["path"] == request_path(kind, session, day),
                "INVENTORY_REQUEST_PATH_BINDING",
            )
        if outcome["status"] == "CAPTURED":
            require(
                set(outcome) == {"session_external_id", "status", "request_indices"}
                and len(indices) == 3
                and all(
                    requests[i]["http_status"] == 200 and payloads[i] is not None
                    for i in indices
                ),
                "INVENTORY_COMPLETED_REQUEST_SET_REQUIRED",
            )
            observations.append(
                {
                    "session_external_id": sid,
                    "status": "CAPTURED",
                    **{
                        kind: payloads[i]
                        for kind, i in zip(("detail", "inspection", "replays"), indices)
                    },
                }
            )
        else:
            require(
                outcome["status"] == "REQUEST_FAILED"
                and set(outcome)
                == {"session_external_id", "status", "request_indices", "reason"},
                "INVENTORY_FAILURE_RECORD_INVALID",
            )
            observations.append(
                {
                    "session_external_id": sid,
                    "status": "REQUEST_FAILED",
                    "reason": outcome["reason"],
                }
            )
    require(used == list(range(len(requests))), "INVENTORY_UNBOUND_REQUEST_RECORD")
    return plan, sessions, observations


def _originals_unchanged(originals):
    for path, raw in originals:
        with path.open("rb") as source:
            require(
                source.read(len(raw) + 1) == raw, "INVENTORY_PROTECTED_INPUT_CHANGED"
            )


def checkpoint(folder, number, plan, reader, outcomes, manifest, archive):
    capture = capture_value(plan, reader, outcomes)
    data = load_capture(capture, folder, manifest, archive)
    report = build_session_inventory(*data, manifest, archive)
    write_json(folder / f"capture_checkpoint_{number:03d}.json", capture)
    write_json(folder / f"inventory_progress_{number:03d}.json", report)
    return capture, report, data


def _negative_controls(report, data, manifest, archive):
    checks = {}
    for kind in ("hash", "authority", "protected_role"):
        altered = deepcopy(report)
        if kind == "hash":
            altered["inventory_hash"] = (
                "f" * 64 if report["inventory_hash"] != "f" * 64 else "0" * 64
            )
        elif kind == "authority":
            altered["training_authorized"] = True
        else:
            selected = next(
                (s for s in altered["sessions"] if s["role"] == "PROTECTED_CONTROL"),
                altered["sessions"][0] if altered["sessions"] else None,
            )
            if selected is None:
                checks["ChangedSessionRoleRejected"] = None
                continue
            selected["role"] = "READY_FOR_TRAINING"
        if kind != "hash":
            altered["inventory_hash"] = canonical_hash(
                {k: v for k, v in altered.items() if k != "inventory_hash"}
            )
        try:
            check_session_inventory(altered, *data, manifest, archive)
        except FAILURES:
            checks[
                {
                    "hash": "TamperedHashRejected",
                    "authority": "RehashedAuthorityRejected",
                    "protected_role": "ChangedSessionRoleRejected",
                }[kind]
            ] = True
        else:
            raise ValueError("INVENTORY_NEGATIVE_CONTROL_ACCEPTED")
    return checks


def fetch(args, manifest, archive, originals):
    from app.services.response_experiment_contract import (
        check_response_experiment_manifest,
    )

    check_response_experiment_manifest(manifest, archive)
    local_base(args.api_base)
    folder = Path(args.output_dir)
    reader = Reader(
        args.api_base,
        folder,
        args.request_timeout_seconds,
        args.batch_timeout_seconds,
    )
    folder.mkdir(parents=True, exist_ok=False)
    outcomes = []
    try:
        sessions = reader.get("sessions")
        plan = prepare_session_inventory(
            manifest,
            archive,
            sessions,
            batch_size=args.batch_size,
            skip_ids=args.skip_session_id,
        )
    except (*FAILURES, OSError) as error:
        write_json(
            folder / "initial_request_failure.json",
            {
                "status": "CONTROL_STOPPED",
                "reason": reason(error),
                "requests": reader.requests,
            },
        )
        raise
    write_json(folder / "inventory_plan.json", plan)
    capture, report, data = checkpoint(
        folder, 0, plan, reader, outcomes, manifest, archive
    )
    lookup = {
        s["external_id"]: s for s in sessions if s["external_provider"] == "POLAR"
    }
    stopped = False
    for number, sid in enumerate(plan["selected_session_ids"], start=1):
        print(
            f"Inventory session {number}/{len(plan['selected_session_ids'])}",
            file=sys.stderr,
        )
        first = len(reader.requests)
        outcome = {
            "session_external_id": sid,
            "status": "CAPTURED",
            "request_indices": [],
        }
        session = lookup[sid]
        try:
            detail = reader.get("detail", session)
            day = provider_date(session, detail)
            require(
                day < plan["older_than_stored_utc_date"],
                "INVENTORY_PROVIDER_DATE_OUTSIDE_OLDER_WINDOW",
            )
            inspection = reader.get("inspection", session, day)
            replays = reader.get("replays", session)
            # A malformed successful HTTP response is a failed inspection, not missing data.
            temporary = {
                "session_external_id": sid,
                "status": "CAPTURED",
                "detail": detail,
                "inspection": inspection,
                "replays": replays,
            }
            prior = load_capture(capture, folder, manifest, archive)[2]
            build_session_inventory(
                plan, sessions, [*prior, temporary], manifest, archive
            )
        except (*FAILURES, OSError) as error:
            outcome.update(status="REQUEST_FAILED", reason=reason(error))
            stopped = reason(error) in {
                "INVENTORY_HTTP_401",
                "INVENTORY_HTTP_403",
                "INVENTORY_BATCH_DEADLINE",
                "INVENTORY_LOCAL_API_REQUEST_FAILED",
                "INVENTORY_LOCAL_API_TIMEOUT",
                "INVENTORY_LOCAL_API_CONNECTION_FAILED",
                "INVENTORY_TOTAL_RESPONSE_SIZE_LIMIT",
            }
        outcome["request_indices"] = list(range(first, len(reader.requests)))
        outcomes.append(outcome)
        capture, report, data = checkpoint(
            folder, number, plan, reader, outcomes, manifest, archive
        )
        if stopped:
            break
    checked = check_session_inventory(report, *data, manifest, archive)
    repeated = build_session_inventory(*data, manifest, archive)
    require(encode(report) == encode(repeated), "INVENTORY_LOCAL_REBUILD_CHANGED")
    _originals_unchanged(originals)
    write_json(folder / "inventory_capture.json", capture)
    write_json(folder / "inventory_report.json", report)
    write_json(folder / "inventory_report_repeat.json", repeated)
    write_json(folder / "inventory_check.json", checked)
    summary = {
        "Status": "CONTROL_STOPPED_WITH_SAVED_PROGRESS"
        if stopped
        else "SESSION_INVENTORY_LOCAL_CONTROL_VERIFIED",
        "InventoryStatus": report["status"],
        "InventoryHash": report["inventory_hash"],
        "PlanHash": plan["inventory_plan_hash"],
        "TotalSyncedSessions": len(sessions),
        "PolarSessions": report["polar_session_count"],
        "KayakSessions": report["kayak_session_count"],
        "EligibleOlderKayakSessions": plan["eligible_older_session_count"],
        "ProtectedSessionIds": plan["protected_session_ids"],
        "SelectedSessionIds": plan["selected_session_ids"],
        "CompletedInspections": len(outcomes),
        "FailedInspections": report["failed_inspection_count"],
        "APIGetRequestRecords": len(reader.requests),
        "ExecutionLimits": reader.limits,
        "RequestTimings": [
            {
                k: r[k]
                for k in (
                    "kind",
                    "session_external_id",
                    "http_status",
                    "elapsed_seconds",
                    "request_timeout_seconds",
                )
            }
            for r in reader.requests
        ],
        "NonGetRequests": 0,
        "EnvironmentProviderParametersSent": [],
        "ScientificEvidenceWriteRequests": 0,
        "ExistingCohortInputBytesPreserved": True,
        "OriginalInputSHA256": {
            str(p): hashlib.sha256(raw).hexdigest() for p, raw in originals
        },
        "ReconstructionVerified": True,
        "RepeatedLocalReportBytesIdentical": True,
        "CurrentReplaySourceBindingVerified": False,
        "NewCohortMembers": 0,
        "SplitAssignmentPersisted": False,
        "ModelFitPerformed": False,
        "TestScoringPerformed": False,
        "TrainingAuthorized": False,
        "NumericOutputAuthorized": False,
        "OutputFolder": str(folder),
        "ClaimScope": report["scope"],
        "InspectedSessions": [
            s
            for s in report["sessions"]
            if s["external_id"] in plan["selected_session_ids"]
            and s["inspection_status"] != "NOT_INSPECTED"
        ],
        **_negative_controls(report, data, manifest, archive),
    }
    write_json(folder / "inventory_control_summary.json", summary)
    return summary, 2 if stopped else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch-control", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("--manifest", type=Path, required=True)
        sub.add_argument("--archive", type=Path, required=True)
        if name == "fetch-control":
            sub.add_argument("--output-dir", type=Path, required=True)
            sub.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
            sub.add_argument("--batch-size", type=int, choices=range(1, 9), default=4)
            sub.add_argument(
                "--request-timeout-seconds", type=int, default=REQUEST_TIMEOUT_SECONDS
            )
            sub.add_argument("--batch-timeout-seconds", type=int, default=MAX_SECONDS)
            sub.add_argument("--skip-session-id", action="append", default=[])
        else:
            sub.add_argument("--capture", type=Path, required=True)
            sub.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest_raw, manifest = read_json(args.manifest, 64 * 1024)
        archive_raw, archive = read_json(args.archive, 3 * 1024 * 1024)
        originals = [(args.manifest, manifest_raw), (args.archive, archive_raw)]
        if args.command == "fetch-control":
            result, status = fetch(args, manifest, archive, originals)
        else:
            _, capture = read_json(args.capture, MAX_ARTIFACT_BYTES)
            data = load_capture(capture, args.capture.parent, manifest, archive)
            _, report = read_json(args.report, MAX_ARTIFACT_BYTES)
            result = check_session_inventory(report, *data, manifest, archive)
            _originals_unchanged(originals)
            status = 0
        print(encode(result).decode(), end="")
        return status
    except (*FAILURES, ValidationError, OSError) as error:
        print(
            encode(
                {
                    "status": "REJECTED",
                    "reason": reason(error),
                    "error_type": type(error).__name__,
                }
            ).decode(),
            end="",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
