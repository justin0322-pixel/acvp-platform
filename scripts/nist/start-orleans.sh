#!/usr/bin/env bash
# Start the NIST Orleans silo. The GenValApp runner connects to it for every
# generate/validate, so this must be running before USE_NIST_GENVAL work. Leave it
# up in its own shell.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER_DLL="${REPO_ROOT}/backend/nist-bin/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet not found. Install the .NET 8 runtime/SDK." >&2
  exit 1
fi
if [[ ! -f "${SERVER_DLL}" ]]; then
  echo "Orleans host not built at ${SERVER_DLL}." >&2
  echo "Run scripts/nist/build-genval.sh first." >&2
  exit 1
fi

# macOS: sharedappsettings.json can carry the UF_HIDDEN flag, which .NET's
# PhysicalFileProvider refuses to read. Clear it before starting.
command -v chflags >/dev/null 2>&1 && chflags -R nohidden "$(dirname "${SERVER_DLL}")" 2>/dev/null || true

exec dotnet "${SERVER_DLL}" --console
