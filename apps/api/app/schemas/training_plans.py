from typing import Literal

from pydantic import Field, StrictBool, model_validator

from app.schemas.athlete_setup import Closed
from app.schemas.planning_cycles import Day, Digest, Token


class SameDayReplacement(Closed):
    schema_version: Literal['same-day-training-replacement-v0.1']
    workout_id: Token
    confirmed_not_started: Literal[True]

    @model_validator(mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if isinstance(value,dict) and value.get('confirmed_not_started') is not True:
            raise ValueError('Confirm that this workout has not started')
        return value


class AlternativesFor(Closed):
    schema_version: Literal['workout-alternatives-request-v0.1']
    workout_id: Token
    expected_workout_hash: Digest


class ReviewInput(Closed):
    start_date: Day
    end_date: Day
    coordinate_mesocycles: StrictBool | None = None
    same_day_replacement: SameDayReplacement | None = None
    alternatives_for: AlternativesFor | None = None

    @model_validator(mode='after')
    def one_scope(self):
        if self.same_day_replacement is not None and self.alternatives_for is not None:
            raise ValueError('Use one replacement scope')
        return self


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


class SavedChoiceInput(Closed):
    expected_workout_hash: Digest
    source_review_reference: ReviewReference
    candidate_key: Digest
