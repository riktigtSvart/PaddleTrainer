"""An athlete-authored prescription, separate from measured or executed training."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import Sport
from app.planning.domain.goals.catalog import CapabilityKey
from app.schemas.planning_calendar import GoalReference


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ManualPhase(Closed):
    block_type: Literal["WARMUP", "WORK", "RECOVERY", "COOLDOWN"]
    name: str = Field(min_length=1, max_length=120)
    duration_sec: int | None = Field(default=None, strict=True, ge=1, le=86400)
    distance_m: float | None = Field(default=None, strict=True, gt=0, le=1000000, allow_inf_nan=False)
    repeat_count: int = Field(default=1, strict=True, ge=1, le=100)
    recovery_duration_sec: int | None = Field(default=None, strict=True, ge=0, le=86400)
    notes: str = Field(default="", max_length=2000)
    intensity_type: str | None = Field(default=None, max_length=32)
    intensity_min: float | None = Field(default=None, strict=True, ge=0, le=1000000, allow_inf_nan=False)
    intensity_max: float | None = Field(default=None, strict=True, ge=0, le=1000000, allow_inf_nan=False)

    @model_validator(mode="after")
    def intensity_range(self):
        if self.intensity_min is not None and self.intensity_max is not None and self.intensity_min > self.intensity_max:
            raise ValueError("Az intenzitás alsó határa ne legyen nagyobb a felsőnél.")
        return self


class ManualExercise(Closed):
    exercise_id: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=160)
    sets: int = Field(strict=True, ge=1, le=20)
    reps: int | None = Field(default=None, strict=True, ge=1, le=1000)
    hold_seconds: int | None = Field(default=None, strict=True, ge=1, le=3600)
    load_mode: Literal["kg", "bodyweight", "none"]
    weight_kg: str | None = Field(default=None, pattern=r"^(?:0|[1-9]\d{0,3})(?:\.\d{1,3})?$")
    load_basis: Literal["total", "per_hand"] = "total"
    rest_seconds: int = Field(strict=True, ge=0, le=3600)
    reserve_reps: int | None = Field(default=None, strict=True, ge=0, le=10)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def quantities(self):
        if (self.reps is None) == (self.hold_seconds is None):
            raise ValueError("Gyakorlatonként ismétlésszámot vagy tartási időt adj meg.")
        if (self.load_mode == "kg") != (self.weight_kg is not None):
            raise ValueError("Súlyzós gyakorlatnál add meg a terhelést kilogrammban.")
        if self.weight_kg is not None and not Decimal(self.weight_kg) > 0:
            raise ValueError("A megadott súly legyen nagyobb nullánál.")
        return self


class ManualDraft(Closed):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")
    start_fold: Literal[0, 1] | None = None
    sport: Sport
    title: str = Field(min_length=1, max_length=200)
    duration_sec: int = Field(strict=True, ge=60, le=86400)
    distance_m: float | None = Field(default=None, strict=True, gt=0, le=1000000, allow_inf_nan=False)
    description: str = Field(default="", max_length=20000)
    location: str = Field(default="", max_length=200)
    intensity_type: str | None = Field(default=None, max_length=32)
    primary_goal: CapabilityKey | Literal["RECOVERY", "MIXED"] | None = None
    mesocycle_id: UUID | None = None
    phases: list[ManualPhase] = Field(default_factory=list, max_length=50)
    exercises: list[ManualExercise] = Field(default_factory=list, max_length=40)

    @field_validator("date")
    @classmethod
    def valid_day(cls, value):
        day = date.fromisoformat(value)
        if value != day.isoformat() or not date(1900, 1, 1) <= day <= date(2100, 12, 31):
            raise ValueError("A dátum 1900 és 2100 közé essen.")
        return value

    @field_validator("start_fold", mode="before")
    @classmethod
    def strict_fold(cls, value):
        if value is not None and type(value) is not int:
            raise ValueError("Az óraátállítás választása nem értelmezhető.")
        return value

    @model_validator(mode="after")
    def timing(self):
        if self.start_time is None and self.start_fold is not None:
            raise ValueError("Óraátállítási választáshoz kezdési idő is szükséges.")
        if sum((p.duration_sec or 0) * p.repeat_count + (p.recovery_duration_sec or 0) * (p.repeat_count - 1) for p in self.phases) > self.duration_sec:
            raise ValueError("Az edzésszakaszok összes ideje hosszabb a teljes edzésidőnél.")
        if sum(2 * p.repeat_count - 1 if p.recovery_duration_sec else 1 for p in self.phases) > 1000:
            raise ValueError("Legfeljebb 1000 tényleges munkaszakasz és pihenő tervezhető egy alkalomba.")
        if self.exercises and self.sport != Sport.STRENGTH:
            raise ValueError("Az erősítő gyakorlatokhoz válaszd a Kondi sportágat.")
        return self


class ManualSave(Closed):
    request_id: UUID
    operation: Literal["create", "update", "cancel"]
    timezone_name: str = Field(min_length=1, max_length=100)
    workout_id: UUID | None = None
    expected_source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    expected_goal_reference: GoalReference | None = None
    draft: ManualDraft | None = None
    repeat_dates: list[str] = Field(default_factory=list, max_length=23)
    copy_from: UUID | None = None
    copy_source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def scope(self):
        if self.operation == "create":
            if self.workout_id is not None or self.expected_source_hash is not None or self.expected_goal_reference is not None:
                raise ValueError("Új edzéshez nem tartozhat módosítandó edzés.")
        elif self.workout_id is None or self.expected_source_hash is None or self.repeat_dates or self.copy_from:
            raise ValueError("A módosításhoz az eredeti edzés aktuális változata szükséges.")
        if (self.operation == "cancel") != (self.draft is None):
            raise ValueError("Mentéskor az edzés adatai szükségesek.")
        if (self.copy_from is None) != (self.copy_source_hash is None):
            raise ValueError("A másolás forrása hiányos.")
        for day in self.repeat_dates:
            ManualDraft.valid_day(day)
        if self.draft and len(set([self.draft.date, *self.repeat_dates])) != len(self.repeat_dates) + 1:
            raise ValueError("Az ismétlés dátumai között ne legyen azonos nap.")
        return self
