#!/usr/bin/env bash
# Build the NIST GenVal engine (GenValApp runner + Orleans host) from the FIPS 203
# fork source, so this server can drive the real crypto instead of the fixtures.
#
# Prereqs: .NET 8 SDK, and a checkout of the 203 fork:
#   git clone https://github.com/hhhylaiii/ACVP-Server.git
#
# Usage:
#   scripts/nist/build-genval.sh /path/to/ACVP-Server        # or set NIST_SRC=...
#
# Output goes to backend/nist-bin/ (gitignored). Afterwards:
#   scripts/nist/start-orleans.sh        # leave running in its own shell
#   set USE_NIST_GENVAL=true + GENVAL_RUNNER_DLL in backend/.env, restart the API.
#
# The 203 fork keeps Directory.Build.props / Directory.Packages.props at its root,
# so `dotnet publish` on each csproj picks them up automatically (no config copy).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# NOTE: must NOT be a dot-prefixed dir — .NET's PhysicalFileProvider excludes
# dot-prefixed paths, so the engine can't read sharedappsettings.json from one.
BIN_ROOT="${REPO_ROOT}/backend/nist-bin"

NIST_SRC="${1:-${NIST_SRC:-}}"
if [[ -z "${NIST_SRC}" ]]; then
  echo "Usage: $0 <path-to-ACVP-Server checkout>   (or set NIST_SRC)" >&2
  echo "Clone it first: git clone https://github.com/hhhylaiii/ACVP-Server.git" >&2
  exit 2
fi
NIST_SRC="$(cd "${NIST_SRC}" && pwd)"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet SDK not found. Install the .NET 8 SDK before building." >&2
  exit 1
fi

runner_csproj="$(find "${NIST_SRC}/gen-val" -iname 'NIST.CVP.ACVTS.Generation.GenValApp.csproj' 2>/dev/null | head -n1)"
orleans_csproj="$(find "${NIST_SRC}/gen-val" -iname 'NIST.CVP.ACVTS.Orleans.ServerHost.csproj' 2>/dev/null | head -n1)"

if [[ -z "${runner_csproj}" || ! -f "${runner_csproj}" ]]; then
  echo "GenValApp csproj not found under ${NIST_SRC}/gen-val — is NIST_SRC the 203 fork?" >&2
  exit 1
fi
if [[ -z "${orleans_csproj}" || ! -f "${orleans_csproj}" ]]; then
  echo "Orleans.ServerHost csproj not found under ${NIST_SRC}/gen-val" >&2
  exit 1
fi

mkdir -p "${BIN_ROOT}/genval-runner" "${BIN_ROOT}/orleans-server"

echo "Publishing GenValApp runner..."
dotnet publish "${runner_csproj}"  -c Release -o "${BIN_ROOT}/genval-runner"
echo "Publishing Orleans.ServerHost..."
dotnet publish "${orleans_csproj}" -c Release -o "${BIN_ROOT}/orleans-server"

# macOS: publish can leave the UF_HIDDEN flag on config files, which .NET's
# PhysicalFileProvider refuses to read. Clear it on the whole output tree.
command -v chflags >/dev/null 2>&1 && chflags -R nohidden "${BIN_ROOT}" 2>/dev/null || true

RUNNER_DLL="${BIN_ROOT}/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll"
echo ""
echo "Built:"
echo "  runner : ${RUNNER_DLL}"
echo "  orleans: ${BIN_ROOT}/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll"
echo ""
echo "Next:"
echo "  1) scripts/nist/start-orleans.sh          # keep running in its own shell"
echo "  2) in backend/.env:"
echo "       USE_NIST_GENVAL=true"
echo "       GENVAL_RUNNER_DLL=${RUNNER_DLL}"
echo "  3) restart the API, or run the acceptance test:"
echo "       ACVP_REAL_ENGINE=1 GENVAL_RUNNER_DLL=${RUNNER_DLL} pytest backend/tests/test_nist_real_engine.py"
