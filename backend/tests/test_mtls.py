"""Tests for the mTLS middleware (app.core.tls.MTLSMiddleware).

Uses a standalone FastAPI app so we can test the middleware in isolation
without the full ACVP router stack.

Security tests verify that:
  - Forging X-Client-Verify without a valid proxy secret is rejected (403)
  - Direct connections to uvicorn (bypassing Nginx) cannot spoof mTLS
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
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

_TEST_PROXY_SECRET = "test-secret-do-not-use-in-production"


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


# ── Tests: fail-closed configuration ─────────────────────────────────────────
# [HUMAN REVIEW] Secret hygiene. mTLS mode without a real PROXY_SECRET would
# let anything on the container network forge X-Client-Verify, so it must be
# a startup error, never a silent bypass. Same for default JWT_SECRET in
# production (project rule: secrets never default).
class TestFailClosedConfig:
    def test_mtls_without_proxy_secret_refused(self):
        with pytest.raises(ValidationError, match="PROXY_SECRET"):
            Settings(_env_file=None, mtls_enabled=True, proxy_secret=None)

    def test_mtls_with_placeholder_proxy_secret_refused(self):
        with pytest.raises(ValidationError, match="PROXY_SECRET"):
            Settings(
                _env_file=None,
                mtls_enabled=True,
                proxy_secret="CHANGE-ME-GENERATE-A-REAL-SECRET",
            )

    def test_mtls_with_short_proxy_secret_refused(self):
        with pytest.raises(ValidationError, match="PROXY_SECRET"):
            Settings(_env_file=None, mtls_enabled=True, proxy_secret="short")

    def test_mtls_with_real_proxy_secret_accepted(self):
        s = Settings(_env_file=None, mtls_enabled=True, proxy_secret=_TEST_PROXY_SECRET)
        assert s.proxy_secret == _TEST_PROXY_SECRET

    def test_production_with_default_jwt_secret_refused(self):
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(_env_file=None, app_env="production")

    def test_production_with_short_jwt_secret_refused(self):
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            Settings(_env_file=None, app_env="production", jwt_secret="tooshort")

    def test_production_with_strong_jwt_secret_accepted(self):
        s = Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="a-genuinely-long-random-secret-0123456789abcdef",
        )
        assert s.app_env == "production"

    def test_dev_defaults_still_work(self):
        s = Settings(_env_file=None)
        assert s.app_env == "dev" and not s.mtls_enabled


# ── Tests: mTLS + proxy secret (production mode) ────────────────────────────
class TestMTLSWithProxySecret:
    """When both MTLS_ENABLED=true and PROXY_SECRET are set, direct
    connections forging X-Client-Verify are blocked."""

    @pytest.fixture(autouse=True)
    def _enable(self, monkeypatch):
        monkeypatch.setenv("MTLS_ENABLED", "true")
        monkeypatch.setenv("PROXY_SECRET", _TEST_PROXY_SECRET)
        get_settings.cache_clear()

    # --- ATTACK: forge X-Client-Verify without proxy secret ---
    def test_forged_header_without_secret_rejected(self):
        """Simulates: curl -H 'X-Client-Verify: SUCCESS' http://host:8000/..."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={"X-Client-Verify": "SUCCESS"},
        )
        assert r.status_code == 403
        assert "Direct access denied" in r.json()["error"]

    def test_forged_header_with_wrong_secret_rejected(self):
        """Attacker guesses the wrong proxy secret."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={
                "X-Client-Verify": "SUCCESS",
                "X-Proxy-Secret": "wrong-secret",
            },
        )
        assert r.status_code == 403
        assert "Direct access denied" in r.json()["error"]

    # --- LEGITIMATE: correct proxy secret + valid client cert ---
    def test_valid_proxy_secret_and_cert_passes(self):
        """Simulates a real request through Nginx with valid client cert."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={
                "X-Proxy-Secret": _TEST_PROXY_SECRET,
                "X-Client-Verify": "SUCCESS",
                "X-Client-DN": "CN=acvp-test-client,O=ACVP-Dev,C=US",
            },
        )
        assert r.status_code == 200
        assert r.json()["client_dn"] == "CN=acvp-test-client,O=ACVP-Dev,C=US"

    def test_valid_proxy_secret_but_no_cert_rejected(self):
        """Request came through Nginx but client didn't provide a certificate."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={
                "X-Proxy-Secret": _TEST_PROXY_SECRET,
                "X-Client-Verify": "NONE",
            },
        )
        assert r.status_code == 403
        assert "mTLS" in r.json()["error"]

    def test_valid_proxy_secret_but_failed_cert_rejected(self):
        """Request came through Nginx but client cert was invalid."""
        r = _client.get(
            "/acvp/v1/algorithms",
            headers={
                "X-Proxy-Secret": _TEST_PROXY_SECRET,
                "X-Client-Verify": "FAILED",
            },
        )
        assert r.status_code == 403

    # --- Exempt paths still work regardless of proxy secret ---
    def test_health_exempt_even_with_proxy_secret(self):
        r = _client.get("/health")
        assert r.status_code == 200
