from dataclasses import asdict
import json
from typing import Any

from app.pft_engine.contracts.output import (
    PftProcessingOutputV2,
)


def pft_output_to_dict(
    output: PftProcessingOutputV2,
) -> dict[str, Any]:
    return asdict(output)


def serialize_pft_output_json(
    output: PftProcessingOutputV2,
    *,
    indent: int | None = None,
) -> str:
    return json.dumps(
        pft_output_to_dict(output),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=indent,
    )