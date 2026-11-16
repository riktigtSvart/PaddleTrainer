"""Explicit bounded import requests; provider access is never implied by a GET."""

from typing import Literal
from uuid import UUID
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator


class HistoryRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    to_exclusive: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def bounded_dates(self):
        first, last = date.fromisoformat(self.from_date), date.fromisoformat(self.to_exclusive)
        if first.year < 1900 or not 1 <= (last - first).days <= 90:
            raise ValueError("Use one to ninety whole days, ending exclusively.")
        return self


class DataSyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    provider: Literal["POLAR", "GARMIN", "SUUNTO"]
    datasets: list[Literal["sessions", "targets", "session_details"]] = Field(min_length=1, max_length=3)
    past_days: int = Field(default=35, ge=1, le=89, strict=True)
    future_days: int = Field(default=30, ge=0, le=30, strict=True)
    history_range: HistoryRange | None = None

    @model_serializer(mode="wrap")
    def preserve_older_shape(self, handler):
        value = handler(self)
        if self.history_range is None:
            value.pop("history_range", None)
        return value

    @model_validator(mode="after")
    def historical_summaries_only(self):
        if self.history_range is not None and (self.provider != "POLAR" or self.datasets != ["sessions"] or self.future_days != 0):
            raise ValueError("Historical imports request completed Polar session summaries only.")
        return self

    @field_validator("datasets")
    @classmethod
    def unique_datasets(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Dataset names must be unique.")
        return values
