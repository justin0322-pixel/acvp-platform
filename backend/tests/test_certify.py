"""Increment 8: certify a test session (PUT /testSessions/{id}) + metadata stubs.

[HUMAN REVIEW] Certification is an authorization gate: the session MUST be
publishable and passed. Sample sessions are never publishable.
"""
import time

import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header, *, is_sample=False):
    reg = [{"acvVersion": v}, {
        "algorithms": [{"algorithm": "ML-KEM", "mode": "keyGen", "revision": "FIPS203"}],
        "isSample": is_sample,
    }]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0]


def _drive_to_passed(client, v, auth_header, vs_url):
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=auth_header).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results", json=[{"acvVersion": v}, {"results": []}], headers=auth_header)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=auth_header).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)


_CERT_BODY = lambda v: [{"acvVersion": v},
                        {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"}]


def test_certify_succeeds_when_passed(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url = _register(client, v, auth_header)
    _drive_to_passed(client, v, auth_header, vs_url)

    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=auth_header).json()[1]
    assert info["passed"] is True and info["publishable"] is True

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=auth_header)
    assert r.status_code == 200
    req = r.json()[1]
    assert set(req.keys()) >= {"url", "status"}

    approved = None
    for _ in range(50):
        approved = client.get(req["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            break
        time.sleep(0.02)
    # request object per spec: url + status + approvedUrl (the validation resource)
    assert approved["status"] == "approved"
    assert set(approved.keys()) >= {"url", "status", "approvedUrl"}
    assert "/validations/" in approved["approvedUrl"]


def test_certify_rejected_when_not_passed(client, acv_version, auth_header):
    v = acv_version
    sid, _ = _register(client, v, auth_header)
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=auth_header)
    assert r.status_code == 403


def test_certify_rejected_for_sample_session(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url = _register(client, v, auth_header, is_sample=True)
    _drive_to_passed(client, v, auth_header, vs_url)
    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=auth_header).json()[1]
    assert info["passed"] is True and info["publishable"] is False  # sample not publishable
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=auth_header)
    assert r.status_code == 403


def test_certify_unknown_session_404(client, acv_version, auth_header):
    assert client.put("/acvp/v1/testSessions/999999", json=_CERT_BODY(acv_version),
                      headers=auth_header).status_code == 404


def test_modules_and_oes_stubs(client, auth_header):
    assert client.get("/acvp/v1/modules", headers=auth_header).json()[1] == {"data": []}
    assert client.get("/acvp/v1/oes", headers=auth_header).json()[1] == {"data": []}
