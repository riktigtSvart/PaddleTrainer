from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..common.enums import DecisionRelevance
from ..common.serialization import CONTENT_HASH_ALGORITHM, compute_content_hash
from ..common.time import to_utc


RATIONALE_HASH_EXCLUDE_FIELDS = frozenset(
    {"content_hash", "rationale_id", "created_at"}
)


class AlternativeDisposition(StrEnum):
    EXCLUDED_DURING_GENERATION = "excluded_during_generation"
    ELIMINATED_BY_POLICY = "eliminated_by_policy"
    VIABLE_NOT_SELECTED = "viable_not_selected"
    PREFERRED_NOT_SELECTED = "preferred_not_selected"
    REQUIRED_NOT_SELECTED = "required_not_selected"


@dataclass(frozen=True)
class RationaleUnknown:
    domain: str
    question: str
    decision_relevance: DecisionRelevance
    fallback_policy: str | None


@dataclass(frozen=True)
class AlternativeRationale:
    action_id: str | None
    target_ref: str | None
    disposition: AlternativeDisposition
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class DecisionRationale:
    rationale_id: str
    decision_hash: str
    context_hash: str
    selected_action_id: str | None
    decision_status: str

    primary_reason_codes: tuple[str, ...]
    binding_constraint_codes: tuple[str, ...]
    supporting_policy_refs: tuple[str, ...]
    alternatives: tuple[AlternativeRationale, ...]
    critical_unknowns: tuple[RationaleUnknown, ...]
    unresolved_dimensions: tuple[str, ...]
    accepted_tradeoffs: tuple[str, ...]
    review_triggers: tuple[str, ...]

    rationale_version: str
    created_at: datetime
    content_hash_algorithm: str
    content_hash: str

    def verify_content_hash(self) -> bool:
        return (
            compute_content_hash(
                self,
                exclude_fields=RATIONALE_HASH_EXCLUDE_FIELDS,
            )
            == self.content_hash
        )


def finalize_decision_rationale(
    *,
    rationale_id: str,
    decision_hash: str,
    context_hash: str,
    selected_action_id: str | None,
    decision_status: str,
    primary_reason_codes: tuple[str, ...],
    binding_constraint_codes: tuple[str, ...],
    supporting_policy_refs: tuple[str, ...],
    alternatives: tuple[AlternativeRationale, ...],
    critical_unknowns: tuple[RationaleUnknown, ...],
    unresolved_dimensions: tuple[str, ...],
    accepted_tradeoffs: tuple[str, ...],
    review_triggers: tuple[str, ...],
    rationale_version: str,
    created_at: datetime,
) -> DecisionRationale:
    if not rationale_id.strip():
        raise ValueError("rationale_id must be non-empty.")
    if not decision_hash.strip():
        raise ValueError("decision_hash must be non-empty.")
    if not context_hash.strip():
        raise ValueError("context_hash must be non-empty.")
    if not rationale_version.strip():
        raise ValueError("rationale_version must be non-empty.")

    created = to_utc(created_at, field_name="created_at")

    provisional = DecisionRationale(
        rationale_id=rationale_id,
        decision_hash=decision_hash,
        context_hash=context_hash,
        selected_action_id=selected_action_id,
        decision_status=decision_status,
        primary_reason_codes=tuple(dict.fromkeys(primary_reason_codes)),
        binding_constraint_codes=tuple(
            dict.fromkeys(binding_constraint_codes)
        ),
        supporting_policy_refs=tuple(
            sorted(set(supporting_policy_refs))
        ),
        alternatives=tuple(alternatives),
        critical_unknowns=tuple(critical_unknowns),
        unresolved_dimensions=tuple(unresolved_dimensions),
        accepted_tradeoffs=tuple(dict.fromkeys(accepted_tradeoffs)),
        review_triggers=tuple(dict.fromkeys(review_triggers)),
        rationale_version=rationale_version,
        created_at=created,
        content_hash_algorithm=CONTENT_HASH_ALGORITHM,
        content_hash="",
    )
    digest = compute_content_hash(
        provisional,
        exclude_fields=RATIONALE_HASH_EXCLUDE_FIELDS,
    )
    return DecisionRationale(
        rationale_id=provisional.rationale_id,
        decision_hash=provisional.decision_hash,
        context_hash=provisional.context_hash,
        selected_action_id=provisional.selected_action_id,
        decision_status=provisional.decision_status,
        primary_reason_codes=provisional.primary_reason_codes,
        binding_constraint_codes=provisional.binding_constraint_codes,
        supporting_policy_refs=provisional.supporting_policy_refs,
        alternatives=provisional.alternatives,
        critical_unknowns=provisional.critical_unknowns,
        unresolved_dimensions=provisional.unresolved_dimensions,
        accepted_tradeoffs=provisional.accepted_tradeoffs,
        review_triggers=provisional.review_triggers,
        rationale_version=provisional.rationale_version,
        created_at=provisional.created_at,
        content_hash_algorithm=provisional.content_hash_algorithm,
        content_hash=digest,
    )
