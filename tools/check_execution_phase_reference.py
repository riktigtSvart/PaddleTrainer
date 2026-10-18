"""Rebuild the fixed stored-source reference offline; do not import a database."""
from collections import Counter
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import zipfile

REFERENCE_SHA = "04f3981f415bff03c580e4c5c110c6d30f850b0425ae0dcf63388f5571d25826"


def require(value, code):
    if not value:
        raise ValueError(code)


def check_reference(reference_root):
    from app.planning_contracts.execution_adapter import build_execution_read, verify_execution_read, ADAPTER_VERSION
    from app.services.plan_execution_comparison_read import build_comparison_read, verify_comparison_read
    from app.planning_contracts.comparison_evidence import PROTECTED_EXTERNAL_IDS, canonical
    from app.planning_contracts.contract_checks import validate_contract
    reference_root = Path(reference_root)
    path = reference_root / "comparator_coverage_reference.zip"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == REFERENCE_SHA, "SOURCE_REFERENCE_ZIP_HASH_DIFFERS")
    screen = json.loads((reference_root / "flow_reference.json").read_bytes())
    counts, old_reasons, new_reasons, clock_counts = Counter(), Counter(), Counter(), Counter()
    changes, flow = [], None
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None, "REFERENCE_ZIP_CRC_ERROR")
        files = json.loads(z.read("OUTPUT_MANIFEST.json"))["files"]
        require(set(z.namelist()) == set(files) | {"OUTPUT_MANIFEST.json"}, "REFERENCE_MANIFEST_COVERAGE_DIFFERS")
        for name, entry in files.items():
            raw = z.read(name)
            require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"],
                    "REFERENCE_MEMBER_HASH_DIFFERS:" + name)
        checkpoint = json.loads(z.read("checkpoint.json"))
        seen = set()
        for page_entry in checkpoint["primary"]:
            page = json.loads(gzip.decompress(z.read(page_entry["file"])))
            for item in page["items"]:
                sid = item["session_id"]
                require(sid not in seen, "REFERENCE_DUPLICATE_SESSION")
                seen.add(sid)
                counts["stored_session_count"] += 1
                if item["status"] == "WITHHELD":
                    counts["unchanged_withheld_metadata_count"] += 1
                    require(not item.get("source_execution_read"), "WITHHELD_REFERENCE_HAS_NUMERIC_SOURCE")
                    continue
                old = item["source_execution_read"]
                require(str(old["source_snapshot"]["external_id"]).lower() not in PROTECTED_EXTERNAL_IDS,
                        "PROTECTED_REFERENCE_NUMERICAL_REPLAY_FORBIDDEN")
                original = canonical(old)
                require(verify_execution_read(old), "LEGACY_EXECUTION_SOURCE_REPLAY_FAILED")
                require(verify_comparison_read(item), "LEGACY_COMPARATOR_SOURCE_REPLAY_FAILED")
                counts["legacy_full_execution_and_comparator_replays"] += 1
                fresh = build_execution_read(old["source_snapshot"], captured_at=old["captured_at"],
                    plan_read=old["plan_capture"], plan_selection=old["plan_selection"], source_mode=old["source_mode"])
                require(fresh["adapter_version"] == ADAPTER_VERSION and verify_execution_read(fresh), "NEW_EXECUTION_REPLAY_FAILED")
                require(fresh["source_snapshot"] == old["source_snapshot"] and
                        fresh["plan_capture"] == old["plan_capture"] and canonical(old) == original,
                        "SOURCE_OR_PREVIOUS_CAPTURE_MUTATED")
                projected = build_comparison_read(fresh, include_source=True, include_bundle=True)
                require(verify_comparison_read(projected), "NEW_COMPARISON_REPLAY_FAILED")
                validate_contract(projected["comparison"])
                validate_contract(projected["integration_bundle"])
                require(all(projected[flag] is False for flag in (
                    "actual_phase_alignment_verified", "historical_plan_content_verified", "numeric_output_authorized",
                    "training_authorized", "capability_update_performed", "speed_model_retrained", "state_model_trained")),
                    "UNEXPECTED_VERIFICATION_OR_MODEL_AUTHORIZATION")
                before = old["adapter_result"]["phase_audit"]
                after = fresh["adapter_result"]["phase_audit"]
                old_candidates = {b["planned_occurrence_id"] for b in old["adapter_result"]["executed"]["blocks"]
                                  if b["execution_role"] == "PLAN_PHASE_CANDIDATE"}
                new_blocks = [b for b in fresh["adapter_result"]["executed"]["blocks"]
                              if b["execution_role"] == "PLAN_PHASE_CANDIDATE"]
                new_candidates = {b["planned_occurrence_id"] for b in new_blocks}
                require(old_candidates <= new_candidates, "PREVIOUS_CANDIDATE_LOST")
                require(len(new_candidates) == len(new_blocks), "NEW_CANDIDATE_OCCURRENCE_DUPLICATE")
                counts["comparable_session_count"] += 1
                counts["planned_occurrence_count"] += len(projected["descriptive_comparison"]["occurrences"])
                counts["old_candidate_count"] += len(old_candidates)
                counts["new_candidate_count"] += len(new_candidates)
                counts["new_partial_candidate_count"] += sum(a.get("partial_recording_phase") is True for a in after)
                old_reasons.update(a["status"] for a in before)
                new_reasons.update(a["status"] for a in after)
                timebase = fresh["adapter_result"]["native_grid_audit"].get("phase_timebase", {})
                clock_counts[timebase.get("status", "NO_NATIVE_GRID")] += 1
                if new_candidates != old_candidates:
                    counts["sessions_with_new_candidates"] += 1
                    changes.append({"session_id": sid, "old_candidates": len(old_candidates),
                                    "new_candidates": len(new_candidates),
                                    "timebase_status": timebase.get("status")})
                if sid == screen["session_id"]:
                    require(len(new_blocks) == len(screen["phase_end_s"]) == 18, "FLOW_REFERENCE_PHASE_COUNT_DIFFERS")
                    deltas = [b["boundary"]["end_offset_s"] - expected
                              for b, expected in zip(new_blocks, screen["phase_end_s"])]
                    require(all(abs(delta) < screen["display_resolution_s"] for delta in deltas),
                            "FLOW_DISPLAY_BOUNDARY_DIFFERENCE_EXCEEDS_ONE_SECOND")
                    durations = [b["boundary"]["end_offset_s"] - b["boundary"]["start_offset_s"] for b in new_blocks]
                    require(all(math.isclose(a,b,abs_tol=1e-7) for a,b in zip(durations[1:17], [160,160,160,120]*4)),
                            "FLOW_REPEAT_DURATION_PATTERN_DIFFERS")
                    flow = {"session_id": sid, "phase_count": 18, "all_16_repeated_durations_match": True,
                            "selected_native_origin_s": timebase["selected_native_origin_s"],
                            "end_differences_from_display_s": deltas,
                            "subsecond_physical_accuracy_verified": False,
                            "user_supplied_display_reference_not_new_independent_model_test": True}
    require(counts["stored_session_count"] == 103 and counts["comparable_session_count"] == 86 and
            counts["unchanged_withheld_metadata_count"] == 17, "REFERENCE_COVERAGE_COUNTS_DIFFER")
    require(flow is not None, "FLOW_REFERENCE_SESSION_NOT_FOUND")
    require(counts["planned_occurrence_count"] == 400 and counts["old_candidate_count"] == 148,
            "BASELINE_PLAN_OR_CANDIDATE_COUNTS_DIFFER")
    require(counts["new_candidate_count"] == 292 and counts["sessions_with_new_candidates"] == 12 and
            counts["new_partial_candidate_count"] == 5, "FIXED_REFERENCE_CANDIDATE_COUNTS_DIFFER")
    require(new_reasons["MANUAL_OR_UNSUPPORTED_TRANSITION"] == old_reasons["MANUAL_OR_UNSUPPORTED_TRANSITION"] == 3 and
            new_reasons["UNASSIGNED_AFTER_MANUAL_OR_UNSUPPORTED_TRANSITION"] ==
            old_reasons["UNASSIGNED_AFTER_MANUAL_OR_UNSUPPORTED_TRANSITION"] == 21,
            "GENUINE_MANUAL_PHASE_BLOCKER_CHANGED")
    return {"status": "EXECUTION_PHASE_FIX_OFFLINE_REFERENCE_REPLAY_PASSED", **dict(counts),
            "old_phase_status_counts": dict(old_reasons), "new_phase_status_counts": dict(new_reasons),
            "new_timebase_status_counts": dict(clock_counts), "changed_sessions": changes, "flow_reference": flow,
            "source_hashes_and_captures_unchanged": True, "offline_replay_is_live_database_read": False,
            "database_writes": 0, "authenticated_polar_requests": 0,
            "speed_model_retrained": False, "new_independent_model_test": False}
