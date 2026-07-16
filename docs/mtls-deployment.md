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
        │  ssl_verify_client optional → INVALID certs get nginx's own 400
        │  "SSL certificate error" (handshake still completes; verified
        │  empirically — see Design decisions); a MISSING cert is forwarded
        │  as X-Client-Verify=NONE
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
# 1. Dev PKI (CA + server + client certs, CRL, and a browser-importable
#    client.p12; backend/certs/ is gitignored)
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

## Browser client setup

The web console needs the dev CA trusted and a client certificate imported —
without both, every API call gets a 403 from the mTLS middleware (the
frontend's own TOTP posture is unchanged, see above; this section is only
about presenting a client certificate at all).

1. **Trust the dev CA** (`backend/certs/ca.crt`), once per machine:
   - **macOS**: open the file (or `security add-trusted-cert -d -r trustRoot
     -k ~/Library/Keychains/login.keychain-db backend/certs/ca.crt`), then in
     Keychain Access set it to "Always Trust" for SSL.
   - **Windows**: double-click `ca.crt` → *Install Certificate* → *Local
     Machine* (or *Current User*) → *Place all certificates in the following
     store* → *Trusted Root Certification Authorities*.
   - **Firefox** (keeps its own store regardless of OS): *Settings* →
     *Privacy & Security* → *Certificates* → *View Certificates* →
     *Authorities* → *Import* → `ca.crt` → check *Trust this CA to identify
     websites*.
2. **Import the client identity**: `backend/certs/client.p12`, password
   `$CERT_P12_PASSWORD` (default `acvp-dev` — see `gen-certs.sh`).
   - **macOS**: double-click the `.p12`, or `security import
     backend/certs/client.p12 -P acvp-dev -k ~/Library/Keychains/login.keychain-db`.
   - **Windows**: double-click the `.p12` → *Current User* → enter the
     password → *Place all certificates in the following store* → *Personal*.
   - **Firefox**: *Certificates* → *Your Certificates* → *Import* →
     `client.p12` → enter the password.
3. Visit `https://localhost:8443` (or the frontend dev server proxied
   through it). The browser prompts to pick a client certificate on first
   connection — select the imported `acvp-test-client` identity.

This is dev-only PKI (self-signed CA, checked-in-gitignore private keys) —
never trust `backend/certs/ca.crt` on a machine outside local development.

## Revoking a client certificate

If a DUT's private key leaks, revoke just that certificate instead of
rotating the whole CA:

```bash
# 1. Revoke (records the serial in backend/certs/index.txt)
openssl ca -config backend/certs/ca.cnf -revoke backend/certs/client.crt

# 2. Re-sign the CRL nginx reads (ssl_crl in nginx.conf.template)
openssl ca -config backend/certs/ca.cnf -gencrl -out backend/certs/ca.crl

# 3. Nginx re-reads the CRL on reload — no restart, no downtime
docker compose exec proxy nginx -s reload
```

Issue the replacement client identity with `gen-certs.sh` (or repeat its
client-cert step manually) and redistribute the new `.p12` to that client
out-of-band. `backend/certs/ca.cnf` is the `openssl ca` database gen-certs.sh
sets up; it's what makes revocation possible without touching the CA key.

## Rate limiting

`/acvp/v1/login` and `/acvp/v1/login/refresh` are throttled per source IP
(`limit_req zone=login_limit`, 10r/m + burst 5, `nginx.conf.template`). The
NIST credentials-spec TOTP is 8 digits (10^8 search space) — large enough
that this isn't the primary defense, but online guessing across the 30s
validity window is still cheap to make more expensive. Exceeding the limit
returns `429`. Tune `rate=`/`burst=` in `nginx.conf.template` if legitimate
automated clients (e.g. a CI job re-logging-in frequently) start tripping it.

## Verifying the SHALL requirements

```bash
docker compose up --build -d
bash scripts/verify-mtls.sh
```

Runs the real handshake against the live proxy — not the middleware in
isolation — and asserts on it:

1. No client certificate → handshake completes (`ssl_verify_client
   optional`, see Design decisions), but every API path MUST return 403 with
   the mTLS error — the request never reaches a handler.
2. INVALID client certificate (wrong CA) → MUST be rejected (verified: nginx
   completes the TLS handshake, then returns its own 400 "SSL certificate
   error" before proxying to the backend — see Design decisions).
3. Valid client certificate → passes the mTLS layer (reaches the JWT-auth
   application code instead of the 403 mTLS error).
4. TLS below 1.2 → MUST be refused.
5. Direct backend access (`:8000`) → MUST be unreachable from the host.
6. Non-FIPS TLS 1.3 suite (ChaCha20-Poly1305) → MUST be refused.
7. A revoked client certificate → MUST be rejected the same way as #2 (HTTP
   400, not a handshake failure — `ssl_crl` is checked as part of the same
   client-cert verification path). Skips cleanly if `backend/certs/ca.cnf`
   predates the current `gen-certs.sh`.

Exit code is nonzero if any check fails — wired into CI at
`.github/workflows/mtls-verify.yml` (one job: build the compose stack,
wait healthy, run the script, tear down).

Automated coverage: `backend/tests/test_mtls.py` (middleware attack
scenarios + fail-closed settings, via `TestClient` — no real TLS) plus
`scripts/verify-mtls.sh` (real handshake, see above).

## Design decisions

- **`ssl_verify_client optional` (not `on`) — a deliberate tradeoff for
  browser clients.** CORS preflight (`OPTIONS`) requests are credential-less
  by the fetch specification, and browsers may open the preflight connection
  without presenting a client certificate; with `on`, every browser request
  would die at the handshake before CORS could even be negotiated. `optional`
  keeps certificate verification (a cert that fails validation is still
  rejected — see below) while letting certless connections reach the
  backend, where `MTLSMiddleware` rejects every non-exempt path with 403 —
  so mutual authentication remains mandatory for all API access, enforced
  one layer up.
  Cost of the tradeoff: unauthenticated peers can now speak HTTP to the
  middleware (larger pre-auth surface than handshake rejection); accepted in
  exchange for a usable browser flow. Non-browser deployments that need
  handshake-level rejection can flip the single directive back to `on`.
  The container health check probes uvicorn directly on the Docker-internal
  network; the middleware's `/health` exemption exists only for that probe.
  **Verified behavior for a presented-but-invalid cert (wrong CA, or
  revoked):** contrary to what this doc used to claim, nginx does NOT abort
  the TLS handshake — under `optional` it completes the handshake regardless
  of verification outcome, then rejects the *HTTP request* with its own
  built-in `400 "The SSL certificate error"` page before proxying anywhere,
  same result (the request never reaches the backend) via a different
  mechanism than a handshake-level TLS alert. Confirmed with
  `scripts/verify-mtls.sh` against a live proxy. Only a genuine
  protocol-level mismatch (TLS version floor, cipher suite) produces an
  actual handshake alert (see checks 3 and 6 below).
- **Cipher policy per SP 800-52r2 / FIPS-approved only.** TLS 1.2 limited to
  ECDHE + AES-GCM suites (forward secrecy, AEAD only). TLS 1.3 explicitly
  restricted to `TLS_AES_256_GCM_SHA384:TLS_AES_128_GCM_SHA256` — OpenSSL's
  default additionally enables ChaCha20-Poly1305, which is AEAD but not a
  FIPS-approved algorithm (the NIST ACVP credentials specification requires
  "FIPS-approved and validated algorithm primitives").
- **Claim level: approved algorithms, not a validated module.** The cipher
  policy guarantees only FIPS-*approved* algorithms are negotiated; the
  crypto underneath is the distribution's stock OpenSSL, which is not a
  CMVP-validated build. See "FIPS 140-3 claim level and upgrade path" below.

## FIPS 140-3 claim level and upgrade path

Two different FIPS standards appear in this project — do not conflate them:

- **FIPS 203 / 204** (ML-KEM / ML-DSA): what the platform *tests DUTs
  against*. Owned by the crypto-team engines behind `crypto_boundary/`.
- **FIPS 140-3**: the quality standard for a *cryptographic module itself* —
  this section is about the module underneath our own TLS stack.

FIPS 140-3 distinguishes two levels of claim:

| Claim | Meaning | Our status |
|---|---|---|
| FIPS-**approved** algorithms | only NIST-approved algorithms are negotiated (AES-GCM yes, ChaCha20 no) | ✅ enforced by the nginx cipher policy above |
| FIPS-**validated** module | the specific code executing them is a CMVP-certified build, on a tested operational environment | ❌ stock Alpine OpenSSL — deliberate, see below |

**Upgrading to "validated" swaps what is under nginx, never nginx itself**
(nginx does no crypto; it calls the linked OpenSSL). Two routes:

| Route | How | Cost | Caveat |
|---|---|---|---|
| A. Vendor FIPS OS base | rebuild proxy/backend images on RHEL UBI or Ubuntu Pro FIPS; run the *host* OS in FIPS mode | vendor subscription — free tiers exist (Ubuntu Pro: personal ≤5 machines; Red Hat developer: ≤16 systems) | full vendor claim requires the container *host* to be the same OS in FIPS mode (containers share the host kernel) |
| B. Self-built OpenSSL FIPS provider | compile the CMVP-listed OpenSSL FIPS provider version, `fipsinstall`, point openssl.cnf at it | free (open source) | version must stay pinned to the certificate's; running on an untested OE is a user affirmation |

**Nothing is paid to or licensed from NIST in either route.** CMVP
certificates are held by the module vendors (who paid an accredited lab for
testing) and are public; *using* a validated module requires no application.
The only money in route A is the OS vendor's subscription. Look up
certificates and their tested environments at:
https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules

Verification once FIPS mode is enabled (either route):

```bash
openssl list -providers            # must show the fips provider as active
cat /proc/sys/crypto/fips_enabled  # 1 when the host kernel is in FIPS mode
```

**Decision for this phase: stay at the approved-algorithms level** and state
it plainly (this section is that statement). The platform's current
deliverable is a spec-faithful protocol layer; a validated-module claim only
becomes necessary if the platform operates as a formal validation authority.
The upgrade is deferred cheaply: both routes leave every nginx directive in
this repo untouched.
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

- No CRL distribution beyond the file nginx reads locally (no CRL Distribution
  Point / OCSP) — fine for a single dev-CA deployment, would need one before
  clients other than this proxy need to check revocation status independently.
- Real-deployment CA hygiene (offline root, intermediate issuing CA, HSM-backed
  key storage) is out of scope for the dev PKI `gen-certs.sh` produces —
  swap it for organization-issued certificates before anything but local dev.
