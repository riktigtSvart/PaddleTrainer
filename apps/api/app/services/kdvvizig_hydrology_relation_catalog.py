from __future__ import annotations

from app.services.hydrology_relation_catalog import build_hydrology_relation_catalog


PROVIDER = "HU_KDVVIZIG_OFFICIAL"
PRODUCT = "RSD_HYDRAULIC_RELATION_EVIDENCE_V1"


def build_kdvvizig_hydrology_relation_catalog() -> dict:
    """Curated official evidence for Hungarian Danube-branch relations.

    V23.2 intentionally encodes only what the cited official material supports.
    For the Ráckevei (Soroksári)-Duna (RSD), the official material establishes
    structure-controlled operation and an operational dependence on both Danube
    and RSD levels.  It does *not* establish a quantitative Budapest-gauge to
    RSD measurement transfer function, so all metric transfer flags remain
    false.
    """
    source_documents = [
        {
            "document_id": "KDVVIZIG_RSD_OPERATION",
            "provider": "KDVVIZIG",
            "reference": (
                "RSD - Ráckevei (Soroksári)-Duna operational description"
            ),
            "url": (
                "https://www.kdvvizig.hu/kozep-duna-volgyi/"
                "vizgazdalkodas-vizszolgaltatas/nagymutargyak-uzemelese/rsd/rsd"
            ),
            "evidence_role": "STRUCTURE_CONTROLLED_BRANCH_OPERATION",
        },
        {
            "document_id": "KDVVIZIG_RSD_LOCK_OPERATION",
            "provider": "KDVVIZIG",
            "reference": (
                "Zsilipelési üzemrend a Ráckevei (Soroksári)-Duna-ágon"
            ),
            "url": (
                "https://www.kdvvizig.hu/kozep-duna-volgyi/"
                "vizgazdalkodas-vizszolgaltatas/nagymutargyak-uzemelese/rsd/"
                "zsilipelesi-uzemrend-a-rackevei-soroksari-duna-agon"
            ),
            "evidence_role": "JOINT_DANUBE_AND_RSD_OPERATIONAL_DEPENDENCY",
        },
        {
            "document_id": "KDVVIZIG_RSD_PUMPING_2026",
            "provider": "KDVVIZIG",
            "reference": "Folyik a szivattyús vízátemelés a Kvassay-vízlépcsőnél",
            "url": (
                "https://www.kdvvizig.hu/kozep-duna-volgyi/hireink/ovf-hirek/"
                "folyik-a-szivattyus-vizatemeles-a-kvassay-vizlepcsonel"
            ),
            "evidence_role": "ACTIVE_CONTROL_OPERATION_EXAMPLE",
            "published_date": "2026-04-02",
        },
        {
            "document_id": "VIZUGY_BUDAPEST_1026",
            "provider": "OVF_VIZUGY",
            "reference": "Budapest Duna gauge, registry number 1026",
            "url": "https://www.vizugy.hu/",
            "evidence_role": "SOURCE_STATION_IDENTITY",
        },
    ]

    rsd_relation = {
        "relation_id": "HU-KDVVIZIG-RSD-BUDAPEST-1026-STRUCTURE-CONTROLLED",
        "relation_type": "STRUCTURE_CONTROLLED",
        "target": {
            "waterbody_names": [
                "Ráckevei (Soroksári)-Duna",
                "Ráckevei (Soroksári)-Duna-ág",
                "Ráckevei (Soroksári) Duna-ág",
                "Ráckevei-Soroksári-Duna",
                "RSD",
            ],
        },
        "source": {
            "station_registry_numbers": [1026],
            "watercourse_names": ["Duna"],
        },
        "authority": {
            "provider": "KDVVIZIG",
            "product": "RSD_OPERATIONAL_DOCUMENTATION",
            "reference": "KDVVIZIG_RSD_OPERATION;KDVVIZIG_RSD_LOCK_OPERATION",
        },
        "source_document_ids": [
            "KDVVIZIG_RSD_OPERATION",
            "KDVVIZIG_RSD_LOCK_OPERATION",
            "KDVVIZIG_RSD_PUMPING_2026",
            "VIZUGY_BUDAPEST_1026",
        ],
        "control_structure_ids": [
            "KVASSAY_VIZLEPCSO",
            "TASSI_VIZLEPCSO",
        ],
        "control_structure_state_required": True,
        "control_state_evidence": {
            "available": False,
            "reason": "NO_ROUTE_TIME_MATCHED_CONTROL_OPERATION_STATE_SOURCE",
        },
        "relation_basis": [
            "RSD_IS_A_REGULATED_OPERATING_WATER_LEVEL_RIVER_REACH",
            "KVASSAY_CONTROLS_UPPER_WATER_SUPPLY_AND_LEVEL",
            "TASSI_CONTROLS_LOWER_RELEASE_AND_LEVEL",
            "LOCK_OPERATION_USES_DANUBE_AND_RSD_LEVELS_JOINTLY",
        ],
        "calibration_evidence": {
            "available": False,
            "status": "NO_QUANTITATIVE_MAINSTEM_TO_RSD_TRANSFER_FUNCTION",
        },
        "metrics": [
            {
                "metric_key": "WATER_LEVEL",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "RSD_WATER_LEVEL_IS_STRUCTURE_CONTROLLED",
                    "NO_AUTHORITATIVE_BUDAPEST_1026_TO_RSD_LEVEL_TRANSFER_FUNCTION",
                    "ROUTE_TIME_MATCHED_CONTROL_STATE_REQUIRED_FOR_ANY_DERIVED_RELATION",
                ],
            },
            {
                "metric_key": "DISCHARGE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "RSD_FLOW_IS_OPERATIONALLY_CONTROLLED",
                    "NO_AUTHORITATIVE_BUDAPEST_1026_TO_RSD_DISCHARGE_TRANSFER_FUNCTION",
                ],
            },
            {
                "metric_key": "WATER_TEMPERATURE",
                "transfer_allowed": False,
                "representativeness_ceiling": "INSUFFICIENT_EVIDENCE",
                "limitations": [
                    "NO_AUTHORITATIVE_BUDAPEST_1026_TO_RSD_TEMPERATURE_TRANSFER_FUNCTION",
                ],
            },
        ],
        "uncertainty": {
            "quantitative_transfer_function_available": False,
            "route_time_matched_control_state_available": False,
        },
        "limitations": [
            "STRUCTURE_CONTROLLED_BRANCH_REQUIRES_EXPLICIT_OPERATIONAL_STATE",
            "MAINSTEM_GAUGE_IS_NOT_A_BRANCH_GAUGE",
            "TOPOLOGICAL_CONNECTION_DOES_NOT_ESTABLISH_METRIC_TRANSFER",
        ],
    }

    return build_hydrology_relation_catalog(
        provider=PROVIDER,
        product=PRODUCT,
        source_mode="CURATED_OFFICIAL_DOCUMENTS",
        jurisdiction="HU",
        source_documents=source_documents,
        relations=[rsd_relation],
        metadata={
            "catalog_semantics": (
                "Official structural/operational relation evidence; not a live "
                "control-state feed and not a hydraulic transfer model."
            ),
            "positive_metric_transfer_claims": 0,
        },
    )
