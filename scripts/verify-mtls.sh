#!/usr/bin/env bash
# verify-mtls.sh — automated version of the manual curl/openssl checks in
# docs/mtls-deployment.md "Verifying the SHALL requirements". Exercises the
# real TLS/mTLS handshake against a running `docker compose up` stack instead
# of only the middleware layer (backend/tests/test_mtls.py uses TestClient
# with fake headers, so it never touches Nginx's actual handshake behavior).
#
# Usage:
#   docker compose up --build -d
#   bash scripts/verify-mtls.sh
#
# Env overrides:
#   HOST            hostname/IP the proxy is reachable on   (default: localhost)
#   HTTPS_PORT       mTLS port                                (default: 8443)
#   DIRECT_PORT      backend port that must stay unpublished  (default: 8000)
#   CERTDIR          dir with ca.crt/server.crt/client.crt/…  (default: backend/certs)
#   COMPOSE_SERVICE  proxy service name, for the CRL reload test (default: proxy)
#
# Exit code: 0 if every check passes, 1 if any check fails.
set -uo pipefail

# Git-Bash/MSYS on Windows auto-converts leading-slash CLI args like
# "/CN=..." into a filesystem path before openssl ever sees them. Exclude
# just that prefix from conversion. No-op on Linux/macOS.
export MSYS2_ARG_CONV_EXCL="${MSYS2_ARG_CONV_EXCL:-}/CN="

HOST="${HOST:-localhost}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
DIRECT_PORT="${DIRECT_PORT:-8000}"
CERTDIR="${CERTDIR:-$(dirname "$0")/../backend/certs}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-proxy}"
CERTDIR="$(realpath "$CERTDIR")"
BASE="https://$HOST:$HTTPS_PORT"

CA="$CERTDIR/ca.crt"
CLIENT_CRT="$CERTDIR/client.crt"
CLIENT_KEY="$CERTDIR/client.key"

FAILURES=0
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# curl's Windows/Schannel backend checks the CA cert for revocation info by
# default and fails a self-signed dev CA with "CERT_TRUST_REVOCATION_STATUS_
# UNKNOWN" before it ever reaches nginx — unrelated to the client-cert
# revocation (ssl_crl) this script tests. --ssl-no-revoke is Schannel-only
# and errors out on OpenSSL-backed curl, so only add it when Schannel is in use.
# Expansions below use ${CURL_OPTS[@]+...}: macOS's bash 3.2 treats an empty
# array as unset, so a bare "${CURL_OPTS[@]}" dies under `set -u`.
CURL_OPTS=()
if curl --version | head -1 | grep -qi schannel; then
    CURL_OPTS+=(--ssl-no-revoke)
fi

pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAILURES=$((FAILURES + 1)); }
skip() { echo "  [SKIP] $1"; SKIPS=$((SKIPS + 1)); }
SKIPS=0

# A nonzero curl exit isn't proof the *server* rejected the handshake — curl
# can fail before it ever reaches the network (e.g. Schannel on Windows
# refusing to import a plain-PEM client cert it insists on as PKCS#12/store
# reference). Distinguish that from a real rejection by inspecting -v output.
assert_handshake_rejected() {
    local label="$1"; shift
    local out; out="$WORKDIR/handshake-$RANDOM.log"
    if curl -v -s -o /dev/null -m 5 "$@" >"$out" 2>&1; then
        fail "$label: handshake unexpectedly succeeded"
    elif grep -qiE 'Failed to import cert|Failed to get certificate location|schannel:.*no such file' "$out"; then
        skip "$label: curl couldn't present the client cert on this platform (client-side error, not a server-side result — see $out)"
    else
        pass "$label: rejected"
    fi
}

# Verified empirically: with `ssl_verify_client optional` (see Design decisions
# in mtls-deployment.md), nginx completes the TLS handshake even for a client
# cert it can't verify (wrong CA, or on the CRL) — it doesn't send a TLS
# alert. It rejects at the HTTP layer instead, with its own built-in 400 "SSL
# certificate error" page, before the request ever reaches the backend.
assert_cert_rejected_400() {
    local label="$1"; shift
    local body; body="$WORKDIR/http400-$RANDOM.html"
    local verbose; verbose="$WORKDIR/http400-$RANDOM.verbose.log"
    local code
    code=$(curl -v -s -o "$body" -w '%{http_code}' -m 5 "$@" 2>"$verbose")
    if [ "$code" = "000" ] || [ -z "$code" ]; then
        if grep -qiE 'Failed to import cert|Failed to get certificate location|schannel:.*no such file' "$verbose"; then
            skip "$label: curl couldn't present the client cert on this platform (client-side error, not a server-side result — see $verbose)"
        else
            fail "$label: request never completed (HTTP $code) — expected a 400 from nginx, not a total connection failure"
        fi
    elif [ "$code" = "400" ]; then
        pass "$label rejected with HTTP 400 before reaching the backend"
    else
        fail "$label: expected HTTP 400 from nginx, got HTTP $code body=$(cat "$body" 2>/dev/null)"
    fi
}

for f in "$CA" "$CLIENT_CRT" "$CLIENT_KEY"; do
    if [ ! -f "$f" ]; then
        echo "Missing $f — run scripts/gen-certs.sh first." >&2
        exit 1
    fi
done

echo "[verify-mtls] Waiting for $BASE/health ..."
ready=0
for _ in $(seq 1 30); do
    if curl -sk -m 2 -o /dev/null ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} "$BASE/health"; then
        ready=1
        break
    fi
    sleep 2
done
if [ "$ready" -ne 1 ]; then
    echo "Proxy never became reachable at $BASE — is 'docker compose up' running?" >&2
    exit 1
fi

# ── 1. No client certificate → handshake OK, every API path 403s with the ──
#      mTLS error (ssl_verify_client optional; MTLSMiddleware enforces it).
echo "[1] No client certificate -> 403 mTLS error"
body="$WORKDIR/1.json"
code=$(curl -s -o "$body" -w '%{http_code}' ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} --cacert "$CA" "$BASE/acvp/v1/algorithms")
if [ "$code" = "403" ] && grep -q "mTLS" "$body" 2>/dev/null; then
    pass "no-cert request rejected with 403 + mTLS error"
else
    fail "no-cert request: expected 403+mTLS error, got HTTP $code body=$(cat "$body" 2>/dev/null)"
fi

# ── 1b. INVALID client certificate (wrong CA) → MUST be rejected ───────────
echo "[1b] Invalid (wrong-CA) client certificate -> rejected (HTTP 400, before reaching the backend)"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -keyout "$WORKDIR/bad.key" -out "$WORKDIR/bad.crt" \
    -subj "/CN=untrusted-throwaway" >/dev/null 2>&1
assert_cert_rejected_400 "wrong-CA client cert" ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} --cacert "$CA" \
    --cert "$WORKDIR/bad.crt" --key "$WORKDIR/bad.key" \
    "$BASE/acvp/v1/algorithms"

# ── 2. Valid client certificate → reaches the app layer (not the mTLS 403) ─
echo "[2] Valid client certificate -> passes the mTLS layer"
body="$WORKDIR/2.json"
verbose="$WORKDIR/2.verbose.log"
code=$(curl -v -s -o "$body" -w '%{http_code}' ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} --cacert "$CA" \
    --cert "$CLIENT_CRT" --key "$CLIENT_KEY" \
    "$BASE/acvp/v1/algorithms" 2>"$verbose")
if [ "$code" = "000" ] || [ -z "$code" ]; then
    if grep -qiE 'Failed to import cert|Failed to get certificate location|schannel:.*no such file' "$verbose"; then
        skip "valid client cert: curl couldn't present the client cert on this platform (client-side error, not a server-side result — see $verbose)"
    else
        fail "valid client cert: request never completed (no HTTP response at all)"
    fi
elif [ "$code" = "403" ] && grep -q "mTLS" "$body" 2>/dev/null; then
    fail "valid client cert: still rejected by the mTLS layer (HTTP $code)"
else
    pass "valid client cert reaches the application layer (HTTP $code, not an mTLS 403)"
fi

# ── 3. TLS below 1.2 → MUST be refused ──────────────────────────────────────
echo "[3] TLS 1.1 -> refused"
assert_handshake_rejected "TLS 1.1" ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} --tls-max 1.1 --cacert "$CA" \
    --cert "$CLIENT_CRT" --key "$CLIENT_KEY" \
    "$BASE/acvp/v1/algorithms"

# ── 4. Direct backend access → MUST be unreachable from the host ───────────
echo "[4] Direct backend :$DIRECT_PORT -> unreachable"
if curl -s -o /dev/null -m 3 "http://$HOST:$DIRECT_PORT/health"; then
    fail "backend port $DIRECT_PORT is reachable directly from the host"
else
    pass "backend port $DIRECT_PORT not reachable from the host"
fi

# ── 5. Non-FIPS TLS 1.3 suite (ChaCha20-Poly1305) → MUST be refused ────────
echo "[5] TLS 1.3 ChaCha20-Poly1305-only -> refused"
out="$WORKDIR/5.txt"
openssl s_client -connect "$HOST:$HTTPS_PORT" -tls1_3 \
    -ciphersuites TLS_CHACHA20_POLY1305_SHA256 \
    -CAfile "$CA" -cert "$CLIENT_CRT" -key "$CLIENT_KEY" \
    </dev/null >"$out" 2>&1
if grep -qE "Cipher is TLS_CHACHA20_POLY1305_SHA256|New, TLSv1.3, Cipher is TLS_CHACHA" "$out"; then
    fail "server negotiated ChaCha20-Poly1305 (non-FIPS-approved) on TLS 1.3"
else
    pass "ChaCha20-Poly1305-only handshake refused (no shared cipher)"
fi

# ── 6. Revoked client certificate → MUST be refused (ssl_crl) ──────────────
# Bonus coverage for the CRL wired up alongside this script: issue a
# throwaway second client cert off the same dev CA, revoke it, regenerate
# the CRL, reload nginx, and confirm the now-revoked cert is rejected. Skips
# cleanly on cert directories created before ca.cnf existed (older gen-certs.sh).
CA_CNF="$CERTDIR/ca.cnf"
if [ -f "$CA_CNF" ]; then
    echo "[6] Revoked client certificate -> refused"
    openssl genrsa -out "$WORKDIR/revme.key" 2048 >/dev/null 2>&1
    openssl req -new -key "$WORKDIR/revme.key" -out "$WORKDIR/revme.csr" \
        -subj "/CN=acvp-verify-revoke-throwaway" >/dev/null 2>&1
    if openssl ca -config "$CA_CNF" -batch -notext \
        -in "$WORKDIR/revme.csr" -out "$WORKDIR/revme.crt" -days 1 >/dev/null 2>&1 \
        && openssl ca -config "$CA_CNF" -revoke "$WORKDIR/revme.crt" >/dev/null 2>&1 \
        && openssl ca -config "$CA_CNF" -gencrl -out "$CERTDIR/ca.crl" >/dev/null 2>&1
    then
        if command -v docker >/dev/null 2>&1 && docker compose exec -T "$COMPOSE_SERVICE" nginx -s reload >/dev/null 2>&1; then
            sleep 1
            assert_cert_rejected_400 "revoked client certificate" ${CURL_OPTS[@]+"${CURL_OPTS[@]}"} --cacert "$CA" \
                --cert "$WORKDIR/revme.crt" --key "$WORKDIR/revme.key" \
                "$BASE/acvp/v1/algorithms"
        else
            skip "could not reload the '$COMPOSE_SERVICE' service via docker compose"
        fi
    else
        skip "could not issue/revoke a throwaway cert against $CA_CNF"
    fi
else
    echo "[6] Revoked client certificate"
    skip "no $CA_CNF; regenerate certs with the current gen-certs.sh"
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
    if [ "$SKIPS" -gt 0 ]; then
        echo "[verify-mtls] All checks passed ($SKIPS skipped — see above)."
    else
        echo "[verify-mtls] All checks passed."
    fi
    exit 0
else
    echo "[verify-mtls] $FAILURES check(s) failed, $SKIPS skipped."
    exit 1
fi
