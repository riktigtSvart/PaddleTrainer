from datetime import datetime, timezone

from app.integrations.ovf_vra.client import (
    DATA_TYPE_OPERATIONAL,
    METRIC_DISCHARGE,
    build_short_series_body,
)


def test_short_series_body_matches_vra_contract_and_normalizes_to_utc():
    body = build_short_series_body(
        station_registry_number=1026,
        metric_code=METRIC_DISCHARGE,
        data_type_code=DATA_TYPE_OPERATIONAL,
        start=datetime(
            2026,
            9,
            30,
            16,
            0,
            tzinfo=timezone.utc,
        ),
        end=datetime(
            2026,
            9,
            30,
            20,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert body == {
        "TorzsszamList": [1026],
        "AdatFajtaKod": 87,
        "AdatTipusKod": 101,
        "StartTime": (
            "2026-09-30T16:00:00+00:00"
        ),
        "EndTime": (
            "2026-09-30T20:00:00+00:00"
        ),
    }
