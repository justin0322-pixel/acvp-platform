import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=True)


def create_access_token(subject: str) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "iss": "acvp-server",
        "sub": subject,
        "iat": now,
        "nbf": now,
        "exp": now + s.jwt_expire_seconds,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg)


def decode_token(token: str, *, verify_exp: bool = True) -> dict:
    s = get_settings()
    try:
        # `algorithms` is an allow-list: an `alg: none` token can never be accepted.
        return jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_alg],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {exc.__class__.__name__}",
        )


def current_subject(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    return decode_token(creds.credentials).get("sub", "")
