"""The arq worker tasks must stay callable against crypto_boundary.client.

The in-process runner (app/core/jobs.py) is what the scaffold actually uses, so the
arq tasks in app/workers/tasks.py are never exercised by the rest of the suite. That
is exactly how they silently drifted out of sync with client.generate/validate once
those grew the registration and session_id/vs_id arguments — the mismatch would only
have surfaced as a TypeError in deployment, the first time a real job ran.

These tests bind the worker signatures to the client's and then actually invoke them.
"""
import asyncio
import inspect

import pytest

from helpers import golden_response, registration

from app.core.config import get_settings
from app.crypto_boundary import client
from app.workers import tasks

_MODE = "ML-KEM-keyGen-FIPS203"
_FIXTURE = get_settings().fixtures_dir / _MODE / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _params(fn):
    return [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]


def _params_after_ctx(fn):
    params = _params(fn)
    assert params[0][0] == "ctx", "an arq task takes the job context first"
    return params[1:]


@pytest.mark.parametrize("task, target", [(tasks.generate, client.generate),
                                          (tasks.validate, client.validate)])
def test_worker_signature_matches_the_crypto_boundary(task, target):
    assert _params_after_ctx(task) == _params(target)


def test_worker_generate_runs():
    result = asyncio.run(
        tasks.generate({}, registration(_MODE), _MODE, session_id=1, vs_id=1)
    )
    # asdict(GeneratedVectors) — arq has to be able to serialize what we hand back.
    assert set(result) == {"prompt", "internal_projection", "expected"}
    assert result["prompt"]["testGroups"]


def test_worker_validate_runs():
    result = asyncio.run(
        tasks.validate({}, None, golden_response(1, _MODE), _MODE, session_id=1, vs_id=1)
    )
    assert result["disposition"] == "passed"
