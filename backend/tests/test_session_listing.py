"""GET /testSessions — paged test session listing (spec 12.16.1, OPTIONAL).

"Returns a paged listing of test sessions for the current user. Each element in
the data array is a test session object as described in Section 12.16.3."

Paged response shape is spec 12.5.2: totalCount / incomplete / links / data.
"""
import pytest

from helpers import registration, session_headers

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header):
    reg = [{"acvVersion": v}, {"algorithms": [registration("ML-KEM-keyGen-FIPS203")]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    return int(body["url"].rsplit("/", 1)[1]), session_headers(body)


def test_listing_is_a_paged_response(client, acv_version, auth_header):
    sid, _ = _register(client, acv_version, auth_header)

    payload = client.get("/acvp/v1/testSessions", headers=auth_header).json()[1]

    assert set(payload.keys()) == {"totalCount", "incomplete", "links", "data"}
    assert set(payload["links"].keys()) == {"first", "next", "prev", "last"}
    assert payload["totalCount"] >= 1
    assert isinstance(payload["data"], list)

    # Each element is a test session object (spec 12.16.3).
    session = next(s for s in payload["data"] if s["url"].endswith(f"/{sid}"))
    assert set(session.keys()) >= {
        "url", "acvpVersion", "createdOn", "expiresOn", "encryptAtRest",
        "vectorSetsUrl", "publishable", "passed", "isSample",
    }
    assert "accessToken" not in session  # never re-disclose a session credential


def test_listing_pages_with_offset_and_limit(client, acv_version, auth_header):
    for _ in range(3):
        _register(client, acv_version, auth_header)

    first = client.get("/acvp/v1/testSessions?offset=0&limit=2", headers=auth_header).json()[1]
    assert len(first["data"]) == 2
    assert first["incomplete"] is True
    assert first["links"]["prev"] is None
    assert "offset=2" in first["links"]["next"]

    second = client.get(first["links"]["next"], headers=auth_header).json()[1]
    assert second["links"]["prev"] is not None
    # No overlap between the pages.
    assert {s["url"] for s in first["data"]}.isdisjoint({s["url"] for s in second["data"]})


def test_listing_excludes_cancelled_sessions(client, acv_version, auth_header):
    sid, sh = _register(client, acv_version, auth_header)
    assert client.delete(f"/acvp/v1/testSessions/{sid}", headers=sh).status_code == 200

    payload = client.get("/acvp/v1/testSessions", headers=auth_header).json()[1]
    assert all(not s["url"].endswith(f"/{sid}") for s in payload["data"])


def test_listing_requires_authentication(client):
    # Spec 12.3.2: accessing a service without a usable JWT is a 401.
    assert client.get("/acvp/v1/testSessions").status_code == 401
