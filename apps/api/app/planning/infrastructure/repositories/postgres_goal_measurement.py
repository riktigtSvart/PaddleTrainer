"""Append the scalar source and its parent in the caller-owned transaction."""

import json
from datetime import UTC
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from app.models.entities import Assessment, AssessmentType, Measurement

from ...domain.common.serialization import canonical_json
from ...domain.common.time import to_utc
from ...domain.goals.assessment import (
    MEASUREMENT_EXECUTION_KEY,
    MEASUREMENT_SOURCE_SCHEMA,
    CapturedGoalMeasurement,
    GoalMeasurementSourceKind,
    measurement_packet,
)
from ...domain.goals.measurement_registration import measurement_float
from ...ports.goal_measurement_write import GoalMeasurementWriteConflict


class SqlAlchemyGoalMeasurementWriter:
    def __init__(self, session):
        self.session = session

    async def save(self, registration):
        # Validate the exact future C2 source envelope, including its byte limit,
        # before writing a source that C2 could not subsequently capture.
        self._snapshot(registration)
        parent_id = UUID(registration.assessment_id)
        measurement_id = UUID(registration.measurement_id)
        for model, identity in ((Assessment, parent_id), (Measurement, measurement_id)):
            result = await self.session.execute(select(model.id).where(model.id == identity))
            if result.scalar_one_or_none() is not None:
                raise GoalMeasurementWriteConflict(
                    "Goal measurement source identity already exists."
                )
        link = {"artifact_id": registration.artifact_id, "content_hash": registration.content_hash}
        self.session.add(
            Assessment(
                id=parent_id,
                user_id=UUID(registration.athlete_id),
                assessment_type=AssessmentType.OTHER,
                sport=None,
                title="Goal measurement: " + registration.proposal.endpoint_key[:170],
                performed_at=registration.execution.started_at,
                source="GOAL_PROTOCOL",
                notes=None,
                extra_data={"goal_measurement_registration": link},
                created_at=registration.created_at,
            )
        )
        await self.session.flush()
        self.session.add(
            Measurement(
                id=measurement_id,
                assessment_id=parent_id,
                metric_key=registration.metric_key,
                value_float=measurement_float(registration.proposal.value),
                value_text=None,
                unit=registration.metric_unit,
                sport=None,
                extra_data={
                    MEASUREMENT_EXECUTION_KEY: json.loads(canonical_json(registration.execution)),
                    "goal_measurement_registration": link,
                },
                created_at=registration.created_at,
            )
        )
        await self.session.flush()

    def _utc(self, value):
        if value.tzinfo is None and self.session.get_bind().dialect.name == "sqlite":
            value = value.replace(tzinfo=UTC)
        return to_utc(value, field_name="measurement source time")

    def _snapshot(self, registration, measurement=None, parent=None):
        link = {"artifact_id": registration.artifact_id, "content_hash": registration.content_hash}
        extra = {
            MEASUREMENT_EXECUTION_KEY: json.loads(canonical_json(registration.execution)),
            "goal_measurement_registration": link,
        }
        packet = {
            "schema_version": MEASUREMENT_SOURCE_SCHEMA,
            "source_kind": GoalMeasurementSourceKind.ASSESSMENT_MEASUREMENT.value,
            "source_id": registration.measurement_id,
            "athlete_id": registration.athlete_id,
            "parent_id": registration.assessment_id,
            "metric_key": registration.metric_key,
            "value_float_text": repr(measurement_float(registration.proposal.value)),
            "value_text": None,
            "unit": registration.metric_unit,
            "measured_at": registration.execution.started_at,
            "created_at": registration.created_at,
            "parent_created_at": registration.created_at,
            "sport": None,
            "parent_sport": None,
            "source_label": "GOAL_PROTOCOL",
            "extra_data": extra,
            "parent_extra_data": {"goal_measurement_registration": link},
            "period_start": None,
            "period_end": None,
            "device_id": None,
            "device_model": None,
            "quality": None,
            "source_record_id": None,
            "parent_type": "OTHER",
            "parent_title": "Goal measurement: " + registration.proposal.endpoint_key[:170],
            "parent_notes": None,
        }
        if measurement is not None:
            packet.update(
                source_id=str(measurement.id),
                athlete_id=str(parent.user_id),
                parent_id=str(parent.id),
                metric_key=measurement.metric_key,
                value_float_text=repr(measurement.value_float)
                if measurement.value_float is not None
                else None,
                value_text=measurement.value_text,
                unit=measurement.unit,
                measured_at=self._utc(parent.performed_at),
                created_at=self._utc(measurement.created_at),
                parent_created_at=self._utc(parent.created_at),
                sport=measurement.sport.value if measurement.sport else None,
                parent_sport=parent.sport.value if parent.sport else None,
                source_label=parent.source,
                extra_data=measurement.extra_data,
                parent_extra_data=parent.extra_data,
                parent_type=parent.assessment_type.value,
                parent_title=parent.title,
                parent_notes=parent.notes,
            )
        encoded = canonical_json(packet)
        source = CapturedGoalMeasurement(
            GoalMeasurementSourceKind.ASSESSMENT_MEASUREMENT,
            packet["source_id"],
            encoded,
            sha256(encoded.encode()).hexdigest(),
        )
        measurement_packet(source)
        return source

    async def verify(self, registration):
        result = await self.session.execute(
            select(Measurement, Assessment)
            .join(Assessment, Assessment.id == Measurement.assessment_id)
            .where(Measurement.id == UUID(registration.measurement_id))
            .execution_options(populate_existing=True)
        )
        row = result.one_or_none()
        if row is None or self._snapshot(registration, *row) != self._snapshot(registration):
            raise GoalMeasurementWriteConflict("Goal measurement source read-back differs.")
