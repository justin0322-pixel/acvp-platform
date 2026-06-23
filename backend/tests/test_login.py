from app.core.config import get_settings


def test_login_initial_returns_token(client, acv_version):
    body = [{"acvVersion": acv_version}, {"password": get_settings().demo_password}]
    r = client.post("/acvp/v1/login", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out[0]["acvVersion"] == acv_version
    assert out[1]["accessToken"]
    assert out[1]["largeEndpointRequired"] is False
    assert out[1]["sizeConstraint"] == -1


def test_login_wrong_password_401(client, acv_version):
    r = client.post("/acvp/v1/login", json=[{"acvVersion": acv_version}, {"password": "nope"}])
    assert r.status_code == 401


def test_protected_requires_auth(client):
    assert client.get("/acvp/v1/algorithms").status_code in (401, 403)


def test_algorithms_with_auth(client, auth_header):
    r = client.get("/acvp/v1/algorithms", headers=auth_header)
    assert r.status_code == 200
    assert len(r.json()[1]["algorithms"]) == 5


def test_alg_none_token_rejected(client):
    import jwt

    forged = jwt.encode({"sub": "demo"}, key="", algorithm="none")
    r = client.get("/acvp/v1/algorithms", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
