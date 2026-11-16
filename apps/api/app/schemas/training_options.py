"""Declared places, recurring opportunities and dated exceptions; no workout mutations."""

from typing import Annotated, Literal
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StringConstraints, model_serializer, model_validator

from app.planning.domain.calendar_constraints import calendar_day
from app.schemas.calendar_constraints import Clock, Closed, Day

Text = Annotated[str, StringConstraints(max_length=200)]
Sport = Literal["KAYAK", "RUNNING", "SWIMMING", "STRENGTH", "CYCLING", "GYMNASTICS", "STRETCHING"]


class ExerciseConfirmation(Closed):
    exercise_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    source_kind: Literal["self_report"] = "self_report"
    note: str = Field(default="", max_length=500)


class Coordinates(Closed):
    # Text keeps persisted proposal hashes identical in Python and the browser.
    latitude: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    longitude: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    timezone_name: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent(self):
        if abs(Decimal(self.latitude)) > 90 or abs(Decimal(self.longitude)) > 180:
            raise ValueError("Coordinates are outside the Earth.")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown location timezone.") from None
        return self


class DaylightRule(Closed):
    sport: Sport
    mode: Literal["none", "daylight", "civil_twilight"]
    start_buffer_minutes: int = Field(default=0, ge=0, le=120, strict=True)
    end_buffer_minutes: int = Field(default=0, ge=0, le=120, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        if self.mode == "none" and (self.start_buffer_minutes or self.end_buffer_minutes):
            raise ValueError("An unrestricted sport has no light buffers.")
        return self


class GeographicArea(Closed):
    schema_version: Literal["training-area-v0.1"] = "training-area-v0.1"
    south: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    north: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    west: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    east: str = Field(pattern=r"^-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,7})?$", strict=True)
    timezone_name: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent(self):
        south, north, west, east = map(Decimal, (self.south, self.north, self.west, self.east))
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ValueError("Use ordered latitude/longitude bounds, without crossing the date line.")
        if north - south > 20 or east - west > 20:
            raise ValueError("An exercise area spans at most twenty degrees on each axis.")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown area timezone.") from None
        return self


class Location(Closed):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["fixed", "mobile"] = "fixed"
    sports: list[Sport] = Field(min_length=1, max_length=7)
    resources: list[Text] = Field(default_factory=list, max_length=128)
    exercise_confirmations: list[ExerciseConfirmation] | None = Field(default=None, max_length=128)
    coordinates: Coordinates | None = None
    area: GeographicArea | None = None
    pool_length_m: str | None = Field(default=None, pattern=r"^(?:[1-9][0-9]?|100)(?:\.[0-9]{1,6})?$", strict=True)
    daylight_overrides: list[DaylightRule] | None = Field(default=None, max_length=7)
    combine_allowed: bool = Field(default=False, strict=True)
    boat_transport: bool = Field(default=False, strict=True)
    notes: str = Field(default="", max_length=2000)
    archived: bool = Field(default=False, strict=True)

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        data = handler(self)
        for key in ("exercise_confirmations", "coordinates", "area", "pool_length_m", "daylight_overrides"):
            if getattr(self, key) is None:
                data.pop(key, None)
        return data

    @model_validator(mode="after")
    def coherent(self):
        if self.coordinates is not None and self.area is not None:
            raise ValueError("Use either an exact point or a geographic area.")
        if self.area is not None and self.kind != "mobile":
            raise ValueError("A geographic area belongs to a variable location.")
        if self.pool_length_m is not None and ("SWIMMING" not in self.sports or not 10 <= Decimal(self.pool_length_m) <= 100):
            raise ValueError("Pool length belongs to swimming and is ten to one hundred metres.")
        if self.name != self.name.strip() or not self.name.strip():
            raise ValueError("Use a trimmed location name.")
        if len(set(self.sports)) != len(self.sports) or len(set(self.resources)) != len(self.resources):
            raise ValueError("Location possibilities must be unique.")
        if any(not resource.strip() or resource != resource.strip() for resource in self.resources):
            raise ValueError("Resources must be nonempty and trimmed.")
        rules = self.daylight_overrides or []
        if len({r.sport for r in rules}) != len(rules) or any(r.sport not in self.sports for r in rules):
            raise ValueError("Use one daylight override per available sport.")
        if self.exercise_confirmations is not None:
            from app.services.strength_catalog import catalog
            known = {e['id'] for e in catalog()['exercises']}
            keys = [e.exercise_id for e in self.exercise_confirmations]
            if len(keys) != len(set(keys)) or not set(keys) <= known:
                raise ValueError("Use unique, known exercise identities for this location.")
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


class CurrentTrainingBaseline(Closed):
    from_date: Day
    to_date: Day
    weekly_sessions: int = Field(ge=1, le=28, strict=True)
    weekly_minutes: int = Field(ge=1, le=10080, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        first, last = calendar_day(self.from_date), calendar_day(self.to_date)
        if not 14 <= (last - first).days + 1 <= 56 or self.weekly_minutes < self.weekly_sessions:
            raise ValueError("Describe two to eight weeks of actual training, with positive time per session.")
        return self


class SwimmingAbility(Closed):
    reported_on: Day
    independent: bool = Field(strict=True)
    strokes: list[Literal["freestyle", "breaststroke", "backstroke", "butterfly"]] = Field(min_length=1, max_length=4)
    preferred_stroke: Literal["freestyle", "breaststroke", "backstroke", "butterfly"]
    continuous_distance_m: int | None = Field(default=None, ge=10, le=20000, strict=True)
    continuous_minutes: int | None = Field(default=None, ge=1, le=240, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        calendar_day(self.reported_on)
        if len(set(self.strokes)) != len(self.strokes) or self.preferred_stroke not in self.strokes:
            raise ValueError("Choose a known preferred stroke, without duplicates.")
        return self


class PrescriptionSettings(Closed):
    schema_version: Literal["training-prescription-settings-v0.1"] = "training-prescription-settings-v0.1"
    current_baseline: CurrentTrainingBaseline | None = None
    swimming: SwimmingAbility | None = None


class OptionsData(Closed):
    timezone_name: str = Field(min_length=1, max_length=64)
    schedule_start_date: Day | None = None
    schedule_end_date: Day | None = None
    locations: list[Location] = Field(default_factory=list, max_length=64)
    weekly_slots: list[WeeklySlot] = Field(default_factory=list, max_length=128)
    exceptions: list[SlotException] = Field(default_factory=list, max_length=1024)
    restrictions: list[LocationRestriction] = Field(default_factory=list, max_length=256)
    daylight_rules: list[DaylightRule] | None = Field(default=None, max_length=7)
    prescription_settings: PrescriptionSettings | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        data = handler(self)
        if self.daylight_rules is None:
            data.pop("daylight_rules", None)
        if self.prescription_settings is None:
            data.pop("prescription_settings", None)
        return data

    @model_validator(mode="after")
    def coherent(self):
        rules = self.daylight_rules or []
        if len({r.sport for r in rules}) != len(rules):
            raise ValueError("Use one daylight rule per sport.")
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


class DaylightPreviewInput(Closed):
    date: Day
    coordinates: Coordinates | None = None
    area: GeographicArea | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None}

    @model_validator(mode="after")
    def coherent(self):
        calendar_day(self.date)
        if (self.coordinates is None) == (self.area is None):
            raise ValueError("Provide exactly one geographic point or area.")
        return self
