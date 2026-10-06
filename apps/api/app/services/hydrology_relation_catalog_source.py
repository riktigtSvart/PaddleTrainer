from __future__ import annotations

from app.services.kdvvizig_hydrology_relation_catalog import (
    PROVIDER as KDVVIZIG_PROVIDER,
    build_kdvvizig_hydrology_relation_catalog,
)


SUPPORTED_HYDROLOGY_RELATION_PROVIDERS = (KDVVIZIG_PROVIDER,)


def load_hydrology_relation_catalog(provider: str | None) -> dict | None:
    if provider is None:
        return None
    provider_value = str(provider).strip().upper()
    if provider_value == KDVVIZIG_PROVIDER:
        return build_kdvvizig_hydrology_relation_catalog()
    raise ValueError(
        "unsupported hydrology relation provider: "
        f"{provider}; supported={','.join(SUPPORTED_HYDROLOGY_RELATION_PROVIDERS)}"
    )
