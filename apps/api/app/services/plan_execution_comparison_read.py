"""Owner-scoped comparator reads; existing session/plan read logic is reused."""
from __future__ import annotations

import copy

from starlette.concurrency import run_in_threadpool

from app.planning_contracts.comparison_adapter import (
    METHOD_SHA256, METHOD_VERSION, SCHEMA_SHA256, to_contract_projection,
)
from app.planning_contracts.comparison_evidence import ComparisonError, PROTECTED_EXTERNAL_IDS
from app.planning_contracts.contract_checks import ContractError
from app.planning_contracts.execution_adapter import ExecutionAdapterError, canonical_bytes
from app.planning_contracts.legacy_plan_adapter import digest
from app.services.executed_workout_read import read_owned_execution

API_RULES_VERSION = "plan-execution-comparison-read-api-0.1"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
DESCRIPTIVE_FIELDS = (
    "rules_version", "status", "session_observations", "session_comparison", "occurrences",
    "unmatched_execution_blocks", "limitations", "counts", "completion_status", "target_adherence_status",
)


class ComparisonReadError(ValueError):
    def __init__(self, code, status_code=409, *, upstream_reason=None):
        super().__init__(code)
        self.code, self.status_code = code, status_code
        self.upstream_reason = upstream_reason


def protected(external_id):
    return str(external_id).lower() in PROTECTED_EXTERNAL_IDS


def build_comparison_read(execution_read, *, include_bundle=False, include_source=False):
    if type(include_bundle) is not bool or type(include_source) is not bool:
        raise ComparisonReadError("COMPARISON_INVALID_VIEW_FLAGS", 422)
    try:
        projection = to_contract_projection(execution_read)
    except ComparisonError as exc:
        code = str(exc)
        if code == "CANONICAL_COMPARISON_REQUIRES_LINKED_PLAN":
            raise ComparisonReadError("COMPARISON_NO_USABLE_OWNED_PLAN") from None
        if code == "PROTECTED_SESSION_NUMERIC_COMPARISON_FORBIDDEN":
            raise ComparisonReadError("COMPARISON_PROTECTED_SESSION_METADATA_ONLY") from None
        raise ComparisonReadError("COMPARISON_" + code) from None
    except ExecutionAdapterError as exc:
        raise ComparisonReadError("COMPARISON_EXECUTION_REPLAY_WITHHELD", exc.status_code, upstream_reason=exc.code) from None
    except (ContractError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ComparisonReadError("COMPARISON_SOURCE_OR_CONTRACT_WITHHELD") from None
    descriptive = projection["descriptive_evidence"]
    value = {
        "status": "PLAN_EXECUTION_COMPARISON_READ_WITH_LIMITATIONS",
        "api_rules_version": API_RULES_VERSION, "adapter_version": METHOD_VERSION,
        "schema_version": "0.1", "contract_release": "DRAFT1",
        "identity_scope": "APPLICATION_DEMO_USER",
        "source_scope": "CURRENT_OWNED_STORED_SESSION_AND_CURRENT_PLAN_CAPTURE",
        "session_id": projection["session_id"], "captured_at": execution_read["captured_at"],
        "capture_id": "comparison_read_" + digest({
            "comparison_id": projection["comparison"]["comparison_id"],
            "include_bundle": include_bundle, "include_source": include_source,
        }),
        "source_content_sha256": execution_read["source_content_sha256"],
        "plan_source_content_sha256": execution_read["plan_capture"]["source_content_sha256"],
        "source_execution_read_sha256": projection["source_execution_read_sha256"],
        "source_execution_capture_id": execution_read["capture_id"],
        "comparison_method_sha256": METHOD_SHA256, "contract_schema_sha256": SCHEMA_SHA256,
        "comparison": projection["comparison"],
        "descriptive_comparison": {key: copy.deepcopy(descriptive[key]) for key in DESCRIPTIVE_FIELDS if key in descriptive},
        "source_evidence_comparison_id": projection["source_evidence_comparison_id"],
        "include_bundle": include_bundle, "include_source": include_source,
        "integration_bundle": projection["integration_bundle"] if include_bundle else None,
        "source_execution_read": copy.deepcopy(execution_read) if include_source else None,
        "source_replay_material_included": include_source,
        "canonical_contract_projection_verified": True,
        "coverage_scope": "ALL_PRESCRIBED_OCCURRENCES_AND_OBSERVED_BLOCKS_HAVE_ROWS_NOT_VERIFIED_ALIGNMENT_OR_COMPLETION",
        "schema_checker_scope": "PINNED_SCHEMA_SUBSET_PLUS_DOMAIN_RULES_NOT_A_GENERAL_JSON_SCHEMA_ENGINE",
        "limitations": ["STATELESS_READ_NOT_PERSISTED_COMPARISON", "HISTORICAL_PLAN_CONTENT_UNVERIFIED",
            "ACTUAL_PHASE_ALIGNMENT_UNVERIFIED", "MEAN_HR_DOES_NOT_ESTABLISH_TIME_IN_TARGET",
            "TARGET_DERIVED_BOUNDARIES_NOT_INDEPENDENT_ADHERENCE_EVIDENCE",
            "WHOLE_SESSION_AND_PHASE_METRICS_OVERLAP_DO_NOT_SUM", "NO_CAPABILITY_OR_NEXT_WORKOUT_INFERENCE"],
        "historical_plan_content_verified": False, "actual_phase_alignment_verified": False,
        "numeric_output_authorized": False, "state_estimation_authorized": False,
        "training_authorized": False, "capability_update_performed": False,
        "database_writes": 0, "provider_calls": 0,
        "speed_model_retrained": False, "state_model_trained": False, "new_independent_test": False,
    }
    if len(canonical_bytes(value)) > MAX_RESPONSE_BYTES:
        raise ComparisonReadError("COMPARISON_RESPONSE_BYTE_LIMIT", 413)
    return value


def verify_comparison_read(value, *, execution_read=None):
    if not isinstance(value, dict):
        raise ComparisonReadError("COMPARISON_RESPONSE_NOT_OBJECT")
    source = execution_read if execution_read is not None else value.get("source_execution_read")
    if source is None:
        raise ComparisonReadError("COMPARISON_SOURCE_READ_REQUIRED_FOR_FULL_REPLAY")
    repeated = build_comparison_read(source, include_bundle=value.get("include_bundle"), include_source=value.get("include_source"))
    if value != repeated:
        raise ComparisonReadError("COMPARISON_FULL_SOURCE_REPLAY_DIFFERS")
    return True


async def read_owned_comparison(db, row, owner_id, *, captured_at=None, include_bundle=False, include_source=False):
    if str(row.user_id) != str(owner_id):
        raise ComparisonReadError("COMPARISON_SESSION_NOT_FOUND", 404)
    # Do not run the numerical execution adapter for a protected session.
    if protected(row.external_id):
        raise ComparisonReadError("COMPARISON_PROTECTED_SESSION_METADATA_ONLY")
    try:
        with db.no_autoflush:
            execution_read = await read_owned_execution(db, row, owner_id, captured_at=captured_at)
    except ExecutionAdapterError as exc:
        raise ComparisonReadError("COMPARISON_EXECUTION_SOURCE_WITHHELD", exc.status_code, upstream_reason=exc.code) from None
    return await run_in_threadpool(build_comparison_read, execution_read,
                                   include_bundle=include_bundle, include_source=include_source)
