from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc


RUN_RECORD_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "run_id", "created_at"}
)


class ReplayMode(StrEnum):
    DETERMINISTIC_EXACT = "deterministic_exact"
    AUDIT_ONLY = "audit_only"


@dataclass(frozen=True)
class PlannerRunRecord:
    run_id: str
    context_hash: str
    envelope_hash: str
    candidate_set_hash: str
    policy_set_hash: str
    policy_execution_hash: str
    decision_hash: str
    rationale_hash: str

    engine_version: str
    policy_set_version: str
    candidate_generation_version: str
    rationale_version: str
    replay_mode: ReplayMode

    decision_time: datetime
    created_at: datetime

    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=RUN_RECORD_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


@dataclass(frozen=True)
class ReplayVerification:
    context_match: bool
    envelope_match: bool
    candidate_set_match: bool
    policy_set_match: bool
    policy_execution_match: bool
    decision_match: bool
    rationale_match: bool
    exact_replay_verified: bool


def finalize_planner_run_record(
    *,
    run_id: str,
    context_hash: str,
    envelope_hash: str,
    candidate_set_hash: str,
    policy_set_hash: str,
    policy_execution_hash: str,
    decision_hash: str,
    rationale_hash: str,
    engine_version: str,
    policy_set_version: str,
    candidate_generation_version: str,
    rationale_version: str,
    replay_mode: ReplayMode,
    decision_time: datetime,
    created_at: datetime,
) -> PlannerRunRecord:
    for field_name, value in (
        ("run_id", run_id),
        ("context_hash", context_hash),
        ("envelope_hash", envelope_hash),
        ("candidate_set_hash", candidate_set_hash),
        ("policy_set_hash", policy_set_hash),
        ("policy_execution_hash", policy_execution_hash),
        ("decision_hash", decision_hash),
        ("rationale_hash", rationale_hash),
        ("engine_version", engine_version),
        ("policy_set_version", policy_set_version),
        ("candidate_generation_version", candidate_generation_version),
        ("rationale_version", rationale_version),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} must be non-empty.")

    decision_time_utc = to_utc(
        decision_time,
        field_name="decision_time",
    )
    created_at_utc = to_utc(created_at, field_name="created_at")
    if created_at_utc < decision_time_utc:
        raise ValueError("created_at must not precede decision_time.")

    provisional = PlannerRunRecord(
        run_id=run_id,
        context_hash=context_hash,
        envelope_hash=envelope_hash,
        candidate_set_hash=candidate_set_hash,
        policy_set_hash=policy_set_hash,
        policy_execution_hash=policy_execution_hash,
        decision_hash=decision_hash,
        rationale_hash=rationale_hash,
        engine_version=engine_version,
        policy_set_version=policy_set_version,
        candidate_generation_version=candidate_generation_version,
        rationale_version=rationale_version,
        replay_mode=replay_mode,
        decision_time=decision_time_utc,
        created_at=created_at_utc,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=RUN_RECORD_HASH_EXCLUDE_FIELDS,
    )
    return PlannerRunRecord(
        run_id=provisional.run_id,
        context_hash=provisional.context_hash,
        envelope_hash=provisional.envelope_hash,
        candidate_set_hash=provisional.candidate_set_hash,
        policy_set_hash=provisional.policy_set_hash,
        policy_execution_hash=provisional.policy_execution_hash,
        decision_hash=provisional.decision_hash,
        rationale_hash=provisional.rationale_hash,
        engine_version=provisional.engine_version,
        policy_set_version=provisional.policy_set_version,
        candidate_generation_version=provisional.candidate_generation_version,
        rationale_version=provisional.rationale_version,
        replay_mode=provisional.replay_mode,
        decision_time=provisional.decision_time,
        created_at=provisional.created_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
