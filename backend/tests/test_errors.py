"""Error responses use the spec's {"error": ...} shape.

Spec (Appendix B): server errors carry an "error" field describing the problem
(e.g. HTTP 400 with "error": "Incorrectly formatted JSON ...").
"""
import pytest

from app.core.config import get_settings

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def test_404_uses_error_key(client, auth_header):
    # A request resource that legitimately 404s under the login token
    # (session-scoped routes now 403 before the existence check).
    r = client.get("/acvp/v1/requests/999999", headers=auth_header)
    assert r.status_code == 404
    assert "error" in r.json() and "detail" not in r.json()


def test_405_uses_error_key(client, auth_header):
    # DELETE is not defined for the results resource.
    r = client.delete("/acvp/v1/testSessions/1/vectorSets/1/results", headers=auth_header)
    assert r.status_code == 405
    assert "error" in r.json()


def test_malformed_envelope_uses_error_key(client, acv_version):
    r = client.post("/acvp/v1/login", json={"not": "an envelope"})
    assert r.status_code == 400
    assert "error" in r.json()
