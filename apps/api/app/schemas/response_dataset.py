"""Read-only dataset assembly options; split rows cannot select fragments."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.response_dataset_split import MAX_ASSIGNMENTS, validate_split_manifest


class DatasetSplitAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: Literal["POLAR"]
    athlete_id: str = Field(min_length=1, max_length=200)
    session_external_id: str = Field(min_length=1, max_length=200)
    split: Literal["TRAIN", "VALIDATION", "TEST"]


class DatasetSplitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["0.1"]
    manifest_id: str = Field(min_length=1, max_length=200)
    assignments: list[DatasetSplitAssignment] = Field(min_length=1, max_length=MAX_ASSIGNMENTS)

    @model_validator(mode="after")
    def validate_whole_session_assignments(self) -> Self:
        validate_split_manifest(self.model_dump())
        return self


class ResponseDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    include_payload: bool = False
    split_manifest: DatasetSplitManifest | None = None
