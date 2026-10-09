import importlib.util
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from test_response_session_inventory import (
    archive as _archive,
    available as _available,
    chronological as _chronological,
    completed as _completed,
    contract,
    environment as _environment,
    sources as _sources,
)

from app.services.environment_replay_snapshot import canonical_hash
from app.services.response_session_inventory import request_path

archive, available, chronological, completed, environment, sources = (
    _archive,
    _available,
    _chronological,
    _completed,
    _environment,
    _sources,
)
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/inspect_response_session_inventory.py"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location("inventory_cli", TOOL)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def files(archive, tmp_path):
    result = []
    for name, value in (("manifest", contract(archive)), ("archive", archive)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8-sig")
        result.append(path)
    return result


def arguments(files):
    return ["--manifest", str(files[0]), "--archive", str(files[1])]


@contextmanager
def server(available, *, bad_path=None, status=200, raw=None, redirect=None):
    sessions, observations = available
    responses = {request_path("sessions"): sessions}
    for session, observation in zip(sessions, observations):
        responses[request_path("detail", session)] = observation["detail"]
        responses[request_path("inspection", session, observation["inspection"]["route_date"])] = (
            observation["inspection"]
        )
        responses[request_path("replays", session)] = observation["replays"]
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(("GET", self.path))
            if self.path == bad_path:
                self.send_response(status)
                if redirect is not None:
                    self.send_header("Location", redirect)
                self.end_headers()
                self.wfile.write(raw if raw is not None else b'{"detail":"private-server-error"}')
            elif self.path in responses:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(responses[self.path]).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            seen.append(("POST", self.path))
            self.send_response(405)
            self.end_headers()

        def log_message(self, *args):
            pass

    http = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}/api/v1", seen, responses
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)


def test_local_get_control_checkpoints_and_reconstruction_preserve_protected_inputs(
    cli, files, available, tmp_path, capsys
):
    original = {p: p.read_bytes() for p in files}
    folder = tmp_path / "control"
    with server(available) as (base, seen, _):
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                ]
            )
            == 0
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["Status"] == "SESSION_INVENTORY_LOCAL_CONTROL_VERIFIED"
    assert summary["TotalSyncedSessions"] == 10
    assert summary["CompletedInspections"] == 4 and summary["FailedInspections"] == 0
    assert summary["APIGetRequestRecords"] == len(seen) == 13
    assert all(method == "GET" for method, _ in seen)
    assert all("capture" not in path and "weather_provider" not in path for _, path in seen)
    assert (
        summary["ScientificEvidenceWriteRequests"]
        == summary["NewCohortMembers"]
        == summary["NonGetRequests"]
        == 0
    )
    assert (
        summary["CurrentReplaySourceBindingVerified"]
        is summary["TrainingAuthorized"]
        is summary["ModelFitPerformed"]
        is False
    )
    assert all(v is True for k, v in summary.items() if k.endswith("Rejected"))
    assert len(list(folder.glob("capture_checkpoint_*.json"))) == 5
    assert (folder / "inventory_report.json").read_bytes() == (
        folder / "inventory_report_repeat.json"
    ).read_bytes()
    assert all(p.read_bytes() == raw for p, raw in original.items())
    assert (
        cli.main(
            [
                "check",
                *arguments(files),
                "--capture",
                str(folder / "inventory_capture.json"),
                str(folder / "inventory_report.json"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["reconstruction_verified"] is True
    # Initial checkpoint is also independently reconstructible with pending rows.
    assert (
        cli.main(
            [
                "check",
                *arguments(files),
                "--capture",
                str(folder / "capture_checkpoint_000.json"),
                str(folder / "inventory_progress_000.json"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["source_evidence_verified"] is False


@pytest.fixture(autouse=True)
def api_prefix(monkeypatch):
    real = request_path
    monkeypatch.setitem(globals(), "request_path", lambda *a, **k: "/api/v1" + real(*a, **k))


@pytest.mark.parametrize("status", [404, 502, 401, 403])
def test_http_failure_is_recorded_as_unknown_and_fatal_auth_keeps_progress(
    cli, files, available, tmp_path, capsys, status
):
    folder = tmp_path / f"failure-{status}"
    bad = request_path("inspection", available[0][0], available[1][0]["inspection"]["route_date"])
    with server(available, bad_path=bad, status=status) as (base, _, _):
        assert cli.main(
            ["fetch-control", *arguments(files), "--api-base", base, "--output-dir", str(folder)]
        ) == (2 if status in (401, 403) else 0)
    summary = json.loads(capsys.readouterr().out)
    assert "private-server-error" not in json.dumps(summary)
    assert summary["FailedInspections"] == 1
    assert summary["CompletedInspections"] == (1 if status in (401, 403) else 4)
    row = summary["InspectedSessions"][0]
    assert row["inspection_status"] == "REQUEST_FAILED"
    assert "gps" not in row and "hr" not in row
    assert (folder / "inventory_control_summary.json").is_file()
    assert (
        cli.main(
            [
                "check",
                *arguments(files),
                "--capture",
                str(folder / "inventory_capture.json"),
                str(folder / "inventory_report.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"private":NaN}', b'{"private":1e999}', b"\xff"]
)
def test_invalid_success_response_is_failed_inspection_not_missing_data(
    cli, files, available, tmp_path, capsys, raw
):
    folder = tmp_path / "invalid"
    bad = request_path("inspection", available[0][0], available[1][0]["inspection"]["route_date"])
    with server(available, bad_path=bad, raw=raw) as (base, _, _):
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                ]
            )
            == 0
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["FailedInspections"] == 1
    assert summary["InspectedSessions"][0]["inspection_status"] == "REQUEST_FAILED"
    assert "private" not in json.dumps(summary)


def test_redirect_is_not_followed_and_output_collision_never_overwrites(
    cli, files, available, tmp_path, capsys
):
    folder = tmp_path / "redirect"
    bad = request_path("detail", available[0][0])
    with server(available, bad_path=bad, status=302, redirect="http://example.invalid/private") as (
        base,
        seen,
        _,
    ):
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                ]
            )
            == 0
        )
        capsys.readouterr()
        assert all("private" not in path for _, path in seen)
        original = (folder / "inventory_plan.json").read_bytes()
        count = len(seen)
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                ]
            )
            == 2
        )
        capsys.readouterr()
        assert len(seen) == count
        assert (folder / "inventory_plan.json").read_bytes() == original


@pytest.mark.parametrize(
    "base",
    [
        "https://127.0.0.1/api/v1",
        "http://example.com/api/v1",
        "http://user:secret@localhost/api/v1",
        "http://localhost/api/v1?token=private",
        "http://localhost:99999/api/v1",
    ],
)
def test_remote_credentialed_or_malformed_base_is_rejected(base, cli):
    with pytest.raises(ValueError):
        cli.local_base(base)


@pytest.mark.parametrize("case", ["post", "path", "body_path", "bytes"])
def test_rehashed_capture_cannot_change_method_target_or_captured_bytes(
    cli, files, available, tmp_path, capsys, case
):
    folder = tmp_path / "tamper"
    with server(available) as (base, _, _):
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                    "--batch-size",
                    "1",
                ]
            )
            == 0
        )
    capsys.readouterr()
    path = folder / "inventory_capture.json"
    value = json.loads(path.read_text())
    if case == "post":
        value["requests"][1]["method"] = "POST"
    elif case == "path":
        value["requests"][1]["path"] = "/integrations/polar/sessions/sync"
    elif case == "body_path":
        value["requests"][1]["body_file"] = "../private.json"
    else:
        (folder / "response_001.json").write_bytes(b"{}")
    value["capture_hash"] = canonical_hash({k: v for k, v in value.items() if k != "capture_hash"})
    path.write_text(json.dumps(value))
    assert (
        cli.main(
            [
                "check",
                *arguments(files),
                "--capture",
                str(path),
                str(folder / "inventory_report.json"),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"


def test_deadline_after_initial_plan_stops_with_reconstructible_saved_progress(
    cli, files, available, tmp_path, capsys, monkeypatch
):
    real = cli.Reader.get

    def get(reader, kind, *args):
        if kind != "sessions":
            reader.started -= cli.MAX_SECONDS + 1
        return real(reader, kind, *args)

    monkeypatch.setattr(cli.Reader, "get", get)
    folder = tmp_path / "deadline"
    with server(available) as (base, seen, _):
        assert (
            cli.main(
                [
                    "fetch-control",
                    *arguments(files),
                    "--api-base",
                    base,
                    "--output-dir",
                    str(folder),
                ]
            )
            == 2
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["Status"] == "CONTROL_STOPPED_WITH_SAVED_PROGRESS"
    assert len(seen) == 1 and summary["CompletedInspections"] == 1
    assert (folder / "inventory_progress_001.json").is_file()
    assert (
        cli.main(
            [
                "check",
                *arguments(files),
                "--capture",
                str(folder / "inventory_capture.json"),
                str(folder / "inventory_report.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
