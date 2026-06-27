"""Client to the FIPS 203 / 204 crypto module across a process boundary.

The crypto teams deliver a language-agnostic module exposing two operations whose
JSON contract is the NIST json-files schema:
  - generate(registration) -> prompt + expected
  - validate(prompt, response) -> validation

Their implementation language is irrelevant here; we only exchange JSON. Until the
real module lands, these functions stand in by reading the vendored NIST fixtures,
which lets the whole server pipeline run end-to-end. See CLAUDE.md and the
acvp-protocol skill.
"""
import json
from pathlib import Path

from app.core.config import get_settings


def _fixture(mode_folder: str, name: str) -> dict:
    path: Path = get_settings().fixtures_dir / mode_folder / name
    if not path.exists():
        raise FileNotFoundError(
            f"NIST fixture not found: {path}. Run scripts/fetch-nist-fixtures.sh first."
        )
    return json.loads(path.read_text())


def generate(mode_folder: str) -> dict:
    """STUB: return the NIST golden prompt for this mode.

    Real implementation: call the 203/204 module with registration capabilities.
    """
    return _fixture(mode_folder, "prompt.json")


def validate(mode_folder: str, response: dict) -> dict:
    """STUB: return the NIST golden validation for this mode.

    Real implementation: call the 203/204 module with prompt + response and let it
    compute per-test-case pass/fail.
    """
    return _fixture(mode_folder, "validation.json")


def expected(mode_folder: str) -> dict:
    """STUB: return the NIST golden expected results (sample mode answer key).

    Real implementation: the 203/204 module emits expected values alongside the
    prompt when generating a sample vector set. Disclosed only for isSample
    sessions; the caller MUST enforce that gate.
    """
    return _fixture(mode_folder, "expectedResults.json")
