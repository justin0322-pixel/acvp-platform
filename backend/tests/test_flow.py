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

    prompt = {"retry": 1}
    for _ in range(50):
        prompt = client.get(vs_url, headers=auth_header).json()[1]
        if "retry" not in prompt:
            break
        time.sleep(0.02)
    assert prompt["algorithm"] == "ML-KEM"

    # Submit responses: no content, no score (disposition is pulled separately).
    r = client.post(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    assert r.status_code == 200 and r.content == b""

    # Pull the disposition from the results endpoint until validation lands.
    disposition = None
    for _ in range(50):
        disposition = client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"]
        if disposition == "passed":
            break
        time.sleep(0.02)
    assert disposition == "passed"
