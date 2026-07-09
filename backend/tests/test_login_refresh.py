"""Multi-Refresh JWT — POST /login/refresh (spec 09-login, optional).

Refresh several session tokens in one call; order is preserved; expired tokens
are refreshable (renewal), forged ones are not.
"""
import time

import jwt
import pytest

from app.core.auth import decode_token
from app.core.config import get_settings
from helpers import registration

_FIXTURE = get_settings().fixtures_dir / "ML-KEM-keyGen-FIPS203" / "prompt.json"

pytestmark = pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="NIST fixtures not vendored; run scripts/fetch-nist-fixtures.sh",
)

PW = get_settings().demo_password


def _session(client, v, auth_header):
    body = client.post("/acvp/v1/testSessions",
                       json=[{"acvVersion": v}, {"algorithms": [registration()]}],
                       headers=auth_header).json()[1]
    return int(body["url"].rsplit("/", 1)[1]), body["accessToken"]


def _refresh(client, v, tokens, password=PW):
    return client.post("/acvp/v1/login/refresh",
                       json=[{"acvVersion": v}, {"password": password, "accessToken": tokens}])


def test_refresh_multiple_tokens_order_preserved(client, acv_version, auth_header):
    v = acv_version
    ida, ta = _session(client, v, auth_header)
    idb, tb = _session(client, v, auth_header)

    r = _refresh(client, v, [ta, tb])
    assert r.status_code == 200
    payload = r.json()[1]
    new = payload["accessToken"]
    assert isinstance(new, list) and len(new) == 2
    # Order preserved: new[i] carries the same subject as input[i].
    assert decode_token(new[0])["sub"] == f"session:{ida}"
    assert decode_token(new[1])["sub"] == f"session:{idb}"
    assert payload["largeEndpointRequired"] is False and payload["sizeConstraint"] == -1


def test_refresh_wrong_password_401(client, acv_version, auth_header):
    v = acv_version
    _, ta = _session(client, v, auth_header)
    assert _refresh(client, v, [ta], password="nope").status_code == 401


def test_refresh_allows_expired_token(client, acv_version):
    s = get_settings()
    now = int(time.time())
    expired = jwt.encode(
        {"iss": "acvp-server", "sub": "session:7", "iat": now - 4000, "nbf": now - 4000, "exp": now - 1000},
        s.jwt_secret, algorithm=s.jwt_alg)
    r = _refresh(client, acv_version, [expired])
    assert r.status_code == 200
    fresh = r.json()[1]["accessToken"][0]
    claims = decode_token(fresh)  # verifies exp -> not expired
    assert claims["sub"] == "session:7" and claims["exp"] > int(time.time())


def test_refresh_rejects_forged_token(client, acv_version):
    now = int(time.time())
    forged = jwt.encode({"sub": "session:1", "iat": now, "nbf": now, "exp": now + 999},
                        "attacker-secret", algorithm="HS256")
    assert _refresh(client, acv_version, [forged]).status_code == 401


def test_refreshed_session_token_still_authorized(client, acv_version, auth_header):
    v = acv_version
    ida, ta = _session(client, v, auth_header)
    idb, _ = _session(client, v, auth_header)

    new = _refresh(client, v, [ta]).json()[1]["accessToken"][0]
    hdr = {"Authorization": f"Bearer {new}"}
    # The refreshed token works on its own session…
    assert client.get(f"/acvp/v1/testSessions/{ida}", headers=hdr).status_code == 200
    # …and still cannot reach another session.
    assert client.get(f"/acvp/v1/testSessions/{idb}", headers=hdr).status_code == 403
