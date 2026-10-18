"""Project comparison evidence into the exact installed v0.1 wire contracts.

Uses the application's unchanged planning schemas and domain validators.
Coverage COMPLETE means every prescribed occurrence and observed block has a
row. It does not mean verified alignment, adherence, or completed prescription.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from .comparison_evidence import (compare_execution_read, canonical, sha256, require,
                                 PROTECTED_EXTERNAL_IDS)
from .execution_adapter import verify_execution_read
from .contract_checks import validate_contract, validate_bundle

METHOD_VERSION = "plan-execution-comparison-contract-0.1-api1"
METHOD_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SCHEMA_SHA256 = hashlib.sha256((Path(__file__).parent / "schemas/integration-contracts.schema.json").read_bytes()).hexdigest()


def merge_evidence(*collections):
    values = {}
    for collection in collections:
        for evidence in collection:
            eid = evidence["evidence_id"]
            require(eid not in values or values[eid] == evidence, "CONFLICTING_SHARED_EVIDENCE_ID")
            values[eid] = copy.deepcopy(evidence)
    return [values[key] for key in sorted(values)]


def reason(code, message):
    return {"code": code, "severity": "BLOCKING", "message": message}


def not_evaluable(metric_type, refs, *, circular=False, intensity=False, unbound=False):
    reasons = [reason("ACTUAL_PHASE_ALIGNMENT_UNVERIFIED",
                      "Candidate or absent boundaries do not establish actual prescribed-phase alignment."),
               reason("HISTORICAL_PLAN_CONTENT_UNVERIFIED",
                      "The captured plan is not proven to be the effective prescription at execution time.")]
    if circular:
        reasons.append(reason("TARGET_USED_TO_CONSTRUCT_CANDIDATE_BOUNDARY",
                              "Equality with a target used to create the boundary is not independent adherence evidence."))
    if intensity:
        reasons.append(reason("TIME_IN_TARGET_NOT_ESTABLISHED", "A phase mean cannot establish time inside, below, or above a target."))
    if unbound:
        reasons.append(reason("PHYSICAL_INTENSITY_OR_ZONE_DEFINITION_NOT_BOUND",
                              "Source zone numbers are retained without inventing physical bpm or speed bounds."))
    return {"metric_type": metric_type, "status": "NOT_EVALUABLE",
            "inside_s": None, "below_s": None, "above_s": None, "unknown_s": None,
            "observed_s": None, "endpoint_policy": "UNKNOWN",
            "reasons": reasons, "evidence_refs": sorted(set(refs))}


def to_contract_projection(read):
    # Enforce the protected-session guard before a pure numerical replay.
    for value in (read.get("source_snapshot", {}).get("external_id"),
                  read.get("adapter_result", {}).get("executed", {}).get("provider_session_id")):
        require(str(value).lower() not in PROTECTED_EXTERNAL_IDS, "PROTECTED_SESSION_NUMERIC_COMPARISON_FORBIDDEN")
    evidence_result = compare_execution_read(read)
    require(read.get("plan_capture") is not None, "CANONICAL_COMPARISON_REQUIRES_LINKED_PLAN")
    # Hashes alone cannot authenticate the raw-to-contract transformation.
    # Replay the exact returned application method before using the projection.
    before = sha256(read)
    require(verify_execution_read(read) is not False, "EXACT_EXECUTION_REPLAY_RETURNED_FALSE")
    require(sha256(read) == before, "EXACT_EXECUTION_REPLAY_MUTATED_CAPTURE")
    executed = read["adapter_result"]["executed"]
    plan = read["plan_capture"]["adapter_result"]["plan"]
    decisions = copy.deepcopy(read["plan_capture"].get("applicability_decisions", []))
    registry = merge_evidence(plan["evidence"], executed["evidence"],
                              *(decision["evidence"] for decision in decisions))
    known_evidence = {item["evidence_id"] for item in registry}
    plan_refs = [item["evidence_id"] for item in plan["evidence"]]
    rows = []
    consumed = set()
    for item in evidence_result["occurrences"]:
        block_id = item["executed_block_id"]
        refs = set(plan_refs)
        if item["candidate_boundary"]:
            refs.update(item["candidate_boundary"]["evidence_refs"])
        for metric in item["candidate_metrics"]:
            refs.update(metric["evidence_refs"])
        require(refs <= known_evidence, "UNRESOLVED_COMPARISON_EVIDENCE_REFERENCE")
        adherences = []
        condition = item["completion_condition"]
        if condition in {"DISTANCE", "DURATION"}:
            adherences.append(not_evaluable(condition, refs, circular=block_id is not None))
        declared_type = (item.get("planned_intensity") or {}).get("type")
        original_type = (item.get("source_intensity_indices_or_definition") or {}).get("type")
        # HR_ZONE is an explicitly declared source target, not a conversion to
        # HR_BPM. Unsupported physical targets remain in the evidence sidecar.
        intensity_type = declared_type if declared_type in {"HR_BPM", "HR_ZONE", "POWER_W", "SPEED_MPS"} else (
            "HR_ZONE" if original_type == "HEART_RATE_ZONES" else None)
        if intensity_type:
            adherences.append(not_evaluable(intensity_type, refs, intensity=True, unbound=declared_type == "UNKNOWN"))
        row_decisions = [d["decision_id"] for d in decisions
                         if d["subject"].get("planned_occurrence_id") == item["planned_occurrence_id"]]
        rows.append({
            "planned_occurrence_id": item["planned_occurrence_id"],
            "executed_block_ids": [block_id] if block_id else [],
            "alignment_status": "MATCHED_CANDIDATE" if block_id else "UNRESOLVED",
            "target_adherence": adherences,
            "applicability_decision_ids": sorted(row_decisions), "evidence_refs": sorted(refs),
        })
        if block_id:
            require(block_id not in consumed, "EXECUTED_BLOCK_USED_IN_MULTIPLE_ROWS")
            consumed.add(block_id)
    # Whole-session summary and any remaining observations have their own rows.
    # They are not silently summed with or classified as unplanned phases.
    for block in executed["blocks"]:
        bid = block["executed_block_id"]
        if bid in consumed:
            continue
        refs = set(block["boundary"]["evidence_refs"])
        for metric in block["metrics"]:
            refs.update(metric["evidence_refs"])
        require(refs <= known_evidence, "UNRESOLVED_UNMATCHED_BLOCK_EVIDENCE_REFERENCE")
        rows.append({"planned_occurrence_id": None, "executed_block_ids": [bid],
                     "alignment_status": "UNRESOLVED", "target_adherence": [],
                     "applicability_decision_ids": [], "evidence_refs": sorted(refs)})
        consumed.add(bid)
    identity = {"method": METHOD_VERSION, "method_sha256": METHOD_SHA256,
                "schema_sha256": SCHEMA_SHA256, "input_execution_read_sha256": before}
    comparison = {
        "contract_type": "PlanExecutionComparison", "schema_version": "0.1",
        "comparison_id": "comparison_" + sha256(identity),
        "athlete_id": executed["athlete_id"], "plan_ref": copy.deepcopy(executed["plan_ref"]),
        "execution_ref": {"executed_workout_id": executed["executed_workout_id"],
                          "execution_revision": executed["execution_revision"]},
        "comparison_method_version": METHOD_VERSION, "coverage": "COMPLETE",
        "rows": rows, "evidence": registry,
    }
    bundle = {"contract_type": "IntegrationBundle", "schema_version": "0.1",
              "plan": copy.deepcopy(plan), "executed": copy.deepcopy(executed),
              "feedback": [], "comparison": comparison, "applicability_decisions": decisions}
    validate_contract(comparison)
    validate_contract(bundle)
    validate_projection_semantics(comparison, executed, evidence_result)
    return {"session_id": read["session_id"], "comparison": comparison, "integration_bundle": bundle,
            "descriptive_evidence": evidence_result,
            "source_execution_read_sha256": before,
            "source_evidence_comparison_id": evidence_result["comparison_id"],
            "comparison_method_sha256": METHOD_SHA256, "schema_sha256": SCHEMA_SHA256,
            "schema_and_domain_validation_verified": True,
            "actual_phase_alignment_verified": False, "historical_plan_content_verified": False,
            "numeric_output_authorized": False, "capability_update_performed": False,
            "training_authorized": False, "state_estimation_authorized": False,
            "database_writes": 0, "network_calls": 0, "speed_model_retrained": False,
            "state_model_trained": False, "new_independent_test": False}


def validate_projection_semantics(comparison, executed, evidence):
    """Additional mapping guards beyond the unchanged shared validator."""
    rows = comparison["rows"]
    expected_occurrences = {r["planned_occurrence_id"]: r for r in evidence["occurrences"]}
    planned_rows = [r for r in rows if r["planned_occurrence_id"] is not None]
    require(len(planned_rows) == len(expected_occurrences), "CANONICAL_PLANNED_ROWS_NOT_ONE_PER_OCCURRENCE")
    require({r["planned_occurrence_id"] for r in planned_rows} == set(expected_occurrences), "CANONICAL_PLAN_COVERAGE_DIFFERS")
    observed = [bid for row in rows for bid in row["executed_block_ids"]]
    require(len(observed) == len(set(observed)) and set(observed) == {
        b["executed_block_id"] for b in executed["blocks"]}, "CANONICAL_EXECUTION_COVERAGE_OR_DUPLICATION")
    for row in planned_rows:
        source = expected_occurrences[row["planned_occurrence_id"]]
        expected_ids = [source["executed_block_id"]] if source["executed_block_id"] else []
        require(row["executed_block_ids"] == expected_ids, "CANONICAL_OCCURRENCE_LINK_DIFFERS")
        require(row["alignment_status"] == ("MATCHED_CANDIDATE" if expected_ids else "UNRESOLVED"),
                "CANONICAL_ALIGNMENT_PROMOTION")
    for row in rows:
        require(row["alignment_status"] in {"MATCHED_CANDIDATE", "UNRESOLVED"}, "UNAUTHORIZED_ALIGNMENT_CLASSIFICATION")
        for assessment in row["target_adherence"]:
            require(assessment["status"] == "NOT_EVALUABLE" and all(assessment[key] is None for key in [
                "inside_s", "below_s", "above_s", "unknown_s", "observed_s"]), "UNAUTHORIZED_ADHERENCE_CLASSIFICATION")
    return True
