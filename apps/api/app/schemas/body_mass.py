"""A dated observation is distinct from a nutrition intention."""
from typing import Annotated, Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.schemas.planning_cycles import Day, Digest, Token

Mass = Annotated[str, StringConstraints(pattern=r'^(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,6})?$')]

class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class BodyMassInput(Closed):
    request_id: Token
    value_kg: Mass
    recorded_on: Day
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ''

    @model_validator(mode='after')
    def positive(self):
        if Decimal(self.value_kg) <= 0: raise ValueError('Mass must be positive.')
        return self

class NutritionReference(Closed):
    artifact_id: Annotated[str, StringConstraints(pattern=r'^pt-nutrition:[0-9a-f]{64}$')]
    content_hash: Digest

class NutritionGoalInput(Closed):
    request_id: Token
    previous_reference: NutritionReference | None
    goal: Literal['weight_loss', 'weight_maintenance', 'weight_gain', 'recomposition']
    target_kg: Mass | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ''

    @model_validator(mode='after')
    def target(self):
        needs = self.goal in {'weight_loss', 'weight_gain'}
        if needs != (self.target_kg is not None): raise ValueError('A loss/gain goal needs a target; maintenance and recomposition do not.')
        if self.target_kg is not None and Decimal(self.target_kg) <= 0: raise ValueError('Target must be positive.')
        return self
