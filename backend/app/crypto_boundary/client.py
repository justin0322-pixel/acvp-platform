"""Client to the FIPS 203 / 204 crypto module across a process boundary.

The crypto engine is the NIST ACVP-Server GenVal (+ Orleans), which handles both
ML-KEM and ML-DSA. It is language-opaque to us: we only exchange JSON files. Two
providers sit behind this facade, selected by `USE_NIST_GENVAL`:

  - fixture (default): reads the vendored NIST golden fixtures by mode folder, so
    the whole server pipeline runs end-to-end with no .NET engine. This is the
    stub the project has always used.
  - NIST GenVal: calls the published GenValApp .NET runner (see genval/). Requires
    the runner built and Orleans running; enable via USE_NIST_GENVAL=true.

Contract (identical for both providers):
  generate(registration, mode_folder, ...)      -> prompt + internalProjection + expected
  validate(internal_projection, response, ...)  -> validation
  expected_results(mode_folder)                 -> expected answer key (sample mode)

The real difference the callers must respect: NIST validate needs the
`internalProjection` (the answer key) produced at generation time, not just the
prompt — so the caller persists it on the vector set. See app/store.VectorSet.

[HUMAN REVIEW] crypto-boundary code — do not auto-merge. No crypto math lives here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings

from .genval import NistCliGenValProvider, vector_set_artifact_dir


@dataclass
class GeneratedVectors:
    """What a generation produces. `internal_projection`/`expected` may be None
    if the provider did not emit them (they are always present for our fixtures)."""
    prompt: dict
    internal_projection: dict | None
    expected: dict | None


# --- fixture (stub) provider ----------------------------------------------------

def _fixture(mode_folder: str, name: str) -> dict:
    path: Path = get_settings().fixtures_dir / mode_folder / name
    if not path.exists():
        raise FileNotFoundError(
            f"NIST fixture not found: {path}. Run scripts/fetch-nist-fixtures.sh first."
        )
    return json.loads(path.read_text())


def _fixture_optional(mode_folder: str, name: str) -> dict | None:
    path: Path = get_settings().fixtures_dir / mode_folder / name
    return json.loads(path.read_text()) if path.exists() else None


def _fixture_generate(mode_folder: str) -> GeneratedVectors:
    return GeneratedVectors(
        prompt=_fixture(mode_folder, "prompt.json"),
        internal_projection=_fixture_optional(mode_folder, "internalProjection.json"),
        expected=_fixture_optional(mode_folder, "expectedResults.json"),
    )


def _fixture_validate(mode_folder: str) -> dict:
    # STUB: the golden validation is returned verbatim; the response is not graded
    # (grading is the crypto engine's job). Enable USE_NIST_GENVAL for real grading.
    return _fixture(mode_folder, "validation.json")


# --- NIST GenVal provider -------------------------------------------------------

def _work_dir(session_id: int, vs_id: int) -> Path:
    return vector_set_artifact_dir(get_settings().genval_artifact_dir, session_id, vs_id)


def _nist_generate(registration: dict, session_id: int, vs_id: int) -> GeneratedVectors:
    work_dir = _work_dir(session_id, vs_id)
    artifacts = NistCliGenValProvider().generate(registration, work_dir)
    expected = (
        json.loads(artifacts.expected_results.read_text())
        if artifacts.expected_results is not None
        else None
    )
    return GeneratedVectors(
        prompt=json.loads(artifacts.prompt.read_text()),
        internal_projection=json.loads(artifacts.internal_projection.read_text()),
        expected=expected,
    )


def _nist_validate(internal_projection: dict | None, response: dict, session_id: int, vs_id: int) -> dict:
    if internal_projection is None:
        raise RuntimeError(
            "NIST validate requires the internalProjection from generation; it was not persisted."
        )
    work_dir = _work_dir(session_id, vs_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    ip_path = work_dir / "internalProjection.json"
    resp_path = work_dir / "response.json"
    ip_path.write_text(json.dumps(internal_projection, indent=2) + "\n", encoding="utf-8")
    resp_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    validation_path = NistCliGenValProvider().validate(ip_path, resp_path, work_dir)
    return json.loads(validation_path.read_text())


# --- public facade --------------------------------------------------------------

def generate(registration: dict, mode_folder: str, *, session_id: int, vs_id: int) -> GeneratedVectors:
    """Produce a vector set. NIST path uses the registration capabilities; the
    fixture path uses the mode folder. Runs in a worker/background thread."""
    if get_settings().use_nist_genval:
        return _nist_generate(registration, session_id, vs_id)
    return _fixture_generate(mode_folder)


def validate(
    internal_projection: dict | None, response: dict, mode_folder: str, *, session_id: int, vs_id: int
) -> dict:
    """Grade a submitted response. NIST path feeds the engine the answer key +
    response; the fixture path returns the golden validation verbatim."""
    if get_settings().use_nist_genval:
        return _nist_validate(internal_projection, response, session_id, vs_id)
    return _fixture_validate(mode_folder)


def expected_results(mode_folder: str) -> dict:
    """Sample-mode answer key. Prefer the value persisted at generation; this
    fixture read is the fallback path. The caller MUST gate on isSample."""
    return _fixture(mode_folder, "expectedResults.json")
