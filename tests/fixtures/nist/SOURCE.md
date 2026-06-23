# NIST ACVP golden test vectors — source & provenance

The JSON files under this directory are the **golden test vectors** for ML-KEM (FIPS 203)
and ML-DSA (FIPS 204), copied verbatim from NIST. They are the objective source of truth for
test-driven development of the server-client layer, and the acceptance oracle for the FIPS 203 /
204 crypto teams (feeding a real crypto module a NIST `prompt` must reproduce the NIST
`expectedResults`).

> **Do not edit these files.** They are READ-ONLY by design (the fetch script removes write
> permission). If a test fails, fix the code — never the fixture. Editing a golden vector
> destroys its value as an oracle.

## Source

- **Repository**: https://github.com/usnistgov/ACVP-Server
- **Path in source**: `gen-val/json-files/<MODE>/`
- **License**: U.S. Government work, public domain (Title 17 U.S.C. §105) — free to vendor here.

## Provenance (auto-filled by scripts/fetch-nist-fixtures.sh)

- **Source ref**: `master`
- **Pinned commit**: `15c0f3deeefbfa8cb6cd32a99e1ca3b738c66bf0`
- **Fetched (UTC)**: `2026-06-23T13:12:39Z`

To pin a specific release instead of `master`, run e.g. `scripts/fetch-nist-fixtures.sh v1.1.0.40`.
The script rewrites the three lines above with the actual resolved values.

## Modes vendored

| Mode folder | FIPS | What it tests |
| --- | --- | --- |
| `ML-KEM-keyGen-FIPS203` | 203 | ML-KEM key generation |
| `ML-KEM-encapDecap-FIPS203` | 203 | ML-KEM encapsulation / decapsulation (+ ek/dk key checks) |
| `ML-DSA-keyGen-FIPS204` | 204 | ML-DSA key generation |
| `ML-DSA-sigGen-FIPS204` | 204 | ML-DSA signature generation |
| `ML-DSA-sigVer-FIPS204` | 204 | ML-DSA signature verification |

## Files per mode

| File | Role |
| --- | --- |
| `registration.json` | example capability registration for the mode |
| `prompt.json` | test cases the server sends to the client |
| `internalProjection.json` | server-internal full answer key |
| `expectedResults.json` | the golden correct responses (acceptance baseline) |
| `validation.json` | example validation output (per-test-case pass/fail) |

## Important: these are payloads, not wire messages

Each file contains the **inner payload object only** — e.g. `prompt.json` is
`{"vsId": 42, "algorithm": "ML-KEM", "mode": "keyGen", ..., "testGroups": [...]}`.

The ACVP **wire format** wraps this payload in the version envelope:

```json
[
  {"acvVersion": "1.0"},
  { ...the object from the fixture file... }
]
```

So the server adds/strips the `[{"acvVersion": ...}, {payload}]` envelope; the fixtures store
the payload. Tests should compare against the payload and assert the envelope separately. (See
the acvp-protocol skill, "Message envelope".)

## How to (re)fetch / update the pin

From the repository root:

```bash
scripts/fetch-nist-fixtures.sh            # default: master, records the resolved commit
scripts/fetch-nist-fixtures.sh v1.1.0.40  # pin to a specific release tag
```

The script sparse-checks-out only the five folders above, copies them here, updates the
provenance block, and re-applies read-only permissions.
