"""Acceptance against the REAL NIST GenVal engine (opt-in; needs .NET + Orleans).

This is the formal five-mode acceptance once you have built the engine
(scripts/nist/build-genval.sh) and started Orleans (scripts/nist/start-orleans.sh).
It skips entirely unless you opt in:

    ACVP_REAL_ENGINE=1 \\
    GENVAL_RUNNER_DLL=/abs/path/nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll \\
    pytest backend/tests/test_nist_real_engine.py -v

It drives the real NIST branch (no fake runner) through the full flow: register ->
generate -> submit the correct answers -> expect `passed`; then a format-preserving
corruption -> expect `failed`.

Unlike the fixture stub, the real engine generates *fresh random vectors* each run,
so the correct answers are the ones produced by THIS generation (persisted on the
vector set as `vs.expected`), not the static golden fixture.
"""
import copy
import os
import shutil
import time
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.store import store

from helpers import registration, session_headers

_MODES = [
    "ML-KEM-keyGen-FIPS203",
    "ML-KEM-encapDecap-FIPS203",
    "ML-DSA-keyGen-FIPS204",
    "ML-DSA-sigGen-FIPS204",
    "ML-DSA-sigVer-FIPS204",
]

_ENABLED = os.environ.get("ACVP_REAL_ENGINE") == "1"
_DLL = os.environ.get("GENVAL_RUNNER_DLL", "")
_READY = bool(_ENABLED and shutil.which("dotnet") and _DLL and Path(_DLL).exists())
_TIMEOUT = int(os.environ.get("ACVP_REAL_ENGINE_TIMEOUT", "300"))

pytestmark = pytest.mark.skipif(
    not _READY,
    reason="real engine not enabled: set ACVP_REAL_ENGINE=1, GENVAL_RUNNER_DLL to a built "
    "runner, ensure dotnet is installed and Orleans is running",
)


@pytest.fixture
def real_nist_mode(monkeypatch, tmp_path):
    """Flip the boundary to the real NIST runner for this test only."""
    monkeypatch.setenv("USE_NIST_GENVAL", "true")
    monkeypatch.setenv("GENVAL_ARTIFACT_ROOT", str(tmp_path))
    # GENVAL_RUNNER_DLL is already in the environment (the real, built DLL).
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()  # restore the fixture provider for other tests


def _register(client, v, auth_header, mode_folder):
    reg = [{"acvVersion": v}, {"algorithms": [registration(mode_folder)]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200, r.text
    body = r.json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0], session_headers(body)


def _await_prompt(client, sid, vs_url, sh):
    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        payload = client.get(vs_url, headers=sh).json()[1]
        if "retry" not in payload:
            return payload
        time.sleep(1.0)
    vs = store.get_vector_set(store.get_session(sid), int(vs_url.rsplit("/", 1)[1]))
    raise AssertionError(
        f"generation did not complete in {_TIMEOUT}s; status={vs.status} error={vs.error} "
        "(is Orleans running?)"
    )


def _await_disposition(client, vs_url, sh, want):
    deadline = time.monotonic() + _TIMEOUT
    disposition = None
    while time.monotonic() < deadline:
        disposition = client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"]
        if disposition == want:
            return disposition
        if disposition == "error":
            raise AssertionError(f"validation errored (want {want}); check the engine/Orleans")
        time.sleep(1.0)
    return disposition


def _corrupt(response: dict) -> dict:
    """Change one answer to a wrong-but-well-formed value so grading fails cleanly
    (a garbage value could read as malformed instead of failed)."""
    for group in response.get("testGroups", []):
        for test in group.get("tests", []):
            for key, val in list(test.items()):
                if key == "tcId":
                    continue
                if isinstance(val, bool):
                    test[key] = not val
                    return response
                if isinstance(val, str) and val:
                    test[key] = ("1" if val[0] == "0" else "0") + val[1:]
                    return response
    return response


@pytest.mark.parametrize("mode_folder", _MODES)
def test_real_engine_grades_pass_and_fail(client, acv_version, auth_header, real_nist_mode, mode_folder):
    sid, vs_url, sh = _register(client, acv_version, auth_header, mode_folder)
    vs_id = int(vs_url.rsplit("/", 1)[1])

    prompt = _await_prompt(client, sid, vs_url, sh)
    assert prompt["vsId"] == vs_id

    # The correct answers for THIS fresh generation (persisted at generate time).
    vs = store.get_vector_set(store.get_session(sid), vs_id)
    assert vs.expected is not None, f"{mode_folder}: engine produced no expectedResults to answer with"
    correct = {**vs.expected, "vsId": vs_id}

    r = client.post(vs_url + "/results", json=[{"acvVersion": acv_version}, correct], headers=sh)
    assert r.status_code == 200
    assert _await_disposition(client, vs_url, sh, "passed") == "passed", f"{mode_folder}: correct answers should pass"

    bad = _corrupt(copy.deepcopy(correct))
    r = client.put(vs_url + "/results", json=[{"acvVersion": acv_version}, bad], headers=sh)
    assert r.status_code == 200
    assert _await_disposition(client, vs_url, sh, "failed") == "failed", f"{mode_folder}: corruption should fail"
