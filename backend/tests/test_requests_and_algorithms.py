"""Request listing (spec 12.7.1) and algorithm resources (spec 12.14)."""
import time

import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _make_request(client, auth_header) -> str:
    """Any resource create produces a request (spec 12.7)."""
    r = client.post("/acvp/v1/vendors", json=[{"acvVersion": "1.0"}, {"name": "Acme"}],
                    headers=auth_header)
    return r.json()[1]["url"]


# --- requests -------------------------------------------------------------------

def test_request_listing_is_paged(client, auth_header):
    url = _make_request(client, auth_header)
    for _ in range(50):
        if client.get(url, headers=auth_header).json()[1]["status"] == "approved":
            break
        time.sleep(0.02)

    payload = client.get("/acvp/v1/requests", headers=auth_header).json()[1]
    assert set(payload.keys()) == {"totalCount", "incomplete", "links", "data"}
    assert payload["totalCount"] >= 1

    mine = next(r for r in payload["data"] if r["url"] == url)
    # Request object per spec 12.7.2: url + status (+ approvedUrl).
    assert mine["status"] == "approved"
    assert "/acvp/v1/vendors/" in mine["approvedUrl"]


def test_request_listing_requires_authentication(client):
    assert client.get("/acvp/v1/requests").status_code == 401


def test_certify_request_belongs_to_the_user_not_the_session(client, acv_version, auth_header):
    """A certify request is authorized by the session token, but it is the *user's*
    request: "session:{id}" is a credential scope, not an identity, and 12.7.1 lists
    the requests of the current user. Filing it under the session would hide it."""
    from helpers import golden_response, registration, session_headers

    v = acv_version
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

    modules = client.get("/acvp/v1/modules", headers=auth_header).json()[1]["data"]
    oes = client.get("/acvp/v1/oes", headers=auth_header).json()[1]["data"]
    r = client.put(f"/acvp/v1/testSessions/{sid}", json=[{"acvVersion": v}, {
        "moduleUrl": modules[0]["url"], "oeUrl": oes[0]["url"],
    }], headers=sh)
    assert r.status_code == 200
    request_url = r.json()[1]["url"]

    # Listed with the LOGIN token — the user's token, not the session's.
    listed = client.get("/acvp/v1/requests", headers=auth_header).json()[1]["data"]
    assert any(item["url"] == request_url for item in listed)


# --- algorithms -----------------------------------------------------------------

def test_algorithm_listing_shape(client, auth_header):
    algorithms = client.get("/acvp/v1/algorithms", headers=auth_header).json()[1]["algorithms"]
    assert len(algorithms) == 5
    for algorithm in algorithms:
        # Spec 12.14.1: id / name / mode / revision (name, not "algorithm").
        assert set(algorithm.keys()) == {"id", "name", "mode", "revision"}
    assert {a["name"] for a in algorithms} == {"ML-KEM", "ML-DSA"}


def test_algorithm_detail(client, auth_header):
    algorithms = client.get("/acvp/v1/algorithms", headers=auth_header).json()[1]["algorithms"]
    first = algorithms[0]
    fetched = client.get(f"/acvp/v1/algorithms/{first['id']}", headers=auth_header).json()[1]
    assert fetched == first


def test_unknown_algorithm_404(client, auth_header):
    assert client.get("/acvp/v1/algorithms/999", headers=auth_header).status_code == 404
