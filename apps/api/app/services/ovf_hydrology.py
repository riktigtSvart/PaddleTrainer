from __future__ import annotations

import math
from datetime import datetime
from typing import Any


SOURCE_PROVIDER = "OVF_VRAQUERY"
SOURCE_PRODUCT = "VRAQUERY_OPENAPI"
SOURCE_TYPE = "OPERATIONAL_HYDROLOGY_OBSERVATION"

METRIC_DEFINITIONS = {
    68: {
        "metric_key": (
            "WATER_LEVEL"
        ),
        "unit": "cm",
    },
    87: {
        "metric_key": (
            "DISCHARGE"
        ),
        "unit": "m3/s",
    },
    85: {
        "metric_key": (
            "WATER_TEMPERATURE"
        ),
        "unit": "degC",
    },
}


def _finite_number(
    value: Any,
) -> float | None:
    if isinstance(
        value,
        bool,
    ):
        return None

    if not isinstance(
        value,
        (int, float),
    ):
        return None

    result = float(
        value
    )

    return (
        result
        if math.isfinite(
            result
        )
        else None
    )


def _normalize_timestamp(
    value: Any,
) -> str | None:
    if not isinstance(
        value,
        str,
    ) or not value.strip():
        return None

    try:
        parsed = (
            datetime.fromisoformat(
                value.strip().replace(
                    "Z",
                    "+00:00",
                )
            )
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return None

    return parsed.isoformat()


def normalize_ovf_surface_station(
    station: dict[str, Any],
) -> dict[str, Any]:
    return {
        "station_registry_number": (
            station.get(
                "Tsz"
            )
        ),
        "station_name": (
            station.get(
                "Nev"
            )
        ),
        "watercourse": (
            station.get(
                "MdrNev"
            )
        ),
        "municipality": (
            station.get(
                "Telepules"
            )
        ),
        "latitude_deg": (
            _finite_number(
                station.get(
                    "Lat"
                )
            )
        ),
        "longitude_deg": (
            _finite_number(
                station.get(
                    "Lon"
                )
            )
        ),
        "river_km": (
            _finite_number(
                station.get(
                    "Fkm"
                )
            )
        ),
        "record_low_water_level_cm": (
            _finite_number(
                station.get(
                    "LKV"
                )
            )
        ),
        "record_high_water_level_cm": (
            _finite_number(
                station.get(
                    "LNV"
                )
            )
        ),
        "alert_level_1_cm": (
            _finite_number(
                station.get(
                    "KF1"
                )
            )
        ),
        "alert_level_2_cm": (
            _finite_number(
                station.get(
                    "KF2"
                )
            )
        ),
        "alert_level_3_cm": (
            _finite_number(
                station.get(
                    "KF3"
                )
            )
        ),
    }


def normalize_ovf_hydrology_measurements(
    *,
    station: dict[str, Any],
    series_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_station = (
        normalize_ovf_surface_station(
            station
        )
    )

    measurements = []

    for series in series_payloads:
        if not isinstance(
            series,
            dict,
        ):
            continue

        metric_code = series.get(
            "metric_code"
        )

        definition = (
            METRIC_DEFINITIONS.get(
                metric_code
            )
        )

        if definition is None:
            continue

        data_type_code = (
            series.get(
                "data_type_code"
            )
        )

        for item_index, item in enumerate(
            series.get(
                "items"
            )
            or []
        ):
            if not isinstance(
                item,
                dict,
            ):
                continue

            observed_at = (
                _normalize_timestamp(
                    item.get(
                        "UTCTime"
                    )
                )
            )
            value = _finite_number(
                item.get(
                    "Adat"
                )
            )

            if (
                observed_at is None
                or value is None
            ):
                continue

            measurements.append(
                {
                    "measurement_id": (
                        f"ovf:"
                        f"{normalized_station.get('station_registry_number')}:"
                        f"{metric_code}:"
                        f"{item_index}:"
                        f"{observed_at}"
                    ),
                    "observed_at": (
                        observed_at
                    ),
                    "metric_code": (
                        metric_code
                    ),
                    "metric_key": (
                        definition[
                            "metric_key"
                        ]
                    ),
                    "value": (
                        value
                    ),
                    "unit": (
                        definition[
                            "unit"
                        ]
                    ),
                    "data_type_code": (
                        data_type_code
                    ),
                    "data_quality_code": (
                        item.get(
                            "AMKod"
                        )
                    ),
                    "field_quality_code": (
                        item.get(
                            "MMKod"
                        )
                    ),
                    "data_ext": (
                        item.get(
                            "DataExt"
                        )
                    ),
                    "source_provider": (
                        SOURCE_PROVIDER
                    ),
                    "source_product": (
                        SOURCE_PRODUCT
                    ),
                    "source_type": (
                        SOURCE_TYPE
                    ),
                    "source_operation": (
                        series.get(
                            "source_operation"
                        )
                    ),
                    "station": (
                        normalized_station
                    ),
                }
            )

    measurements.sort(
        key=lambda measurement: (
            measurement[
                "observed_at"
            ],
            measurement[
                "metric_code"
            ],
        )
    )

    return {
        "provider": (
            SOURCE_PROVIDER
        ),
        "product": (
            SOURCE_PRODUCT
        ),
        "source_type": (
            SOURCE_TYPE
        ),
        "station": (
            normalized_station
        ),
        "available": bool(
            measurements
        ),
        "measurement_count": (
            len(
                measurements
            )
        ),
        "metric_keys": sorted(
            {
                measurement[
                    "metric_key"
                ]
                for measurement in measurements
            }
        ),
        "semantics": {
            "operational_data_may_be_preliminary": (
                True
            ),
            "quality_codes_preserved_when_present": (
                True
            ),
            "estimates_current_velocity": (
                False
            ),
            "water_level_is_not_current_speed": (
                True
            ),
        },
        "measurements": (
            measurements
        ),
    }
