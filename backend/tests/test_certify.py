"""Increment 8: certify a test session (PUT /testSessions/{id}) + metadata stubs.

[HUMAN REVIEW] Certification is an authorization gate: the session MUST be
publishable and passed. Sample sessions are never publishable.
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


def _register(client, v, auth_header, *, is_sample=False):
    reg = [{"acvVersion": v}, {
        "algorithms": [registration("ML-KEM-keyGen-FIPS203")],
        "isSample": is_sample,
    }]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0], session_headers(body)


def _drive_to_passed(client, v, sh, vs_url):
    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results",
                json=[{"acvVersion": v}, golden_response(int(vs_url.rsplit("/", 1)[1]))],
                headers=sh)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)


_CERT_BODY = lambda v: [{"acvVersion": v},
                        {"moduleUrl": "/acvp/v1/modules/1", "oeUrl": "/acvp/v1/oes/1"}]


def test_certify_succeeds_when_passed(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url, sh = _register(client, v, auth_header)
    _drive_to_passed(client, v, sh, vs_url)

    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).json()[1]
    assert info["passed"] is True and info["publishable"] is True

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=sh)
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
    sid, _, sh = _register(client, v, auth_header)
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=sh)
    assert r.status_code == 403


def test_certify_rejected_for_sample_session(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url, sh = _register(client, v, auth_header, is_sample=True)
    _drive_to_passed(client, v, sh, vs_url)
    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).json()[1]
    assert info["passed"] is True and info["publishable"] is False  # sample not publishable
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_CERT_BODY(v), headers=sh)
    assert r.status_code == 403


def test_certify_unknown_session_forbidden(client, acv_version, auth_header):
    # Authz runs before existence: any token is 403 for a non-existent session.
    assert client.put("/acvp/v1/testSessions/999999", json=_CERT_BODY(acv_version),
                      headers=auth_header).status_code == 403


def test_modules_and_oes_stubs(client, auth_header):
    # Spec: listings MUST be a paged response (totalCount/incomplete/links/data).
    for resource in ("modules", "oes"):
        payload = client.get(f"/acvp/v1/{resource}", headers=auth_header).json()[1]
        assert set(payload.keys()) == {"totalCount", "incomplete", "links", "data"}
        assert payload["totalCount"] == 0
        assert payload["incomplete"] is False
        assert payload["data"] == []
        assert set(payload["links"].keys()) == {"first", "next", "prev", "last"}
