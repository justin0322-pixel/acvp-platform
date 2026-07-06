"""Per-session authorization: a session's resources require that session's token.

[HUMAN REVIEW] Spec: the accessToken issued per test session MUST be supplied to
access that Test Session (11-messaging §jwtToken; 09-login §Multi Refresh JWT).
A token for session A (or a bare login token) must NOT reach session B — 403.
"""
import time

import pytest

from app.core.config import get_settings
from helpers import registration, session_headers, golden_response

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)


def _register(client, v, auth_header, *, is_sample=False, mode="ML-KEM-keyGen-FIPS203"):
    payload = {"algorithms": [registration(mode)], "isSample": is_sample}
    body = client.post("/acvp/v1/testSessions", json=[{"acvVersion": v}, payload],
                       headers=auth_header).json()[1]
    sid = int(body["url"].rsplit("/", 1)[1])
    return sid, body["vectorSetUrls"][0], session_headers(body)


def test_cross_session_token_forbidden(client, acv_version, auth_header):
    v = acv_version
    _, _, a_hdr = _register(client, v, auth_header)                     # session A token
    b_sid, b_vs, _ = _register(client, v, auth_header)                  # session B resources

    # A's token must not reach any of B's session-scoped routes.
    assert client.get(f"/acvp/v1/testSessions/{b_sid}", headers=a_hdr).status_code == 403
    assert client.get(f"/acvp/v1/testSessions/{b_sid}/vectorSets", headers=a_hdr).status_code == 403
    assert client.get(b_vs, headers=a_hdr).status_code == 403
    assert client.get(b_vs + "/results", headers=a_hdr).status_code == 403
    assert client.post(b_vs + "/results", json=[{"acvVersion": v}, golden_response(1)],
                       headers=a_hdr).status_code == 403
    assert client.put(f"/acvp/v1/testSessions/{b_sid}",
                      json=[{"acvVersion": v}, {"moduleUrl": "/m", "oeUrl": "/o"}],
                      headers=a_hdr).status_code == 403


def test_expected_answer_key_gated_by_session_token(client, acv_version, auth_header):
    v = acv_version
    _, _, a_hdr = _register(client, v, auth_header, mode="ML-KEM-encapDecap-FIPS203")
    _, b_vs, _ = _register(client, v, auth_header, is_sample=True,
                           mode="ML-KEM-encapDecap-FIPS203")
    # Even a sample session's answer key must not be reachable with A's token.
    assert client.get(b_vs + "/expected", headers=a_hdr).status_code == 403


def test_login_token_rejected_on_session_route(client, acv_version, auth_header):
    # The bare login token (sub=demo) is shared by everyone -> must be rejected
    # on session-scoped routes; only the session's own token works.
    sid, vs_url, _ = _register(client, acv_version, auth_header)
    assert client.get(f"/acvp/v1/testSessions/{sid}", headers=auth_header).status_code == 403
    assert client.get(vs_url, headers=auth_header).status_code == 403


def test_own_session_token_allowed(client, acv_version, auth_header):
    sid, vs_url, hdr = _register(client, acv_version, auth_header)
    # The session's own token works normally.
    assert client.get(f"/acvp/v1/testSessions/{sid}", headers=hdr).status_code == 200
    for _ in range(50):
        r = client.get(vs_url, headers=hdr)
        if "retry" not in r.json()[1]:
            break
        time.sleep(0.02)
    assert r.status_code == 200
    assert r.json()[1]["algorithm"] == "ML-KEM"


def test_login_level_routes_still_use_login_token(client, auth_header):
    # Login-level (non session-scoped) routes keep using the login token.
    assert client.get("/acvp/v1/algorithms", headers=auth_header).status_code == 200
    assert client.get("/acvp/v1/modules", headers=auth_header).status_code == 200
