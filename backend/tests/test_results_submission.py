"""Increment 6: result submission returns no content (no score).

Spec: POST .../results is a "No content response" -- standard HTTP status only,
no disposition. The request-retry mechanism (GET /requests/{id}) is NOT used for
result submissions; disposition is pulled solely from GET .../results.
"""
import time

import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _ready_vs(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}
    ]}]
    vs_url = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]["vectorSetUrls"][0]
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=auth_header).json()[1]:
            break
        time.sleep(0.02)
    return vs_url


def test_post_results_is_no_content_no_score(client, acv_version, auth_header):
    vs_url = _ready_vs(client, acv_version, auth_header)
    r = client.post(vs_url + "/results",
                    json=[{"acvVersion": acv_version}, {"results": []}], headers=auth_header)

    # Accepted for processing, empty body, no disposition/score/url leaked.
    assert r.status_code == 202
    assert r.content == b""
    assert "disposition" not in r.text and "passed" not in r.text and "url" not in r.text


def test_disposition_pulled_only_via_get_results(client, acv_version, auth_header):
    vs_url = _ready_vs(client, acv_version, auth_header)
    client.post(vs_url + "/results",
                json=[{"acvVersion": acv_version}, {"results": []}], headers=auth_header)

    disposition = None
    for _ in range(50):
        disposition = client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"]
        if disposition == "passed":
            break
        time.sleep(0.02)
    assert disposition == "passed"
