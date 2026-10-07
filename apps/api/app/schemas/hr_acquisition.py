"""Only user-observable acquisition details may enter a sensor declaration."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ProviderId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SensorLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SensorModality = Literal["OPTICAL_PPG", "ELECTRICAL", "OTHER", "UNKNOWN"]
BodyLocation = Literal["WRIST", "CHEST", "UPPER_ARM", "FOREARM", "OTHER", "UNKNOWN"]
ReportedIssue = Literal["LOOSE_CONTACT", "SIGNAL_DROPOUT", "SENSOR_MOVED", "OTHER"]


class HRAcquisitionDeclarationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercise_external_id: ProviderId
    sensor_modality: SensorModality
    body_location: BodyLocation = "UNKNOWN"
    sensor_manufacturer: SensorLabel | None = None
    sensor_model: SensorLabel | None = None
    reported_issue_codes: list[ReportedIssue] = Field(default_factory=list, max_length=4)
    supersedes_declaration_ids: list[str] = Field(default_factory=list, max_length=512)

    @field_validator("exercise_external_id", "sensor_manufacturer", "sensor_model")
    @classmethod
    def printable_labels(cls, value):
        if value is not None and any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Control characters are not supported")
        return value

    @field_validator("reported_issue_codes")
    @classmethod
    def canonical_issues(cls, value):
        return sorted(set(value))

    @field_validator("supersedes_declaration_ids")
    @classmethod
    def canonical_predecessors(cls, value):
        normalized = [str(UUID(item)) for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("A declaration may only be superseded once in a request")
        return sorted(normalized)
