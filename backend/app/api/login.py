from fastapi import APIRouter, Body, HTTPException, status

from app.core.auth import create_access_token, decode_token
from app.core.config import get_settings
from app.models.envelope import wrap, unwrap
from app.models.login import LoginPayload, LoginResult, LoginRefreshPayload, LoginRefreshResult

router = APIRouter()


@router.post("/login")
def login(body: list = Body(...)) -> list:
    payload = LoginPayload(**unwrap(body))
    s = get_settings()

    if payload.password != s.demo_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    subject = "demo"
    if payload.accessToken is not None:
        try:
            subject = decode_token(payload.accessToken, verify_exp=False).get("sub", "demo")
        except HTTPException:
            pass  

    return wrap(LoginResult(accessToken=create_access_token(subject)).model_dump())


@router.post("/login/refresh")
def refresh(body: list = Body(...)) -> list:
    """Multi-Refresh JWT: reissue several (session) tokens at once (spec 09-login).

    Each token is re-signed with a fresh expiry, preserving its subject and the
    request order. Expired tokens are refreshable (that is the point); a token
    with a bad signature is rejected (decode_token raises 401).
    """
    payload = LoginRefreshPayload(**unwrap(body))
    s = get_settings()

    if payload.password != s.demo_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    refreshed = [
        create_access_token(decode_token(tok, verify_exp=False).get("sub", "demo"))
        for tok in payload.accessToken
    ]
    return wrap(LoginRefreshResult(accessToken=refreshed).model_dump())
