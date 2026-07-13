"""mTLS enforcement middleware (ACVP spec §7.1).

Architecture: Nginx (ACV Proxy) terminates TLS and performs client-cert
verification.  It forwards two headers to uvicorn:

    X-Client-Verify : "SUCCESS" | "FAILED" | "NONE"
    X-Client-DN     : the client certificate's Subject DN (if verified)

This middleware checks those headers when MTLS_ENABLED=true and rejects
requests that lack a valid client certificate, except for paths listed
in MTLS_EXEMPT_PATHS (e.g. /health for orchestrator probes).
"""

from typing import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings


class MTLSMiddleware(BaseHTTPMiddleware):
    """Enforce mTLS client-certificate verification via Nginx proxy headers."""

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

        # ── Verify Nginx-injected header ─────────────────────────────────
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
