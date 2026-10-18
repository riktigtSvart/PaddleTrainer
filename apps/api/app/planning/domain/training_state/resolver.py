from collections import defaultdict
from datetime import datetime

from ..common.enums import KnowledgeStatus
from ..evidence.models import EvidenceBundle, EvidenceItem
from .evidence import evidence_domain, training_exposure_from_evidence
from .models import (
    CurrentTrainingState,
    DomainCoverageDeclaration,
    EvidenceCoverage,
    EvidenceDomain,
    EvidenceDomainSummary,
    LoadAnchorState,
    LoadAnchorStatus,
    ModalityExposureSummary,
    ObservationWindow,
    TrainingExposureObservation,
    TrainingExposureWindowSummary,
    finalize_current_training_state,
)


def _coverage_map(
    declarations: tuple[DomainCoverageDeclaration, ...],
) -> dict[EvidenceDomain, EvidenceCoverage]:
    result: dict[EvidenceDomain, EvidenceCoverage] = {}
    for declaration in declarations:
        if declaration.domain in result:
            raise ValueError(
                f"Duplicate coverage declaration for {declaration.domain.value}."
            )
        result[declaration.domain] = declaration.coverage
    return result


def _summarize_exposure(
    observations: tuple[TrainingExposureObservation, ...],
    *,
    window: ObservationWindow,
    source_coverage: EvidenceCoverage,
) -> TrainingExposureWindowSummary:
    selected = tuple(
        sorted(
            (
                observation
                for observation in observations
                if window.start_at <= observation.observed_at <= window.end_at
            ),
            key=lambda observation: (
                observation.observed_at,
                observation.evidence_id,
            ),
        )
    )

    known = tuple(
        observation
        for observation in selected
        if observation.duration_status == KnowledgeStatus.KNOWN
    )
    observed_known_duration_s = sum(
        observation.duration_s or 0
        for observation in known
    )

    complete_total: int | None = None
    if (
        source_coverage == EvidenceCoverage.COMPLETE
        and len(known) == len(selected)
    ):
        complete_total = observed_known_duration_s

    by_modality: dict[str, list[TrainingExposureObservation]] = defaultdict(list)
    for observation in selected:
        by_modality[observation.modality_key].append(observation)

    modality_summaries = []
    for modality_key in sorted(by_modality):
        modality_items = tuple(by_modality[modality_key])
        modality_known = tuple(
            item
            for item in modality_items
            if item.duration_status == KnowledgeStatus.KNOWN
        )
        modality_summaries.append(
            ModalityExposureSummary(
                modality_key=modality_key,
                observed_session_count=len(modality_items),
                known_duration_session_count=len(modality_known),
                observed_known_duration_s=sum(
                    item.duration_s or 0
                    for item in modality_known
                ),
                source_evidence_ids=tuple(
                    item.evidence_id for item in modality_items
                ),
            )
        )

    dates = {item.observed_at.date() for item in selected}

    return TrainingExposureWindowSummary(
        window=window,
        source_coverage=source_coverage,
        observed_session_count=len(selected),
        known_duration_session_count=len(known),
        observed_known_duration_s=observed_known_duration_s,
        complete_window_total_duration_s=complete_total,
        active_days_observed=len(dates),
        first_training_observed_at=(
            selected[0].observed_at if selected else None
        ),
        last_training_observed_at=(
            selected[-1].observed_at if selected else None
        ),
        modality_summaries=tuple(modality_summaries),
        source_evidence_ids=tuple(
            item.evidence_id for item in selected
        ),
    )


def _load_anchor_status(
    exposure: TrainingExposureWindowSummary,
) -> LoadAnchorStatus:
    if exposure.source_coverage == EvidenceCoverage.COMPLETE:
        if exposure.observed_session_count == 0:
            return LoadAnchorStatus.VERIFIED_ZERO_EXPOSURE
        if (
            exposure.known_duration_session_count
            == exposure.observed_session_count
        ):
            return LoadAnchorStatus.VERIFIED_EXPOSURE
        return LoadAnchorStatus.PARTIAL_EXPOSURE

    if exposure.observed_session_count > 0:
        return LoadAnchorStatus.PARTIAL_EXPOSURE

    return LoadAnchorStatus.UNKNOWN


def _domain_summaries(
    items: tuple[EvidenceItem, ...],
    *,
    cutoff: datetime,
    coverage: dict[EvidenceDomain, EvidenceCoverage],
) -> tuple[EvidenceDomainSummary, ...]:
    grouped: dict[EvidenceDomain, list[EvidenceItem]] = defaultdict(list)

    for item in items:
        domain = evidence_domain(item)
        if domain is not None:
            grouped[domain].append(item)

    summaries = []
    for domain in EvidenceDomain:
        domain_items = tuple(
            sorted(
                grouped.get(domain, ()),
                key=lambda item: (
                    item.observed_at,
                    item.available_at,
                    item.evidence_id,
                ),
            )
        )
        latest_observed = (
            domain_items[-1].observed_at if domain_items else None
        )
        latest_available = (
            max(item.available_at for item in domain_items)
            if domain_items
            else None
        )
        age_s = (
            int((cutoff - latest_observed).total_seconds())
            if latest_observed is not None
            else None
        )

        summaries.append(
            EvidenceDomainSummary(
                domain=domain,
                source_coverage=coverage.get(
                    domain,
                    EvidenceCoverage.UNKNOWN,
                ),
                observed_item_count=len(domain_items),
                first_observed_at=(
                    domain_items[0].observed_at
                    if domain_items
                    else None
                ),
                latest_observed_at=latest_observed,
                latest_available_at=latest_available,
                age_s_at_cutoff=age_s,
                source_evidence_ids=tuple(
                    item.evidence_id for item in domain_items
                ),
            )
        )

    return tuple(summaries)


def build_current_training_state(
    *,
    bundle: EvidenceBundle,
    state_id: str,
    schema_version: str,
    created_at: datetime,
    recent_window: ObservationWindow,
    load_anchor_window: ObservationWindow,
    recent_training_coverage: EvidenceCoverage,
    load_anchor_training_coverage: EvidenceCoverage,
    domain_coverage: tuple[DomainCoverageDeclaration, ...] = (),
) -> CurrentTrainingState:
    """Build descriptive state from cutoff-safe evidence.

    This resolver intentionally does not produce readiness/entry-gate
    decisions. It also does not infer missing training as zero unless source
    coverage is explicitly COMPLETE.
    """
    if not bundle.verify_content_hash():
        raise ValueError("EvidenceBundle hash does not verify.")

    cutoff = bundle.information_cutoff_at

    if recent_window.end_at > cutoff:
        raise ValueError(
            "recent_window must not extend past evidence cutoff."
        )
    if load_anchor_window.end_at > cutoff:
        raise ValueError(
            "load_anchor_window must not extend past evidence cutoff."
        )

    training_observations = tuple(
        observation
        for item in bundle.items
        if (observation := training_exposure_from_evidence(item))
        is not None
    )

    recent_exposure = _summarize_exposure(
        training_observations,
        window=recent_window,
        source_coverage=recent_training_coverage,
    )
    anchor_exposure = _summarize_exposure(
        training_observations,
        window=load_anchor_window,
        source_coverage=load_anchor_training_coverage,
    )

    load_anchor = LoadAnchorState(
        status=_load_anchor_status(anchor_exposure),
        exposure=anchor_exposure,
        prescription_target=False,
    )

    coverage = _coverage_map(domain_coverage)
    coverage[EvidenceDomain.TRAINING_EXPOSURE] = recent_training_coverage

    return finalize_current_training_state(
        state_id=state_id,
        athlete_id=bundle.athlete_id,
        schema_version=schema_version,
        as_of=bundle.as_of,
        information_cutoff_at=cutoff,
        created_at=created_at,
        recent_exposure=recent_exposure,
        load_anchor=load_anchor,
        evidence_domains=_domain_summaries(
            bundle.items,
            cutoff=cutoff,
            coverage=coverage,
        ),
        source_evidence_bundle_hash=bundle.content_hash,
    )
