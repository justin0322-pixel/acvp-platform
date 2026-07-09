"""Strict JWT verification: the four required claims must be present and iss
must match (spec 12.3 "the first four claims are required"), and a renewal that
presents an invalid token is rejected rather than silently downgraded.
"""
import time

import jwt
import pytest

from app.core.config import get_settings

S = get_settings()


def _tok(claims: dict, *, secret=None, alg=None) -> str:
    return jwt.encode(claims, secret or S.jwt_secret, algorithm=alg or S.jwt_alg)


def _full(**over) -> dict:
    now = int(time.time())
    base = {"iss": "acvp-server", "sub": "demo", "iat": now, "nbf": now, "exp": now + 999}
    base.update(over)
    return base


def _get_algorithms(client, token: str):
    return client.get("/acvp/v1/algorithms", headers={"Authorization": f"Bearer {token}"})


# --- (1) strict claim presence + issuer ----------------------------------------

@pytest.mark.parametrize("drop", ["exp", "iat", "nbf", "iss"])
def test_token_missing_required_claim_rejected(client, drop):
    claims = _full()
    del claims[drop]
    assert _get_algorithms(client, _tok(claims)).status_code == 401


def test_token_wrong_issuer_rejected(client):
    assert _get_algorithms(client, _tok(_full(iss="EVIL"))).status_code == 401


def test_valid_token_still_accepted(client, auth_header):
    # regression: a normally-issued token keeps working
    assert client.get("/acvp/v1/algorithms", headers=auth_header).status_code == 200


# --- (2) renewal rejects invalid tokens ----------------------------------------

def test_renewal_with_forged_token_rejected(client, acv_version):
    forged = _tok(_full(sub="session:999"), secret="attacker-secret", alg="HS256")
    r = client.post("/acvp/v1/login",
                    json=[{"acvVersion": acv_version}, {"password": S.demo_password, "accessToken": forged}])
    assert r.status_code == 401


def test_renewal_with_malformed_token_rejected(client, acv_version):
    r = client.post("/acvp/v1/login",
                    json=[{"acvVersion": acv_version}, {"password": S.demo_password, "accessToken": "not.a.jwt"}])
    assert r.status_code == 401


def test_renewal_with_valid_expired_token_succeeds(client, acv_version):
    # A genuinely-issued token that merely expired must still renew (that's the point).
    now = int(time.time())
    expired = _tok(_full(sub="session:5", iat=now - 4000, nbf=now - 4000, exp=now - 100))
    r = client.post("/acvp/v1/login",
                    json=[{"acvVersion": acv_version}, {"password": S.demo_password, "accessToken": expired}])
    assert r.status_code == 200
    from app.core.auth import decode_token
    assert decode_token(r.json()[1]["accessToken"])["sub"] == "session:5"
