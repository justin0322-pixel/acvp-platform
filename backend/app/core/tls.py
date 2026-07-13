"""mTLS enforcement middleware (ACVP spec §7.1).

Architecture: Nginx (ACV Proxy) terminates TLS and performs client-cert
verification.  It forwards two headers to uvicorn:

    X-Client-Verify : "SUCCESS" | "FAILED" | "NONE"
    X-Client-DN     : the client certificate's Subject DN (if verified)

SECURITY: To prevent attackers from bypassing Nginx and connecting directly
to uvicorn (:8000) with forged X-Client-Verify headers, a shared secret
(PROXY_SECRET) is injected by Nginx as X-Proxy-Secret.  The middleware
rejects any request where this header is missing or does not match.

This middleware checks those headers when MTLS_ENABLED=true and rejects
requests that lack a valid client certificate, except for paths listed
in MTLS_EXEMPT_PATHS (e.g. /health for orchestrator probes).
"""

import hmac
from typing import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings


class MTLSMiddleware(BaseHTTPMiddleware):
    """Enforce mTLS client-certificate verification via Nginx proxy headers.

    Two-layer verification:
      1. X-Proxy-Secret must match PROXY_SECRET (proves the request came
         through the trusted Nginx proxy, not a direct connection).
      2. X-Client-Verify must be "SUCCESS" (proves Nginx verified the
         client certificate).
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        settings = get_settings()

        # ── Bypass when mTLS is disabled ─────────────────────────────────
        if not settings.mtls_enabled:
            return await call_next(request)

        # ── Exempt paths (e.g. /health) ──────────────────────────────────
        if request.url.path in settings.mtls_exempt_paths:
            return await call_next(request)

        # ── Layer 1: Verify the request came through the trusted proxy ───
        # Without this check, an attacker could connect directly to
        # uvicorn (:8000) and forge the X-Client-Verify header.
        if settings.proxy_secret:
            incoming_secret = request.headers.get("X-Proxy-Secret", "")
            if not hmac.compare_digest(incoming_secret, settings.proxy_secret):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": (
                            "Direct access denied. "
                            "Requests must be routed through the TLS proxy."
                        )
                    },
                )

        # ── Layer 2: Verify Nginx confirmed the client certificate ───────
        client_verify = request.headers.get("X-Client-Verify")
        if client_verify != "SUCCESS":
            return JSONResponse(
                status_code=403,
                content={
                    "error": (
                        "mTLS authentication required. "
                        "Client certificate missing or invalid."
                    )
                },
            )

        # Store the Distinguished Name on request.state for audit logging.
        request.state.client_dn = request.headers.get("X-Client-DN", "")

        return await call_next(request)
