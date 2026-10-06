from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "0.1"
CATALOG_TYPE = "AUTHORITATIVE_HYDROLOGY_RELATION_CATALOG"


def build_hydrology_relation_catalog(
    *,
    provider: str,
    product: str,
    relations: Sequence[Mapping[str, Any]],
    source_documents: Sequence[Mapping[str, Any]] | None = None,
    source_mode: str = "CURATED_OFFICIAL_DOCUMENTS",
    jurisdiction: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a provider-independent hydrology relation catalog.

    The catalog stores relation evidence and provenance; it does not itself
    decide whether measurements are transferable.  V23 relation evaluation and
    V23.1 metric-aware trust projection remain the decision layers.
    """
    provider_value = _required_text(provider, "provider")
    product_value = _required_text(product, "product")
    source_mode_value = _required_text(source_mode, "source_mode")

    normalized_relations: list[dict[str, Any]] = []
    relation_ids: set[str] = set()

    for position, relation in enumerate(relations):
        if not isinstance(relation, Mapping):
            raise ValueError(f"relation at position {position} must be a mapping")

        relation_copy = deepcopy(dict(relation))
        relation_id = _required_text(
            relation_copy.get("relation_id"),
            f"relations[{position}].relation_id",
        )
        if relation_id in relation_ids:
            raise ValueError(f"duplicate hydrology relation_id: {relation_id}")
        relation_ids.add(relation_id)

        _required_text(
            relation_copy.get("relation_type"),
            f"relations[{position}].relation_type",
        )

        target = relation_copy.get("target")
        if not isinstance(target, Mapping):
            raise ValueError(f"relations[{position}].target must be a mapping")
        if not (
            _nonempty_sequence(target.get("waterbody_ids"))
            or _nonempty_sequence(target.get("waterbody_names"))
        ):
            raise ValueError(
                f"relations[{position}].target must select waterbody ids or names"
            )

        source = relation_copy.get("source")
        if not isinstance(source, Mapping):
            raise ValueError(f"relations[{position}].source must be a mapping")
        if not (
            _nonempty_sequence(source.get("station_registry_numbers"))
            or _nonempty_sequence(source.get("watercourse_names"))
        ):
            raise ValueError(
                f"relations[{position}].source must select station ids or watercourses"
            )

        metrics = relation_copy.get("metrics")
        if not isinstance(metrics, Sequence) or isinstance(
            metrics, (str, bytes, bytearray)
        ):
            raise ValueError(f"relations[{position}].metrics must be a sequence")
        if not metrics:
            raise ValueError(f"relations[{position}].metrics must not be empty")

        metric_keys: set[str] = set()
        for metric_position, metric in enumerate(metrics):
            if not isinstance(metric, Mapping):
                raise ValueError(
                    f"relations[{position}].metrics[{metric_position}] must be a mapping"
                )
            metric_key = _required_text(
                metric.get("metric_key"),
                f"relations[{position}].metrics[{metric_position}].metric_key",
            )
            if metric_key in metric_keys:
                raise ValueError(
                    f"duplicate metric_key {metric_key} in relation {relation_id}"
                )
            metric_keys.add(metric_key)
            if not isinstance(metric.get("transfer_allowed"), bool):
                raise ValueError(
                    f"relations[{position}].metrics[{metric_position}]."
                    "transfer_allowed must be boolean"
                )

        normalized_relations.append(relation_copy)

    documents: list[dict[str, Any]] = []
    for position, document in enumerate(source_documents or []):
        if not isinstance(document, Mapping):
            raise ValueError(f"source_documents[{position}] must be a mapping")
        document_copy = deepcopy(dict(document))
        _required_text(
            document_copy.get("document_id"),
            f"source_documents[{position}].document_id",
        )
        _required_text(
            document_copy.get("provider"),
            f"source_documents[{position}].provider",
        )
        _required_text(
            document_copy.get("reference"),
            f"source_documents[{position}].reference",
        )
        documents.append(document_copy)

    return {
        "provider": provider_value,
        "product": product_value,
        "schema_version": SCHEMA_VERSION,
        "catalog_type": CATALOG_TYPE,
        "source_mode": source_mode_value,
        "jurisdiction": _text(jurisdiction),
        "relation_count": len(normalized_relations),
        "source_document_count": len(documents),
        "source_documents": documents,
        "metadata": deepcopy(dict(metadata or {})),
        "scope": {
            "provider_independent_relation_contract": True,
            "contains_authoritative_relation_evidence": True,
            "measurement_transfer_decided_by_catalog": False,
            "requires_v23_relation_evaluation": True,
            "requires_v23_1_metric_trust_projection": True,
            "nearest_station_is_not_relation_evidence": True,
            "topological_connection_alone_is_not_transfer_evidence": True,
            "water_level_transfer_does_not_imply_discharge_transfer": True,
            "estimates_local_current_velocity": False,
            "raw_data_mutated": False,
        },
        "relations": normalized_relations,
    }


def build_hydrology_relation_catalog_summary(
    catalog: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(catalog, Mapping):
        return None
    result = deepcopy(dict(catalog))
    result["relations"] = []
    result["relations_included"] = False
    return result


def _required_text(value: Any, field: str) -> str:
    text = _text(value)
    if text is None:
        raise ValueError(f"{field} must be a non-empty string")
    return text


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nonempty_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and len(value) > 0
    )
