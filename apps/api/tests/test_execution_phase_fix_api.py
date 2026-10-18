"""Installed FastAPI routes expose corrected candidates using SELECT only."""
from copy import deepcopy

from test_plan_contract_read_api import environment, polar_target
from test_executed_workout_read_api import executions
from test_execution_phase_fix import routed_source, phase
from app.planning_contracts.execution_adapter import verify_execution_read
from app.services.plan_execution_comparison_read import verify_comparison_read


def session(env):
    raw = polar_target()
    raw["exercise"][0]["phaseOrRepeat"] = [
        phase("DISTANCE", 20),
        {"changeType": "MANUAL", "repeatCount": 2,
         "phaseOrRepeat": [phase(value=10000), phase(value=10000)]},
        phase(),
    ]
    env.add(source="POLAR", raw=raw)
    return env.add_execution(raw=routed_source()["raw_data"])


def test_corrected_execution_detail_has_explicit_clock_and_source_replay(executions):
    env = executions; row = session(env); before = deepcopy(row.raw_data)
    response = env.client.get(f"/api/v1/sessions/{row.id}/executed-workout")
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["adapter_version"] == "executed-workout-adapter-0.1-draft2"
    assert verify_execution_read(value)
    blocks = [b for b in value["adapter_result"]["executed"]["blocks"] if b["execution_role"] == "PLAN_PHASE_CANDIDATE"]
    assert len(blocks) == 6
    assert all(b["boundary"]["clock_domain"] == "WALL_CLOCK_UTC" and b["boundary"]["status"] == "CANDIDATE" for b in blocks)
    assert value["adapter_result"]["native_grid_audit"]["phase_timebase"]["selected_native_origin_s"] == 2.5
    assert row.raw_data == before and set(env.sql) == {"SELECT"}


def test_corrected_comparator_is_replayable_without_authorization_promotion(executions):
    env = executions; row = session(env)
    response = env.client.get(f"/api/v1/sessions/{row.id}/plan-execution-comparison",
                              params={"include_bundle":"true", "include_source":"true"})
    assert response.status_code == 200, response.text
    value = response.json()
    assert verify_comparison_read(value)
    assert sum(r["alignment_status"] == "MATCHED_CANDIDATE" for r in value["comparison"]["rows"]) == 6
    assert value["actual_phase_alignment_verified"] is False
    assert value["numeric_output_authorized"] is False
    assert set(env.sql) == {"SELECT"}
