#!/usr/bin/env bash
# gen-certs.sh — Generate CA + server + client self-signed certs for mTLS dev/test.
#
# Usage:  bash scripts/gen-certs.sh [outdir] [days]
#   outdir  path to write cert files  (default: backend/certs)
#   days    certificate validity days (default: 825)
#
# Env overrides:
#   CERT_P12_PASSWORD  password for the browser-importable client.p12 (default: acvp-dev)
#
# IMPORTANT: DEVELOPMENT ONLY — use a real CA in production.
set -euo pipefail

# Git-Bash/MSYS on Windows auto-converts leading-slash CLI args like
# "/C=US/O=..." into a filesystem path before openssl ever sees them. Exclude
# just that "/C=" prefix from the conversion (real file-path args elsewhere in
# this script don't start with "/C=", so they still get translated normally).
# No-op on Linux/macOS.
export MSYS2_ARG_CONV_EXCL="${MSYS2_ARG_CONV_EXCL:-}/C="

OUTDIR="${1:-$(dirname "$0")/../backend/certs}"
DAYS="${2:-825}"
COUNTRY="US"
ORG="ACVP-Dev"
P12_PASSWORD="${CERT_P12_PASSWORD:-acvp-dev}"

mkdir -p "$OUTDIR"
OUTDIR="$(realpath "$OUTDIR")"
echo "[gen-certs] Writing to: $OUTDIR"

# openssl.exe on Git-Bash/MSYS is a native Windows build: it translates
# POSIX-style paths given as CLI args (bash's exec layer rewrites those) but
# NOT paths embedded inside a config file's *values*, which it reads as
# literal strings. The ca.cnf "dir" value below must therefore be a
# Windows-style path on that platform; everywhere else keep using $OUTDIR.
CNF_DIR="$OUTDIR"
if command -v cygpath >/dev/null 2>&1; then
    CNF_DIR="$(cygpath -m "$OUTDIR")"
fi

# ── 0. CA database (so we can issue a CRL and later revoke certs) ────────────
# openssl ca needs a small on-disk database to track issued/revoked serials.
# It lives alongside the certs (gitignored, dev-only) and is reused by the
# revoke → re-sign-CRL → nginx reload flow described in mtls-deployment.md.
mkdir -p "$OUTDIR/newcerts"
: > "$OUTDIR/index.txt"
echo "unique_subject = no" > "$OUTDIR/index.txt.attr"
[ -f "$OUTDIR/serial" ]     || echo 1000 > "$OUTDIR/serial"
[ -f "$OUTDIR/crlnumber" ]  || echo 1000 > "$OUTDIR/crlnumber"

CA_CNF="$OUTDIR/ca.cnf"
cat > "$CA_CNF" <<EOF
[ca]
default_ca = CA_default

[CA_default]
dir              = $CNF_DIR
database         = \$dir/index.txt
serial           = \$dir/serial
new_certs_dir    = \$dir/newcerts
certificate      = \$dir/ca.crt
private_key      = \$dir/ca.key
crlnumber        = \$dir/crlnumber
default_md       = sha256
default_days     = $DAYS
default_crl_days = 30
policy           = policy_loose
unique_subject   = no

[policy_loose]
countryName            = optional
stateOrProvinceName    = optional
organizationName       = optional
organizationalUnitName = optional
commonName             = supplied
emailAddress           = optional

[req]
distinguished_name = dn
[dn]
EOF

# ── 1. Root CA ────────────────────────────────────────────────────────────────
echo "[gen-certs] 1/4 Generating Root CA..."
openssl genrsa -out "$OUTDIR/ca.key" 4096
openssl req -new -x509 \
    -key  "$OUTDIR/ca.key" \
    -out  "$OUTDIR/ca.crt" \
    -days "$DAYS" \
    -subj "/C=$COUNTRY/O=$ORG/CN=$ORG Root CA"

# ── 2. Server certificate ─────────────────────────────────────────────────────
echo "[gen-certs] 2/4 Generating server certificate..."
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
openssl ca -config "$CA_CNF" -batch -notext \
    -in         "$OUTDIR/server.csr" \
    -out        "$OUTDIR/server.crt" \
    -days       "$DAYS" \
    -extfile    "$EXT_FILE" \
    -extensions v3_req
rm -f "$EXT_FILE" "$OUTDIR/server.csr"

# ── 3. Client certificate ─────────────────────────────────────────────────────
echo "[gen-certs] 3/4 Generating client certificate..."
openssl genrsa -out "$OUTDIR/client.key" 2048
openssl req -new \
    -key  "$OUTDIR/client.key" \
    -out  "$OUTDIR/client.csr" \
    -subj "/C=$COUNTRY/O=$ORG/CN=acvp-test-client"
openssl ca -config "$CA_CNF" -batch -notext \
    -in   "$OUTDIR/client.csr" \
    -out  "$OUTDIR/client.crt" \
    -days "$DAYS"
rm -f "$OUTDIR/client.csr"

# Browser-importable bundle (Keychain / Firefox / Windows cert store). Some
# browsers/OSes still expect the older RC2/3DES PKCS#12 encryption rather than
# OpenSSL 3's new default (AES) — pass -legacy when the installed openssl
# supports it (3.0+); older openssl (1.1.1, no -legacy flag) already defaults
# to the compatible encryption, so it's safe to skip.
PKCS12_LEGACY_FLAG=()
if openssl pkcs12 -help 2>&1 | grep -q -- '-legacy'; then
    PKCS12_LEGACY_FLAG=(-legacy)
fi
openssl pkcs12 -export "${PKCS12_LEGACY_FLAG[@]}" \
    -in       "$OUTDIR/client.crt" \
    -inkey    "$OUTDIR/client.key" \
    -certfile "$OUTDIR/ca.crt" \
    -name     "acvp-test-client" \
    -out      "$OUTDIR/client.p12" \
    -passout  "pass:$P12_PASSWORD"

# ── 4. Certificate Revocation List ────────────────────────────────────────────
# Starts empty (nothing revoked yet). nginx's ssl_crl directive points at this
# file — see backend/nginx/nginx.conf.template and the "Revoking a client
# certificate" section of docs/mtls-deployment.md for the revoke → re-sign →
# reload flow.
echo "[gen-certs] 4/4 Generating (empty) CRL..."
openssl ca -config "$CA_CNF" -gencrl -out "$OUTDIR/ca.crl"

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
echo "Browser import: backend/certs/client.p12 (password: \$CERT_P12_PASSWORD, default 'acvp-dev')"
echo "  1. Trust the dev CA:      import backend/certs/ca.crt into your OS/browser"
echo "                            trust store as a trusted root (see"
echo "                            docs/mtls-deployment.md § Browser client setup)."
echo "  2. Import the client id:  import backend/certs/client.p12 (same password)."
echo "  3. Visit https://localhost:8443 and pick the imported certificate when prompted."
echo ""
echo "NOTE: Add backend/certs/ to .gitignore — never commit private keys!"
