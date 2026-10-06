from __future__ import annotations

from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog


PROVIDER = "HU_SZENTENDRE_OFFICIAL_FLOOD_STAGE"
PRODUCT = "NAGYMAROS_TO_SZENTENDRE_FLOOD_STAGE_RELATION_V1"
SOURCE_STATION_REGISTRY_NUMBER = 1020

# Conservative applicability envelope derived only from explicit source->target
# flood-stage examples published by Szentendre's official site in September 2024:
#   Nagymaros 532 cm -> Szentendre 560-570 cm  (offset +28..+38)
#   Nagymaros 643 cm -> Szentendre 670-680 cm  (offset +27..+37)
#   Nagymaros 704 cm -> Szentendre ~740 cm     (offset about +36)
#   Nagymaros 716 cm -> Szentendre 740-750 cm  (offset +24..+34)
# V23.5 uses the union envelope +24..+38 cm and never extrapolates outside
# the documented 532..716 cm Nagymaros source range.
DOCUMENTED_SOURCE_LEVEL_MIN_CM = 532.0
DOCUMENTED_SOURCE_LEVEL_MAX_CM = 716.0
DOCUMENTED_TARGET_OFFSET_MIN_CM = 24.0
DOCUMENTED_TARGET_OFFSET_MAX_CM = 38.0


def build_szentendre_flood_hydrology_relation_catalog() -> dict:
    """Curated real-world flood-stage relation for Szentendrei-Duna.

    Official Szentendre flood-protection communications repeatedly publish
    paired Nagymaros and expected Szentendre stages. V23.5 deliberately models
    those observations as an interval-only empirical proxy. It never copies
    the Nagymaros gauge reading as a Szentendre measurement, never establishes
    a scalar target value, and never extrapolates outside the source-stage
    range covered by the published examples.
    """
    source_documents = [
        {
            "document_id": "SZENTENDRE_FLOOD_FORECAST_SERIES_2024",
            "provider": "SZENTENDRE_VAROS_HIVATALOS_HONLAPJA",
            "reference": "Szeptemberi árhullám a Duna magyarországi szakaszán",
            "url": (
                "https://szentendre.hu/"
                "szeptemberi-arhullam-a-duna-magyarorszagi-szakaszan/"
            ),
            "evidence_role": "OPERATIONAL_CROSS_GAUGE_STAGE_EXAMPLES",
            "evidence": {
                "examples": [
                    {
                        "source_station": "Nagymaros",
                        "source_level_cm": 532,
                        "target_location": "Szentendre",
                        "target_level_range_cm": [560, 570],
                    },
                    {
                        "source_station": "Nagymaros",
                        "source_level_cm": 643,
                        "target_location": "Szentendre",
                        "target_level_range_cm": [670, 680],
                    },
                    {
                        "source_station": "Nagymaros",
                        "source_level_cm": 716,
                        "target_location": "Szentendre",
                        "target_level_range_cm": [740, 750],
                    },
                ],
            },
        },
        {
            "document_id": "SZENTENDRE_FLOOD_FORECAST_704_2024",
            "provider": "SZENTENDRE_VAROS_HIVATALOS_HONLAPJA",
            "reference": "Az árvízi védekezésnek nem a tetőzéskor lesz vége",
            "url": (
                "https://szentendre.hu/"
                "az-arvizi-vedekezesnek-nem-a-tetozeskor-lesz-vege/"
            ),
            "evidence_role": "OPERATIONAL_CROSS_GAUGE_STAGE_EXAMPLE",
            "evidence": {
                "source_station": "Nagymaros",
                "source_level_cm": 704,
                "target_location": "Szentendre",
                "target_level_approx_cm": 740,
            },
        },
        {
            "document_id": "VIZUGY_NAGYMAROS_1020",
            "provider": "OVF_VIZUGY",
            "reference": (
                "Nagymaros vízmérce; Duna; törzsszám 1020; 1694,600 fkm"
            ),
            "url": (
                "https://www.vizugy.hu/?AllomasVOA="
                "16496053-97AB-11D4-BB62-00508BA24287"
                "&mapData=OrasIdosor&mapModule=OpGrafikon"
            ),
            "evidence_role": "SOURCE_STATION_IDENTITY",
        },
    ]

    relation = {
        "relation_id": "HU-SZENTENDRE-NAGYMAROS-1020-FLOOD-STAGE-INTERVAL",
        "relation_type": "EMPIRICAL_PROXY",
        "target": {
            "waterbody_names": [
                "Szentendrei-Duna",
                "Szentendrei Duna",
                "Szentendrei-Dunaág",
                "Szentendrei Duna-ág",
            ],
        },
        "source": {
            "station_registry_numbers": [SOURCE_STATION_REGISTRY_NUMBER],
            "watercourse_names": ["Duna"],
        },
        "authority": {
            "provider": "SZENTENDRE_VAROS_ONKORMANYZAT",
            "product": "ARVIZVEDELMI_OPERATIV_TAJEKOZTATAS_2024",
            "reference": (
                "SZENTENDRE_FLOOD_FORECAST_SERIES_2024;"
                "SZENTENDRE_FLOOD_FORECAST_704_2024"
            ),
        },
        "source_document_ids": [
            "SZENTENDRE_FLOOD_FORECAST_SERIES_2024",
            "SZENTENDRE_FLOOD_FORECAST_704_2024",
            "VIZUGY_NAGYMAROS_1020",
        ],
        "control_structure_state_required": False,
        "calibration_evidence": {
            "available": True,
            "status": "AUTHORITATIVE",
            "evidence_mode": "DERIVED_ENVELOPE_FROM_AUTHORITATIVE_OPERATIONAL_EXAMPLES",
            "documented_source_level_range_cm": [
                DOCUMENTED_SOURCE_LEVEL_MIN_CM,
                DOCUMENTED_SOURCE_LEVEL_MAX_CM,
            ],
            "derived_target_offset_envelope_cm": [
                DOCUMENTED_TARGET_OFFSET_MIN_CM,
                DOCUMENTED_TARGET_OFFSET_MAX_CM,
            ],
            "operational_examples": [
                {
                    "source_level_cm": 532,
                    "target_level_range_cm": [560, 570],
                },
                {
                    "source_level_cm": 643,
                    "target_level_range_cm": [670, 680],
                },
                {
                    "source_level_cm": 704,
                    "target_level_approx_cm": 740,
                },
                {
                    "source_level_cm": 716,
                    "target_level_range_cm": [740, 750],
                },
            ],
        },
        "relation_basis": [
            "OFFICIAL_SZENTENDRE_COMMUNICATION_PUBLISHES_REPEATED_NAGYMAROS_TO_SZENTENDRE_STAGE_PAIRS",
            "PUBLISHED_OPERATIONAL_EXAMPLES_SUPPORT_POSITIVE_FLOOD_STAGE_RELATION",
            "OFFSET_ENVELOPE_DERIVED_ONLY_FROM_PUBLISHED_OPERATIONAL_EXAMPLES",
        ],
        "metrics": [
            {
                "metric_key": "WATER_LEVEL",
                "transfer_allowed": True,
                "representativeness_ceiling": "PARTIALLY_REPRESENTATIVE",
                "value_projection": {
                    "projection_type": "ADDITIVE_INTERVAL",
                    "projection_contract_version": "0.1",
                    "source_unit": "cm",
                    "target_unit": "cm",
                    "source_value_min": DOCUMENTED_SOURCE_LEVEL_MIN_CM,
                    "source_value_max": DOCUMENTED_SOURCE_LEVEL_MAX_CM,
                    "offset_min": DOCUMENTED_TARGET_OFFSET_MIN_CM,
                    "offset_max": DOCUMENTED_TARGET_OFFSET_MAX_CM,
                    "scalar_value_established": False,
                    "target_semantics": "SZENTENDRE_FLOOD_STAGE_INTERVAL",
                    "extrapolation_allowed": False,
                },
                "uncertainty": {
                    "representation": "INTERVAL_ONLY",
                    "target_minus_source_cm": [
                        DOCUMENTED_TARGET_OFFSET_MIN_CM,
                        DOCUMENTED_TARGET_OFFSET_MAX_CM,
                    ],
                    "scalar_target_stage_established": False,
                    "offset_envelope_is_derived_from_examples": True,
                },
                "limitations": [
                    "FLOOD_STAGE_OPERATIONAL_RELATION_ONLY",
                    "TARGET_STAGE_IS_INTERVAL_NOT_POINT_ESTIMATE",
                    "OFFSET_ENVELOPE_IS_DERIVED_FROM_FINITE_PUBLISHED_EXAMPLES",
                    "NO_EXTRAPOLATION_OUTSIDE_DOCUMENTED_SOURCE_LEVEL_RANGE",
                    "RIVER_MORPHOLOGY_OR_OPERATIONAL_PRACTICE_CHANGE_CAN_INVALIDATE_PROXY",
                    "RELATION_IS_NOT_LOCAL_CURRENT_EVIDENCE",
                ],
            },
            {
                "metric_key": "DISCHARGE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "DOCUMENTED_FLOOD_STAGE_RELATION_DOES_NOT_ESTABLISH_DISCHARGE_TRANSFER",
                ],
            },
            {
                "metric_key": "WATER_TEMPERATURE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "DOCUMENTED_FLOOD_STAGE_RELATION_DOES_NOT_ESTABLISH_TEMPERATURE_TRANSFER",
                ],
            },
        ],
        "uncertainty": {
            "flood_stage_only": True,
            "interval_projection_only": True,
            "scalar_target_stage_established": False,
            "low_water_transfer_claim": False,
            "finite_operational_example_set": True,
        },
        "limitations": [
            "EMPIRICAL_OPERATIONAL_FLOOD_STAGE_PROXY",
            "NOT_A_GENERAL_LOW_WATER_RELATION",
            "NOT_A_DISCHARGE_RELATION",
            "NOT_LOCAL_CURRENT_EVIDENCE",
        ],
    }

    return build_hydrology_relation_catalog(
        provider=PROVIDER,
        product=PRODUCT,
        source_mode="CURATED_OFFICIAL_OPERATIONAL_EVIDENCE",
        jurisdiction="HU",
        source_documents=source_documents,
        relations=[relation],
        metadata={
            "catalog_semantics": (
                "Real-world official Szentendre flood-stage relation using "
                "Nagymaros 1020 as source gauge and a conservative interval "
                "envelope derived from published operational examples."
            ),
            "validation_only": False,
            "synthetic": False,
            "positive_metric_transfer_claims": 1,
            "positive_metric_transfer_keys": ["WATER_LEVEL"],
            "positive_transfer_semantics": "INTERVAL_ONLY_FLOOD_STAGE",
            "documented_source_level_range_cm": [
                DOCUMENTED_SOURCE_LEVEL_MIN_CM,
                DOCUMENTED_SOURCE_LEVEL_MAX_CM,
            ],
            "derived_target_offset_envelope_cm": [
                DOCUMENTED_TARGET_OFFSET_MIN_CM,
                DOCUMENTED_TARGET_OFFSET_MAX_CM,
            ],
        },
    )
