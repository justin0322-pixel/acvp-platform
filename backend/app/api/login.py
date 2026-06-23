from fastapi import APIRouter, Body, HTTPException, status

from app.core.auth import create_access_token, decode_token
from app.core.config import get_settings
from app.models.envelope import wrap, unwrap
from app.models.login import LoginPayload, LoginResult

router = APIRouter()


@router.post("/login")
def login(body: list = Body(...)) -> list:
    payload = LoginPayload(**unwrap(body))
    s = get_settings()

    if payload.password != s.demo_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    # Renewal: an (expired or valid) token may be presented for re-issue.
    subject = "demo"
    if payload.accessToken is not None:
        try:
            subject = decode_token(payload.accessToken, verify_exp=False).get("sub", "demo")
        except HTTPException:
            pass  # malformed token is tolerated on renewal once the password matches

    return wrap(LoginResult(accessToken=create_access_token(subject)).model_dump())
