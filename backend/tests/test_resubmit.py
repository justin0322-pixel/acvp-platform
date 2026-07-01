"""Increment 4: resubmit an entire vector set via PUT .../results.

Spec: PUT request is identical to POST; resending is for the entire vector set
even if only one test case failed, and MUST occur prior to expiry. The response,
like POST, carries no content.
"""
import time

import pytest

from app.core.config import get_settings
from app.store import store

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _ready_vs(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [
        {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}
    ]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    sid = int(body["url"].rsplit("/", 1)[1])
    vs_url = body["vectorSetUrls"][0]
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=auth_header).json()[1]:
            break
        time.sleep(0.02)
    return sid, vs_url


def _vs(sid, vs_url):
    return store.get_vector_set(store.get_session(sid), int(vs_url.rsplit("/", 1)[1]))


def _wait_passed(client, auth_header, vs_url):
    for _ in range(50):
        if client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)


def test_put_resubmits_entire_vector_set(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url = _ready_vs(client, v, auth_header)
    client.post(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    _wait_passed(client, auth_header, vs_url)

    r = client.put(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    assert r.status_code == 200 and r.content == b""  # no content, like POST
    assert _vs(sid, vs_url).resubmit_count == 1

    _wait_passed(client, auth_header, vs_url)
    assert client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"] == "passed"


def test_put_without_prior_post_is_accepted(client, acv_version, auth_header):
    v = acv_version
    _, vs_url = _ready_vs(client, v, auth_header)
    r = client.put(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    assert r.status_code == 200


def test_put_rejected_after_expiry(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url = _ready_vs(client, v, auth_header)
    _vs(sid, vs_url).status = "expired"
    # Spec: resubmission MUST occur prior to expiry.
    r = client.put(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    assert r.status_code == 403
