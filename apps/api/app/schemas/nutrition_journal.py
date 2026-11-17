"""Reported intake, civil meal times and explicitly sourced assessment data."""
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from app.schemas.nutrition import Closed, FoodId, Reference, Quantity
from app.schemas.planning_cycles import Day, Digest, Token

Time = Annotated[str, StringConstraints(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]
Slot = Literal['breakfast', 'lunch', 'dinner', 'snack']
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class Timing(Closed):
    date: Day
    slot: Slot
    time: Time | None


class MealSource(Closed):
    reference: Reference
    date: Day
    slot: Slot


class Entry(Closed):
    id: Token
    date: Day
    time: Time | None
    timezone: Text
    fold: Annotated[int, Field(ge=0, le=1)] | None = None
    status: Literal['eaten', 'skipped']
    title: Text
    amount: Quantity
    unit: Literal['portion', 'g', 'ml', 'db']
    recipe_id: FoodId | None = None
    source: MealSource | None = None
    note: Note = ''
    satisfaction: Annotated[int, Field(ge=1, le=5)] | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.status == 'eaten' and (self.time is None or Decimal(self.amount) <= 0):
            raise ValueError('Actual intake requires a positive amount and actual time.')
        if self.status == 'skipped' and (self.time is not None or self.amount != '0' or self.source is None or self.satisfaction is not None):
            raise ValueError('Skipped meals have a plan source, no actual time, quantity or rating.')
        if self.source is not None and (self.unit != 'portion' or self.recipe_id is None):
            raise ValueError('Planned intake is a fraction of one personal planned portion.')
        return self


class Observation(Closed):
    id: Token
    analyte: Text
    value: Quantity
    qualifier: Literal['exact', 'less_than', 'greater_than'] = 'exact'
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    sampled_on: Day
    source_name: Text
    reference_low: Quantity | None = None
    reference_high: Quantity | None = None
    interpretation: Note = ''
    note: Note = ''

    @model_validator(mode='after')
    def ordered(self):
        if self.reference_low is not None and self.reference_high is not None and Decimal(self.reference_low) > Decimal(self.reference_high):
            raise ValueError('The laboratory reference interval is reversed.')
        return self


class Target(Closed):
    id: Token
    nutrient: Literal['energy', 'protein', 'carbohydrate', 'fat', 'vitamin_d', 'b12', 'iron', 'calcium', 'magnesium', 'zinc', 'iodine', 'folate', 'selenium']
    minimum: Quantity | None
    maximum: Quantity | None
    unit: Literal['kcal', 'g', 'mg', 'µg']
    scope: Literal['food_only', 'total_intake']
    source_name: Text
    assessed_on: Day
    valid_until: Day | None = None
    observation_ids: list[Token] = Field(default_factory=list, max_length=20)
    note: Note = ''

    @model_validator(mode='after')
    def ordered(self):
        units = {'energy': 'kcal', 'protein': 'g', 'carbohydrate': 'g', 'fat': 'g', 'vitamin_d': 'µg', 'b12': 'µg', 'iron': 'mg', 'calcium': 'mg', 'magnesium': 'mg', 'zinc': 'mg', 'iodine': 'µg', 'folate': 'µg', 'selenium': 'µg'}
        if self.unit != units[self.nutrient] or self.minimum is None and self.maximum is None:
            raise ValueError('Use the displayed daily intake unit and at least one bound.')
        if self.minimum is not None and self.maximum is not None and Decimal(self.minimum) > Decimal(self.maximum):
            raise ValueError('Target interval is reversed.')
        if self.valid_until is not None and self.valid_until < self.assessed_on:
            raise ValueError('Target expires before its assessment.')
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError('Duplicate observation reference.')
        return self


class JournalData(Closed):
    default_times: dict[Slot, Time | None] = Field(default_factory=lambda: dict.fromkeys(['breakfast', 'lunch', 'dinner', 'snack']))
    timings: list[Timing] = Field(default_factory=list, max_length=112)
    entries: list[Entry] = Field(default_factory=list, max_length=500)
    observations: list[Observation] = Field(default_factory=list, max_length=100)
    targets: list[Target] = Field(default_factory=list, max_length=50)
    muscle_goal: Literal['unspecified', 'maintain', 'gain'] = 'unspecified'
    performance_goal: Literal['unspecified', 'strength', 'endurance', 'wellbeing'] = 'unspecified'

    @model_validator(mode='after')
    def unique(self):
        if set(self.default_times) != {'breakfast', 'lunch', 'dinner', 'snack'}:
            raise ValueError('Specify all four default time keys, using null for unknown.')
        if len({(t.date, t.slot) for t in self.timings}) != len(self.timings):
            raise ValueError('Duplicate meal timing.')
        for rows in [self.entries, self.observations, self.targets]:
            if len({r.id for r in rows}) != len(rows):
                raise ValueError('Duplicate record identity.')
        if len({(e.source.date, e.source.slot) for e in self.entries if e.source}) != len([e for e in self.entries if e.source]):
            raise ValueError('A planned meal can be reported once; edit the existing record to correct it.')
        ids = {o.id for o in self.observations}
        if any(not set(t.observation_ids) <= ids for t in self.targets):
            raise ValueError('A target references a missing observation.')
        return self


class JournalReference(Closed):
    artifact_id: Annotated[str, StringConstraints(pattern=r'^pt-nutrition-journal:[0-9a-f]{64}$')]
    content_hash: Digest


class JournalWrite(Closed):
    request_id: Token
    previous_reference: JournalReference | None
    data: JournalData
