"""Increment 3: isSample flow + expected-results disclosure.

[HUMAN REVIEW] This endpoint discloses the answer key. It MUST be gated on the
session's isSample flag; non-sample sessions must never receive expected values.
"""
import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-encapDecap-FIPS203" / "expectedResults.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header, *, algo, mode, is_sample):
    payload = {"algorithms": [{"algorithm": algo, "mode": mode, "revision":
                               "FIPS203" if algo == "ML-KEM" else "FIPS204"}]}
    if is_sample is not None:
        payload["isSample"] = is_sample
    r = client.post("/acvp/v1/testSessions", json=[{"acvVersion": v}, payload], headers=auth_header)
    assert r.status_code == 200
    body = r.json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0]


def test_expected_returned_when_sample(client, acv_version, auth_header):
    _, vs_url = _register(client, acv_version, auth_header,
                          algo="ML-KEM", mode="encapDecap", is_sample=True)
    r = client.get(vs_url + "/expected", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["acvVersion"] == acv_version
    payload = body[1]
    assert "testGroups" in payload
    # vsId stamped to the resource id (not the fixture's baked-in value)
    assert payload["vsId"] == int(vs_url.rsplit("/", 1)[1])


def test_expected_forbidden_when_not_sample(client, acv_version, auth_header):
    _, vs_url = _register(client, acv_version, auth_header,
                          algo="ML-KEM", mode="keyGen", is_sample=False)
    assert client.get(vs_url + "/expected", headers=auth_header).status_code == 403


def test_expected_forbidden_when_is_sample_omitted(client, acv_version, auth_header):
    # isSample defaults to false -> answer key must stay gated.
    _, vs_url = _register(client, acv_version, auth_header,
                          algo="ML-KEM", mode="keyGen", is_sample=None)
    assert client.get(vs_url + "/expected", headers=auth_header).status_code == 403


def test_session_echoes_is_sample(client, acv_version, auth_header):
    sid, _ = _register(client, acv_version, auth_header,
                       algo="ML-KEM", mode="encapDecap", is_sample=True)
    payload = client.get(f"/acvp/v1/testSessions/{sid}", headers=auth_header).json()[1]
    assert payload["isSample"] is True


def test_registration_response_echoes_is_sample(client, acv_version, auth_header):
    # The created-session object returned by POST must agree with GET on isSample.
    r = client.post(
        "/acvp/v1/testSessions",
        json=[{"acvVersion": acv_version},
              {"algorithms": [{"algorithm": "ML-KEM", "mode": "encapDecap", "revision": "FIPS203"}],
               "isSample": True}],
        headers=auth_header,
    )
    assert r.json()[1]["isSample"] is True
