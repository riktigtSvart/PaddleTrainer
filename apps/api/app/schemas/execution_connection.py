from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ExecutionConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledge_current_state_baseline_only: Literal[True]
    acknowledge_session_identity_only: Literal[True]

    @field_validator("acknowledge_current_state_baseline_only", "acknowledge_session_identity_only", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("An explicit boolean acknowledgement is required")
        return value
