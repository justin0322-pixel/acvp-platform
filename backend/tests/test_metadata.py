"""Metadata resources: vendors, persons, modules, OEs, dependencies (spec 12.8-12.13).

Creates go through the request-approval flow (spec 12.7): POST returns a request
URL, and GET /requests/{id} yields the approvedUrl of the resource once processed.

The point of all this is the last test in the file: a certificate must not be able
to name a module that does not exist.
"""
import time

import pytest

from helpers import golden_response, registration, session_headers

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _create(client, auth_header, resource: str, payload: dict) -> str:
    """POST a metadata resource and follow the request through to its approvedUrl."""
    r = client.post(f"/acvp/v1/{resource}", json=[{"acvVersion": "1.0"}, payload],
                    headers=auth_header)
    assert r.status_code == 200, r.text
    req = r.json()[1]
    assert req["status"] == "processing" and "/requests/" in req["url"]

    for _ in range(50):
        approved = client.get(req["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            return approved["approvedUrl"]
        time.sleep(0.02)
    raise AssertionError(f"{resource} request was never approved")


def _vendor(client, auth_header, name="Acme, LLC") -> str:
    return _create(client, auth_header, "vendors", {
        "name": name,
        "website": "www.acme.acme",
        "addresses": [{"street1": "123 Main Street", "locality": "Any Town", "country": "USA"}],
    })


def _module(client, auth_header, vendor_url: str) -> str:
    return _create(client, auth_header, "modules", {
        "name": "ACME ACV Test Module",
        "version": "3.0",
        "type": "Software",          # spec enumerates lowercase; its example capitalises
        "vendorUrl": vendor_url,
        "description": "ACME module",
    })


def _oe(client, auth_header) -> str:
    return _create(client, auth_header, "oes", {"name": "Ubuntu 24.04 on x86_64"})


# --- the request-approval create flow -------------------------------------------

def test_create_resolves_through_a_request(client, auth_header):
    vendor_url = _vendor(client, auth_header)
    assert "/acvp/v1/vendors/" in vendor_url

    body = client.get(vendor_url, headers=auth_header).json()[1]
    assert body["url"] == vendor_url
    assert body["name"] == "Acme, LLC"
    # A vendor's addresses are addressable sub-resources (spec 12.9).
    address_url = body["addresses"][0]["url"]
    assert client.get(address_url, headers=auth_header).status_code == 200


def test_module_type_is_case_insensitive(client, auth_header):
    module_url = _module(client, auth_header, _vendor(client, auth_header))
    assert client.get(module_url, headers=auth_header).json()[1]["type"] == "software"


def test_listing_is_paged(client, auth_header):
    _vendor(client, auth_header)
    payload = client.get("/acvp/v1/vendors", headers=auth_header).json()[1]
    assert set(payload.keys()) == {"totalCount", "incomplete", "links", "data"}
    assert payload["totalCount"] >= 1


def test_update_and_delete(client, auth_header):
    vendor_url = _vendor(client, auth_header, name="Before")
    vid = vendor_url.rsplit("/", 1)[1]

    r = client.put(vendor_url, json=[{"acvVersion": "1.0"}, {"name": "After"}],
                   headers=auth_header)
    assert r.status_code == 200
    for _ in range(50):
        if client.get(r.json()[1]["url"], headers=auth_header).json()[1]["status"] == "approved":
            break
        time.sleep(0.02)
    assert client.get(vendor_url, headers=auth_header).json()[1]["name"] == "After"

    assert client.delete(vendor_url, headers=auth_header).status_code == 200
    assert client.get(vendor_url, headers=auth_header).status_code == 404
    assert client.delete(vendor_url, headers=auth_header).status_code == 404


def test_unknown_resource_404(client, auth_header):
    assert client.get("/acvp/v1/modules/999999", headers=auth_header).status_code == 404


def test_metadata_requires_authentication(client):
    assert client.get("/acvp/v1/vendors").status_code == 401


# --- references must resolve ----------------------------------------------------

def test_module_rejects_a_dangling_vendor(client, auth_header):
    r = client.post("/acvp/v1/modules", json=[{"acvVersion": "1.0"}, {
        "name": "m", "description": "d", "vendorUrl": "/acvp/v1/vendors/999999",
    }], headers=auth_header)
    assert r.status_code == 400
    assert "vendorUrl" in r.json()["error"]


def test_module_rejects_a_vendor_url_of_the_wrong_kind(client, auth_header):
    """An oeUrl must not satisfy a vendorUrl just because it resolves to something."""
    oe_url = _oe(client, auth_header)
    r = client.post("/acvp/v1/modules", json=[{"acvVersion": "1.0"}, {
        "name": "m", "description": "d", "vendorUrl": oe_url,
    }], headers=auth_header)
    assert r.status_code == 400


def test_module_requires_name_vendor_and_description(client, auth_header):
    vendor_url = _vendor(client, auth_header)
    r = client.post("/acvp/v1/modules", json=[{"acvVersion": "1.0"}, {
        "name": "m", "vendorUrl": vendor_url,   # description missing
    }], headers=auth_header)
    assert r.status_code == 400


def test_oe_rejects_a_dangling_dependency(client, auth_header):
    r = client.post("/acvp/v1/oes", json=[{"acvVersion": "1.0"}, {
        "name": "oe", "dependencyUrls": ["/acvp/v1/dependencies/999999"],
    }], headers=auth_header)
    assert r.status_code == 400


def test_extra_properties_are_ignored_not_rejected(client, auth_header):
    """Spec, on every create: "Any additional properties ... are ignored"."""
    url = _create(client, auth_header, "vendors", {"name": "Acme", "nonsense": True})
    assert "nonsense" not in client.get(url, headers=auth_header).json()[1]


# --- the whole point ------------------------------------------------------------

def _passed_session(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [registration("ML-KEM-keyGen-FIPS203")]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    sh = session_headers(body)
    sid, vs_url = int(body["url"].rsplit("/", 1)[1]), body["vectorSetUrls"][0]
    vs_id = int(vs_url.rsplit("/", 1)[1])

    for _ in range(50):
        if "retry" not in client.get(vs_url, headers=sh).json()[1]:
            break
        time.sleep(0.02)
    client.post(vs_url + "/results", json=[{"acvVersion": v}, golden_response(vs_id)], headers=sh)
    for _ in range(50):
        if client.get(vs_url + "/results", headers=sh).json()[1]["results"]["disposition"] == "passed":
            break
        time.sleep(0.02)
    return sid, sh


def test_certify_refuses_a_module_that_does_not_exist(client, acv_version, auth_header):
    """A certificate that names a nonexistent module states nothing at all."""
    sid, sh = _passed_session(client, acv_version, auth_header)
    oe_url = _oe(client, auth_header)

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=[{"acvVersion": acv_version}, {
        "moduleUrl": "/acvp/v1/modules/999999", "oeUrl": oe_url,
    }], headers=sh)
    assert r.status_code == 400
    assert "moduleUrl" in r.json()["error"]


def test_certify_refuses_an_oe_that_does_not_exist(client, acv_version, auth_header):
    sid, sh = _passed_session(client, acv_version, auth_header)
    module_url = _module(client, auth_header, _vendor(client, auth_header))

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=[{"acvVersion": acv_version}, {
        "moduleUrl": module_url, "oeUrl": "/acvp/v1/oes/999999",
    }], headers=sh)
    assert r.status_code == 400


def test_certify_succeeds_against_real_module_and_oe(client, acv_version, auth_header):
    sid, sh = _passed_session(client, acv_version, auth_header)
    module_url = _module(client, auth_header, _vendor(client, auth_header))
    oe_url = _oe(client, auth_header)

    r = client.put(f"/acvp/v1/testSessions/{sid}", json=[{"acvVersion": acv_version}, {
        "moduleUrl": module_url, "oeUrl": oe_url,
    }], headers=sh)
    assert r.status_code == 200

    for _ in range(50):
        approved = client.get(r.json()[1]["url"], headers=auth_header).json()[1]
        if approved["status"] == "approved":
            break
        time.sleep(0.02)

    validation = client.get(approved["approvedUrl"], headers=auth_header).json()[1]
    # The certificate's references now resolve — no dangling module.
    assert client.get(validation["moduleUrl"], headers=auth_header).status_code == 200
    assert client.get(validation["oeUrl"], headers=auth_header).status_code == 200
