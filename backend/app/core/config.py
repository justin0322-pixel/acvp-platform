from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    acv_version: str = "1.0"
    jwt_secret: str = "change-me-dev-only"
    jwt_alg: str = "HS256"
    jwt_issuer: str = "acvp-server"
    jwt_expire_seconds: int = 1800
    session_expire_seconds: int = 30 * 24 * 3600  # test sessions live ~30 days
    # Deadline for submitting a vector set's responses (spec section 14). The spec
    # leaves the length to the server; NIST's own deployment uses ~30 days.
    vector_set_expire_seconds: int = 30 * 24 * 3600
    demo_password: str = "acvp-demo"
    # Seed a starting catalogue of vendors/modules/OEs (see core/seed.py). Without
    # one, a fresh server has nothing certifiable to bind a certificate to.
    seed_demo_metadata: bool = True

    # Browser origins allowed to call the API (the web client dev servers).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Set FIXTURES_DIR_OVERRIDE to point at the golden vectors explicitly
    # (e.g. when running in a container). Otherwise resolved relative to the repo.
    fixtures_dir_override: str | None = None

    # --- Crypto boundary (NIST ACVP-Server GenVal) ------------------------------
    # When false (default), the boundary stands in with the vendored NIST fixtures
    # so the whole pipeline runs without the .NET engine. Flip to true once the
    # NIST GenValApp runner is built and Orleans is running (see scripts/nist/).
    use_nist_genval: bool = False
    # Absolute path to the published NIST.CVP.ACVTS.Generation.GenValApp.dll.
    genval_runner_dll: str | None = None
    # Root under which per-vector-set work dirs (registration/prompt/... json) live.
    genval_artifact_root: str | None = None
    genval_timeout_seconds: int = 120

    @property
    def fixtures_dir(self) -> Path:
        if self.fixtures_dir_override:
            return Path(self.fixtures_dir_override)
        # repo-root/tests/fixtures/nist  (this file: backend/app/core/config.py)
        return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "nist"

    @property
    def genval_artifact_dir(self) -> Path:
        if self.genval_artifact_root:
            return Path(self.genval_artifact_root)
        # backend/data/acvp-sessions  (this file: backend/app/core/config.py)
        return Path(__file__).resolve().parents[2] / "data" / "acvp-sessions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
