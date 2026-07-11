#!/usr/bin/env bash
# Invoke the GenValApp runner directly — for smoke-testing the engine before wiring
# the server. Requires Orleans running (scripts/nist/start-orleans.sh).
#
#   scripts/nist/run-genval.sh check    registration.json
#   scripts/nist/run-genval.sh generate registration.json
#   scripts/nist/run-genval.sh validate internalProjection.json response.json
#
# generate writes prompt.json + internalProjection.json + expectedResults.json into
# the current directory; validate writes validation.json. Run it from a scratch dir.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNNER_DLL="${GENVAL_RUNNER_DLL:-${REPO_ROOT}/backend/nist-bin/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll}"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet not found. Install the .NET 8 runtime/SDK." >&2
  exit 1
fi
if [[ ! -f "${RUNNER_DLL}" ]]; then
  echo "GenValApp runner not built: ${RUNNER_DLL}" >&2
  echo "Run scripts/nist/build-genval.sh first (or set GENVAL_RUNNER_DLL)." >&2
  exit 1
fi

# macOS: clear the UF_HIDDEN flag on the config files (see start-orleans.sh).
command -v chflags >/dev/null 2>&1 && chflags -R nohidden "$(dirname "${RUNNER_DLL}")" 2>/dev/null || true

case "${1:-}" in
  check)
    [[ $# -eq 2 ]] || { echo "usage: $0 check registration.json" >&2; exit 2; }
    exec dotnet "${RUNNER_DLL}" -c "$2" ;;
  generate)
    [[ $# -eq 2 ]] || { echo "usage: $0 generate registration.json" >&2; exit 2; }
    exec dotnet "${RUNNER_DLL}" -g "$2" ;;
  validate)
    [[ $# -eq 3 ]] || { echo "usage: $0 validate internalProjection.json response.json" >&2; exit 2; }
    exec dotnet "${RUNNER_DLL}" -n "$2" -b "$3" ;;
  *)
    echo "usage: $0 {check|generate|validate} ..." >&2
    exit 2 ;;
esac
