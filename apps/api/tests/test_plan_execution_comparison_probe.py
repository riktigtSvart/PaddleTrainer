import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

from test_plan_contract_read_api import environment
from test_executed_workout_read_api import executions
from test_plan_execution_comparison_api import good


def probe():
    path = Path(__file__).resolve().parents[3] / "tools/probe_plan_execution_comparison_api.py"
    spec = importlib.util.spec_from_file_location("comparison_probe_test", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("with_sample", [True, False])
def test_probe_uses_real_app_responses_and_replays_same_capture(executions, tmp_path, monkeypatch, with_sample):
    env = executions
    if with_sample:
        good(env)
    module = probe()
    def get_json(base, path):
        response = env.client.get(path)
        assert response.status_code == 200, response.text
        return response.json()
    monkeypatch.setattr(module, "get_json", get_json)
    output = tmp_path / "probe with spaces"
    assert module.main(["--output", str(output)]) == 0
    with zipfile.ZipFile(output.with_name(output.name + ".zip")) as archive:
        summary = json.loads(archive.read("summary.json"))
        assert summary["sample_contract_round_trip_verified"] is with_sample
        assert summary["status"] == ("COMPARISON_API_READ_PROBE_PASSED" if with_sample else "COMPARISON_API_REACHABLE_WITHOUT_ELIGIBLE_SAMPLE")
        assert not summary["complete_history_coverage_claimed"]


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1@evil.test", "http://localhost:8000/?x=y", "file:///tmp/a"])
def test_probe_only_accepts_literal_loopback_urls(url):
    with pytest.raises(ValueError):
        probe().loopback_base(url)
