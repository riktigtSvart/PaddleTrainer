from __future__ import annotations

import sqlite3

from app.services.eea_msfd_geometry_store import EEAMSFDGeometryStore


def _feature(object_id: int = 7) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "subregion": "MAD",
            "subregionName": "Adriatic Sea",
        },
        "geometry": {
            "rings": [
                [
                    [15.0, 44.0],
                    [15.5, 44.0],
                    [15.5, 44.5],
                    [15.0, 44.0],
                ]
            ]
        },
    }


def test_raw_feature_snapshot_round_trips(tmp_path) -> None:
    store = EEAMSFDGeometryStore(tmp_path / "msfd.sqlite3")
    stored = store.put_features(
        features=[_feature()],
        fetched_at="2026-10-05T12:00:00+00:00",
    )

    assert stored == ("7",)
    found = store.get_features(object_ids=[7])
    assert found["7"].raw_feature == _feature()
    assert len(found["7"].snapshot_sha256) == 64
    assert found["7"].fetched_at == "2026-10-05T12:00:00+00:00"


def test_zero_result_coverage_is_cached(tmp_path) -> None:
    store = EEAMSFDGeometryStore(tmp_path / "msfd.sqlite3")
    cell = store.coverage_cells_for_bounds(
        xmin_lon=19.01,
        ymin_lat=47.51,
        xmax_lon=19.02,
        ymax_lat=47.52,
    )[0]

    assert store.get_cell_object_ids(cell=cell) is None
    store.put_cell_object_ids(cell=cell, object_ids=[])
    assert store.get_cell_object_ids(cell=cell) == ()


def test_nearby_bounds_map_to_stable_coverage_cells(tmp_path) -> None:
    store = EEAMSFDGeometryStore(
        tmp_path / "msfd.sqlite3",
        cell_size_deg=0.25,
    )
    first = store.coverage_cells_for_bounds(
        xmin_lon=15.18,
        ymin_lat=44.24,
        xmax_lon=15.22,
        ymax_lat=44.28,
    )
    second = store.coverage_cells_for_bounds(
        xmin_lon=15.19,
        ymin_lat=44.25,
        xmax_lon=15.21,
        ymax_lat=44.27,
    )

    assert {cell.key for cell in second}.issubset(
        {cell.key for cell in first}
    )


def test_changed_provider_feature_preserves_previous_snapshot(tmp_path) -> None:
    store = EEAMSFDGeometryStore(tmp_path / "msfd.sqlite3")
    first = _feature()
    changed = _feature()
    changed["geometry"]["rings"][0][1] = [15.6, 44.0]

    store.put_features(
        features=[first],
        fetched_at="2026-10-05T12:00:00+00:00",
    )
    first_record = store.get_features(object_ids=[7])["7"]

    store.put_features(
        features=[changed],
        fetched_at="2026-11-05T12:00:00+00:00",
    )
    latest = store.get_features(object_ids=[7])["7"]

    assert latest.snapshot_sha256 != first_record.snapshot_sha256
    assert latest.raw_feature == changed

    with sqlite3.connect(store.path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM eea_msfd_feature_snapshots "
            "WHERE object_id = '7'"
        ).fetchone()[0]
    assert count == 2
