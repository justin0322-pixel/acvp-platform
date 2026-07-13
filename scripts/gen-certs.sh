#!/usr/bin/env bash
# gen-certs.sh — Generate CA + server + client self-signed certs for mTLS dev/test.
#
# Usage:  bash scripts/gen-certs.sh [outdir] [days]
#   outdir  path to write cert files  (default: backend/certs)
#   days    certificate validity days (default: 825)
#
# IMPORTANT: DEVELOPMENT ONLY — use a real CA in production.
set -euo pipefail

OUTDIR="${1:-$(dirname "$0")/../backend/certs}"
DAYS="${2:-825}"
COUNTRY="US"
ORG="ACVP-Dev"

mkdir -p "$OUTDIR"
echo "[gen-certs] Writing to: $(realpath "$OUTDIR")"

# ── 1. Root CA ────────────────────────────────────────────────────────────────
echo "[gen-certs] 1/3 Generating Root CA..."
openssl genrsa -out "$OUTDIR/ca.key" 4096
openssl req -new -x509 \
    -key  "$OUTDIR/ca.key" \
    -out  "$OUTDIR/ca.crt" \
    -days "$DAYS" \
    -subj "/C=$COUNTRY/O=$ORG/CN=$ORG Root CA"

# ── 2. Server certificate ─────────────────────────────────────────────────────
echo "[gen-certs] 2/3 Generating server certificate..."
EXT_FILE=$(mktemp)
cat > "$EXT_FILE" <<EOF
[req]
req_extensions = v3_req
distinguished_name = dn
[dn]
[v3_req]
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = acvp-server
IP.1  = 127.0.0.1
EOF

openssl genrsa -out "$OUTDIR/server.key" 2048
openssl req -new \
    -key    "$OUTDIR/server.key" \
    -out    "$OUTDIR/server.csr" \
    -subj   "/C=$COUNTRY/O=$ORG/CN=localhost" \
    -config "$EXT_FILE"
openssl x509 -req \
    -in             "$OUTDIR/server.csr" \
    -CA             "$OUTDIR/ca.crt" \
    -CAkey          "$OUTDIR/ca.key" \
    -CAcreateserial \
    -out            "$OUTDIR/server.crt" \
    -days           "$DAYS" \
    -extfile        "$EXT_FILE" \
    -extensions     v3_req
rm -f "$EXT_FILE" "$OUTDIR/server.csr"

# ── 3. Client certificate ─────────────────────────────────────────────────────
echo "[gen-certs] 3/3 Generating client certificate..."
openssl genrsa -out "$OUTDIR/client.key" 2048
openssl req -new \
    -key  "$OUTDIR/client.key" \
    -out  "$OUTDIR/client.csr" \
    -subj "/C=$COUNTRY/O=$ORG/CN=acvp-test-client"
openssl x509 -req \
    -in             "$OUTDIR/client.csr" \
    -CA             "$OUTDIR/ca.crt" \
    -CAkey          "$OUTDIR/ca.key" \
    -CAcreateserial \
    -out            "$OUTDIR/client.crt" \
    -days           "$DAYS"
rm -f "$OUTDIR/client.csr"

echo ""
echo "[gen-certs] Done:"
ls -lh "$OUTDIR"
echo ""
echo "Test TLS:  curl --cacert backend/certs/ca.crt https://localhost:8443/health"
echo "Test mTLS: curl --cacert backend/certs/ca.crt \\"
echo "                --cert   backend/certs/client.crt \\"
echo "                --key    backend/certs/client.key \\"
echo "                https://localhost:8443/acvp/v1/login"
echo ""
echo "NOTE: Add backend/certs/ to .gitignore — never commit private keys!"
