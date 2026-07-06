"""Increment 6: result submission returns no content (no score).

Spec: POST .../results is a "No content response" -- standard HTTP status only,
no disposition. The request-retry mechanism (GET /requests/{id}) is NOT used for
result submissions; disposition is pulled solely from GET .../results.
"""
import time

import pytest

from app.core.config import get_settings

from helpers import golden_response, registration, session_headers

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _ready_vs(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203")
    ]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    sh = session_headers(body)
    vs_url = body["vectorSetUrls"][0]
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    return vs_url, sh


def test_post_results_is_no_content_no_score(client, acv_version, auth_header):
    vs_url, sh = _ready_vs(client, acv_version, auth_header)
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, golden_response(int(vs_url.rsplit("/", 1)[1]))], headers=sh)

    # Success with empty body, no disposition/score/url leaked. ACVP signals
    # "still processing" at the application layer (GET .../results disposition),
    # never via the HTTP status, and uses 200 as its success code throughout.
    assert r.status_code == 200
    assert r.content == b""
    assert "disposition" not in r.text and "passed" not in r.text and "url" not in r.text


def test_disposition_pulled_only_via_get_results(client, acv_version, auth_header):
    vs_url, sh = _ready_vs(client, acv_version, auth_header)
    client.post(vs_url + "/results",
                json=[{"acvVersion": acv_version}, golden_response(int(vs_url.rsplit("/", 1)[1]))], headers=sh)

    disposition = None
    for _ in range(50):
        disposition = client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"]
        if disposition == "passed":
            break
        time.sleep(0.02)
    assert disposition == "passed"
