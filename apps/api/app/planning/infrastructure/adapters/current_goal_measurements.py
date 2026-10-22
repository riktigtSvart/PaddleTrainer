"""One SQL statement freezes both existing measurement families.

Source created_at fields are application metadata, not proof of historical
database availability. Mutable rows are observed at capture time only.
"""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import DateTime, String, cast, literal, select, union_all

from app.models.entities import Assessment, Measurement, PhysiologicalMeasurement

from ...domain.common.serialization import canonical_json
from ...domain.common.time import to_utc
from ...domain.goals.assessment import (
    GOAL_MEASUREMENT_CENSUS_LIMIT,
    MEASUREMENT_SOURCE_SCHEMA,
    CapturedGoalMeasurement,
    GoalMeasurementSourceKind,
    measurement_packet,
)


class SqlAlchemyGoalMeasurementSource:
    def __init__(self, session):
        self.session = session

    async def capture(self, *, athlete_id, starts_at, ends_at, recorded_before):
        owner = UUID(athlete_id)
        start = to_utc(starts_at, field_name="starts_at")
        end = to_utc(ends_at, field_name="ends_at")
        deadline = to_utc(recorded_before, field_name="recorded_before")
        if str(owner) != athlete_id or start > end or end > deadline:
            raise ValueError("Invalid measurement census identity or interval.")
        M, A, P = Measurement, Assessment, PhysiologicalMeasurement
        assessment = (
            select(
                literal(GoalMeasurementSourceKind.ASSESSMENT_MEASUREMENT.value).label(
                    "source_kind"
                ),
                cast(M.id, String).label("source_id"),
                cast(A.user_id, String).label("athlete_id"),
                cast(A.id, String).label("parent_id"),
                M.metric_key,
                M.value_float,
                M.value_text,
                M.unit,
                A.performed_at.label("measured_at"),
                M.created_at,
                A.created_at.label("parent_created_at"),
                M.sport,
                A.sport.label("parent_sport"),
                A.source.label("source_label"),
                M.extra_data,
                A.extra_data.label("parent_extra_data"),
                literal(None, type_=DateTime(timezone=True)).label("period_start"),
                literal(None, type_=DateTime(timezone=True)).label("period_end"),
                literal(None).label("device_id"),
                literal(None).label("device_model"),
                literal(None).label("quality"),
                literal(None).label("source_record_id"),
                A.assessment_type.label("parent_type"),
                A.title.label("parent_title"),
                A.notes.label("parent_notes"),
            )
            .join(A, A.id == M.assessment_id)
            .where(
                A.user_id == owner,
                A.performed_at >= start,
                A.performed_at <= end,
                M.created_at <= deadline,
                A.created_at <= deadline,
            )
        )
        physiological = select(
            literal(GoalMeasurementSourceKind.PHYSIOLOGICAL_MEASUREMENT.value),
            cast(P.id, String),
            cast(P.user_id, String),
            literal(None),
            P.metric_key,
            P.value_float,
            P.value_text,
            P.unit,
            P.measured_at,
            P.created_at,
            literal(None),
            literal(None),
            literal(None),
            P.provider,
            P.extra_data,
            literal(None),
            P.period_start,
            P.period_end,
            P.device_id,
            P.device_model,
            P.quality,
            P.source_record_id,
            literal(None),
            literal(None),
            literal(None),
        ).where(
            P.user_id == owner,
            P.measured_at >= start,
            P.measured_at <= end,
            P.created_at <= deadline,
        )
        combined = union_all(assessment, physiological).subquery()
        result = await self.session.execute(
            select(combined)
            .order_by(combined.c.source_kind, combined.c.source_id)
            .limit(GOAL_MEASUREMENT_CENSUS_LIMIT)
        )
        rows = result.mappings().all()
        if len(rows) >= GOAL_MEASUREMENT_CENSUS_LIMIT:
            raise ValueError("Measurement census limit reached; partial assessment is forbidden.")
        sources = []
        for row in rows:
            packet = dict(row)
            packet["schema_version"] = MEASUREMENT_SOURCE_SCHEMA
            for key in ("source_id", "athlete_id", "parent_id"):
                if packet[key] is not None:
                    packet[key] = str(UUID(packet[key]))
            for key, value in tuple(packet.items()):
                if isinstance(value, datetime):
                    if value.tzinfo is None and self.session.get_bind().dialect.name == "sqlite":
                        value = value.replace(tzinfo=UTC)
                    packet[key] = to_utc(value, field_name=key)
                elif hasattr(value, "value"):
                    packet[key] = value.value
            raw_number = packet.pop("value_float")
            packet["value_float_text"] = repr(raw_number) if raw_number is not None else None
            encoded = canonical_json(packet)
            source = CapturedGoalMeasurement(
                GoalMeasurementSourceKind(packet["source_kind"]),
                packet["source_id"],
                encoded,
                sha256(encoded.encode("utf-8")).hexdigest(),
            )
            measurement_packet(source)
            sources.append(source)
        return tuple(sorted(sources, key=lambda s: (s.source_kind.value, s.source_id)))
