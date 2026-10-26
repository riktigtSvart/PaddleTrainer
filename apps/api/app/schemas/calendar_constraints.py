"""Declared calendar opportunities/commitments; no workout or dose mutations."""

from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.athlete_setup import AvailabilityInput

Day = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Clock = Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]
Short = Annotated[str, StringConstraints(max_length=200)]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScheduleReference(Closed):
    artifact_id: str = Field(pattern=r"^pt-calendar-constraints:[a-f0-9]{32}:[a-f0-9]{32}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class EntryDetails(Closed):
    kind: Literal["busy", "available"]
    category: Literal["work", "travel", "personal", "other", "training"]
    title: str = Field(min_length=1, max_length=100)
    firmness: Literal["fixed", "flexible"]
    start_time: Clock
    end_time: Clock
    ends_next_day: bool = Field(strict=True)
    start_fold: Literal[0, 1] | None
    end_fold: Literal[0, 1] | None
    max_minutes: int | None = Field(ge=1, le=1440, strict=True)
    sport_scope: Literal["unknown", "any", "specified"]
    sports: list[Short] = Field(max_length=16)
    effort_cap: Literal["unknown", "easy", "moderate", "any"]
    resources: list[Short] = Field(max_length=32)
    location: Short
    notes: str = Field(max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def deliberate_folds(cls, value):
        if isinstance(value, dict):
            for key in ("start_fold", "end_fold"):
                if value.get(key) is not None and type(value[key]) is not int:
                    raise ValueError("Fold must be an integer, not a boolean or float.")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if not self.title.strip() or self.title != self.title.strip():
            raise ValueError("Use a nonempty trimmed title.")
        if (self.kind == "available") != (self.category == "training"):
            raise ValueError("Training opportunities use the training category.")
        if (self.kind == "available") != (self.max_minutes is not None):
            raise ValueError("Only training opportunities have a training-minute budget.")
        if (self.sport_scope == "specified") != bool(self.sports):
            raise ValueError("Specified sports need a nonempty list.")
        if len(set(self.sports)) != len(self.sports) or len(set(self.resources)) != len(self.resources):
            raise ValueError("Lists must be unique.")
        a, b = int(self.start_time[:2]) * 60 + int(self.start_time[3:]), int(self.end_time[:2]) * 60 + int(self.end_time[3:])
        span = b + 1440 * self.ends_next_day - a
        if not self.ends_next_day and self.start_fold == 0 and self.end_fold == 1 and -60 < span <= 0:
            span += 60
        if not 0 < span <= 1440:
            raise ValueError("Use a positive local interval of at most one day.")
        if self.max_minutes is not None and self.max_minutes > span:
            raise ValueError("Training minutes must fit the declared local window.")
        return self


class CalendarRule(Closed):
    id: UUID
    start_date: Day
    end_date: Day | None
    repeat: Literal["once", "weekly"]
    weekdays: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(max_length=7)
    details: EntryDetails


class CalendarException(Closed):
    rule_id: UUID
    date: Day
    replacement: EntryDetails | None


class ScheduleData(Closed):
    timezone_name: str = Field(min_length=1, max_length=64)
    rules: list[CalendarRule] = Field(max_length=512)
    exceptions: list[CalendarException] = Field(max_length=4096)

    @model_validator(mode="after")
    def timezone_exists(self):
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown calendar timezone.") from None
        return self


class ScheduleInput(Closed):
    request_id: UUID
    previous_reference: ScheduleReference | None
    data: ScheduleData


class SchedulePreview(Closed):
    proposal: ScheduleInput
    start_date: Day
    end_date: Day
    availability_proposal: AvailabilityInput | None = None
