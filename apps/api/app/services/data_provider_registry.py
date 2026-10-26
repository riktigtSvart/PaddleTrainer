"""Provider capabilities drive one UI; unimplemented adapters stay unavailable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    implemented: bool
    delivery: str
    datasets: tuple[str, ...]


PROVIDERS = (
    Provider("POLAR", "Polar", True, "pull", ("sessions", "targets")),
    Provider("GARMIN", "Garmin", False, "not_configured", ()),
    Provider("SUUNTO", "Suunto", False, "not_configured", ()),
)
REGISTRY = {item.key: item for item in PROVIDERS}
DATASET_SCOPES = {
    "sessions": ("training_sessions:read", "sports:read"),
    "targets": ("training_targets:read",),
}
