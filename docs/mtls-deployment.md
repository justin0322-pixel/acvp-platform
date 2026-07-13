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
        │  TLS 1.2+ handshake, client certificate REQUIRED
        ▼
Nginx ACV Proxy (:8443)          backend/nginx/nginx.conf.template
        │  ssl_verify_client on  → certless connections die at handshake
        │  proxies to uvicorn with:
        │    X-Client-Verify / X-Client-DN   (verification result + audit DN)
        │    X-Proxy-Secret                  (proves "came through the proxy")
        ▼
uvicorn backend (:8000, Docker-internal only — never published to the host)
        │  MTLSMiddleware re-checks both headers (defense in depth)
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

## Setup

```bash
# 1. Dev PKI (CA + server + client certs; backend/certs/ is gitignored)
bash scripts/gen-certs.sh

# 2. Secret (repo root — compose reads .env for interpolation)
cp .env.example .env
python3 -c "import secrets; print('PROXY_SECRET=' + secrets.token_urlsafe(32))" > .env

# 3. Bring everything up
docker compose up --build
```

For a real deployment, replace the dev CA with organization-PKI-issued
certificates and rotate `PROXY_SECRET` alongside them.

## Verifying the SHALL requirements

```bash
# 1. No client certificate → MUST fail at the TLS handshake (not HTTP 403):
curl --cacert backend/certs/ca.crt https://localhost:8443/acvp/v1/algorithms
# expect: alert certificate required / handshake failure

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

- **`ssl_verify_client on` (not `optional`).** Certless connections are
  rejected during the handshake, so unauthenticated traffic never reaches the
  application. The container health check probes uvicorn directly on the
  Docker-internal network, so no certless path through the proxy is needed;
  the middleware's `/health` exemption exists only for that internal probe.
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
  `gen-certs.sh` does not yet emit a browser-importable `.p12` bundle, so the
  web frontend cannot complete the mTLS handshake out of the box.
- No automated live-handshake integration test yet (items 1–4 above are
  manual).
- Script executable bits were lost in the branch snapshot
  (`gen-certs.sh` etc.) — invoke with `bash scripts/...` until fixed.
