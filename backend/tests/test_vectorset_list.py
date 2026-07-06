"""Increment 5: list a session's vector sets.

Spec: GET /testSessions/{id}/vectorSets returns {"vectorSetUrls": [...]} only.
"""
import pytest

from helpers import registration, session_headers

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def test_list_vector_sets_matches_registration(client, acv_version, auth_header):
    reg = [{"acvVersion": acv_version}, {"algorithms": [
        registration("ML-KEM-keyGen-FIPS203"),
        registration("ML-DSA-keyGen-FIPS204"),
    ]}]
    body = client.post("/acvp/v1/testSessions", json=reg, headers=auth_header).json()[1]
    sid = int(body["url"].rsplit("/", 1)[1])
    registered = body["vectorSetUrls"]

    r = client.get(f"/acvp/v1/testSessions/{sid}/vectorSets", headers=session_headers(body))
    assert r.status_code == 200
    payload = r.json()[1]
    # Spec: only vectorSetUrls, nothing else.
    assert set(payload.keys()) == {"vectorSetUrls"}
    assert payload["vectorSetUrls"] == registered
    assert len(payload["vectorSetUrls"]) == 2


def test_list_vector_sets_unknown_session_forbidden(client, auth_header):
    # Authz runs before existence: any token is 403 for a non-existent session.
    assert client.get("/acvp/v1/testSessions/999999/vectorSets", headers=auth_header).status_code == 403
