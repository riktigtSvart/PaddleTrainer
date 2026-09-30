from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Paddle Coach API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://paddle:paddle@127.0.0.1:5433/paddle"

    polar_client_id: str = ""
    polar_client_secret: str = ""
    polar_redirect_uri: str = "http://localhost:8000/api/v1/integrations/polar/callback"
    polar_scopes: str = "training_sessions:read training_targets:read sports:read"

    token_encryption_key: str = ""
    frontend_url: str = "http://localhost:3000"
    demo_user_email: str = "athlete@example.com"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",
    )

    @property
    def polar_scope_list(self) -> list[str]:
        return [s for s in self.polar_scopes.split() if s]


@lru_cache
def get_settings() -> Settings:
    return Settings()