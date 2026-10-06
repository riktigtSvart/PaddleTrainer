from copy import deepcopy

import pytest

from app.services.hydrology_relation_catalog import (
    CATALOG_TYPE,
    build_hydrology_relation_catalog,
    build_hydrology_relation_catalog_summary,
)


def _relation():
    return {
        "relation_id": "rel-1",
        "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
        "target": {"waterbody_names": ["Branch A"]},
        "source": {"station_registry_numbers": [1001]},
        "authority": {"provider": "AUTH", "reference": "DOC-1"},
        "metrics": [
            {
                "metric_key": "WATER_LEVEL",
                "transfer_allowed": True,
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
            }
        ],
    }


def test_catalog_contract_is_provider_independent_and_preserves_evidence():
    relation = _relation()
    document = {
        "document_id": "doc-1",
        "provider": "AUTH",
        "reference": "Official document",
    }
    result = build_hydrology_relation_catalog(
        provider="TEST_AUTH",
        product="RELATIONS_V1",
        relations=[relation],
        source_documents=[document],
        jurisdiction="XX",
    )
    assert result["catalog_type"] == CATALOG_TYPE
    assert result["relation_count"] == 1
    assert result["source_document_count"] == 1
    assert result["relations"][0] == relation
    assert result["scope"]["provider_independent_relation_contract"] is True
    assert result["scope"]["nearest_station_is_not_relation_evidence"] is True


def test_catalog_builder_does_not_mutate_inputs():
    relation = _relation()
    before = deepcopy(relation)
    result = build_hydrology_relation_catalog(
        provider="TEST_AUTH",
        product="RELATIONS_V1",
        relations=[relation],
    )
    result["relations"][0]["target"]["waterbody_names"].append("changed")
    assert relation == before


def test_catalog_rejects_duplicate_relation_ids():
    relation = _relation()
    with pytest.raises(ValueError, match="duplicate hydrology relation_id"):
        build_hydrology_relation_catalog(
            provider="TEST_AUTH",
            product="RELATIONS_V1",
            relations=[relation, deepcopy(relation)],
        )


def test_catalog_rejects_duplicate_metric_keys_within_relation():
    relation = _relation()
    relation["metrics"].append(deepcopy(relation["metrics"][0]))
    with pytest.raises(ValueError, match="duplicate metric_key"):
        build_hydrology_relation_catalog(
            provider="TEST_AUTH",
            product="RELATIONS_V1",
            relations=[relation],
        )


def test_catalog_summary_removes_relation_payloads_but_keeps_provenance():
    catalog = build_hydrology_relation_catalog(
        provider="TEST_AUTH",
        product="RELATIONS_V1",
        relations=[_relation()],
        source_documents=[
            {
                "document_id": "doc-1",
                "provider": "AUTH",
                "reference": "Official document",
            }
        ],
    )
    summary = build_hydrology_relation_catalog_summary(catalog)
    assert summary["provider"] == "TEST_AUTH"
    assert summary["relations"] == []
    assert summary["relations_included"] is False
    assert summary["source_documents"][0]["document_id"] == "doc-1"
