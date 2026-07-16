"""RFC 6238 TOTP per the NIST ACVP credentials specification.

[HUMAN REVIEW] Auth-critical. Parameters are pinned by the NIST wiki
"Credentials Specification for Accessing ACVP": HMAC-SHA-256, 8 digits
(leading zeros preserved — codes are compared as strings, never as ints),
30-second time step. One step of client clock drift is tolerated in each
direction (RFC 6238 §6; NIST tells clients to sync with time.nist.gov).
An accepted code cannot be accepted again (SP 800-63B one-time use) — the
last accepted step is tracked per client identity.
"""
import base64
import hmac
import struct
import time
from hashlib import sha256

STEP_SECONDS = 30
DIGITS = 8
DRIFT_WINDOW = 1  # accept ± one step of client clock drift

# client key (mTLS cert DN, or "default") -> last accepted time step.
# In-process state, matching the prototype's in-memory store; a multi-worker
# deployment must move this next to wherever sessions live.
_last_accepted_step: dict[str, int] = {}


def code_at(seed_b64: str, unix_time: float) -> str:
    """The 8-digit TOTP for this seed at this instant (RFC 6238, SHA-256)."""
    key = base64.b64decode(seed_b64)
    step = int(unix_time) // STEP_SECONDS
    digest = hmac.new(key, struct.pack(">Q", step), sha256).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 10**DIGITS:0{DIGITS}d}"


def verify(client_key: str, seed_b64: str, code: str, *, now: float | None = None) -> bool:
    """Check a submitted code, tolerating ±1 step; reject replays.

    Comparison is constant-time (hmac.compare_digest) and every window in
    range is always evaluated, so timing does not reveal which window (if
    any) matched.
    """
    if now is None:
        now = time.time()
    current = int(now) // STEP_SECONDS

    matched_step: int | None = None
    for step in range(current - DRIFT_WINDOW, current + DRIFT_WINDOW + 1):
        expected = code_at(seed_b64, step * STEP_SECONDS)
        if hmac.compare_digest(expected, code) and matched_step is None:
            matched_step = step

    if matched_step is None:
        return False
    if _last_accepted_step.get(client_key, -1) >= matched_step:
        return False  # replay of an already-used (or older) code
    _last_accepted_step[client_key] = matched_step
    return True


def reset_replay_state() -> None:
    """Test hook: forget accepted codes."""
    _last_accepted_step.clear()
