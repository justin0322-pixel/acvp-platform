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


def _approved_url(client, auth_header, resource: str, payload: dict) -> str:
    """Create a metadata resource and follow its request through to approval."""
    req = client.post(f"/acvp/v1/{resource}", json=[{"acvVersion": "1.0"}, payload],
                      headers=auth_header).json()[1]
    for _ in range(50):
        approved = client.get(req["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            return approved["approvedUrl"]
        time.sleep(0.02)
    raise AssertionError(f"{resource} request was never approved")


def _module_and_oe(client, auth_header) -> tuple[str, str]:
    """A real module and OE. certify now refuses references that do not resolve,
    so a certificate can no longer be issued against made-up URLs."""
    vendor = _approved_url(client, auth_header, "vendors", {"name": "Acme, LLC"})
    module = _approved_url(client, auth_header, "modules", {
        "name": "ACME ACV Test Module", "vendorUrl": vendor, "description": "module",
    })
    oe = _approved_url(client, auth_header, "oes", {"name": "Ubuntu 24.04 on x86_64"})
    return module, oe


def _cert_body(client, auth_header, v) -> list:
    module, oe = _module_and_oe(client, auth_header)
    return [{"acvVersion": v}, {"moduleUrl": module, "oeUrl": oe}]


def test_certify_succeeds_when_passed(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url, sh = _register(client, v, auth_header)
    _drive_to_passed(client, v, sh, vs_url)

    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).json()[1]
    assert info["passed"] is True and info["publishable"] is True

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_cert_body(client, auth_header, v), headers=sh)
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
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_cert_body(client, auth_header, v), headers=sh)
    assert r.status_code == 403


def test_certify_rejected_for_sample_session(client, acv_version, auth_header):
    v = acv_version
    sid, vs_url, sh = _register(client, v, auth_header, is_sample=True)
    _drive_to_passed(client, v, sh, vs_url)
    info = client.get(f"/acvp/v1/testSessions/{sid}", headers=sh).json()[1]
    assert info["passed"] is True and info["publishable"] is False  # sample not publishable
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=_cert_body(client, auth_header, v), headers=sh)
    assert r.status_code == 403


def test_certify_unknown_session_forbidden(client, acv_version, auth_header):
    # Authz runs before existence: any token is 403 for a non-existent session.
    assert client.put("/acvp/v1/testSessions/999999", json=_cert_body(client, auth_header, acv_version),
                      headers=auth_header).status_code == 403


# --- certify request body (spec 12.16.4.1) --------------------------------------

def _certify(client, v, sid, sh, payload):
    return client.put(f"/acvp/v1/testSessions/{sid}", json=[{"acvVersion": v}, payload], headers=sh)


def _passed_session(client, v, auth_header):
    sid, vs_url, sh = _register(client, v, auth_header)
    _drive_to_passed(client, v, sh, vs_url)
    return sid, sh


def test_certify_requires_a_module_reference(client, acv_version, auth_header):
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    _, oe = _module_and_oe(client, auth_header)
    assert _certify(client, v, sid, sh, {"oeUrl": oe}).status_code == 400


def test_certify_requires_an_oe_reference(client, acv_version, auth_header):
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    module, _ = _module_and_oe(client, auth_header)
    assert _certify(client, v, sid, sh, {"moduleUrl": module}).status_code == 400


def test_certify_rejects_both_url_and_inline_object(client, acv_version, auth_header):
    """Spec: `module` MAY be used *instead of* moduleUrl — not alongside it."""
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    module, oe = _module_and_oe(client, auth_header)
    payload = {"moduleUrl": module, "module": {"name": "m"}, "oeUrl": oe}
    assert _certify(client, v, sid, sh, payload).status_code == 400


def test_certify_accepts_algorithm_prerequisites(client, acv_version, auth_header):
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    module, oe = _module_and_oe(client, auth_header)
    payload = {
        "moduleUrl": module,
        "oeUrl": oe,
        "algorithmPrerequisites": [{
            "algorithm": "ML-KEM",
            "prerequisites": [{"algorithm": "SHA3-256", "validationId": "123456"}],
        }],
    }
    assert _certify(client, v, sid, sh, payload).status_code == 200


def test_certify_rejects_malformed_prerequisites(client, acv_version, auth_header):
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    module, oe = _module_and_oe(client, auth_header)
    payload = {
        "moduleUrl": module,
        "oeUrl": oe,
        # validationId is required on each prerequisite.
        "algorithmPrerequisites": [{
            "algorithm": "ML-KEM",
            "prerequisites": [{"algorithm": "SHA3-256"}],
        }],
    }
    assert _certify(client, v, sid, sh, payload).status_code == 400


def test_certified_validation_records_the_module_and_oe(client, acv_version, auth_header):
    v = acv_version
    sid, sh = _passed_session(client, v, auth_header)
    module, oe = _module_and_oe(client, auth_header)
    r = _certify(client, v, sid, sh, {"moduleUrl": module, "oeUrl": oe})
    assert r.status_code == 200

    approved = None
    for _ in range(50):
        approved = client.get(r.json()[1]["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            break
        time.sleep(0.02)

    validation = client.get(approved["approvedUrl"], headers=auth_header).json()[1]
    assert validation["moduleUrl"] == module
    assert validation["oeUrl"] == oe


def test_metadata_listings_are_paged(client, auth_header):
    # Spec 12.5.2: listings MUST be a paged response (totalCount/incomplete/links/data).
    for resource in ("vendors", "persons", "modules", "oes", "dependencies"):
        payload = client.get(f"/acvp/v1/{resource}", headers=auth_header).json()[1]
        assert set(payload.keys()) == {"totalCount", "incomplete", "links", "data"}
        assert set(payload["links"].keys()) == {"first", "next", "prev", "last"}
        assert isinstance(payload["data"], list)
