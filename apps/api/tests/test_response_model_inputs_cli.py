import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from test_response_model_inputs import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    inputs as _inputs,
    plan,
    sources as _sources,
)

from app.services.environment_replay_snapshot import canonical_hash

archive, completed, chronological, environment, sources, inputs = (
    _archive,
    _completed,
    _chronological,
    _environment,
    _sources,
    _inputs,
)
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/build_response_model_inputs.py"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location("model_inputs_cli", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def files(inputs, tmp_path):
    record, datasets = inputs
    manifest, archive = tmp_path / "manifest.json", tmp_path / "archive.json"
    manifest.write_text(json.dumps(plan(record)), encoding="utf-8-sig")
    archive.write_text(json.dumps(record), encoding="utf-8-sig")
    paths = []
    for index, dataset in enumerate(datasets):
        path = tmp_path / f"dataset-{index}.json"
        path.write_text(json.dumps(dataset), encoding="utf-8-sig")
        paths.append(path)
    return manifest, archive, paths


def args(files):
    manifest, archive, datasets = files
    result = ["--manifest", str(manifest), "--archive", str(archive)]
    for path in datasets:
        result.extend(["--dataset", str(path)])
    return result


def test_offline_build_check_control_preserve_originals_and_valid_negative_hashes(
    cli, files, completed, tmp_path, capsys, monkeypatch
):
    env, _ = completed
    original = {p: p.read_bytes() for p in [files[0], files[1], *files[2]]}
    calls = env.provider.await_count
    output = tmp_path / "inputs.json"
    assert cli.main(["build", *args(files), "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["model_input_row_count"] == 3
    for index in range(2):
        assert cli.main(["check", str(output), *args(files)]) == 0
        raw = capsys.readouterr().out
        if index == 0:
            first = raw
        else:
            assert raw == first
    valid_hashes = []
    real_rejected = cli._rejected

    def rejected(package, manifest, archive, datasets):
        valid_hashes.append(
            package["input_package_hash"]
            == canonical_hash({k: v for k, v in package.items() if k != "input_package_hash"})
        )
        return real_rejected(package, manifest, archive, datasets)

    monkeypatch.setattr(cli, "_rejected", rejected)
    folder = tmp_path / "control"
    assert cli.main(["control", *args(files), "--output-dir", str(folder)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["Status"] == "RESPONSE_MODEL_INPUT_LOCAL_CONTROL_VERIFIED"
    assert summary["ModelInputRowCount"] == 3
    assert summary["ObservationCount"] == 6
    assert summary["ArchivedReplayPackagePinsVerified"] is True
    assert summary["ModelInputArraysChecked"] is True
    assert summary["CurrentSourceEvidenceVerified"] is summary["TrainingAuthorized"] is False
    assert summary["ModelFitPerformed"] is False
    assert (
        summary["ReplayAPIRequestsPerformed"]
        == summary["DatabaseStorageWritesLocalMaterializer"]
        == 0
    )
    for name, value in summary.items():
        if name.endswith("Rejected"):
            assert value is True
    assert valid_hashes[0] is False and all(valid_hashes[1:])
    assert output.read_bytes() == (folder / "model_inputs.json").read_bytes()
    assert output.read_bytes() == (folder / "model_inputs_repeat.json").read_bytes()
    assert len(list(folder.iterdir())) == summary["LocalFilesWritten"] == 4
    assert all(p.read_bytes() == raw for p, raw in original.items())
    assert env.provider.await_count == calls


def test_fresh_process_without_pythonpath_or_database_still_builds(files, tmp_path):
    process_env = {**os.environ, "DATABASE_URL": "not-a-database-url"}
    process_env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "build",
            *args(files),
            "--output",
            str(tmp_path / "fresh.json"),
        ],
        cwd=ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["model_input_row_count"] == 3
    assert "not-a-database-url" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "raw",
    [
        b'{"private":NaN}',
        b'{"private":Infinity}',
        b'{"same":1,"same":2}',
        b"\xff",
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_malformed_json_rejected_without_output_or_payload_echo(cli, files, tmp_path, capsys, raw):
    files[0].write_bytes(raw)
    output = tmp_path / "bad-output.json"
    assert cli.main(["build", *args(files), "--output", str(output)]) == 1
    text = capsys.readouterr().out
    assert json.loads(text)["status"] == "REJECTED"
    assert "private" not in text
    assert not output.exists() and files[0].read_bytes() == raw


def test_wrong_pin_makes_no_partial_package_or_control_folder(cli, files, tmp_path, capsys):
    dataset = json.loads(files[2][0].read_text(encoding="utf-8-sig"))
    dataset["observations"][0]["workload_observation"]["gps_ground_speed_mps"] += 1
    dataset["package_hash"] = canonical_hash(
        {k: v for k, v in dataset.items() if k != "package_hash"}
    )
    files[2][0].write_text(json.dumps(dataset), encoding="utf-8")
    folder = tmp_path / "bad-control"
    assert cli.main(["control", *args(files), "--output-dir", str(folder)]) == 1
    assert (
        json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_REPLAY_PACKAGE_PIN_MISMATCH"
    )
    assert not folder.exists()


def test_output_collision_and_bounded_reads_preserve_existing_files(
    cli, files, tmp_path, capsys, monkeypatch
):
    output = tmp_path / "keep.json"
    output.write_bytes(b"user-content")
    assert cli.main(["build", *args(files), "--output", str(output)]) == 1
    capsys.readouterr()
    assert output.read_bytes() == b"user-content"
    monkeypatch.setattr(cli, "MAX_REPLAY_FILE_BYTES", 8)
    assert cli.main(["build", *args(files), "--output", str(tmp_path / "never.json")]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_FILE_SIZE_LIMIT"
    assert not (tmp_path / "never.json").exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8000/api/v1/integrations/polar",
        "http://example.org/api/v1/integrations/polar",
        "http://localhost:8000/other",
        "http://user:secret@localhost:8000/api/v1/integrations/polar",
        "http://localhost:8000/api/v1/integrations/polar?x=1",
        "http://localhost:8000/api/v1/integrations/polar#fragment",
    ],
)
def test_fetch_is_explicit_loopback_api_only_and_rejects_other_destinations(cli, url):
    with pytest.raises(ValueError, match="MODEL_INPUT_LOCAL_API_BASE_REQUIRED"):
        cli.local_api_base(url)


@pytest.fixture
def api_server(inputs):
    record, datasets = inputs
    lookup = {d["session_external_id"]: d for d in datasets}
    calls = []
    configuration = {"failure_index": None, "redirect": False}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            if configuration["redirect"]:
                self.send_response(302)
                self.send_header("Location", "http://example.org/private")
                self.end_headers()
                return
            if len(calls) - 1 == configuration["failure_index"]:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"detail":"private-token-not-to-echo"}')
                return
            sid = self.path.split("/sessions/", 1)[1].split("/", 1)[0]
            raw = json.dumps(lookup[sid]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/api/v1/integrations/polar", calls, configuration
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def fetch_args(files, api_server, folder):
    return [
        "fetch-control",
        "--manifest",
        str(files[0]),
        "--archive",
        str(files[1]),
        "--api-base",
        api_server[0],
        "--output-dir",
        str(folder),
    ]


def test_fetch_reads_each_exact_archive_pin_without_split_reassignment_and_runs_local_control(
    cli, files, inputs, api_server, tmp_path, capsys, monkeypatch
):
    monkeypatch.setenv("http_proxy", "http://example.org:9")
    monkeypatch.setenv("no_proxy", "")
    record, datasets = inputs
    folder = tmp_path / "fetched"
    assert cli.main(fetch_args(files, api_server, folder)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ReplayAPIRequestsPerformed"] == 3
    assert summary["LocalFilesWritten"] == len(list(folder.iterdir())) == 7
    assert summary["CurrentSourceEvidenceVerified"] is False
    assert summary["ReplayEndpointReportedStorageWrites"] == 0
    for index, (uri, body) in enumerate(api_server[1]):
        member = record["cohort_index"]["members"][index]
        assert (
            "/sessions/" + member["session_external_id"] + "/response-dataset/replay?route_date="
            in uri
        )
        assert body == {"replay_snapshot_id": member["replay_snapshot_id"], "include_payload": True}
        saved = json.loads((folder / f"member_{index:03d}_replay.json").read_text())
        dataset = next(
            d for d in datasets if d["session_external_id"] == member["session_external_id"]
        )
        assert saved == dataset


def test_failed_later_fetch_keeps_successful_raw_file_but_creates_no_partial_input_package(
    cli, files, api_server, tmp_path, capsys
):
    api_server[2]["failure_index"] = 1
    folder = tmp_path / "stopped"
    assert cli.main(fetch_args(files, api_server, folder)) == 1
    raw = capsys.readouterr().out
    assert json.loads(raw)["reason"] == "MODEL_INPUT_REPLAY_HTTP_404"
    assert "private-token-not-to-echo" not in raw
    assert len(api_server[1]) == 2
    assert [p.name for p in folder.iterdir()] == ["member_000_replay.json"]


def test_fetch_redirect_and_invalid_contract_stop_without_following_or_fetching(
    cli, files, api_server, tmp_path, capsys
):
    api_server[2]["redirect"] = True
    assert cli.main(fetch_args(files, api_server, tmp_path / "redirect")) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_REPLAY_REDIRECT_REJECTED"
    assert len(api_server[1]) == 1
    invalid = json.loads(files[0].read_text(encoding="utf-8-sig"))
    invalid["training_authorized"] = True
    files[0].write_text(json.dumps(invalid))
    assert cli.main(fetch_args(files, api_server, tmp_path / "bad-plan")) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
    assert len(api_server[1]) == 1 and not (tmp_path / "bad-plan").exists()


def test_empty_input_control_reports_target_negative_tests_not_performed(
    cli, files, inputs, tmp_path, capsys
):
    record, _ = inputs
    files[0].write_text(json.dumps(plan(record, [120000])))
    folder = tmp_path / "empty"
    assert cli.main(["control", *args(files), "--output-dir", str(folder)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ModelInputRowCount"] == 0
    assert (
        result["ChangedHRTargetRejected"] is result["FutureOrCrossBoundaryWindowRejected"] is None
    )
    assert result["EmptyInputPartitions"] == ["TRAIN", "VALIDATION", "TEST"]


def test_total_replay_file_limit_is_checked_before_any_package_write(
    cli, files, tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(cli, "MAX_TOTAL_REPLAY_FILE_BYTES", 8)
    output = tmp_path / "none.json"
    assert cli.main(["build", *args(files), "--output", str(output)]) == 1
    assert (
        json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_TOTAL_REPLAY_FILE_SIZE_LIMIT"
    )
    assert not output.exists()


def test_fetch_deadline_stops_before_provider_request_without_partial_package(
    cli, files, api_server, tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(cli, "MAX_FETCH_SECONDS", 0)
    folder = tmp_path / "deadline"
    assert cli.main(fetch_args(files, api_server, folder)) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_REPLAY_DEADLINE"
    assert api_server[1] == []
    assert list(folder.iterdir()) == []
