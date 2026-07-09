"""The /validations resource — certify's approvedUrl must resolve to it."""
import time

import pytest

from app.core.config import get_settings
from helpers import registration, session_headers, golden_response

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def test_certify_approved_url_resolves_to_validation(client, acv_version, auth_header):
    v = acv_version
    reg = client.post("/acvp/v1/testSessions",
                      json=[{"acvVersion": v}, {"algorithms": [registration()]}],
                      headers=auth_header).json()[1]
    sid = int(reg["url"].rsplit("/", 1)[1])
    vs_url = reg["vectorSetUrls"][0]
    sh = session_headers(reg)

    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results",
                json=[{"acvVersion": v}, golden_response(int(vs_url.rsplit("/", 1)[1]))], headers=sh)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)

    req = client.put(f"/acvp/v1/testSessions/{sid}",
                     json=[{"acvVersion": v}, {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"}],
                     headers=sh).json()[1]
    approved = None
    for _ in range(50):
        approved = client.get(req["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            break
        time.sleep(0.02)

    # The approvedUrl must now resolve (previously 404 — dangling reference).
    r = client.get(approved["approvedUrl"], headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    assert set(body.keys()) == {"url", "createdOn", "testSessionUrl"}
    assert body["testSessionUrl"] == f"/acvp/v1/testSessions/{sid}"


def test_unknown_validation_404(client, auth_header):
    assert client.get("/acvp/v1/validations/999999", headers=auth_header).status_code == 404
