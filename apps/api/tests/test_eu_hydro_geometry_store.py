from __future__ import annotations

from app.services.eu_hydro_geometry_store import EUHydroGeometryStore


def _feature(object_id: int = 7) -> dict:
    return {
        "attributes": {
            "OBJECTID": object_id,
            "OBJECT_ID": f"river-{object_id}",
        },
        "geometry": {
            "rings": [
                [
                    [19.0, 47.0],
                    [19.1, 47.0],
                    [19.1, 47.1],
                    [19.0, 47.0],
                ]
            ]
        },
    }


def test_raw_feature_snapshot_round_trips(tmp_path) -> None:
    store = EUHydroGeometryStore(tmp_path / "hydro.sqlite3")
    stored = store.put_features(
        source_layer="RIVER_NET_POLYGON",
        features=[_feature()],
        fetched_at="2026-10-05T10:00:00+00:00",
    )

    assert stored == ("7",)
    found = store.get_features(
        source_layer="RIVER_NET_POLYGON",
        object_ids=[7],
    )
    assert found["7"].raw_feature == _feature()
    assert len(found["7"].snapshot_sha256) == 64
    assert found["7"].fetched_at == "2026-10-05T10:00:00+00:00"


def test_zero_result_coverage_is_cached(tmp_path) -> None:
    store = EUHydroGeometryStore(tmp_path / "hydro.sqlite3")
    cell = store.coverage_cells_for_bounds(
        xmin_lon=19.01,
        ymin_lat=47.51,
        xmax_lon=19.02,
        ymax_lat=47.52,
    )[0]

    assert store.get_cell_object_ids(
        source_layer="INLAND_WATER",
        cell=cell,
    ) is None

    store.put_cell_object_ids(
        source_layer="INLAND_WATER",
        cell=cell,
        object_ids=[],
    )

    assert store.get_cell_object_ids(
        source_layer="INLAND_WATER",
        cell=cell,
    ) == ()


def test_repeated_bounds_map_to_stable_coverage_cells(tmp_path) -> None:
    store = EUHydroGeometryStore(
        tmp_path / "hydro.sqlite3",
        cell_size_deg=0.05,
    )
    first = store.coverage_cells_for_bounds(
        xmin_lon=19.046,
        ymin_lat=47.519,
        xmax_lon=19.062,
        ymax_lat=47.554,
    )
    second = store.coverage_cells_for_bounds(
        xmin_lon=19.047,
        ymin_lat=47.520,
        xmax_lon=19.061,
        ymax_lat=47.553,
    )

    assert {cell.key for cell in second}.issubset(
        {cell.key for cell in first}
    )


def test_changed_provider_feature_preserves_previous_snapshot(tmp_path) -> None:
    store = EUHydroGeometryStore(tmp_path / "hydro.sqlite3")
    first = _feature()
    changed = _feature()
    changed["geometry"]["rings"][0][1] = [19.2, 47.0]

    store.put_features(
        source_layer="RIVER_NET_POLYGON",
        features=[first],
        fetched_at="2026-10-05T10:00:00+00:00",
    )
    first_record = store.get_features(
        source_layer="RIVER_NET_POLYGON",
        object_ids=[7],
    )["7"]

    store.put_features(
        source_layer="RIVER_NET_POLYGON",
        features=[changed],
        fetched_at="2026-11-05T10:00:00+00:00",
    )
    latest = store.get_features(
        source_layer="RIVER_NET_POLYGON",
        object_ids=[7],
    )["7"]

    assert latest.snapshot_sha256 != first_record.snapshot_sha256
    assert latest.raw_feature == changed

    import sqlite3

    with sqlite3.connect(store.path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM eu_hydro_feature_snapshots WHERE object_id = '7'"
        ).fetchone()[0]
    assert count == 2
