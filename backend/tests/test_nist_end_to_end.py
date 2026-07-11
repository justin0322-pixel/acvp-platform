"""End-to-end proof of the NIST GenVal code path, all 5 modes, without .NET.

With USE_NIST_GENVAL=true and a fixture-backed fake runner (invoked as a real
subprocess), this drives the actual NIST branch — client._nist_generate /
_nist_validate -> NistCliGenValProvider._run -> subprocess.run — through the full
protocol flow: register -> poll vectors -> submit -> poll disposition. It asserts a
golden response grades `passed` and a corrupted one grades `failed`, proving the
server truly grades responses (not the fixture stub, which ignores them).
"""
import sys
import time
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.store import store

from helpers import golden_response, registration, session_headers

_MODES = [
    "ML-KEM-keyGen-FIPS203",
    "ML-KEM-encapDecap-FIPS203",
    "ML-DSA-keyGen-FIPS204",
    "ML-DSA-sigGen-FIPS204",
    "ML-DSA-sigVer-FIPS204",
]

_FAKE_RUNNER = Path(__file__).parent / "fake_genval_runner.py"
_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


@pytest.fixture
def nist_mode(monkeypatch, tmp_path):
    """Route the crypto boundary through the fake NIST runner for this test."""
    monkeypatch.setenv("USE_NIST_GENVAL", "true")
    monkeypatch.setenv("GENVAL_RUNNER_DLL", str(_FAKE_RUNNER))
    monkeypatch.setenv("GENVAL_ARTIFACT_ROOT", str(tmp_path))
    get_settings.cache_clear()
    # Make the provider run `python fake_genval_runner.py ...` instead of `dotnet ...`.
    import app.crypto_boundary.genval.nist_cli_provider as prov
    monkeypatch.setattr(prov.shutil, "which", lambda name: sys.executable)
    yield
    get_settings.cache_clear()  # restore default (fixture) provider for other tests


def _register(client, v, auth_header, mode_folder):
    reg = [{"acvVersion": v}, {"algorithms": [registration(mode_folder)]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200, r.text
    body = r.json()[1]
    sid = int(body["url"].rsplit("/", 1)[1])
    return sid, body["vectorSetUrls"][0], session_headers(body)


def _await_prompt(client, sid, vs_url, sh):
    for _ in range(150):
        payload = client.get(vs_url, headers=sh).json()[1]
        if "retry" not in payload:
            return payload
        time.sleep(0.02)
    vs = store.get_vector_set(store.get_session(sid), int(vs_url.rsplit("/", 1)[1]))
    raise AssertionError(f"generation did not complete; status={vs.status} error={vs.error}")


def _await_disposition(client, vs_url, sh, want):
    disposition = None
    for _ in range(150):
        disposition = client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"]
        if disposition == want:
            return disposition
        time.sleep(0.02)
    return disposition


def _corrupt(response: dict) -> dict:
    """Flip the first answer field of the first test case so it fails grading."""
    for group in response.get("testGroups", []):
        for test in group.get("tests", []):
            for key in test:
                if key != "tcId":
                    test[key] = "__CORRUPTED__"
                    return response
    return response


@pytest.mark.parametrize("mode_folder", _MODES)
def test_nist_path_grades_pass_and_fail(client, acv_version, auth_header, nist_mode, mode_folder):
    sid, vs_url, sh = _register(client, acv_version, auth_header, mode_folder)
    vs_id = int(vs_url.rsplit("/", 1)[1])

    prompt = _await_prompt(client, sid, vs_url, sh)
    assert prompt["vsId"] == vs_id  # our resource id, not the fixture's baked-in 42

    # Golden response (== NIST expectedResults) must grade passed.
    gold = golden_response(vs_id, mode_folder)
    r = client.post(vs_url + "/results", json=[{"acvVersion": acv_version}, gold], headers=sh)
    assert r.status_code == 200
    assert _await_disposition(client, vs_url, sh, "passed") == "passed"

    # A corrupted resubmission must grade failed (the engine actually checks answers).
    bad = _corrupt(golden_response(vs_id, mode_folder))
    r = client.put(vs_url + "/results", json=[{"acvVersion": acv_version}, bad], headers=sh)
    assert r.status_code == 200
    assert _await_disposition(client, vs_url, sh, "failed") == "failed"
