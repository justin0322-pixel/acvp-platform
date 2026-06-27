import time

import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _create_session(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}
    ]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    return body["url"], body["vectorSetUrls"][0]


def test_session_results_incomplete_before_submission(client, acv_version, auth_header):
    session_url, vs_url = _create_session(client, acv_version, auth_header)

    r = client.get(session_url + "/results", headers=auth_header)
    assert r.status_code == 200
    summary = r.json()[1]

    # No answers submitted yet: session not passed, vectorSet is incomplete.
    assert summary["passed"] is False
    assert len(summary["results"]) == 1
    entry = summary["results"][0]
    assert entry["vectorSetUrl"] == vs_url
    assert entry["status"] == "incomplete"


def test_session_results_passed_after_submission(client, acv_version, auth_header):
    v = acv_version
    session_url, vs_url = _create_session(client, v, auth_header)

    # Retrieve prompt (polling past any retry), then submit a response.
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=auth_header).json()[1]:
            break
        time.sleep(0.02)
    r = client.post(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    req_url = r.json()[1]["url"]

    # Wait for the async validation to land.
    for _ in range(40):
        if client.get(req_url, headers=auth_header).json()[1]["status"] != "processing":
            break
        time.sleep(0.05)

    r = client.get(session_url + "/results", headers=auth_header)
    assert r.status_code == 200
    summary = r.json()[1]

    assert summary["passed"] is True
    assert summary["results"][0]["vectorSetUrl"] == vs_url
    assert summary["results"][0]["status"] == "passed"


def test_session_results_envelope_and_404(client, acv_version, auth_header):
    session_url, _ = _create_session(client, acv_version, auth_header)

    # Envelope shape: [{"acvVersion": ...}, {...}]
    r = client.get(session_url + "/results", headers=auth_header)
    assert r.json()[0]["acvVersion"] == acv_version

    # Unknown session -> 404
    assert client.get("/acvp/v1/testSessions/999999/results", headers=auth_header).status_code == 404
