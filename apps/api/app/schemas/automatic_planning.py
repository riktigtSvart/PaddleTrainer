from pydantic import StrictBool, model_validator

from app.schemas.athlete_setup import Closed
from app.schemas.planning_cycles import CycleReference, Digest, Token
from typing import Annotated
from pydantic import StringConstraints


class AutomaticReference(Closed):
    artifact_id: Annotated[str, StringConstraints(pattern=r'^pt-automatic:[0-9a-f]{64}$')]
    content_hash: Digest


class AutomaticSettingInput(Closed):
    request_id: Token
    previous_reference: AutomaticReference | None
    program_reference: CycleReference | None
    enabled: StrictBool
    onboarding_completed: StrictBool

    @model_validator(mode='after')
    def selected_program_required(self):
        if self.enabled and (self.program_reference is None or not self.onboarding_completed):
            raise ValueError('Automatic planning needs a selected programme and completed setup.')
        return self


class AutomaticRunInput(Closed):
    pass
