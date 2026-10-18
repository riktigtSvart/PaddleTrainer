"""Pure, descriptive comparison of captured plan and execution reads.

This is an evidence adapter, not the already-deployed PlanExecutionComparison
wire contract. That schema is deliberately not guessed here. No boundary,
intensity, completion, readiness, or model authorization is inferred.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

RULES_VERSION = "plan-execution-comparison-evidence-0.1-draft1"
EXECUTION_ADAPTER = "executed-workout-adapter-0.1-draft1"
SUPPORTED_EXECUTION_ADAPTERS = {EXECUTION_ADAPTER, "executed-workout-adapter-0.1-draft2"}
PLAN_ADAPTER = "legacy-plan-adapter-0.1-draft1"
PROTECTED_EXTERNAL_IDS = frozenset({
    "0e1bc738-5f97-7a0e-45a9-13c8b829a119",
    "0e1c32b1-669f-3e67-9a26-a18cc8599b94",
    "0e242691-9390-397f-e854-90d1072a66d5",
    "0e276e10-9993-73d5-e3e3-702ad5f1f72c",
    "0e2791e4-5399-6e29-9a10-a40c7b3ecbe3",
    "0e27d18d-279f-2d26-1ae3-bb53e19b2b1f",
})


class ComparisonError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ComparisonError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_number(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def unique_index(items, key, code):
    result = {}
    for item in items:
        require(isinstance(item, dict), code + "_NOT_OBJECT")
        value = item.get(key)
        require(isinstance(value, str) and bool(value), code + "_MISSING_ID")
        require(value not in result, code + "_DUPLICATE_ID")
        result[value] = item
    return result


METRICS = {
    "DURATION": "SECOND", "DISTANCE": "METRE",
    "MEAN_HEART_RATE": "BPM", "MEAN_SPEED": "M_PER_S",
    "CARDIO_LOAD": "SOURCE_NATIVE",
}


def metric_index(block, *, whole=False):
    metrics = block.get("metrics")
    require(isinstance(metrics, list), "METRICS_NOT_LIST")
    result = unique_index(metrics, "metric_name", "METRIC")
    for name, value in result.items():
        require(name in METRICS and value.get("unit") == METRICS[name],
                "METRIC_UNIT_OR_NAME_UNSUPPORTED")
        require(value.get("status") in {"AVAILABLE", "MISSING", "UNRESOLVED"},
                "METRIC_STATUS_UNSUPPORTED")
        expected_aggregation = ("WHOLE_SESSION" if whole else
                                "BLOCK_TOTAL" if name in {"DURATION", "DISTANCE"}
                                else "BLOCK_MEAN")
        require(value.get("aggregation") == expected_aggregation,
                "METRIC_AGGREGATION_MISMATCH")
        if value["status"] == "AVAILABLE":
            require(is_number(value.get("value")), "AVAILABLE_METRIC_NOT_FINITE_NONNEGATIVE")
        else:
            require(value.get("value") is None, "UNAVAILABLE_METRIC_HAS_VALUE")
        count = value.get("sample_count")
        require(count is None or type(count) is int and count >= 0,
                "INVALID_METRIC_SAMPLE_COUNT")
    return result


def expand_plan(plan, supplied):
    """Check occurrence paths/order/multiplicity against the contract tree.

    We retain the existing adapter's occurrence IDs. We independently expand
    tree paths and target fields, rather than guessing its ID hash algorithm.
    """
    require(isinstance(plan.get("blocks"), list), "PLAN_BLOCKS_NOT_LIST")
    require(isinstance(supplied, list), "EXPANDED_OCCURRENCES_NOT_LIST")
    index = {}
    expected = []
    structural_issues = set()

    def visit(block, path, depth):
        require(depth <= 32 and len(expected) <= 10000, "PLAN_EXPANSION_LIMIT")
        require(isinstance(block, dict), "PLAN_BLOCK_NOT_OBJECT")
        bid = block.get("block_id")
        require(isinstance(bid, str) and bid, "PLAN_BLOCK_ID_MISSING")
        # A repeated subtree is revisited, but each structural block has one
        # definition. Structural duplicate IDs are checked before expansion.
        count = block.get("repeat_count")
        require(type(count) is int and 1 <= count <= 10000, "INVALID_REPEAT_COUNT")
        structure = block.get("structure")
        require(structure in {"SEGMENT", "SEQUENCE"}, "UNSUPPORTED_PLAN_STRUCTURE")
        children = block.get("children")
        require(isinstance(children, list), "PLAN_CHILDREN_NOT_LIST")
        for key in ("duration_s", "distance_m"):
            value = block.get(key)
            require(value is None or is_number(value, positive=True), "INVALID_PLANNED_TARGET")
        if block.get("recovery") is not None:
            structural_issues.add("SEPARATE_RECOVERY_NOT_EXPANDED")
        if structure == "SEQUENCE":
            require(bool(children), "EMPTY_PLAN_SEQUENCE")
            require(block.get("completion_condition") == "CHILDREN", "UNSUPPORTED_CONTAINER_COMPLETION")
            if block.get("duration_s") is not None or block.get("distance_m") is not None:
                structural_issues.add("CONTAINER_TARGET_NOT_ADDED_TO_LEAF_TARGETS")
        else:
            require(not children, "SEGMENT_HAS_CHILDREN")
        for repetition in range(1, count + 1):
            current_path = path + [f"{bid}@{repetition}"]
            if structure == "SEQUENCE":
                for child in children:
                    visit(child, current_path, depth + 1)
            else:
                expected.append({
                    "block_id": bid, "block_type": block.get("block_type"),
                    "completion_condition": block.get("completion_condition"),
                    "distance_m": block.get("distance_m"),
                    "duration_s": block.get("duration_s"),
                    "occurrence_path": current_path,
                })
                require(len(expected) <= 10000, "PLAN_EXPANSION_LIMIT")

    def definitions(blocks, depth=0):
        require(depth <= 32, "PLAN_DEPTH_LIMIT")
        for block in blocks:
            require(isinstance(block, dict), "PLAN_BLOCK_NOT_OBJECT")
            bid = block.get("block_id")
            require(isinstance(bid, str) and bid and bid not in index,
                    "PLAN_BLOCK_ID_MISSING_OR_DUPLICATE")
            index[bid] = block
            children = block.get("children")
            require(isinstance(children, list), "PLAN_CHILDREN_NOT_LIST")
            definitions(children, depth + 1)

    definitions(plan["blocks"])
    for block in plan["blocks"]:
        visit(block, [], 0)
    require(len(supplied) == len(expected), "OCCURRENCE_EXPANSION_COUNT_MISMATCH")
    unique_index(supplied, "planned_occurrence_id", "PLANNED_OCCURRENCE")
    for actual, expected_item in zip(supplied, expected):
        require(all(actual.get(key) == value for key, value in expected_item.items()),
                "OCCURRENCE_EXPANSION_CONTENT_OR_ORDER_MISMATCH")
    return index, sorted(structural_issues)


def planned_dimension(occurrences, field, structural_issues):
    condition = "DURATION" if field == "duration_s" else "DISTANCE"
    eligible = [o for o in occurrences if o.get("completion_condition") == condition
                and is_number(o.get(field), positive=True)]
    all_known = bool(occurrences) and len(eligible) == len(occurrences) and not structural_issues
    subtotal = math.fsum(o[field] for o in eligible) if eligible else None
    return {
        "status": "EXACT_EXPANDED_LEAF_TARGET_TOTAL" if all_known else "EXACT_TOTAL_NOT_ESTABLISHED",
        "value": subtotal if all_known else None,
        "known_target_subtotal": subtotal,
        "known_target_occurrence_count": len(eligible),
        "total_occurrence_count": len(occurrences),
        "reasons": sorted(set(structural_issues + ([] if all_known else [
            "MISSING_OR_MIXED_COMPLETION_DIMENSIONS_DO_NOT_IMPLY_ZERO"
        ]))),
        "basis": "CURRENT_CAPTURE_EXPANDED_LEAVES_NOT_PROVEN_HISTORICAL_PLAN",
    }


def dimensional_comparison(planned, metric, *, reasons=()):
    observed = copy.deepcopy(metric) if metric else None
    available = metric is not None and metric.get("status") == "AVAILABLE"
    difference = (metric["value"] - planned["value"]
                  if available and planned.get("value") is not None and not reasons else None)
    return {
        "planned": planned, "observed": observed,
        "observed_minus_planned": difference,
        "difference_scope": "DESCRIPTIVE_ONLY" if difference is not None else "NOT_ESTABLISHED",
        "completion_status": "NOT_ASSESSED",
        "reasons": list(reasons),
    }


def _source_phase_field(adapter, bid, field):
    """Keep source declarations unchanged. No name parsing or bpm conversion."""
    mappings = [m for m in adapter.get("block_mapping", []) if m.get("block_id") == bid]
    if len(mappings) != 1:
        return None
    pointer = mappings[0].get("source_pointer")
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return None
    value = adapter.get("source", {}).get("payload")
    try:
        for token in pointer.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
        return copy.deepcopy(value.get(field)) if isinstance(value, dict) else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def validate_read(read):
    require(isinstance(read, dict), "EXECUTION_READ_NOT_OBJECT")
    require(read.get("adapter_version") in SUPPORTED_EXECUTION_ADAPTERS and
            read.get("schema_version") == "0.1" and read.get("contract_release") == "DRAFT1",
            "UNSUPPORTED_EXECUTION_READ_VERSION")
    result = read.get("adapter_result")
    require(isinstance(result, dict) and isinstance(result.get("executed"), dict),
            "EXECUTION_RESULT_MISSING")
    executed = result["executed"]
    source = read.get("source_snapshot")
    require(isinstance(source, dict), "SOURCE_SNAPSHOT_MISSING")
    for external in (source.get("external_id"), executed.get("provider_session_id")):
        require(str(external).lower() not in PROTECTED_EXTERNAL_IDS,
                "PROTECTED_SESSION_NUMERIC_COMPARISON_FORBIDDEN")
    require(sha256(source) == read.get("source_content_sha256"), "EXECUTION_SOURCE_HASH_MISMATCH")
    require(read.get("session_id") == source.get("id") and bool(source.get("id")),
            "SESSION_ID_MISMATCH")
    require(executed.get("athlete_id") == source.get("user_id") and bool(source.get("user_id")),
            "EXECUTION_OWNER_MISMATCH")
    require(executed.get("provider_session_id") == source.get("external_id") and
            executed.get("provider") == source.get("external_provider") and
            executed.get("sport") == source.get("sport"), "EXECUTION_PROVIDER_OR_SPORT_MISMATCH")
    require(executed.get("contract_type") == "ExecutedWorkout" and
            executed.get("schema_version") == "0.1", "EXECUTED_CONTRACT_VERSION_MISMATCH")
    for flag in ("actual_phase_alignment_verified", "historical_plan_content_verified",
                 "numeric_output_authorized", "state_estimation_authorized",
                 "capability_update_performed", "speed_model_retrained",
                 "state_model_trained", "new_independent_test"):
        require(read.get(flag) is False, "UNSUPPORTED_AUTHORITY_OR_VERIFICATION_FLAG:" + flag)
    require(read.get("database_writes") == 0 and read.get("provider_calls") == 0,
            "EXECUTION_READ_HAS_SIDE_EFFECTS")
    require(executed.get("speed_results") == [], "SPEED_MODEL_RESULTS_NOT_SUPPORTED")
    blocks = executed.get("blocks")
    require(isinstance(blocks, list), "EXECUTED_BLOCKS_NOT_LIST")
    unique_index(blocks, "executed_block_id", "EXECUTED_BLOCK")
    summaries = [b for b in blocks if b.get("execution_role") == "WHOLE_SESSION_SUMMARY"]
    require(len(summaries) == 1, "EXACTLY_ONE_WHOLE_SESSION_SUMMARY_REQUIRED")
    require(summaries[0].get("planned_occurrence_id") is None and
            summaries[0].get("planned_block_id") is None, "WHOLE_SUMMARY_MUST_NOT_LINK_ONE_PHASE")
    metric_index(summaries[0], whole=True)
    for block in blocks:
        if block is summaries[0]:
            continue
        require(block.get("execution_role") == "PLAN_PHASE_CANDIDATE", "UNSUPPORTED_EXECUTION_ROLE")
        boundary = block.get("boundary", {})
        require(boundary.get("status") == "CANDIDATE", "VERIFIED_BOUNDARY_MODE_NOT_SUPPORTED")
        start, end = boundary.get("start_offset_s"), boundary.get("end_offset_s")
        require(is_number(start) and is_number(end) and end > start,
                "INVALID_CANDIDATE_BOUNDARY")
        metrics = metric_index(block)
        duration = metrics.get("DURATION")
        if duration and duration["status"] == "AVAILABLE":
            require(math.isclose(duration["value"], end - start, rel_tol=1e-9, abs_tol=1e-6),
                    "CANDIDATE_DURATION_DIFFERS_FROM_BOUNDARY")
    plan_capture = read.get("plan_capture")
    if plan_capture is None:
        require(executed.get("plan_ref") is None, "PLAN_REF_WITHOUT_PLAN_CAPTURE")
        return executed, summaries[0], None
    require(isinstance(plan_capture, dict), "PLAN_CAPTURE_NOT_OBJECT")
    plan_source = plan_capture.get("source_snapshot")
    require(isinstance(plan_source, dict) and
            sha256(plan_source) == plan_capture.get("source_content_sha256"), "PLAN_SOURCE_HASH_MISMATCH")
    require(plan_source.get("user_id") == executed["athlete_id"], "PLAN_OWNER_MISMATCH")
    require(plan_source.get("id") == plan_capture.get("workout_id"), "PLAN_STORAGE_ID_MISMATCH")
    adapter = plan_capture.get("adapter_result", {})
    require(adapter.get("adapter_version") == PLAN_ADAPTER, "UNSUPPORTED_PLAN_ADAPTER_VERSION")
    plan = adapter.get("plan", {})
    require(plan.get("contract_type") == "WorkoutPlanContract" and plan.get("schema_version") == "0.1",
            "PLAN_CONTRACT_VERSION_MISMATCH")
    require(plan.get("athlete_id") == executed["athlete_id"], "PLAN_CONTRACT_OWNER_MISMATCH")
    require(plan.get("sport") == executed.get("sport"), "PLAN_EXECUTION_SPORT_MISMATCH")
    require(executed.get("plan_ref") == {"plan_id": plan.get("plan_id"),
                                        "plan_revision": plan.get("plan_revision")}, "PLAN_REVISION_LINK_MISMATCH")
    require(plan_capture.get("historical_plan_content_verified") is False and
            plan_capture.get("actual_phase_alignment_verified") is False,
            "VERIFIED_PLAN_MODE_NOT_SUPPORTED")
    stored_link = source.get("planned_workout_id")
    if stored_link is not None:
        require(stored_link == plan_capture["workout_id"], "STORED_PLAN_LINK_DIFFERS")
    else:
        target = source.get("raw_data", {}).get("trainingTarget")
        require(source.get("external_provider") == "POLAR" and isinstance(target, dict) and
                target.get("id") is not None and
                str(target["id"]) == str(plan_source.get("polar_target_id")),
                "EXACT_PROVIDER_TARGET_LINK_MISSING")
    return executed, summaries[0], adapter


def compare_execution_read(read):
    """Return deterministic observations bound to one exact captured read."""
    executed, summary, plan_adapter = validate_read(read)
    whole_metrics = metric_index(summary, whole=True)
    source_hash = sha256(read)
    comparison = {
        "artifact_type": "PlanExecutionComparisonEvidence",
        "evidence_schema_version": "0.1", "rules_version": RULES_VERSION,
        "comparison_id": "comparison_" + sha256({"rules": RULES_VERSION, "input": source_hash}),
        "contract_binding": {
            "target_contract": "PlanExecutionComparison", "target_schema_version": "0.1",
            "status": "AUTHORITATIVE_CONTRACT_PROJECTION_PENDING",
            "reason": "EXISTING_CANONICAL_SCHEMA_NOT_IN_REFERENCE_INPUT_DO_NOT_INVENT_REPLACEMENT",
        },
        "session_id": read["session_id"], "provider_session_id": executed["provider_session_id"],
        "athlete_id": executed["athlete_id"], "sport": executed["sport"],
        "execution_ref": {"executed_workout_id": executed["executed_workout_id"],
                          "execution_revision": executed["execution_revision"]},
        "plan_ref": copy.deepcopy(executed.get("plan_ref")),
        "provenance": {
            "execution_read_sha256": source_hash,
            "source_content_sha256": read["source_content_sha256"],
            "capture_id": read.get("capture_id"), "captured_at": read.get("captured_at"),
            "execution_adapter_version": read["adapter_version"],
            "plan_source_content_sha256": (read["plan_capture"]["source_content_sha256"]
                                           if read.get("plan_capture") else None),
            "pure_execution_replay_status": "CHECKED_BY_RUNNER_NOT_BY_THIS_PURE_FUNCTION",
        },
        "status": "CURRENT_PLAN_DESCRIPTIVE_COMPARISON" if plan_adapter else "NO_LINKED_PLAN",
        "plan_content_at_execution_status": executed.get("plan_content_at_execution_status"),
        "session_observations": {
            "start_time": executed.get("start_time"), "end_time": executed.get("end_time"),
            "reported_duration_s": executed.get("reported_duration_s"),
            "active_duration_s": executed.get("active_duration_s"),
            "wall_clock_duration_s": executed.get("wall_clock_duration_s"),
            "whole_session_metrics": copy.deepcopy(summary["metrics"]),
            "whole_session_executed_block_id": summary["executed_block_id"],
        },
        "session_comparison": {}, "occurrences": [], "unmatched_execution_blocks": [],
        "limitations": [
            "HISTORICAL_PLAN_CONTENT_UNVERIFIED", "ACTUAL_PHASE_ALIGNMENT_UNVERIFIED",
            "SOURCE_INTEGRITY_IS_NOT_SENSOR_ACCURACY",
            "CANDIDATE_TARGET_EQUALITY_IS_NOT_INDEPENDENT_COMPLETION_EVIDENCE",
            "WHOLE_SESSION_AND_PHASE_METRICS_OVERLAP_DO_NOT_SUM",
            "MEAN_HR_DOES_NOT_ESTABLISH_TIME_IN_TARGET",
            "SPEED_UNIT_USES_EXISTING_ADAPTER_ASSUMPTION",
            "NO_READINESS_FATIGUE_FITNESS_CAUSAL_OR_NEXT_WORKOUT_INFERENCE",
        ],
        "completion_status": "NOT_ASSESSED", "target_adherence_status": "NOT_ASSESSED",
        "actual_phase_alignment_verified": False, "historical_plan_content_verified": False,
        "training_authorized": False, "numeric_output_authorized": False,
        "capability_update_performed": False, "speed_model_retrained": False,
        "state_model_trained": False, "new_independent_test": False,
        "database_writes": 0, "network_calls": 0,
    }
    candidates = [b for b in executed["blocks"] if b is not summary]
    if not plan_adapter:
        comparison["unmatched_execution_blocks"] = copy.deepcopy(candidates)
        comparison["limitations"].append("NO_LINKED_PLAN_DOES_NOT_MEAN_NO_OR_FAILED_WORKOUT")
        validate_evidence(comparison)
        return comparison

    plan = plan_adapter["plan"]
    occurrences = plan_adapter.get("expanded_occurrences")
    definitions, structural_issues = expand_plan(plan, occurrences)
    occurrence_index = unique_index(occurrences, "planned_occurrence_id", "PLANNED_OCCURRENCE")
    assigned = {}
    for candidate in candidates:
        oid = candidate.get("planned_occurrence_id")
        if oid not in occurrence_index:
            comparison["unmatched_execution_blocks"].append(copy.deepcopy(candidate))
            continue
        require(oid not in assigned, "DUPLICATE_EXECUTED_OCCURRENCE_LINK")
        require(candidate.get("planned_block_id") == occurrence_index[oid]["block_id"],
                "EXECUTED_PLANNED_BLOCK_LINK_MISMATCH")
        assigned[oid] = candidate
    audits = read["adapter_result"].get("phase_audit", [])
    require(isinstance(audits, list), "PHASE_AUDIT_NOT_LIST")
    audit_index = unique_index(audits, "planned_occurrence_id", "PHASE_AUDIT")
    require(set(audit_index) <= set(occurrence_index), "PHASE_AUDIT_UNKNOWN_OCCURRENCE")
    for field, metric_name in (("duration_s", "DURATION"), ("distance_m", "DISTANCE")):
        total = planned_dimension(occurrences, field, structural_issues)
        comparison["session_comparison"][field] = dimensional_comparison(total, whole_metrics.get(metric_name))
    comparison["plan_title"] = plan.get("title")
    comparison["planned_date"] = plan.get("planned_date")
    comparison["session_type"] = plan.get("session_type")
    for sequence, occurrence in enumerate(occurrences):
        oid = occurrence["planned_occurrence_id"]
        definition = definitions[occurrence["block_id"]]
        candidate = assigned.get(oid)
        audit = audit_index.get(oid)
        if audit:
            require(audit.get("planned_block_id") == occurrence["block_id"], "AUDIT_PLANNED_BLOCK_MISMATCH")
            require(audit.get("actual_boundary_verified") is False and
                    audit.get("outcome_hr_used_for_boundary") is False, "AUDIT_BOUNDARY_OR_HR_FIT_UNSUPPORTED")
        if candidate:
            require(audit is not None, "CANDIDATE_WITHOUT_PHASE_AUDIT")
            require(audit.get("status") in {"SOURCE_GRID_PLAN_CANDIDATE", "SOURCE_GRID_PLAN_CANDIDATE_PARTIAL"},
                    "CANDIDATE_AUDIT_STATUS_MISMATCH")
            boundary = candidate["boundary"]
            require(audit.get("candidate_start_s") == boundary["start_offset_s"] and
                    audit.get("candidate_end_s") == boundary["end_offset_s"], "CANDIDATE_AUDIT_BOUNDARY_MISMATCH")
            partial = audit.get("partial_recording_phase") is True
            require(partial == (audit["status"] == "SOURCE_GRID_PLAN_CANDIDATE_PARTIAL"),
                    "PARTIAL_CANDIDATE_FLAG_MISMATCH")
        else:
            require(not audit or audit.get("status") not in {
                "SOURCE_GRID_PLAN_CANDIDATE", "SOURCE_GRID_PLAN_CANDIDATE_PARTIAL"
            }, "AUDIT_CANDIDATE_WITHOUT_EXECUTION_BLOCK")
            partial = None
        metrics = metric_index(candidate) if candidate else {}
        match_status = ("PARTIAL_PLAN_PHASE_CANDIDATE" if partial else "PLAN_PHASE_CANDIDATE"
                        if candidate else "UNASSIGNED")
        reason = (audit.get("status") if audit else
                  read["adapter_result"].get("native_grid_audit", {}).get("status", "NO_PHASE_EVIDENCE"))
        row = {
            "sequence_index": sequence, "planned_occurrence_id": oid,
            "planned_block_id": occurrence["block_id"],
            "occurrence_path": copy.deepcopy(occurrence["occurrence_path"]),
            "description": definition.get("description"),
            "block_type": definition.get("block_type"),
            "execution_role": definition.get("execution_role"),
            "completion_condition": occurrence["completion_condition"],
            "planned_intensity": copy.deepcopy(definition.get("intensity")),
            "source_intensity_indices_or_definition": _source_phase_field(plan_adapter, occurrence["block_id"], "intensity"),
            "source_goal_declaration": _source_phase_field(plan_adapter, occurrence["block_id"], "goal"),
            "source_change_type": _source_phase_field(plan_adapter, occurrence["block_id"], "changeType"),
            "matching_status": match_status, "matching_reason": reason,
            "executed_block_id": candidate.get("executed_block_id") if candidate else None,
            "candidate_boundary": copy.deepcopy(candidate.get("boundary")) if candidate else None,
            "candidate_metrics": copy.deepcopy(candidate["metrics"]) if candidate else [],
            "phase_audit": copy.deepcopy(audit), "partial_recording_phase": partial,
            "dimensions": {}, "completion_status": "NOT_ASSESSED",
            "intensity_assessment": {
                "status": "NOT_ASSESSED", "in_target_fraction": None,
                "reasons": ["CANDIDATE_BOUNDARIES_UNVERIFIED", "MEAN_IS_NOT_TIME_IN_TARGET"],
            },
        }
        intensity = definition.get("intensity", {})
        if intensity.get("type") == "UNKNOWN":
            row["intensity_assessment"]["reasons"].append("PHYSICAL_INTENSITY_TARGET_NOT_BOUND")
        if intensity.get("type") == "FREE":
            row["intensity_assessment"]["reasons"].append("NO_PRESCRIBED_INTENSITY_TARGET")
        for field, metric_name, condition in (("duration_s", "DURATION", "DURATION"),
                                               ("distance_m", "DISTANCE", "DISTANCE")):
            value = occurrence.get(field)
            target = {"value": value, "status": "TARGET_PRESENT" if value is not None else "NO_TARGET"}
            reasons = []
            if candidate and occurrence["completion_condition"] == condition:
                reasons.append("TARGET_USED_TO_CONSTRUCT_CANDIDATE_BOUNDARY")
            if candidate:
                reasons.append("ACTUAL_BOUNDARY_UNVERIFIED")
            else:
                reasons.append("NO_MATCHED_EXECUTION_EVIDENCE_NOT_PROOF_OF_SKIPPING")
            row["dimensions"][field] = dimensional_comparison(target, metrics.get(metric_name), reasons=reasons)
        comparison["occurrences"].append(row)
    comparison["limitations"].extend(structural_issues)
    comparison["counts"] = {
        "prescribed_occurrences": len(occurrences),
        "matched_candidate_occurrences": len(assigned),
        "unassigned_occurrences": len(occurrences) - len(assigned),
        "partial_candidate_occurrences": sum(r["partial_recording_phase"] is True for r in comparison["occurrences"]),
        "unmatched_execution_blocks": len(comparison["unmatched_execution_blocks"]),
    }
    validate_evidence(comparison)
    return comparison


def validate_evidence(value):
    """Local evidence invariant checker, NOT the shared JSON-schema validator."""
    require(value.get("artifact_type") == "PlanExecutionComparisonEvidence", "NOT_COMPARISON_EVIDENCE")
    require(value.get("rules_version") == RULES_VERSION, "EVIDENCE_RULES_VERSION_MISMATCH")
    require(value.get("contract_binding", {}).get("status") == "AUTHORITATIVE_CONTRACT_PROJECTION_PENDING",
            "CANONICAL_CONTRACT_CONFORMANCE_NOT_ESTABLISHED")
    require(value.get("completion_status") == "NOT_ASSESSED" and
            value.get("target_adherence_status") == "NOT_ASSESSED", "ADHERENCE_NOT_AUTHORIZED")
    require(str(value.get("provider_session_id")).lower() not in PROTECTED_EXTERNAL_IDS,
            "PROTECTED_EVIDENCE_FORBIDDEN")
    for flag in ("actual_phase_alignment_verified", "historical_plan_content_verified", "training_authorized",
                 "numeric_output_authorized", "capability_update_performed", "speed_model_retrained",
                 "state_model_trained", "new_independent_test"):
        require(value.get(flag) is False, "EVIDENCE_AUTHORIZATION_ESCALATION")
    for row in value.get("occurrences", []):
        require(row.get("completion_status") == "NOT_ASSESSED" and
                row.get("intensity_assessment", {}).get("status") == "NOT_ASSESSED" and
                row["intensity_assessment"].get("in_target_fraction") is None, "OCCURRENCE_ADHERENCE_NOT_AUTHORIZED")
        for dimension in row.get("dimensions", {}).values():
            require(dimension.get("observed_minus_planned") is None, "CANDIDATE_DELTA_NOT_INDEPENDENT")
    canonical(value)  # Also rejects NaN/infinite JSON output.
    return True
