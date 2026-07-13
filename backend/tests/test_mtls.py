"""Tests for the mTLS middleware (app.core.tls.MTLSMiddleware).

Uses a standalone FastAPI app so we can test the middleware in isolation
without the full ACVP router stack.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.tls import MTLSMiddleware

# ── Standalone test app ──────────────────────────────────────────────────────
_app = FastAPI()
_app.add_middleware(MTLSMiddleware)


@_app.get("/health")
def _health():
    return {"status": "ok"}


@_app.get("/acvp/v1/algorithms")
def _algorithms(request: Request):
    # Expose the client_dn set by the middleware (if any) so tests can assert it.
    dn = getattr(request.state, "client_dn", None)
    return {"algorithms": [], "client_dn": dn}


_client = TestClient(_app)


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_settings():
    """Clear the LRU-cached settings before/after every test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Tests: mTLS disabled ────────────────────────────────────────────────────
class TestMTLSDisabled:
    """When MTLS_ENABLED=false the middleware is a no-op."""

    def test_health_passes(self, monkeypatch):
        monkeypatch.setenv("MTLS_ENABLED", "false")
        get_settings.cache_clear()
        assert _client.get("/health").status_code == 200

    def test_api_passes_without_headers(self, monkeypatch):
        monkeypatch.setenv("MTLS_ENABLED", "false")
        get_settings.cache_clear()
        r = _client.get("/acvp/v1/algorithms")
        assert r.status_code == 200


# ── Tests: mTLS enabled ─────────────────────────────────────────────────────
class TestMTLSEnabled:
    """When MTLS_ENABLED=true the middleware enforces client-cert headers."""

    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("MTLS_ENABLED", "true")
        get_settings.cache_clear()

    # --- exempt paths ---
    def test_health_exempt(self):
        """Exempt paths bypass the check even without any cert header."""
        r = _client.get("/health")
        assert r.status_code == 200

    # --- missing / bad header ---
    def test_no_header_returns_403(self):
        r = _client.get("/acvp/v1/algorithms")
        assert r.status_code == 403
        assert "mTLS" in r.json()["error"]

    def test_failed_verify_returns_403(self):
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={"X-Client-Verify": "FAILED"},
        )
        assert r.status_code == 403

    def test_none_verify_returns_403(self):
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={"X-Client-Verify": "NONE"},
        )
        assert r.status_code == 403

    # --- valid header ---
    def test_success_passes(self):
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={
                "X-Client-Verify": "SUCCESS",
                "X-Client-DN": "CN=acvp-test-client,O=ACVP-Dev,C=US",
            },
        )
        assert r.status_code == 200
        assert r.json()["client_dn"] == "CN=acvp-test-client,O=ACVP-Dev,C=US"

    def test_success_without_dn_still_passes(self):
        """If Nginx sends SUCCESS but no DN, the middleware sets an empty string."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={"X-Client-Verify": "SUCCESS"},
        )
        assert r.status_code == 200
        assert r.json()["client_dn"] == ""
