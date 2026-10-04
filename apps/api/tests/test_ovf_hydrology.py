from app.services.ovf_hydrology import (
    normalize_ovf_hydrology_measurements,
)


def _station():
    return {
        "Tsz": 1026,
        "Nev": "Budapest",
        "MdrNev": "Duna",
        "Telepules": "Budapest",
        "Lat": 47.5,
        "Lon": 19.04,
        "Fkm": 1646.5,
        "LKV": 0,
        "LNV": 891,
        "KF1": 620,
        "KF2": 700,
        "KF3": 800,
    }


def test_normalizes_multiple_hydrology_metrics_without_current_estimate():
    result = normalize_ovf_hydrology_measurements(
        station=_station(),
        series_payloads=[
            {
                "metric_code": 68,
                "data_type_code": 101,
                "source_operation": "level",
                "items": [
                    {
                        "UTCTime": (
                            "2026-09-30T16:00:00+00:00"
                        ),
                        "Adat": 14,
                    }
                ],
            },
            {
                "metric_code": 87,
                "data_type_code": 101,
                "source_operation": "discharge",
                "items": [
                    {
                        "UTCTime": (
                            "2026-09-30T16:00:00+00:00"
                        ),
                        "Adat": 754,
                    }
                ],
            },
            {
                "metric_code": 85,
                "data_type_code": 101,
                "source_operation": "temperature",
                "items": [
                    {
                        "UTCTime": (
                            "2026-09-30T16:00:00+00:00"
                        ),
                        "Adat": 18.1,
                    }
                ],
            },
        ],
    )

    assert result["measurement_count"] == 3
    assert result["station"]["watercourse"] == "Duna"
    assert result["station"]["river_km"] == 1646.5
    assert result["metric_keys"] == [
        "DISCHARGE",
        "WATER_LEVEL",
        "WATER_TEMPERATURE",
    ]
    assert (
        result["semantics"][
            "water_level_is_not_current_speed"
        ]
        is True
    )
    assert (
        result["semantics"][
            "estimates_current_velocity"
        ]
        is False
    )


def test_preserves_quality_codes_when_present():
    result = normalize_ovf_hydrology_measurements(
        station=_station(),
        series_payloads=[
            {
                "metric_code": 68,
                "data_type_code": 101,
                "items": [
                    {
                        "UTCTime": (
                            "2026-09-30T16:00:00+00:00"
                        ),
                        "Adat": 14,
                        "AMKod": 2,
                        "MMKod": 3,
                    }
                ],
            }
        ],
    )

    measurement = result["measurements"][0]

    assert measurement["data_quality_code"] == 2
    assert measurement["field_quality_code"] == 3
