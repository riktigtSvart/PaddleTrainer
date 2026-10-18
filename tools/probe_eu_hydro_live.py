from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

LOCAL_INSPECT = (
    "http://127.0.0.1:8000/api/v1/integrations/polar/"
    "sessions/routes/inspect"
)
ARCGIS_BASE = (
    "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
    "EUHydro/EUHydro_RiverNetworkDatabase/MapServer"
)
LAYERS = {
    "River_Net_polygon": 19,
    "InlandWater": 2,
}
EARTH_RADIUS_M = 6_371_008.8
PADDING_M = 50.0
ABSOLUTE_TIMEOUT_S = 15.0


def collect_coordinates(value: Any, out: list[tuple[float, float]]) -> None:
    if isinstance(value, Mapping):
        pairs = (
            ("latitude_deg", "longitude_deg"),
            ("latitude", "longitude"),
            ("lat", "lon"),
            ("lat", "lng"),
        )
        for lat_key, lon_key in pairs:
            if lat_key in value and lon_key in value:
                try:
                    lat = float(value[lat_key])
                    lon = float(value[lon_key])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(lat) and math.isfinite(lon):
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        out.append((lat, lon))
                        break
        for child in value.values():
            collect_coordinates(child, out)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            collect_coordinates(child, out)


def expand_bounds(bounds: tuple[float, float, float, float], padding_m: float):
    xmin, ymin, xmax, ymax = bounds
    center_lat = (ymin + ymax) / 2.0
    lat_pad = math.degrees(padding_m / EARTH_RADIUS_M)
    c = abs(math.cos(math.radians(center_lat)))
    lon_pad = 180.0 if c < 1e-12 else math.degrees(padding_m / (EARTH_RADIUS_M * c))
    return xmin - lon_pad, ymin - lat_pad, xmax + lon_pad, ymax + lat_pad


def vertex_count(payload: Any) -> int:
    total = 0
    if not isinstance(payload, Mapping):
        return 0
    features = payload.get("features")
    if not isinstance(features, list):
        return 0
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        geom = feature.get("geometry")
        if not isinstance(geom, Mapping):
            continue
        rings = geom.get("rings")
        if not isinstance(rings, list):
            continue
        for ring in rings:
            if isinstance(ring, list):
                total += len(ring)
    return total


async def timed_get(client: httpx.AsyncClient, url: str, params: dict[str, str], label: str):
    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(ABSOLUTE_TIMEOUT_S):
            response = await client.get(url, params=params)
            content = response.content
    except TimeoutError:
        print(f"  {label:<30} TIMEOUT > {ABSOLUTE_TIMEOUT_S:.0f}s")
        return None
    elapsed = time.perf_counter() - t0
    print(
        f"  {label:<30} {elapsed:7.3f}s  "
        f"status={response.status_code}  bytes={len(content):,}"
    )
    try:
        payload = response.json()
    except ValueError:
        print("    invalid JSON")
        return None
    if isinstance(payload, Mapping) and payload.get("error"):
        print(f"    ArcGIS error: {payload['error']}")
    return payload


async def probe_layer(client: httpx.AsyncClient, name: str, layer_id: int, bounds):
    xmin, ymin, xmax, ymax = bounds
    url = f"{ARCGIS_BASE}/{layer_id}/query"
    common = {
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
    }

    print(f"\n{name} (layer {layer_id})")

    count_payload = await timed_get(
        client,
        url,
        {**common, "returnCountOnly": "true"},
        "count only",
    )
    if isinstance(count_payload, Mapping):
        print(f"    count={count_payload.get('count')}")

    ids_payload = await timed_get(
        client,
        url,
        {**common, "returnIdsOnly": "true"},
        "IDs only",
    )
    ids: list[Any] = []
    if isinstance(ids_payload, Mapping) and isinstance(ids_payload.get("objectIds"), list):
        ids = ids_payload["objectIds"]
        print(f"    objectIds={len(ids)}")

    attrs_payload = await timed_get(
        client,
        url,
        {
            **common,
            "outFields": "OBJECTID",
            "returnGeometry": "false",
            "resultRecordCount": "1000",
        },
        "attributes, no geometry",
    )
    if isinstance(attrs_payload, Mapping) and isinstance(attrs_payload.get("features"), list):
        print(f"    features={len(attrs_payload['features'])}")

    current_payload = await timed_get(
        client,
        url,
        {
            **common,
            "outFields": "OBJECTID",
            "returnGeometry": "true",
            "returnZ": "false",
            "returnM": "false",
            "geometryPrecision": "6",
            "resultRecordCount": "1000",
        },
        "full geometry (current-like)",
    )
    if current_payload is not None:
        features = current_payload.get("features", []) if isinstance(current_payload, Mapping) else []
        print(f"    features={len(features) if isinstance(features, list) else '?'} vertices={vertex_count(current_payload):,}")

    generalized_payload = await timed_get(
        client,
        url,
        {
            **common,
            "outFields": "OBJECTID",
            "returnGeometry": "true",
            "returnZ": "false",
            "returnM": "false",
            "geometryPrecision": "6",
            # About 0.7-1.1 m in Budapest, far below the current 25 m boundary-near tolerance.
            "maxAllowableOffset": "0.00001",
            "resultRecordCount": "1000",
        },
        "geometry, ~1m generalized",
    )
    if generalized_payload is not None:
        features = generalized_payload.get("features", []) if isinstance(generalized_payload, Mapping) else []
        print(f"    features={len(features) if isinstance(features, list) else '?'} vertices={vertex_count(generalized_payload):,}")

    if ids:
        one_payload = await timed_get(
            client,
            url,
            {
                "objectIds": str(ids[0]),
                "outFields": "OBJECTID",
                "returnGeometry": "true",
                "outSR": "4326",
                "returnZ": "false",
                "returnM": "false",
                "geometryPrecision": "6",
                "f": "json",
            },
            "first feature geometry",
        )
        if one_payload is not None:
            print(f"    first-feature vertices={vertex_count(one_payload):,}")


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        print("Fetching baseline route inspect...")
        t0 = time.perf_counter()
        r = await client.get(
            LOCAL_INSPECT,
            params={
                "route_date": "2026-09-30",
                "artifact_policy_profile": "BALANCED",
            },
        )
        r.raise_for_status()
        baseline = r.json()
        print(f"baseline: {time.perf_counter() - t0:.3f}s")

        sessions = baseline.get("route_sessions") or []
        if not sessions:
            raise RuntimeError("No route_sessions in baseline response")
        normalized = sessions[0].get("normalized")
        coords: list[tuple[float, float]] = []
        collect_coordinates(normalized, coords)
        if not coords:
            raise RuntimeError("Could not find route coordinates in normalized response")

        lats = [p[0] for p in coords]
        lons = [p[1] for p in coords]
        bounds = (min(lons), min(lats), max(lons), max(lats))
        expanded = expand_bounds(bounds, PADDING_M)
        print(f"coordinate pairs found: {len(coords):,}")
        print(
            "raw bounds:      "
            f"xmin={bounds[0]:.7f} ymin={bounds[1]:.7f} "
            f"xmax={bounds[2]:.7f} ymax={bounds[3]:.7f}"
        )
        print(
            "expanded bounds: "
            f"xmin={expanded[0]:.7f} ymin={expanded[1]:.7f} "
            f"xmax={expanded[2]:.7f} ymax={expanded[3]:.7f}"
        )

        for name, layer_id in LAYERS.items():
            await probe_layer(client, name, layer_id, expanded)


if __name__ == "__main__":
    asyncio.run(main())
