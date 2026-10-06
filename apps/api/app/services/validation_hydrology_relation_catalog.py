from __future__ import annotations

from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog


PROVIDER = "PADDLETRAINER_VALIDATION_RELATION"
PRODUCT = "SZENTENDRE_1026_WATER_LEVEL_POSITIVE_CONTROL_V1"
VALIDATION_ROUTE_DATE = "2026-08-29"


def build_validation_hydrology_relation_catalog() -> dict:
    """Build a synthetic positive-control catalog for V23.4 validation only.

    This fixture is deliberately *not* real-world hydrological evidence.  It
    exists to exercise the production relation-evaluation, metric-gating,
    lineage, and persistence path with one positive metric and one explicitly
    withheld metric.  The validity window is intentionally limited to the
    historical Szentendre validation date used by the project.
    """
    relation = {
        "relation_id": "V23.4-SYNTHETIC-SZENTENDRE-1026-WATER-LEVEL",
        "relation_type": "UNCONTROLLED_HYDRAULIC_CONNECTION",
        "target": {
            "waterbody_names": [
                "Szentendrei-Duna",
                "Szentendrei Duna",
            ],
        },
        "source": {
            "station_registry_numbers": [1026],
            "watercourse_names": ["Duna"],
        },
        "authority": {
            "provider": "PADDLETRAINER_VALIDATION",
            "product": "V23_4_POSITIVE_CONTROL_FIXTURE",
            "reference": "V23.4 synthetic validation contract",
        },
        "source_document_ids": ["V23_4_SYNTHETIC_POSITIVE_CONTROL_SPEC"],
        "valid_from": "2026-08-29T00:00:00+02:00",
        "valid_to": "2026-08-29T23:59:59.999999+02:00",
        "control_structure_state_required": False,
        "calibration_evidence": {
            "available": False,
            "status": "NOT_REQUIRED_FOR_SYNTHETIC_VALIDATION_FIXTURE",
        },
        "metrics": [
            {
                "metric_key": "WATER_LEVEL",
                "transfer_allowed": True,
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                "limitations": [
                    "SYNTHETIC_VALIDATION_RELATION_NOT_REAL_WORLD_EVIDENCE",
                    "VALID_FOR_V23_4_PIPELINE_CONTROL_ONLY",
                ],
            },
            {
                "metric_key": "DISCHARGE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "SYNTHETIC_VALIDATION_FIXTURE_EXPLICITLY_WITHHOLDS_DISCHARGE",
                ],
            },
            {
                "metric_key": "WATER_TEMPERATURE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "SYNTHETIC_VALIDATION_FIXTURE_EXPLICITLY_WITHHOLDS_TEMPERATURE",
                ],
            },
        ],
        "uncertainty": {
            "synthetic_validation_fixture": True,
            "real_world_transfer_claim": False,
        },
        "limitations": [
            "SYNTHETIC_VALIDATION_ONLY",
            "MUST_NOT_BE_INTERPRETED_AS_AUTHORITATIVE_HYDROLOGICAL_EVIDENCE",
            "FIXTURE_VALIDITY_LIMITED_TO_2026_08_29_SZENTENDRE_CONTROL",
        ],
    }

    return build_hydrology_relation_catalog(
        provider=PROVIDER,
        product=PRODUCT,
        source_mode="SYNTHETIC_VALIDATION_FIXTURE",
        jurisdiction="VALIDATION_ONLY",
        source_documents=[
            {
                "document_id": "V23_4_SYNTHETIC_POSITIVE_CONTROL_SPEC",
                "provider": "PADDLETRAINER",
                "reference": (
                    "V23.4 synthetic positive-control contract; not real-world "
                    "hydrological evidence"
                ),
                "evidence_role": "SOFTWARE_PIPELINE_VALIDATION_ONLY",
            }
        ],
        relations=[relation],
        metadata={
            "validation_only": True,
            "synthetic": True,
            "real_world_hydrology_claim": False,
            "allowed_route_date": VALIDATION_ROUTE_DATE,
            "positive_metric_transfer_claims": 1,
            "positive_metric_transfer_keys": ["WATER_LEVEL"],
            "explicitly_withheld_metric_keys": [
                "DISCHARGE",
                "WATER_TEMPERATURE",
            ],
        },
    )
