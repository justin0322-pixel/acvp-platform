"""GenVal artifact record + per-vector-set work directory layout.

Ported from the FIPS 204 team's genval provider. The NIST GenValApp is file/dir
based: generation writes prompt.json + internalProjection.json + expectedResults.json
into a work dir, and validation writes validation.json beside them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GenValArtifacts:
    registration: Path
    prompt: Path
    internal_projection: Path
    expected_results: Optional[Path]
    stdout: Optional[Path]
    stderr: Optional[Path]


def session_artifact_dir(root: Path, session_id: str | int) -> Path:
    return root / str(session_id)


def vector_set_artifact_dir(root: Path, session_id: str | int, vector_set_id: str | int) -> Path:
    return session_artifact_dir(root, session_id) / "vectorSets" / str(vector_set_id)
