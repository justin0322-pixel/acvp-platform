#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate CA + server + client self-signed certificates for mTLS dev/test.

.DESCRIPTION
    Produces the following files under backend/certs/:
      ca.key / ca.crt          - Root CA (signs server & client certs)
      server.key / server.crt  - Server cert (CN=localhost, SANs for 127.0.0.1)
      client.key / client.crt  - Client cert for mTLS testing

    IMPORTANT: These are DEVELOPMENT-ONLY self-signed certs.
    Production deployments MUST use certs from a trusted CA (e.g. Let's Encrypt).

.NOTES
    Requires OpenSSL to be installed and on PATH.
    On Windows: 'winget install ShiningLight.OpenSSL' or use Git Bash's bundled openssl.
#>

param(
    [string]$OutDir  = "$PSScriptRoot\..\backend\certs",
    [int]   $Days    = 825,          # max validity Chrome accepts for self-signed
    [string]$Country = "US",
    [string]$Org     = "ACVP-Dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Resolve & create output directory ────────────────────────────────────────
$OutDir = (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Force -Path $OutDir)).Path
Write-Host "[gen-certs] Writing to: $OutDir"

# ── Helper: run openssl and abort on error ────────────────────────────────────
function Invoke-OpenSSL {
    param([string[]]$Args)
    & openssl @Args
    if ($LASTEXITCODE -ne 0) { throw "openssl failed (exit $LASTEXITCODE)" }
}

# ─────────────────────────────────────────────────────────────────────────────
# 1. Root CA
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[gen-certs] 1/3 Generating Root CA..."

Invoke-OpenSSL genrsa -out "$OutDir\ca.key" 4096

Invoke-OpenSSL req -new -x509 `
    -key    "$OutDir\ca.key" `
    -out    "$OutDir\ca.crt" `
    -days   $Days `
    -subj   "/C=$Country/O=$Org/CN=$Org Root CA" `
    -extensions v3_ca

# ─────────────────────────────────────────────────────────────────────────────
# 2. Server certificate (CN=localhost, SAN includes 127.0.0.1)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[gen-certs] 2/3 Generating server certificate..."

$serverExtCfg = @"
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
"@
$serverExtFile = [System.IO.Path]::GetTempFileName()
Set-Content -Path $serverExtFile -Value $serverExtCfg

Invoke-OpenSSL genrsa -out "$OutDir\server.key" 2048

Invoke-OpenSSL req -new `
    -key    "$OutDir\server.key" `
    -out    "$OutDir\server.csr" `
    -subj   "/C=$Country/O=$Org/CN=localhost" `
    -config $serverExtFile

Invoke-OpenSSL x509 -req `
    -in             "$OutDir\server.csr" `
    -CA             "$OutDir\ca.crt" `
    -CAkey          "$OutDir\ca.key" `
    -CAcreateserial `
    -out            "$OutDir\server.crt" `
    -days           $Days `
    -extfile        $serverExtFile `
    -extensions     v3_req

Remove-Item $serverExtFile, "$OutDir\server.csr" -ErrorAction SilentlyContinue

# ─────────────────────────────────────────────────────────────────────────────
# 3. Client certificate (for mTLS testing)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host "[gen-certs] 3/3 Generating client certificate..."

Invoke-OpenSSL genrsa -out "$OutDir\client.key" 2048

Invoke-OpenSSL req -new `
    -key  "$OutDir\client.key" `
    -out  "$OutDir\client.csr" `
    -subj "/C=$Country/O=$Org/CN=acvp-test-client"

Invoke-OpenSSL x509 -req `
    -in             "$OutDir\client.csr" `
    -CA             "$OutDir\ca.crt" `
    -CAkey          "$OutDir\ca.key" `
    -CAcreateserial `
    -out            "$OutDir\client.crt" `
    -days           $Days

Remove-Item "$OutDir\client.csr" -ErrorAction SilentlyContinue

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[gen-certs] Done. Files created:"
Get-ChildItem $OutDir | Format-Table Name, Length, LastWriteTime

Write-Host @"

To test TLS with curl:
  curl --cacert backend/certs/ca.crt https://localhost:8443/health

To test mTLS with curl (client cert required):
  curl --cacert backend/certs/ca.crt \
       --cert   backend/certs/client.crt \
       --key    backend/certs/client.key \
       https://localhost:8443/acvp/v1/login

Add backend/certs/ to .gitignore — never commit private keys!
"@
