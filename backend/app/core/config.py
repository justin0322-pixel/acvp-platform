from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    acv_version: str = "1.0"
    jwt_secret: str = "change-me-dev-only"
    jwt_alg: str = "HS256"
    jwt_expire_seconds: int = 1800
    demo_password: str = "acvp-demo"

    # Set FIXTURES_DIR_OVERRIDE to point at the golden vectors explicitly
    # (e.g. when running in a container). Otherwise resolved relative to the repo.
    fixtures_dir_override: str | None = None

    @property
    def fixtures_dir(self) -> Path:
        if self.fixtures_dir_override:
            return Path(self.fixtures_dir_override)
        # repo-root/tests/fixtures/nist  (this file: backend/app/core/config.py)
        return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "nist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
