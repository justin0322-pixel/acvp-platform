"""NIST ACVP-Server GenVal boundary provider.

Adapted from the FIPS 204 team's `backend/app/genval/` provider
(William901105/ACVP-FIPS204, branch feat/nist-genval-adapter). The crypto engine
is the vendored NIST ACVP-Server GenVal + Orleans Silo (.NET 8); it handles both
ML-KEM and ML-DSA. We only exchange files/JSON across the process boundary — no
crypto math lives here. See the acvp-protocol skill and CLAUDE.md.

[HUMAN REVIEW] crypto-boundary code — do not auto-merge.
"""
from .artifacts import GenValArtifacts, vector_set_artifact_dir
from .errors import (
    GenValArtifactError,
    GenValConfigurationError,
    GenValError,
    GenValExecutionError,
)
from .nist_cli_provider import NistCliGenValProvider
from .provider import GenValProvider
from .settings import GenValSettings, get_genval_settings

__all__ = [
    "GenValArtifacts",
    "vector_set_artifact_dir",
    "GenValError",
    "GenValArtifactError",
    "GenValConfigurationError",
    "GenValExecutionError",
    "GenValProvider",
    "NistCliGenValProvider",
    "GenValSettings",
    "get_genval_settings",
]
