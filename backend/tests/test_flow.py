import time

import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def test_full_stub_flow(client, acv_version, auth_header):
    v = acv_version

    reg = [{"acvVersion": v}, {"algorithms": [
        {"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}
    ]}]
    r = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header)
    assert r.status_code == 200
    vs_url = r.json()[1]["vectorSetUrls"][0]

    prompt = client.get(vs_url, headers=auth_header).json()[1]
    assert prompt["algorithm"] == "ML-KEM"

    r = client.post(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    req_url = r.json()[1]["url"]

    body = {"status": "processing"}
    for _ in range(20):
        body = client.get(req_url, headers=auth_header).json()[1]
        if body["status"] != "processing":
            break
        time.sleep(0.05)
    assert body["status"] == "approved"

    assert client.get(vs_url + "/results", headers=auth_header).status_code == 200
