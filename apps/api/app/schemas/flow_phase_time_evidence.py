"""Source-bound Flow display evidence; these are not user clarification commands."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

SHA = r'^[0-9a-f]{64}$'
UUID = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'


class StrictEvidence(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class DisplayImage(StrictEvidence):
    filename: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=SHA)
    session_id_or_date_visible: bool


class DisplayPhase(StrictEvidence):
    phase_number: int = Field(ge=1, le=512)
    displayed_name: str = Field(max_length=200)
    duration_s: int = Field(gt=0, le=86400)
    cumulative_end_s: int = Field(gt=0, le=172800)


class DisplayUserReport(StrictEvidence):
    report_number: int = Field(ge=1, le=100)
    reported_at: str = Field(min_length=20, max_length=64)
    text: str = Field(min_length=1, max_length=4096)


class DisplayReportedEvent(StrictEvidence):
    report_number: int = Field(ge=1, le=100)
    phase_number: int = Field(ge=1, le=512)
    event_role: Literal['ACTIVE_PHASE_START']
    reported_time_s: int = Field(ge=0, le=172800)
    clock_domain: Literal['USER_REPORTED_ELAPSED_CLOCK_UNVERIFIED']


class FlowPhaseTimeReference(StrictEvidence):
    schema_version: Literal['0.1']
    evidence_id: str = Field(pattern=r'^flow_display_reference_[0-9a-f]{64}$')
    athlete_id: str = Field(pattern=UUID)
    session_id: str = Field(pattern=UUID)
    source_sha256: str = Field(pattern=SHA)
    plan_sha256: str = Field(pattern=SHA)
    source_kind: Literal['USER_SUPPLIED_FLOW_PHASE_TABLE_TRANSCRIPTION']
    association_basis: Literal['CONVERSATION_CONTEXT_AND_MATCHING_PHASE_STRUCTURE']
    source_available_at_utc: None
    display_resolution_s: Literal[1]
    exact_rounding_policy_known: Literal[False]
    images: list[DisplayImage] = Field(min_length=1, max_length=20)
    phases: list[DisplayPhase] = Field(min_length=1, max_length=512)
    user_reports: list[DisplayUserReport] = Field(max_length=100)
    reported_events: list[DisplayReportedEvent] = Field(max_length=100)
