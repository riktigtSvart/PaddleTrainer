from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
import inspect
from typing import Any

from app.services.athlete_state_scientific_view_adapter import (
    build_athlete_state_temporal_binding_from_scientific_views,
)
from app.services.athlete_state_temporal_binding import (
    DEFAULT_MAX_CARRY_FORWARD_SECONDS,
)


SCHEMA_VERSION = "0.1"
SOURCE_STATUS_LOADED = "LOADED"
SOURCE_STATUS_EMPTY = "EMPTY"

ScientificViewLoader = Callable[..., Awaitable[Any] | Any]


async def load_and_bind_athlete_state_scientific_views(
    target_timestamp: Any,
    scientific_view_loader: ScientificViewLoader,
    *,
    loader_args: Sequence[Any] | None = None,
    loader_kwargs: Mapping[str, Any] | None = None,
    max_carry_forward_seconds: int = DEFAULT_MAX_CARRY_FORWARD_SECONDS,
) -> dict[str, Any]:
    """Load existing scientific AthleteState view(s), adapt, and bind in time.

    This is the V22.2 live-source seam.  The caller supplies the *existing*
    project scientific-view builder/loader.  This service deliberately does
    not import or guess that callable by name, does not query AthleteState
    tables itself, and does not synthesize readiness into AthleteState.

    Accepted loader return shapes are intentionally small and mechanical:
    - one scientific-view mapping;
    - one V22.1 wrapper mapping containing ``scientific_view``;
    - a sequence of either of the above;
    - ``None`` / empty sequence.

    Temporal authority remains with V22.1 + V22.  In particular, component
    timestamps are never promoted to a whole-state timestamp here.
    """
    if not callable(scientific_view_loader):
        raise TypeError("scientific_view_loader must be callable")

    args = tuple(loader_args or ())
    kwargs = dict(loader_kwargs or {})

    loaded = scientific_view_loader(*args, **kwargs)
    if inspect.isawaitable(loaded):
        loaded = await loaded

    wrappers, payload_shape = _normalize_loader_result(loaded)
    binding = build_athlete_state_temporal_binding_from_scientific_views(
        target_timestamp,
        wrappers,
        max_carry_forward_seconds=max_carry_forward_seconds,
    )

    loader_name = getattr(scientific_view_loader, "__qualname__", None) or getattr(
        scientific_view_loader, "__name__", None
    )
    loader_module = getattr(scientific_view_loader, "__module__", None)

    return {
        **binding,
        "live_source": {
            "schema_version": SCHEMA_VERSION,
            "status": SOURCE_STATUS_LOADED if wrappers else SOURCE_STATUS_EMPTY,
            "loader_module": loader_module,
            "loader_name": loader_name,
            "loader_result_shape": payload_shape,
            "scientific_view_wrapper_count": len(wrappers),
            "source_contract_discovered_by_introspection": False,
            "source_callable_name_guessed": False,
            "queries_athlete_state_storage_directly": False,
            "synthesizes_readiness_into_athlete_state": False,
            "infers_whole_view_timestamp_from_components": False,
        },
    }


def _normalize_loader_result(value: Any) -> tuple[list[dict[str, Any]], str]:
    if value is None:
        return [], "NONE"

    if isinstance(value, Mapping):
        return [_as_wrapper(value)], "MAPPING"

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        wrappers: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                wrappers.append(_as_wrapper(item))
        return wrappers, "SEQUENCE"

    raise TypeError(
        "scientific_view_loader must return a mapping, sequence of mappings, or None"
    )


def _as_wrapper(value: Mapping[str, Any]) -> dict[str, Any]:
    item = deepcopy(dict(value))
    if isinstance(item.get("scientific_view"), Mapping):
        return item
    return {
        "scientific_view": item,
        "state_timestamp": None,
        "snapshot_id": None,
        "source_reference": None,
    }
