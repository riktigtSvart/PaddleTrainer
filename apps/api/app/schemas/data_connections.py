"""Explicit bounded import requests; provider access is never implied by a GET."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataSyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    provider: Literal["POLAR", "GARMIN", "SUUNTO"]
    datasets: list[Literal["sessions", "targets"]] = Field(min_length=1, max_length=2)
    past_days: int = Field(default=35, ge=1, le=89, strict=True)
    future_days: int = Field(default=30, ge=0, le=30, strict=True)

    @field_validator("datasets")
    @classmethod
    def unique_datasets(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Dataset names must be unique.")
        return values
