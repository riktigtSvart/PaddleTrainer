"""Declared places, recurring opportunities and dated exceptions; no workout mutations."""

from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StringConstraints, model_validator

from app.planning.domain.calendar_constraints import calendar_day
from app.schemas.calendar_constraints import Clock, Closed, Day

Text = Annotated[str, StringConstraints(max_length=200)]
Sport = Literal["KAYAK", "RUNNING", "SWIMMING", "STRENGTH", "CYCLING", "GYMNASTICS", "STRETCHING"]


class Location(Closed):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["fixed", "mobile"] = "fixed"
    sports: list[Sport] = Field(min_length=1, max_length=7)
    resources: list[Text] = Field(default_factory=list, max_length=32)
    combine_allowed: bool = Field(default=False, strict=True)
    boat_transport: bool = Field(default=False, strict=True)
    notes: str = Field(default="", max_length=2000)
    archived: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        if self.name != self.name.strip() or not self.name.strip():
            raise ValueError("Use a trimmed location name.")
        if len(set(self.sports)) != len(self.sports) or len(set(self.resources)) != len(self.resources):
            raise ValueError("Location possibilities must be unique.")
        if any(not resource.strip() or resource != resource.strip() for resource in self.resources):
            raise ValueError("Resources must be nonempty and trimmed.")
        return self


class SlotDetails(Closed):
    start_time: Clock
    end_time: Clock
    ends_next_day: bool = Field(default=False, strict=True)
    start_fold: Literal[0, 1] | None = None
    end_fold: Literal[0, 1] | None = None
    max_minutes: int = Field(ge=1, le=1440, strict=True)
    location_ids: list[UUID] = Field(min_length=1, max_length=32)
    effort_cap: Literal["easy", "moderate", "any"] = "any"
    combine_allowed: bool = Field(default=False, strict=True)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def explicit_fold(cls, value):
        if isinstance(value, dict) and any(value.get(k) is not None and type(value[k]) is not int for k in ("start_fold", "end_fold")):
            raise ValueError("A repeated-hour fold is an integer.")
        return value

    @model_validator(mode="after")
    def coherent(self):
        a = int(self.start_time[:2]) * 60 + int(self.start_time[3:])
        b = int(self.end_time[:2]) * 60 + int(self.end_time[3:])
        span = b - a + 1440 * self.ends_next_day
        if not self.ends_next_day and self.start_fold == 0 and self.end_fold == 1 and -60 < span <= 0:
            span += 60
        if not 0 < span <= 1440 or self.max_minutes > span:
            raise ValueError("The opportunity must fit its local time window.")
        if len(set(self.location_ids)) != len(self.location_ids):
            raise ValueError("Location alternatives must be unique.")
        return self


class WeeklySlot(Closed):
    id: UUID
    start_date: Day
    end_date: Day | None = None
    weekdays: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(min_length=1, max_length=7)
    details: SlotDetails


class SlotException(Closed):
    slot_id: UUID
    date: Day
    replacement: SlotDetails | None


class LocationRestriction(Closed):
    id: UUID
    location_id: UUID
    start_date: Day
    end_date: Day
    unavailable_sports: list[Sport] = Field(min_length=1, max_length=7)
    reason: str = Field(default="", max_length=1000)


class OptionsData(Closed):
    timezone_name: str = Field(min_length=1, max_length=64)
    schedule_start_date: Day | None = None
    schedule_end_date: Day | None = None
    locations: list[Location] = Field(default_factory=list, max_length=64)
    weekly_slots: list[WeeklySlot] = Field(default_factory=list, max_length=128)
    exceptions: list[SlotException] = Field(default_factory=list, max_length=1024)
    restrictions: list[LocationRestriction] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def coherent(self):
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone.") from None
        locations = {location.id: location for location in self.locations}
        if self.schedule_start_date is not None:
            calendar_day(self.schedule_start_date)
        if self.schedule_end_date is not None:
            calendar_day(self.schedule_end_date)
            if self.schedule_start_date is None or self.schedule_end_date < self.schedule_start_date:
                raise ValueError("The general timetable validity is invalid.")
        if self.weekly_slots and self.schedule_start_date is None:
            raise ValueError("An explicit timetable validity is required.")
        slots = {slot.id: slot for slot in self.weekly_slots}
        if len(locations) != len(self.locations) or len(slots) != len(self.weekly_slots):
            raise ValueError("Location and slot identities must be unique.")
        names = [location.name.casefold() for location in self.locations if not location.archived]
        if len(set(names)) != len(names):
            raise ValueError("Active location names must be unique.")
        for slot in self.weekly_slots:
            calendar_day(slot.start_date)
            if slot.end_date is not None:
                calendar_day(slot.end_date)
                if slot.end_date < slot.start_date:
                    raise ValueError("A slot date range is reversed.")
            if slot.weekdays != sorted(set(slot.weekdays)) or not set(slot.details.location_ids) <= locations.keys():
                raise ValueError("Use ordered weekdays and known location identities.")
        seen = set()
        for exception in self.exceptions:
            day = calendar_day(exception.date)
            key = exception.slot_id, exception.date
            slot = slots.get(exception.slot_id)
            if key in seen or slot is None or exception.date < slot.start_date or slot.end_date and exception.date > slot.end_date or day.weekday() not in slot.weekdays:
                raise ValueError("The exception must refer to one existing occurrence.")
            seen.add(key)
            if exception.replacement and not set(exception.replacement.location_ids) <= locations.keys():
                raise ValueError("The dated alternative references an unknown location.")
        ids = set()
        for restriction in self.restrictions:
            calendar_day(restriction.start_date)
            calendar_day(restriction.end_date)
            if restriction.id in ids or restriction.location_id not in locations or restriction.end_date < restriction.start_date or len(set(restriction.unavailable_sports)) != len(restriction.unavailable_sports):
                raise ValueError("A location restriction is invalid.")
            ids.add(restriction.id)
        return self


class OptionsReference(Closed):
    artifact_id: str = Field(pattern=r"^pt-training-options:[a-f0-9]{32}:[a-f0-9]{32}$")
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class OptionsInput(Closed):
    request_id: UUID
    previous_reference: OptionsReference | None
    data: OptionsData
