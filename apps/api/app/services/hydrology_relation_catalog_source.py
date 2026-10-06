from __future__ import annotations

from app.services.kdvvizig_hydrology_relation_catalog import (
    PROVIDER as KDVVIZIG_PROVIDER,
    build_kdvvizig_hydrology_relation_catalog,
)
from app.services.validation_hydrology_relation_catalog import (
    PROVIDER as VALIDATION_PROVIDER,
    build_validation_hydrology_relation_catalog,
)


PRODUCTION_HYDROLOGY_RELATION_PROVIDERS = (KDVVIZIG_PROVIDER,)
VALIDATION_HYDROLOGY_RELATION_PROVIDERS = (VALIDATION_PROVIDER,)
SUPPORTED_HYDROLOGY_RELATION_PROVIDERS = (
    *PRODUCTION_HYDROLOGY_RELATION_PROVIDERS,
    *VALIDATION_HYDROLOGY_RELATION_PROVIDERS,
)


def load_hydrology_relation_catalog(
    provider: str | None,
    *,
    allow_validation_provider: bool = False,
) -> dict | None:
    if provider is None:
        return None
    provider_value = str(provider).strip().upper()
    if provider_value == KDVVIZIG_PROVIDER:
        return build_kdvvizig_hydrology_relation_catalog()
    if provider_value == VALIDATION_PROVIDER:
        if not allow_validation_provider:
            raise ValueError(
                "validation hydrology relation provider requires explicit "
                "validation mode"
            )
        return build_validation_hydrology_relation_catalog()
    raise ValueError(
        "unsupported hydrology relation provider: "
        f"{provider}; supported={','.join(SUPPORTED_HYDROLOGY_RELATION_PROVIDERS)}"
    )
