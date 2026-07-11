"""Increment 2: spec-faithful disposition vocabulary + response formats.

Disposition values (ACVP messaging spec): failed / unreceived / incomplete /
expired / passed / missing / error. We synthesize unreceived/incomplete/
expired/error from lifecycle state; passed/failed come through from the crypto
module's validation, normalized against the known vocabulary.
"""
import time

import pytest

from app.core.config import get_settings
from app.store import store

from helpers import golden_response, registration, session_headers

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203")
    ]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0], session_headers(body)


def _vs(session_id, vs_url):
    return store.get_vector_set(store.get_session(session_id), int(vs_url.rsplit("/", 1)[1]))


def _drive_to_passed(client, v, sh, vs_url):
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results",
                json=[{"acvVersion": v}, golden_response(int(vs_url.rsplit("/", 1)[1]))],
                headers=sh)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)


# --- per-vectorSet disposition state derivation ---------------------------------

def test_disposition_unreceived_before_response(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    payload = client.get(vs_url + "/results", headers=sh).json()[1]
    assert payload["results"]["disposition"] == "unreceived"
    assert payload["results"]["tests"] == []


def test_disposition_incomplete_while_validating(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    vs = _vs(sid, vs_url)
    vs.status = "response_submitted"
    vs.validation = None
    payload = client.get(vs_url + "/results", headers=sh).json()[1]
    assert payload["results"]["disposition"] == "incomplete"


def test_disposition_expired(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    vs = _vs(sid, vs_url)
    vs.status = "expired"
    payload = client.get(vs_url + "/results", headers=sh).json()[1]
    assert payload["results"]["disposition"] == "expired"


def test_disposition_passed(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    _drive_to_passed(client, acv_version, sh, vs_url)
    payload = client.get(vs_url + "/results", headers=sh).json()[1]
    assert payload["results"]["disposition"] == "passed"


def test_disposition_fail_passthrough(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    vs = _vs(sid, vs_url)
    # Crypto module reported a failure: server passes the disposition through verbatim.
    vs.validation = {"vsId": vs.vs_id, "disposition": "failed",
                     "tests": [{"tcId": 1, "result": "failed"}]}
    payload = client.get(vs_url + "/results", headers=sh).json()[1]
    assert payload["results"]["disposition"] == "failed"


# --- per-vectorSet results response format (spec: wrapped in "results") ---------

def test_vsid_is_consistent_with_resource_id(client, acv_version, auth_header):
    # The vsId in the prompt and in the results must equal the URL's resource id,
    # so a client can correlate them (the stub fixture's baked-in vsId must not leak).
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    url_id = int(vs_url.rsplit("/", 1)[1])

    for _ in range(50):
        prompt = client.get(vs_url, headers=sh).json()[1]
        if "retry" not in prompt:
            break
        time.sleep(0.02)
    assert prompt["vsId"] == url_id

    _drive_to_passed(client, acv_version, sh, vs_url)
    results = client.get(vs_url + "/results", headers=sh).json()[1]["results"]
    assert results["vsId"] == url_id


def test_vectorset_results_spec_envelope(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    _drive_to_passed(client, acv_version, sh, vs_url)
    body = client.get(vs_url + "/results", headers=sh).json()
    assert body[0]["acvVersion"] == acv_version
    results = body[1]["results"]
    assert set(results.keys()) >= {"vsId", "disposition", "tests"}
    assert isinstance(results["tests"], list)


# --- session-level summary format (spec: passed + results[], NO top-level status) -

def test_session_results_shape_is_spec_exact(client, acv_version, auth_header):
    sid, vs_url, sh = _register(client, acv_version, auth_header)
    session_url = "/acvp/v1/testSessions/%d" % sid
    payload = client.get(session_url + "/results", headers=sh).json()[1]
    assert set(payload.keys()) == {"passed", "results"}  # no extra top-level status
    for entry in payload["results"]:
        assert set(entry.keys()) == {"vectorSetUrl", "status"}
    # before any response: not passed, vectorSet unreceived
    assert payload["passed"] is False
    assert payload["results"][0]["status"] == "unreceived"
