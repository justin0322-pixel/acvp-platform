# mTLS deployment notes (ACV Proxy)

The deployment notes referenced by `docs/acvp-conformance.md` §5. Covers the
TLS/mTLS architecture, the secret model, setup, and how to verify the SHALL
requirements hold.

## Spec basis

| Requirement | Level | Source |
|---|---|---|
| HTTPS + TLS 1.2 or greater + mutual authentication | **SHALL** (validation authority) | spec §4.2 Goals |
| Clients used with a validation authority: same requirements | **SHALL** | spec §4.2 |
| Internal-organizational-testing deployments may omit | MAY | spec §4.2 |
| "TLS mutual certificate authentication" as the strong mechanism | named option | spec §7.1 Authentication |
| TLS parameter selection (protocol floor, cipher suites) | guidance | NIST SP 800-52 Rev. 2 |

This platform *is* the validation-authority side, so the SHALL applies to our
deployment, independent of any connection to NIST systems.

## Architecture

```
DUT / browser / curl
        │  TLS 1.2+ handshake; client certificate verified when presented
        ▼
Nginx ACV Proxy (:8443)          backend/nginx/nginx.conf.template
        │  ssl_verify_client optional → INVALID certs die at handshake;
        │  a MISSING cert is forwarded as X-Client-Verify=NONE
        │  proxies to uvicorn with:
        │    X-Client-Verify / X-Client-DN   (verification result + audit DN)
        │    X-Proxy-Secret                  (proves "came through the proxy")
        ▼
uvicorn backend (:8000, Docker-internal only — never published to the host)
        │  MTLSMiddleware: X-Proxy-Secret must match, X-Client-Verify must be
        │  SUCCESS → certless requests get 403 on every non-exempt path
        ▼
FastAPI app (JWT auth per spec §12.3 — unchanged, orthogonal layer)
```

mTLS and JWT are two independent layers: mTLS authenticates the transport
peer; JWT authorizes the message-level session. Both are required.

## Secret model (fail-closed)

| Setting | Rule | Enforced where |
|---|---|---|
| `PROXY_SECRET` | REQUIRED when `MTLS_ENABLED=true`; ≥16 chars; placeholders rejected | `Settings` validator — server refuses to start |
| `JWT_SECRET` | REQUIRED real value when `APP_ENV=production`; ≥32 chars | `Settings` validator — server refuses to start |
| nginx side of `PROXY_SECRET` | injected at container start via the nginx image's envsubst template | `nginx.conf.template` + compose `environment` |

No real secret exists in version control: the template contains only
`${PROXY_SECRET}`, and compose uses required interpolation
(`${PROXY_SECRET:?...}`), so `docker compose up` fails with a clear message
rather than starting with a known placeholder. Both containers receive the
same value from the repo-root `.env` (see `.env.example`).

Generate a secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## TOTP second factor (NIST credentials specification)

Source: https://github.com/usnistgov/ACVP/wiki/Credentials-Specification-for-Accessing-ACVP
— NIST's deployment defines the login `password` field as an RFC 6238 TOTP.
The protocol spec leaves the field's content open, so this is an opt-in mode:

| Parameter | Value (pinned by the wiki) |
|---|---|
| Algorithm | HMAC-SHA-256 |
| Digits | 8, leading zeros preserved (string compare) |
| Time step | 30 seconds; ±1 step drift tolerated (clients should NTP-sync) |
| Seed | Base64, per client, distributed out-of-band |
| Replay | an accepted code is never accepted again (SP 800-63B) |

- `TOTP_ENABLED=false` (default): static `DEMO_PASSWORD`, for development and
  the web console — spec §4.2 lets internal testing omit this.
- `TOTP_ENABLED=true` (validation-authority mode): `/login` and
  `/login/refresh` require a fresh code. The caller's seed is looked up in
  `TOTP_SEEDS` by the mTLS certificate Subject DN (forwarded as
  `X-Client-DN`), falling back to the `"default"` entry — mirroring NIST's
  model where the certificate says *who you are* and the TOTP proves you
  *hold that client's seed*. Fail-closed: enabling without valid seeds
  refuses to start.

Seed lifecycle (operational, mirrors NIST): the authority generates a seed
per client, delivers it out-of-band (never via the API, never in version
control), and registers it in `TOTP_SEEDS`. Machine clients keep the seed in
their own configuration and compute codes on demand — same as NIST's
reference clients. For manual testing:

```bash
CODE=$(python3 scripts/totp.py "$TOTP_SEED")   # fresh 8-digit code
```

The web console intentionally stays on dev mode (decision 2026-07-16): a
browser holding a long-term seed would be a worse exposure than the demo
password, and TOTP mode targets machine clients.

Correctness oracle: `backend/tests/test_totp.py` pins the implementation to
the RFC 6238 Appendix B SHA-256 test vectors.

## Setup

```bash
# 1. Dev PKI (CA + server + client certs; backend/certs/ is gitignored)
bash scripts/gen-certs.sh

# 2. Secrets (repo root — compose reads .env for interpolation).
#    Both are required: compose refuses to start without them (fail-closed).
python3 - <<'EOF' > .env
import secrets
print("PROXY_SECRET=" + secrets.token_urlsafe(32))
print("JWT_SECRET=" + secrets.token_urlsafe(48))
EOF

# 3. Bring everything up
docker compose up --build
```

For a real deployment, replace the dev CA with organization-PKI-issued
certificates and rotate `PROXY_SECRET` alongside them.

## Verifying the SHALL requirements

```bash
# 1. No client certificate → handshake completes (ssl_verify_client optional,
#    see Design decisions), but every API path MUST return 403 with the
#    mTLS error — the request never reaches a handler:
curl --cacert backend/certs/ca.crt https://localhost:8443/acvp/v1/algorithms
# expect: {"error": "mTLS authentication required. ..."}  (HTTP 403)

# 1b. INVALID client certificate (wrong CA) → MUST still fail at the handshake:
#     (generate a self-signed throwaway cert to test, or use any cert not
#      signed by backend/certs/ca.crt)
# expect: TLS alert / handshake failure

# 2. Valid client certificate → 200 (with a Bearer token for the JWT layer):
curl --cacert backend/certs/ca.crt \
     --cert backend/certs/client.crt --key backend/certs/client.key \
     https://localhost:8443/acvp/v1/algorithms -H "Authorization: Bearer $TOKEN"

# 3. TLS below 1.2 → MUST be refused:
curl --tls-max 1.1 --cacert backend/certs/ca.crt \
     --cert backend/certs/client.crt --key backend/certs/client.key \
     https://localhost:8443/acvp/v1/algorithms
# expect: protocol version alert

# 4. Direct backend access → MUST be unreachable from the host:
curl -m 3 http://localhost:8000/acvp/v1/algorithms
# expect: connection refused / timeout (port not published)
```

Automated coverage: `backend/tests/test_mtls.py` (middleware attack scenarios
+ fail-closed settings). A live-handshake integration test is still TODO.

## Design decisions

- **`ssl_verify_client optional` (not `on`) — a deliberate tradeoff for
  browser clients.** CORS preflight (`OPTIONS`) requests are credential-less
  by the fetch specification, and browsers may open the preflight connection
  without presenting a client certificate; with `on`, every browser request
  would die at the handshake before CORS could even be negotiated. `optional`
  keeps certificate verification (a cert that fails validation still aborts
  the handshake) while letting certless connections reach the backend, where
  `MTLSMiddleware` rejects every non-exempt path with 403 — so mutual
  authentication remains mandatory for all API access, enforced one layer up.
  Cost of the tradeoff: unauthenticated peers can now speak HTTP to the
  middleware (larger pre-auth surface than handshake rejection); accepted in
  exchange for a usable browser flow. Non-browser deployments that need
  handshake-level rejection can flip the single directive back to `on`.
  The container health check probes uvicorn directly on the Docker-internal
  network; the middleware's `/health` exemption exists only for that probe.
- **Cipher policy per SP 800-52r2.** TLS 1.2 limited to ECDHE + AES-GCM
  suites (forward secrecy, AEAD only); TLS 1.3 suites are fixed by
  nginx/OpenSSL and are all AEAD.
- **Header trust is conditional on `X-Proxy-Secret`.** The middleware
  compares with `hmac.compare_digest` and cannot be skipped: settings
  validation guarantees the secret exists whenever mTLS is on.

## Operational rules

- When an ACVP client is attached to a cryptographic module that is in use,
  access to ACVP MUST be restricted to an administrator or other authorized
  user (spec §7.2).
- Never include a JWT, TOTP seed, password, or any authentication secret in
  bug reports, issues, logs, or URLs (rule adopted from the NIST ACVP-Server
  repository README).
- Private keys and real `.env` files never enter version control
  (`backend/certs/`, `.env` are gitignored).

## Known gaps (tracked separately)

- Browser clients need the dev CA trusted and a client certificate imported;
  `gen-certs.sh` does not yet emit a browser-importable `.p12` bundle. Until
  then the web frontend's API calls are rejected (403 from the mTLS
  middleware) — demo the protocol flow with curl (see Verifying above).
- No automated live-handshake integration test yet (items 1–4 above are
  manual).
