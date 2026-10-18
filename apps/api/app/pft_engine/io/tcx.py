from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from app.pft_engine.contracts.input import (
    ImportedSession,
    RawSample,
)


TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
ACTIVITY_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"

NS = {
    "tcx": TCX_NS,
    "ae": ACTIVITY_NS,
}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    return float(value)


def parse_tcx(path: str | Path) -> ImportedSession:
    path = Path(path)

    root = ET.parse(path).getroot()

    trackpoints = root.findall(".//tcx:Trackpoint", NS)

    if not trackpoints:
        raise ValueError("TCX file contains no trackpoints.")

    samples: list[RawSample] = []

    started_at: datetime | None = None

    for trackpoint in trackpoints:
        time_text = trackpoint.findtext("tcx:Time", namespaces=NS)

        if time_text is None:
            continue

        timestamp = _parse_datetime(time_text)

        if started_at is None:
            started_at = timestamp

        elapsed_s = (timestamp - started_at).total_seconds()

        hr_bpm = _optional_float(
            trackpoint.findtext(
                "tcx:HeartRateBpm/tcx:Value",
                namespaces=NS,
            )
        )

        power_w = _optional_float(
            trackpoint.findtext(
                "tcx:Extensions/ae:TPX/ae:Watts",
                namespaces=NS,
            )
        )

        distance_m = _optional_float(
            trackpoint.findtext(
                "tcx:DistanceMeters",
                namespaces=NS,
            )
        )

        cadence_rpm = _optional_float(
            trackpoint.findtext(
                "tcx:Cadence",
                namespaces=NS,
            )
        )

        latitude_deg = _optional_float(
            trackpoint.findtext(
                "tcx:Position/tcx:LatitudeDegrees",
                namespaces=NS,
            )
        )

        longitude_deg = _optional_float(
            trackpoint.findtext(
                "tcx:Position/tcx:LongitudeDegrees",
                namespaces=NS,
            )
        )

        altitude_m = _optional_float(
            trackpoint.findtext(
                "tcx:AltitudeMeters",
                namespaces=NS,
            )
        )

        samples.append(
            RawSample(
                timestamp=timestamp,
                elapsed_s=elapsed_s,
                hr_bpm=hr_bpm,
                power_w=power_w,
                distance_m=distance_m,
                cadence_rpm=cadence_rpm,
                latitude_deg=latitude_deg,
                longitude_deg=longitude_deg,
                altitude_m=altitude_m,
            )
        )

    if started_at is None or not samples:
        raise ValueError("TCX file contains no usable timed samples.")

    return ImportedSession(
        started_at=started_at,
        samples=tuple(samples),
    )