"""Bounded TCX ingestion and deterministic observation processing; no state scores."""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy
import scipy
import app.pft_engine as paddletrainer_physiology
from app.pft_engine.contracts.input import ImportedSession, RawSample
from app.pft_engine.io.json_output import pft_output_to_dict
from app.pft_engine.pft.output_mapper import build_pft_output_contract
from app.pft_engine.pft.processor import PftProcessingRules, process_pft
from app.pft_engine.pft.protocol import pft_run_v01
from app.pft_engine.pft.reference_context import build_pft_reference_context
from app.schemas.pft import PftMeasurementContext

MAX_PFT_IMPORT_BYTES = 16 * 1024 * 1024
MAX_RECORDING_SAMPLES = 20000
MAX_PROCESSING_SAMPLES = 1200
PFT_ADAPTER_VERSION = "pft_api_ingestion_v0.1"
NS = {"t": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
      "a": "http://www.garmin.com/xmlschemas/ActivityExtension/v2"}


class PftInputError(ValueError):
    pass


class PftIntegrityError(ValueError):
    pass


def canonical_hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")).hexdigest()


def _number(point, path):
    text = point.findtext(path, namespaces=NS)
    if text is None:
        return None
    try:
        value = float(text)
    except (ValueError, OverflowError):
        raise PftInputError("TCX_METRIC_NOT_NUMERIC") from None
    if not math.isfinite(value):
        raise PftInputError("TCX_METRIC_NOT_FINITE")
    return value


def parse_recording(raw: bytes):
    if not raw or len(raw) > MAX_PFT_IMPORT_BYTES:
        raise PftInputError("TCX_EMPTY_OR_OVER_SIZE_LIMIT")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise PftInputError("TCX_UTF8_REQUIRED") from None
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise PftInputError("TCX_DTD_OR_ENTITY_NOT_SUPPORTED")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise PftInputError("TCX_XML_INVALID") from None
    activities = root.findall(".//t:Activity", NS)
    if len(activities) != 1 or activities[0].get("Sport") != "Running":
        raise PftInputError("PFT_RUN_REQUIRES_ONE_RUNNING_ACTIVITY")
    points = activities[0].findall(".//t:Trackpoint", NS)
    if not 1 <= len(points) <= MAX_RECORDING_SAMPLES:
        raise PftInputError("TCX_TRACKPOINT_COUNT_INVALID")
    samples = []
    origin = None
    previous = None
    for point in points:
        try:
            timestamp = datetime.fromisoformat(point.findtext("t:Time", namespaces=NS).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise PftInputError("TCX_TIMESTAMP_INVALID") from None
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise PftInputError("TCX_TIMEZONE_REQUIRED")
        timestamp = timestamp.astimezone(UTC)
        if previous is not None and timestamp <= previous:
            raise PftInputError("TCX_TIMESTAMPS_NOT_STRICTLY_INCREASING")
        origin = origin or timestamp
        previous = timestamp
        hr = _number(point, "t:HeartRateBpm/t:Value")
        power = _number(point, "t:Extensions/a:TPX/a:Watts")
        if hr is not None and hr <= 0:
            hr = None
        if power is not None and power < 0:
            raise PftInputError("TCX_POWER_NEGATIVE")
        samples.append(RawSample(
            timestamp=timestamp, elapsed_s=(timestamp-origin).total_seconds(),
            hr_bpm=hr, power_w=power,
            distance_m=_number(point, "t:DistanceMeters"),
            cadence_rpm=_number(point, "t:Cadence"),
            latitude_deg=_number(point, "t:Position/t:LatitudeDegrees"),
            longitude_deg=_number(point, "t:Position/t:LongitudeDegrees"),
            altitude_m=_number(point, "t:AltitudeMeters"),
        ))
    session = ImportedSession(started_at=origin, samples=tuple(samples))
    if session.duration_s > 14400:
        raise PftInputError("TCX_RECORDING_DURATION_OVER_LIMIT")
    return session


def recording_hash(session):
    values = []
    for sample in session.samples:
        value = asdict(sample)
        value["timestamp"] = sample.timestamp.astimezone(UTC).isoformat()
        values.append(value)
    return canonical_hash({"started_at": session.started_at.isoformat(), "samples": values})


def sample_payload(session):
    values = []
    previous = None
    for sample in session.samples:
        speed = None
        if previous is not None and sample.distance_m is not None and previous.distance_m is not None:
            duration = sample.elapsed_s-previous.elapsed_s
            distance = sample.distance_m-previous.distance_m
            if duration > 0 and distance >= 0:
                speed = distance/duration
        values.append(dict(
            asdict(sample), timestamp=sample.timestamp.isoformat(),
            speed_mps_derived=speed,
            speed_source="TCX_DISTANCE_DIFFERENCE_OVER_OBSERVED_TIME",
        ))
        previous = sample
    return values


def processing_manifest(context):
    rules = PftProcessingRules()
    source = Path(paddletrainer_physiology.__file__).resolve().parent
    build = canonical_hash({
        p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(source.rglob("*.py"))
    })
    return {
        "schema_version": "pft_processing_manifest_v0.1",
        "adapter": PFT_ADAPTER_VERSION,
        "engine_version": paddletrainer_physiology.__version__,
        "engine_source_hash": build,
        "numpy_version": numpy.__version__, "scipy_version": scipy.__version__,
        "processing_rules": asdict(rules),
        "context": context.model_dump(mode="json"),
    }


def process_recording(raw, context: PftMeasurementContext):
    whole = parse_recording(raw)
    offset = context.pft_start_offset_s
    selected = tuple(
        RawSample(**dict(asdict(s), elapsed_s=s.elapsed_s-offset))
        for s in whole.samples if offset <= s.elapsed_s <= offset+810.0
    )
    if not selected or len(selected) > MAX_PROCESSING_SAMPLES:
        raise PftInputError("PFT_SELECTED_SAMPLE_COUNT_INVALID")
    session = ImportedSession(started_at=whole.started_at+timedelta(seconds=offset), samples=selected)
    protocol = pft_run_v01()
    result = process_pft(session=session, protocol=protocol)
    profile = {
        "schema_version": "0.1", "profile_id": context.profile_id,
        "protocol": {"name": protocol.name, "version": protocol.version},
        "target_power_w": context.target_power_w.model_dump(),
        "modality": "RUNNING", "hr_acquisition": context.sensor_modality,
        "power_origin": context.power_origin,
    }
    observed = build_pft_reference_context(
        session=session, protocol=protocol, profile=profile,
        raw_source_sha256=hashlib.sha256(raw).hexdigest(),
    )
    document = {
        "schema_version": "pft_api_measurement_v0.1",
        "processing_output": pft_output_to_dict(build_pft_output_contract(session=session, result=result)),
        "observed_context": observed,
        "declared_context": context.model_dump(mode="json"),
        "provenance": {
            "source_kind": "TCX_UPLOAD", "source_raw_sha256": hashlib.sha256(raw).hexdigest(),
            "recording_hash": recording_hash(whole),
            "time_origin": "FIRST_TCX_TRACKPOINT_PLUS_DECLARED_PFT_START_OFFSET",
            "sensor_statement_source": "USER_DECLARATION",
            "sensor_identity_verified": False, "hr_kinetics_accuracy_verified": False,
            "environment_statement_source": "USER_DECLARATION",
            "provider_identity_or_api_match_verified": False,
        },
        "state_estimation_authorized": False,
        "training_plan_modification_authorized": False,
        "causal_prediction_authorized": False,
    }
    return whole, session, processing_manifest(context), document


def comparable_context(context):
    return {key: context[key] for key in (
        "protocol_version", "profile_id", "target_power_w", "sensor_model",
        "sensor_modality", "power_origin", "recovery_mode", "preparation_id"
    )}
