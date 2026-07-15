#!/usr/bin/env python3
"""Print the current 8-digit ACVP TOTP code for a seed.

Usage:
    python3 scripts/totp.py <base64-seed>
    TOTP_SEED=<base64-seed> python3 scripts/totp.py

Parameters follow the NIST wiki "Credentials Specification for Accessing
ACVP": HMAC-SHA-256, 8 digits, 30-second step. Typical use in a shell:

    CODE=$(python3 scripts/totp.py "$TOTP_SEED")
    curl ... -d "[{\"acvVersion\":\"1.0\"},{\"password\":\"$CODE\"}]" .../login
"""
import base64
import hmac
import os
import struct
import sys
import time
from hashlib import sha256


def code_at(seed_b64: str, unix_time: float) -> str:
    key = base64.b64decode(seed_b64)
    step = int(unix_time) // 30
    digest = hmac.new(key, struct.pack(">Q", step), sha256).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 10**8:08d}"


def main() -> int:
    seed = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TOTP_SEED", "")
    if not seed:
        print("usage: totp.py <base64-seed>   (or set TOTP_SEED)", file=sys.stderr)
        return 2
    try:
        print(code_at(seed, time.time()))
    except Exception:
        print("error: seed is not valid Base64", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
