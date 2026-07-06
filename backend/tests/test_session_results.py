import time

import pytest

from app.core.config import get_settings

from helpers import golden_response, registration, session_headers

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _create_session(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203")
    ]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    return body["url"], body["vectorSetUrls"][0], session_headers(body)


def test_session_results_unreceived_before_submission(client, acv_version, auth_header):
    session_url, vs_url, sh = _create_session(client, acv_version, auth_header)

    r = client.get(session_url + "/results", headers=sh)
    assert r.status_code == 200
    summary = r.json()[1]

    # No answers received yet: session not passed; spec disposition is "unreceived".
    assert summary["passed"] is False
    assert len(summary["results"]) == 1
    entry = summary["results"][0]
    assert entry["vectorSetUrl"] == vs_url
    assert entry["status"] == "unreceived"


def test_session_results_passed_after_submission(client, acv_version, auth_header):
    v = acv_version
    session_url, vs_url, sh = _create_session(client, v, auth_header)

    # Retrieve prompt (polling past any retry), then submit a response.
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results",
                json=[{"acvVersion": v}, golden_response(int(vs_url.rsplit("/", 1)[1]))],
                headers=sh)

    # Wait for the async validation to land (pulled via the results endpoint).
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)

    r = client.get(session_url + "/results", headers=sh)
    assert r.status_code == 200
    summary = r.json()[1]

    assert summary["passed"] is True
    assert summary["results"][0]["vectorSetUrl"] == vs_url
    assert summary["results"][0]["status"] == "passed"


def test_session_results_envelope_and_404(client, acv_version, auth_header):
    session_url, _, sh = _create_session(client, acv_version, auth_header)

    # Envelope shape: [{"acvVersion": ...}, {...}]
    r = client.get(session_url + "/results", headers=sh)
    assert r.json()[0]["acvVersion"] == acv_version

    # Unknown session -> 403 (authz runs before existence check).
    assert client.get("/acvp/v1/testSessions/999999/results", headers=auth_header).status_code == 403
