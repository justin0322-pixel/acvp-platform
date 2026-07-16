"""TOTP second factor per the NIST ACVP credentials specification.

[HUMAN REVIEW] Auth-critical. Parameter source:
https://github.com/usnistgov/ACVP/wiki/Credentials-Specification-for-Accessing-ACVP
— HMAC-SHA-256, 8 digits (leading zeros preserved), 30-second step.
Correctness oracle: RFC 6238 Appendix B test vectors (SHA-256 column).
Dev mode (TOTP_ENABLED=false, the default) must keep the static demo
password working so existing tests and workflows are untouched.
"""
import base64
import json
import time

import pytest
from pydantic import ValidationError

from app.core import totp
from app.core.config import Settings, get_settings

# RFC 6238 Appendix B seed for the SHA-256 rows (raw ASCII, base64 here).
_RFC_SEED = base64.b64encode(b"12345678901234567890123456789012").decode()

_TEST_SEED = base64.b64encode(b"acvp-platform-test-seed-32bytes!").decode()


@pytest.fixture(autouse=True)
def _clean_state():
    totp.reset_replay_state()
    get_settings.cache_clear()
    yield
    totp.reset_replay_state()
    get_settings.cache_clear()


# ── RFC 6238 Appendix B vectors (SHA-256, 8 digits) ─────────────────────────

@pytest.mark.parametrize(
    "unix_time,expected",
    [
        (59, "46119246"),
        (1111111109, "68084774"),
        (1111111111, "67062674"),
        (1234567890, "91819424"),
        (2000000000, "90698825"),
        (20000000000, "77737706"),
    ],
)
def test_rfc6238_sha256_vectors(unix_time, expected):
    assert totp.code_at(_RFC_SEED, unix_time) == expected


def test_code_is_8_digit_string_with_leading_zeros_preserved():
    # Scan a range of steps; every code must be an 8-char digit string
    # (zero-padded), never an int-truncated 7-char value.
    for step in range(0, 2000):
        code = totp.code_at(_TEST_SEED, step * totp.STEP_SECONDS)
        assert isinstance(code, str) and len(code) == 8 and code.isdigit()


# ── verify(): drift window and replay ───────────────────────────────────────

def test_verify_accepts_current_and_adjacent_windows():
    now = 1_700_000_015  # mid-window
    for drift in (-totp.STEP_SECONDS, 0, totp.STEP_SECONDS):
        totp.reset_replay_state()
        code = totp.code_at(_TEST_SEED, now + drift)
        assert totp.verify("c1", _TEST_SEED, code, now=now)


def test_verify_rejects_two_windows_away():
    now = 1_700_000_015
    stale = totp.code_at(_TEST_SEED, now - 2 * totp.STEP_SECONDS)
    ahead = totp.code_at(_TEST_SEED, now + 2 * totp.STEP_SECONDS)
    assert not totp.verify("c1", _TEST_SEED, stale, now=now)
    assert not totp.verify("c1", _TEST_SEED, ahead, now=now)


def test_verify_rejects_replay_of_accepted_code():
    now = 1_700_000_015
    code = totp.code_at(_TEST_SEED, now)
    assert totp.verify("c1", _TEST_SEED, code, now=now)
    assert not totp.verify("c1", _TEST_SEED, code, now=now)  # SP 800-63B


def test_replay_state_is_per_client():
    now = 1_700_000_015
    code = totp.code_at(_TEST_SEED, now)
    assert totp.verify("c1", _TEST_SEED, code, now=now)
    assert totp.verify("c2", _TEST_SEED, code, now=now)  # other client unaffected


def test_verify_rejects_garbage():
    assert not totp.verify("c1", _TEST_SEED, "notdigits", now=time.time())
    assert not totp.verify("c1", _TEST_SEED, "", now=time.time())


# ── fail-closed configuration ────────────────────────────────────────────────

def test_totp_enabled_without_seeds_refused():
    with pytest.raises(ValidationError, match="TOTP_SEEDS"):
        Settings(_env_file=None, totp_enabled=True)


def test_totp_enabled_with_bad_base64_refused():
    with pytest.raises(ValidationError, match="TOTP_SEEDS"):
        Settings(_env_file=None, totp_enabled=True, totp_seeds={"default": "not-b64!!"})


def test_totp_enabled_with_short_seed_refused():
    short = base64.b64encode(b"short").decode()
    with pytest.raises(ValidationError, match="TOTP_SEEDS"):
        Settings(_env_file=None, totp_enabled=True, totp_seeds={"default": short})


def test_totp_enabled_with_valid_seed_accepted():
    s = Settings(_env_file=None, totp_enabled=True, totp_seeds={"default": _TEST_SEED})
    assert s.totp_enabled


# ── /login and /login/refresh behaviour ──────────────────────────────────────

def _enable_totp(monkeypatch):
    monkeypatch.setenv("TOTP_ENABLED", "true")
    monkeypatch.setenv("TOTP_SEEDS", json.dumps({"default": _TEST_SEED}))
    get_settings.cache_clear()


def test_login_with_fresh_totp_succeeds(client, acv_version, monkeypatch):
    _enable_totp(monkeypatch)
    code = totp.code_at(_TEST_SEED, time.time())
    r = client.post("/acvp/v1/login", json=[{"acvVersion": acv_version}, {"password": code}])
    assert r.status_code == 200
    assert r.json()[1]["accessToken"]


def test_login_with_static_password_fails_in_totp_mode(client, acv_version, monkeypatch):
    _enable_totp(monkeypatch)
    r = client.post(
        "/acvp/v1/login",
        json=[{"acvVersion": acv_version}, {"password": get_settings().demo_password}],
    )
    assert r.status_code == 401


def test_login_with_wrong_code_fails(client, acv_version, monkeypatch):
    _enable_totp(monkeypatch)
    r = client.post("/acvp/v1/login", json=[{"acvVersion": acv_version}, {"password": "00000000"}])
    assert r.status_code == 401


def test_renewal_requires_fresh_totp(client, acv_version, monkeypatch):
    _enable_totp(monkeypatch)
    code = totp.code_at(_TEST_SEED, time.time())
    r = client.post("/acvp/v1/login", json=[{"acvVersion": acv_version}, {"password": code}])
    token = r.json()[1]["accessToken"]

    # Same code again within the window is a replay — must be rejected.
    r2 = client.post(
        "/acvp/v1/login",
        json=[{"acvVersion": acv_version}, {"password": code, "accessToken": token}],
    )
    assert r2.status_code == 401

    # A fresh (next-window) code renews fine.
    totp.reset_replay_state()
    fresh = totp.code_at(_TEST_SEED, time.time())
    r3 = client.post(
        "/acvp/v1/login",
        json=[{"acvVersion": acv_version}, {"password": fresh, "accessToken": token}],
    )
    assert r3.status_code == 200


def test_dev_mode_static_password_still_works(client, acv_version):
    # TOTP disabled (default): existing behaviour byte-for-byte unchanged.
    r = client.post(
        "/acvp/v1/login",
        json=[{"acvVersion": acv_version}, {"password": get_settings().demo_password}],
    )
    assert r.status_code == 200
