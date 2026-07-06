"""Protocol-layer checks on result submission (no crypto involved).

Three gaps closed here:
  1. Structural validation of the submitted response (vsId must match the URL,
     testGroups/tcId shape must be well-formed, tcIds must exist in the prompt).
  2. The `missing` disposition: a submission lacking some of the prompt's test
     cases is graded `missing`, not passed through to the crypto validation.
  3. State-machine guard: submitting results before the prompt has been
     retrieved is an illegal transition (409).
"""
import copy
import time

import pytest

from app.core.config import get_settings

from helpers import golden_response, registration

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203")
    ]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    vs_url = body["vectorSetUrls"][0]
    return vs_url, int(vs_url.rsplit("/", 1)[1])


def _retrieve_prompt(client, auth_header, vs_url) -> dict:
    for _ in range(50):
        payload = client.get(vs_url, headers=auth_header).json()[1]
        if "retry" not in payload:
            return payload
        time.sleep(0.02)
    raise AssertionError("prompt never became ready")


def _disposition(client, auth_header, vs_url) -> str:
    for _ in range(50):
        d = client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"]
        if d != "incomplete":
            return d
        time.sleep(0.02)
    return d


# --- state-machine guard ---------------------------------------------------------

def test_submit_before_prompt_retrieval_is_conflict(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    # No GET on the vector set yet: the prompt has never been retrieved.
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, golden_response(vs_id)],
                    headers=auth_header)
    assert r.status_code == 409


# --- structural validation (400) --------------------------------------------------

def test_submit_vsid_mismatch_rejected(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, golden_response(vs_id + 100)],
                    headers=auth_header)
    assert r.status_code == 400


def test_submit_without_testgroups_rejected(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    for bad in ({"vsId": vs_id}, {"vsId": vs_id, "testGroups": "nope"},
                {"vsId": vs_id, "testGroups": [{"tests": []}]},
                {"vsId": vs_id, "testGroups": [{"tgId": 1, "tests": [{}]}]}):
        r = client.post(vs_url + "/results",
                        json=[{"acvVersion": acv_version}, bad], headers=auth_header)
        assert r.status_code == 400, bad


def test_submit_unknown_tcid_rejected(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    body = copy.deepcopy(golden_response(vs_id))
    body["testGroups"][0]["tests"].append({"tcId": 99999})
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, body], headers=auth_header)
    assert r.status_code == 400


# --- missing disposition -----------------------------------------------------------

def test_missing_test_cases_yield_missing_disposition(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    body = copy.deepcopy(golden_response(vs_id))
    del body["testGroups"][0]["tests"][0]  # drop one answered test case
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, body], headers=auth_header)
    assert r.status_code == 200
    assert _disposition(client, auth_header, vs_url) == "missing"


def test_resubmitting_full_set_clears_missing(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    partial = copy.deepcopy(golden_response(vs_id))
    partial["testGroups"] = partial["testGroups"][:1]
    client.post(vs_url + "/results",
                json=[{"acvVersion": acv_version}, partial], headers=auth_header)
    assert _disposition(client, auth_header, vs_url) == "missing"

    client.put(vs_url + "/results",
               json=[{"acvVersion": acv_version}, golden_response(vs_id)], headers=auth_header)
    assert _disposition(client, auth_header, vs_url) == "passed"


def test_complete_submission_still_passes(client, acv_version, auth_header):
    vs_url, vs_id = _register(client, acv_version, auth_header)
    _retrieve_prompt(client, auth_header, vs_url)
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, golden_response(vs_id)],
                    headers=auth_header)
    assert r.status_code == 200
    assert _disposition(client, auth_header, vs_url) == "passed"
