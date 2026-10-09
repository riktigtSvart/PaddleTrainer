import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_response_baseline_experiment import (
    archive as _archive,
    chronological as _chronological,
    completed as _completed,
    environment as _environment,
    inputs as _inputs,
    ready as _ready,
    sources as _sources,
)

archive, chronological, completed, environment, inputs, ready, sources = (
    _archive,
    _chronological,
    _completed,
    _environment,
    _inputs,
    _ready,
    _sources,
)
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools/run_response_baseline_experiment.py"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location("baseline_cli", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def files(ready, tmp_path):
    policy, package, manifest, record, datasets = ready
    paths = {}
    for name, value in (
        ("plan", policy),
        ("inputs", package),
        ("manifest", manifest),
        ("archive", record),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8-sig")
        paths[name] = path
    paths["datasets"] = []
    for i, value in enumerate(datasets):
        path = tmp_path / f"dataset_{i}.json"
        path.write_text(json.dumps(value), encoding="utf-8-sig")
        paths["datasets"].append(path)
    return paths


def arguments(files):
    result = []
    for key in ("manifest", "archive", "inputs"):
        result.extend([f"--{key}", str(files[key])])
    for path in files["datasets"]:
        result.extend(["--dataset", str(path)])
    return result


def test_offline_control_is_repeatable_preserves_sources_and_commits_policy_before_scoring(
    cli, files, completed, tmp_path, capsys, monkeypatch
):
    original = {
        p: p.read_bytes()
        for p in [files["manifest"], files["archive"], files["inputs"], *files["datasets"]]
    }
    env, _ = completed
    before = env.provider.await_count, env.db.commit_count
    output = tmp_path / "control"
    real_run = cli.run_response_baseline_experiment

    def committed_run(*args):
        assert (output / "baseline_plan.json").is_file()
        assert (
            json.loads((output / "baseline_plan.json").read_text())["plan_hash"]
            == args[0]["plan_hash"]
        )
        return real_run(*args)

    monkeypatch.setattr(cli, "run_response_baseline_experiment", committed_run)
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["Status"] == "RESPONSE_BASELINE_LOCAL_CONTROL_VERIFIED"
    assert summary["RidgeFitPerformed"] is False
    assert summary["RidgeStatus"] == "WITHHELD_MULTIPLE_TRAIN_SESSIONS_REQUIRED"
    assert summary["ConstantBaselineFitPerformed"] is True
    assert summary["TrainPreprocessingFitPerformed"] is True
    assert summary["BModelInputRowCount"] == 3
    assert summary["DevelopmentRows"] == 2
    assert summary["TrainRows"] == summary["ValidationRows"] == summary["ReservedTestRows"] == 1
    assert (
        summary["TestAdaptedRows"]
        == summary["DatabaseStorageWrites"]
        == summary["PolarProviderCalls"]
        == 0
    )
    assert summary["TestPayloadReadForIntegrityOnly"] is True
    assert summary["TestScoringPerformed"] is summary["GeneralizationEvidenceVerified"] is False
    assert summary["TrainingAuthorized"] is summary["NumericOutputAuthorized"] is False
    assert summary["PlanWrittenBeforeDevelopmentScoring"] is True
    assert all(v is True for k, v in summary.items() if k.endswith("Rejected"))
    assert summary["LocalFilesWritten"] == len(list(output.iterdir())) == 7
    assert (output / "baseline_run.json").read_bytes() == (
        output / "baseline_run_repeat.json"
    ).read_bytes()
    assert all(p.read_bytes() == raw for p, raw in original.items())
    assert before == (env.provider.await_count, env.db.commit_count)
    assert (
        cli.main(
            [
                "check",
                str(output / "baseline_run.json"),
                *arguments(files),
                "--plan",
                str(output / "baseline_plan.json"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["reconstruction_verified"] is True


def test_prepare_then_run_then_repeated_check_uses_exact_frozen_plan(cli, files, tmp_path, capsys):
    plan, result = tmp_path / "new_plan.json", tmp_path / "run.json"
    assert cli.main(["prepare", *arguments(files), "--output", str(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "FIXED_DEVELOPMENT_PLAN_PREPARED"
    raw = plan.read_bytes()
    assert cli.main(["run", *arguments(files), "--plan", str(plan), "--output", str(result)]) == 0
    assert json.loads(capsys.readouterr().out)["test_scoring_performed"] is False
    for i in range(2):
        assert cli.main(["check", str(result), *arguments(files), "--plan", str(plan)]) == 0
        checked = capsys.readouterr().out
        if i == 0:
            first = checked
        else:
            assert first == checked
    assert plan.read_bytes() == raw


def test_new_python_process_with_no_pythonpath_or_database_runs_offline(files, tmp_path):
    process_env = {**os.environ, "DATABASE_URL": "private-invalid-database"}
    process_env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "run",
            *arguments(files),
            "--plan",
            str(files["plan"]),
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
    assert json.loads(result.stdout)["status"] == "SINGLE_TRAIN_SESSION_BASELINE_SMOKE_ONLY"
    assert "private-invalid-database" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "raw",
    [
        b'{"private":NaN}',
        b'{"private":Infinity}',
        b'{"private":1e999}',
        b'{"a":1,"a":2}',
        b"\xff",
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_invalid_json_fails_before_creating_output_without_echoing_private_input(
    cli, files, tmp_path, capsys, raw
):
    files["inputs"].write_bytes(raw)
    output = tmp_path / "invalid"
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 2
    response = capsys.readouterr().out
    assert json.loads(response)["status"] == "REJECTED"
    assert "private" not in response
    assert not output.exists()


def test_existing_output_directory_and_sources_are_never_overwritten(cli, files, tmp_path, capsys):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_bytes(b"preserve")
    original = files["inputs"].read_bytes()
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
    assert list(output.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"preserve"
    assert files["inputs"].read_bytes() == original
    assert cli.main(["prepare", *arguments(files), "--output", str(files["inputs"])]) == 2
    capsys.readouterr()
    assert files["inputs"].read_bytes() == original


@pytest.mark.parametrize(
    "field,limit",
    [("MAX_INPUT_BYTES", 1), ("MAX_TOTAL_DATASET_BYTES", 1), ("MAX_MANIFEST_BYTES", 1)],
)
def test_file_size_limits_fail_before_writing_plan(
    cli, files, tmp_path, capsys, monkeypatch, field, limit
):
    monkeypatch.setattr(cli, field, limit)
    output = tmp_path / "limited"
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
    assert not output.exists()


def test_changed_pinned_b_input_is_rejected_before_plan_write(cli, files, tmp_path, capsys):
    payload = json.loads(files["inputs"].read_text(encoding="utf-8-sig"))
    payload["members"][0]["targets"][0]["recorded_hr_mean_bpm"] += 10
    files["inputs"].write_text(json.dumps(payload))
    output = tmp_path / "wrong"
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "MODEL_INPUT_PACKAGE_HASH_MISMATCH"
    assert not output.exists()


def test_failure_after_plan_commit_retains_plan_without_automatic_removal(
    cli, files, tmp_path, capsys, monkeypatch
):
    output = tmp_path / "stopped"

    def stop(*args):
        raise ValueError("BASELINE_CONTROL_STOPPED_FIXTURE")

    monkeypatch.setattr(cli, "run_response_baseline_experiment", stop)
    assert cli.main(["control", *arguments(files), "--output-dir", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "BASELINE_CONTROL_STOPPED_FIXTURE"
    assert [p.name for p in output.iterdir()] == ["baseline_plan.json"]


def test_write_size_limit_prevents_partial_output_and_source_change_is_detected(
    cli, files, tmp_path, monkeypatch
):
    monkeypatch.setattr(cli, "MAX_ARTIFACT_BYTES", 1)
    path = tmp_path / "large.json"
    with pytest.raises(ValueError, match="BASELINE_OUTPUT_FILE_SIZE_LIMIT"):
        cli.write_new(path, {"large": "value"})
    assert not path.exists()
    source = files["manifest"]
    raw = source.read_bytes()
    source.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="BASELINE_SOURCE_CHANGED_DURING_CONTROL"):
        cli._unchanged([(source, raw)])
