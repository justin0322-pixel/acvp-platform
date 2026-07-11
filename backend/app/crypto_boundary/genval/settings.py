"""GenVal runtime settings, sourced from the app's central config.

Adapted from the FIPS 204 team's genval settings, but reads our
`app.core.config.Settings` so there is a single source of truth for env vars
(the values are surfaced in .env.example).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass(frozen=True)
class GenValSettings:
    runner_dll: Path          # published NIST.CVP.ACVTS.Generation.GenValApp.dll
    artifact_root: Path       # where per-vector-set work dirs are created
    timeout_seconds: int


def get_genval_settings() -> GenValSettings:
    s = get_settings()
    # runner_dll may be unset; NistCliGenValProvider raises a clear
    # GenValConfigurationError when it is missing rather than failing here.
    runner_dll = Path(s.genval_runner_dll).expanduser() if s.genval_runner_dll else Path()
    return GenValSettings(
        runner_dll=runner_dll,
        artifact_root=s.genval_artifact_dir,
        timeout_seconds=s.genval_timeout_seconds,
    )
