from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


CONTENT_HASH_ALGORITHM = "sha256-canonical-json-v0.1"


class CanonicalSerializationError(TypeError):
    pass


def _datetime_string(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalSerializationError(
            "Naive datetimes are not canonicalizable."
        )
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        frozen = {
            str(key): deep_freeze(item)
            for key, item in value.items()
        }
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    return value


def to_contract_primitive(
    value: object,
    *,
    exclude_fields: frozenset[str] = frozenset(),
) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise CanonicalSerializationError(
                "NaN and infinity are forbidden in planning contracts."
            )
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalSerializationError(
                "Non-finite Decimal values are forbidden."
            )
        return format(value, "f")
    if isinstance(value, datetime):
        return _datetime_string(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return to_contract_primitive(
            value.value,
            exclude_fields=exclude_fields,
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_contract_primitive(
                getattr(value, field.name),
                exclude_fields=exclude_fields,
            )
            for field in fields(value)
            if field.name not in exclude_fields
        }
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalSerializationError(
                    "Contract mapping keys must be strings."
                )
            if key in exclude_fields:
                continue
            result[key] = to_contract_primitive(
                item,
                exclude_fields=exclude_fields,
            )
        return result
    if isinstance(value, (tuple, list)):
        return [
            to_contract_primitive(item, exclude_fields=exclude_fields)
            for item in value
        ]
    if isinstance(value, (set, frozenset)):
        normalized = [
            to_contract_primitive(item, exclude_fields=exclude_fields)
            for item in value
        ]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
    raise CanonicalSerializationError(
        f"Unsupported contract type: {type(value).__name__}"
    )


def canonical_json(
    value: object,
    *,
    exclude_fields: frozenset[str] = frozenset(),
) -> str:
    primitive = to_contract_primitive(
        value,
        exclude_fields=exclude_fields,
    )
    return json.dumps(
        primitive,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_bytes(
    value: object,
    *,
    exclude_fields: frozenset[str] = frozenset(),
) -> bytes:
    return canonical_json(
        value,
        exclude_fields=exclude_fields,
    ).encode("utf-8")


def compute_content_hash(
    value: object,
    *,
    exclude_fields: frozenset[str] = frozenset({"content_hash"}),
) -> str:
    return sha256(
        canonical_json_bytes(
            value,
            exclude_fields=exclude_fields,
        )
    ).hexdigest()
