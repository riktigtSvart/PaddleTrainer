"""Strict source-bound clarification inspection; no storage command."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PhaseClarificationItem(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    question_id:str=Field(pattern=r'^phase_question_[0-9a-f]{64}$')
    answer_type:Literal['SELECT_CANDIDATE','DONT_KNOW']
    candidate_id:str|None=Field(pattern=r'^phase_option_[0-9a-f]{64}$')
    submitted_at:str=Field(min_length=20,max_length=64)

    @model_validator(mode='after')
    def selection_matches_type(self):
        if (self.answer_type=='SELECT_CANDIDATE')!=(self.candidate_id is not None):
            raise ValueError('candidate_id must match answer_type')
        return self


class PhaseClarificationInspectionRequest(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    schema_version:Literal['0.1']
    artifact_id:str=Field(pattern=r'^phase_reconciliation_[0-9a-f]{64}$')
    answers:list[PhaseClarificationItem]=Field(max_length=400)
