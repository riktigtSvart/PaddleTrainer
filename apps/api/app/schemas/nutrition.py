"""Explicit recipe choices and shopping quantities; no inferred energy requirement."""
from typing import Annotated, Literal
from decimal import Decimal
from datetime import date, timedelta
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.schemas.planning_cycles import Day, Digest, Token

Quantity = Annotated[str, StringConstraints(pattern=r'^(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,3})?$')]
FoodId = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9_]{0,59}$')]
Allergen = Literal['gluten', 'crustaceans', 'eggs', 'fish', 'peanuts', 'soy', 'milk', 'nuts', 'celery', 'mustard', 'sesame', 'sulphites', 'lupin', 'molluscs']


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Preferences(Closed):
    diet: Literal['omnivore', 'pescatarian', 'vegetarian', 'vegan'] = 'omnivore'
    allergens_reviewed: bool = False
    excluded_allergens: list[Allergen] = Field(default_factory=list, max_length=14)
    excluded_foods: list[FoodId] = Field(default_factory=list, max_length=100)
    max_prep_minutes: Literal[15, 30, 45, 60] = 45
    meals_per_day: Literal[3, 4] = 4

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.excluded_allergens)) != len(self.excluded_allergens) or len(set(self.excluded_foods)) != len(self.excluded_foods):
            raise ValueError('Duplicate exclusion.')
        return self


class Meal(Closed):
    date: Day
    slot: Literal['breakfast', 'lunch', 'dinner', 'snack']
    recipe_id: FoodId
    portion_factor: Literal['0.5', '1', '1.5', '2'] = '1'


class Plan(Closed):
    start_date: Day
    day_count: Annotated[int, Field(ge=1, le=14)]
    people: Annotated[int, Field(ge=1, le=8)]
    meals: list[Meal] = Field(max_length=56)

    @model_validator(mode='after')
    def valid_range(self):
        if (date.fromisoformat(self.start_date) + timedelta(days=self.day_count-1)).isoformat() > '2100-12-31':
            raise ValueError('Range ends after supported dates.')
        return self


class NutritionData(Closed):
    preferences: Preferences = Field(default_factory=Preferences)
    plan: Plan | None = None
    pantry: dict[FoodId, Quantity] = Field(default_factory=dict, max_length=100)
    checked: list[FoodId] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def shopping(self):
        if len(set(self.checked)) != len(self.checked) or any(Decimal(v) > 999999 for v in self.pantry.values()):
            raise ValueError('Invalid shopping state.')
        return self


class Reference(Closed):
    artifact_id: Annotated[str, StringConstraints(pattern=r'^pt-meals:[0-9a-f]{64}$')]
    content_hash: Digest


class NutritionWrite(Closed):
    request_id: Token
    previous_reference: Reference | None
    catalog_hash: Digest
    data: NutritionData
