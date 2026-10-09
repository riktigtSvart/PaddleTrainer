import json
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from test_response_session_inventory_cli import (
    api_prefix,  # noqa: F401 -- shared autouse HTTP-prefix fixture
    archive as _archive,
    available as _available,
    chronological as _chronological,
    cli as _cli,
    completed as _completed,
    environment as _environment,
    files as _files,
    server,
    sources as _sources,
    arguments,
)

from app.services.environment_replay_snapshot import canonical_hash

archive, available, chronological, cli, completed, environment, files, sources = (
    _archive,
    _available,
    _chronological,
    _cli,
    _completed,
    _environment,
    _files,
    _sources,
)


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return b"[]"


def test_reported_126_second_read_uses_longer_timeout_without_sleep(cli, tmp_path, monkeypatch):
    clock, seen = [0.0], []
    monkeypatch.setattr(cli, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    reader = cli.Reader("http://127.0.0.1:8000/api/v1", tmp_path, 180, 360)

    def open_request(request, timeout):
        seen.append((request.get_method(), timeout))
        clock[0] = 126.41
        return Response()

    reader.opener = SimpleNamespace(open=open_request)
    assert reader.get("sessions") == []
    assert seen == [("GET", 180)]
    assert reader.requests[0]["elapsed_seconds"] == 126.41
    assert reader.requests[0]["request_timeout_seconds"] == 180
    assert (tmp_path / "response_000.json").read_bytes() == b"[]"


def test_socket_timeout_is_clipped_to_remaining_batch_budget(cli, tmp_path, monkeypatch):
    clock, seen = [0.0], []
    monkeypatch.setattr(cli, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    reader = cli.Reader("http://127.0.0.1:8000/api/v1", tmp_path, 180, 100)
    clock[0] = 60.0

    def open_request(_, timeout):
        seen.append(timeout)
        clock[0] = 95.0
        return Response()

    reader.opener = SimpleNamespace(open=open_request)
    assert reader.get("sessions") == []
    assert seen == [40]
    assert reader.requests[0]["elapsed_seconds"] == 35


def test_completed_read_past_batch_deadline_is_stopped_and_still_timed(cli, tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(cli, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    reader = cli.Reader("http://127.0.0.1:8000/api/v1", tmp_path, 180, 120)

    def open_request(_, timeout):
        assert timeout == 120
        clock[0] = 126.41
        return Response()

    reader.opener = SimpleNamespace(open=open_request)
    with pytest.raises(ValueError, match="INVENTORY_BATCH_DEADLINE"):
        reader.get("sessions")
    assert reader.requests[0]["elapsed_seconds"] == 126.41
    assert reader.requests[0]["http_status"] == 200
    assert (tmp_path / "response_000.json").is_file()


@pytest.mark.parametrize(
    "error, expected",
    [
        (TimeoutError("private"), "INVENTORY_LOCAL_API_TIMEOUT"),
        (URLError(TimeoutError("private")), "INVENTORY_LOCAL_API_TIMEOUT"),
        (URLError(ConnectionRefusedError("private")), "INVENTORY_LOCAL_API_CONNECTION_FAILED"),
        (ConnectionResetError("private"), "INVENTORY_LOCAL_API_CONNECTION_FAILED"),
        (IncompleteRead(b"private", 10), "INVENTORY_LOCAL_API_CONNECTION_FAILED"),
        (HTTPError("http://localhost/private", 504, "private", {}, None), "INVENTORY_HTTP_504"),
    ],
)
def test_transport_failures_are_distinct_and_timed_without_body_capture(
    cli, tmp_path, monkeypatch, error, expected
):
    clock = [0.0]
    monkeypatch.setattr(cli, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    reader = cli.Reader("http://127.0.0.1:8000/api/v1", tmp_path)

    def open_request(*_, **__):
        clock[0] = 12.5
        raise error

    reader.opener = SimpleNamespace(open=open_request)
    with pytest.raises(ValueError, match="^" + expected + "$"):
        reader.get("sessions")
    assert reader.requests[0]["elapsed_seconds"] == 12.5
    assert reader.requests[0]["body_file"] is None
    assert "private" not in json.dumps(reader.requests)
    assert not list(tmp_path.glob("response_*.json"))


@pytest.fixture
def capture(cli, files, available, tmp_path, capsys):
    folder = tmp_path / "timed"
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
                    "--request-timeout-seconds",
                    "180",
                    "--batch-timeout-seconds",
                    "360",
                ]
            )
            == 0
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["ExecutionLimits"] == {
        "request_timeout_seconds": 180,
        "batch_timeout_seconds": 360,
    }
    assert len(summary["RequestTimings"]) == 4
    assert summary["ScientificEvidenceWriteRequests"] == summary["NewCohortMembers"] == 0
    return folder


def check(cli, files, folder):
    return cli.main(
        [
            "check",
            *arguments(files),
            "--capture",
            str(folder / "inventory_capture.json"),
            str(folder / "inventory_report.json"),
        ]
    )


def test_original_d1_capture_schema_remains_checkable(cli, files, capture, capsys):
    path = capture / "inventory_capture.json"
    value = json.loads(path.read_text())
    value["schema_version"] = "0.1"
    value.pop("execution_limits")
    for request in value["requests"]:
        request.pop("elapsed_seconds")
        request.pop("request_timeout_seconds")
    value["capture_hash"] = canonical_hash({k: v for k, v in value.items() if k != "capture_hash"})
    path.write_text(json.dumps(value))
    original = path.read_bytes()
    assert check(cli, files, capture) == 0
    assert json.loads(capsys.readouterr().out)["reconstruction_verified"] is True
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "error, expected, phase",
    [
        (TimeoutError("private"), "INVENTORY_LOCAL_API_TIMEOUT", "open"),
        (
            URLError(ConnectionRefusedError("private")),
            "INVENTORY_LOCAL_API_CONNECTION_FAILED",
            "open",
        ),
        (TimeoutError("private"), "INVENTORY_LOCAL_API_TIMEOUT", "read"),
    ],
)
def test_fatal_network_failure_preserves_timed_checkpoint_and_uninspected_rows(
    cli, files, available, tmp_path, capsys, monkeypatch, error, expected, phase
):
    real = cli.Reader.get

    def get(reader, kind, *args):
        if kind != "inspection":
            return real(reader, kind, *args)
        original = reader.opener

        def fail(*_, **__):
            if phase == "read":

                class Interrupted(Response):
                    def read(self, _):
                        raise error

                return Interrupted()
            raise error

        reader.opener = SimpleNamespace(open=fail)
        try:
            return real(reader, kind, *args)
        finally:
            reader.opener = original

    monkeypatch.setattr(cli.Reader, "get", get)
    folder = tmp_path / "failure"
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
                ]
            )
            == 2
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["Status"] == "CONTROL_STOPPED_WITH_SAVED_PROGRESS"
    assert summary["CompletedInspections"] == summary["FailedInspections"] == 1
    assert summary["InspectedSessions"][0]["request_failure_reason"] == expected
    assert len(summary["RequestTimings"]) == 3
    assert (folder / "capture_checkpoint_001.json").is_file()
    assert check(cli, files, folder) == 0
    capsys.readouterr()


@pytest.mark.parametrize(
    "option, value",
    [
        ("--request-timeout-seconds", "0"),
        ("--request-timeout-seconds", "301"),
        ("--batch-timeout-seconds", "0"),
        ("--batch-timeout-seconds", "1801"),
    ],
)
def test_invalid_timing_limits_make_no_folder_or_api_request(
    cli, files, available, tmp_path, capsys, option, value
):
    folder = tmp_path / "invalid-limits"
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
                    option,
                    value,
                ]
            )
            == 2
        )
    assert not folder.exists() and not seen
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"


@pytest.mark.parametrize(
    "case", ["negative_elapsed", "bool_elapsed", "large_timeout", "extra_limit"]
)
def test_rehashed_capture_with_invalid_timing_metadata_is_rejected(
    cli, files, capture, capsys, case
):
    path = capture / "inventory_capture.json"
    value = json.loads(path.read_text())
    if case == "negative_elapsed":
        value["requests"][0]["elapsed_seconds"] = -1
    elif case == "bool_elapsed":
        value["requests"][0]["elapsed_seconds"] = True
    elif case == "large_timeout":
        value["requests"][0]["request_timeout_seconds"] = 301
    else:
        value["execution_limits"]["unlimited"] = True
    value["capture_hash"] = canonical_hash({k: v for k, v in value.items() if k != "capture_hash"})
    path.write_text(json.dumps(value))
    assert check(cli, files, capture) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
