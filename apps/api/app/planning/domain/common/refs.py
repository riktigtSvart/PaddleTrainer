from dataclasses import dataclass
from datetime import datetime
from re import fullmatch

from .enums import ProvenanceKind
from .time import to_utc


_SHA256_RE = r"[0-9a-f]{64}"


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")


def _validate_optional_hash(value: str | None) -> None:
    if value is None:
        return
    if fullmatch(_SHA256_RE, value) is None:
        raise ValueError(
            "content_hash must be a lowercase SHA-256 hex digest."
        )


@dataclass(frozen=True)
class VersionRef:
    namespace: str
    version: str

    def __post_init__(self) -> None:
        _require_text(self.namespace, "namespace")
        _require_text(self.version, "version")


@dataclass(frozen=True)
class RegistryKey:
    """Reference to an intentionally open registry entry."""

    registry: str
    key: str
    registry_version: str

    def __post_init__(self) -> None:
        _require_text(self.registry, "registry")
        _require_text(self.key, "key")
        _require_text(self.registry_version, "registry_version")


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    evidence_type: str
    available_at: datetime
    provenance: ProvenanceKind
    content_hash: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        _require_text(self.evidence_type, "evidence_type")
        _validate_optional_hash(self.content_hash)
        object.__setattr__(
            self,
            "available_at",
            to_utc(self.available_at, field_name="available_at"),
        )


@dataclass(frozen=True)
class SourceSnapshotRef:
    """Exact source snapshot used while building another snapshot."""

    domain: str
    object_id: str
    object_version: str
    as_of: datetime
    information_cutoff_at: datetime
    available_at: datetime
    content_hash: str

    def __post_init__(self) -> None:
        _require_text(self.domain, "domain")
        _require_text(self.object_id, "object_id")
        _require_text(self.object_version, "object_version")
        _validate_optional_hash(self.content_hash)

        as_of = to_utc(self.as_of, field_name="as_of")
        cutoff = to_utc(
            self.information_cutoff_at,
            field_name="information_cutoff_at",
        )
        available = to_utc(
            self.available_at,
            field_name="available_at",
        )

        if cutoff > as_of:
            raise ValueError(
                "information_cutoff_at must not be after as_of."
            )

        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(
            self,
            "information_cutoff_at",
            cutoff,
        )
        object.__setattr__(self, "available_at", available)
