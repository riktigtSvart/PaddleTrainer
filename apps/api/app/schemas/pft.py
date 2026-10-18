"""Declarations accompany a recording; they cannot confer physiological authority."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class PftPowerTargets(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    p0: FiniteFloat = Field(gt=0, le=10000)
    p1: FiniteFloat = Field(gt=0, le=10000)
    p2: FiniteFloat = Field(gt=0, le=10000)

    @model_validator(mode="after")
    def increasing_targets(self):
        if not self.p0 < self.p1 < self.p2:
            raise ValueError("PFT power targets must increase from P0 to P1 to P2.")
        return self


class PftMeasurementContext(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    protocol_version: Literal["0.1"] = "0.1"
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    target_power_w: PftPowerTargets
    pft_start_offset_s: FiniteFloat = Field(default=0.0, ge=0, le=14400)
    targets_prespecified: bool = False
    sensor_model: str | None = Field(default=None, min_length=1, max_length=100)
    sensor_modality: Literal["WRIST_OPTICAL", "CHEST_STRAP", "UNKNOWN"] = "UNKNOWN"
    power_origin: Literal["POLAR_RUNNING_POWER_ESTIMATE", "EXTERNAL_SENSOR", "UNKNOWN"] = "UNKNOWN"
    recovery_mode: Literal["PASSIVE", "ACTIVE", "UNKNOWN"] = "UNKNOWN"
    preparation_id: str | None = Field(default=None, min_length=1, max_length=100)
    air_temperature_c: FiniteFloat | None = Field(default=None, ge=-80, le=70)
    relative_humidity_pct: FiniteFloat | None = Field(default=None, ge=0, le=100)
    hydration_note: str | None = Field(default=None, max_length=300)
    illness_note: str | None = Field(default=None, max_length=300)
    sleep_note: str | None = Field(default=None, max_length=300)
    device_body_weight_setting_kg: FiniteFloat | None = Field(default=None, gt=0, le=500)


class PftComparisonRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    reference_measurement_id: str = Field(min_length=36, max_length=36)
