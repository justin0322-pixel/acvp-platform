from fastapi import APIRouter, Body, HTTPException, Request, status

from app.core import totp
from app.core.auth import create_access_token, decode_token
from app.core.config import get_settings
from app.models.envelope import wrap, unwrap
from app.models.login import LoginPayload, LoginResult, LoginRefreshPayload, LoginRefreshResult

router = APIRouter()


def _check_credentials(request: Request, password: str | None) -> None:
    """Authenticate the login/refresh caller.

    TOTP mode (NIST credentials spec): the password field carries a fresh
    RFC 6238 code, verified against the caller's seed — looked up by the
    mTLS certificate DN that MTLSMiddleware stored on request.state, falling
    back to the "default" registry entry. The static demo password is NOT
    accepted in this mode.
    Dev mode (default): static demo password, behaviour unchanged.
    """
    s = get_settings()
    if s.totp_enabled:
        client_key = getattr(request.state, "client_dn", "") or "default"
        seed = s.totp_seeds.get(client_key) or s.totp_seeds.get("default")
        if not password or not seed or not totp.verify(client_key, seed, password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    elif password != s.demo_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")


@router.post("/login")
def login(request: Request, body: list = Body(...)) -> list:
    payload = LoginPayload(**unwrap(body))
    _check_credentials(request, payload.password)

    subject = "demo"
    if payload.accessToken is not None:
        # Renewal: carry the subject over from the presented token. A forged or
        # malformed token is rejected (401) rather than silently downgraded — an
        # expired-but-valid token is still accepted (verify_exp=False).
        subject = decode_token(payload.accessToken, verify_exp=False).get("sub", "demo")

    return wrap(LoginResult(accessToken=create_access_token(subject)).model_dump())


@router.post("/login/refresh")
def refresh(request: Request, body: list = Body(...)) -> list:
    """Multi-Refresh JWT: reissue several (session) tokens at once (spec 09-login).

    Each token is re-signed with a fresh expiry, preserving its subject and the
    request order. Expired tokens are refreshable (that is the point); a token
    with a bad signature is rejected (decode_token raises 401).
    """
    payload = LoginRefreshPayload(**unwrap(body))
    _check_credentials(request, payload.password)

    refreshed = [
        create_access_token(decode_token(tok, verify_exp=False).get("sub", "demo"))
        for tok in payload.accessToken
    ]
    return wrap(LoginRefreshResult(accessToken=refreshed).model_dump())
