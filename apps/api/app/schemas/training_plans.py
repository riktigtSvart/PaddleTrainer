from typing import Literal

from pydantic import Field, model_validator

from app.schemas.athlete_setup import Closed
from app.schemas.planning_cycles import Day, Digest, Token


class ReviewInput(Closed):
    start_date: Day
    end_date: Day


class ReviewReference(Closed):
    artifact_id: str = Field(pattern=r"^pt-training-plan:[0-9a-f]{64}$")
    content_hash: Digest


class AcceptInput(Closed):
    request_id: Token
    review_reference: ReviewReference
    acknowledge_reviewed_plan: Literal[True]

    @model_validator(mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if isinstance(value, dict) and value.get("acknowledge_reviewed_plan") is not True:
            raise ValueError("An explicit review acknowledgement is required.")
        return value


class MissedInput(Closed):
    request_id: Token
    workout_id: Token
    expected_workout_hash: Digest


class ChoiceInput(Closed):
    review_reference: ReviewReference
    date: Day
    candidate_key: Digest
