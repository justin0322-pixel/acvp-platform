#!/usr/bin/env bash
# Build the NIST GenVal engine (GenValApp runner + Orleans host) from OUR OWN fork
# of the engine, so this server can drive the real crypto instead of the fixtures.
#
# Engine source of record is our fork justin0322-pixel/ACVP-Server — a fork of the
# 203 team's hhhylaiii/ACVP-Server, itself a fork of usnistgov/ACVP-Server. We own
# it, so the pinned commit can't move or vanish under us (the "203 way": own your fork).
#
# Prereqs: .NET 8 SDK. The engine source is fetched automatically from our fork.
#
# Usage:
#   scripts/nist/build-genval.sh                        # auto-clones our fork at the pin
#   scripts/nist/build-genval.sh /path/to/ACVP-Server   # or build from an existing checkout
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

# The engine is pinned, exactly like the golden vectors are (tests/fixtures/nist/SOURCE.md).
# An unpinned engine is a silent correctness risk: it grades our vector sets, so a change in
# it changes verdicts with nothing in this repo recording that it moved. Bump deliberately.
ENGINE_REPO="https://github.com/justin0322-pixel/ACVP-Server.git"   # our own fork of the 203 engine
ENGINE_PINNED_COMMIT="61b549e51ca18c75c303cf83f6fb58f40c1de700"   # 2026-07-09 (203 PR #11)

# Where a local checkout of our engine fork lives when no path is supplied.
# Git-ignored (see backend/.gitignore) — the authoritative copy is our GitHub fork.
DEFAULT_SRC="${REPO_ROOT}/backend/nist-src/ACVP-Server"

NIST_SRC="${1:-${NIST_SRC:-}}"
if [[ -z "${NIST_SRC}" ]]; then
  # No path given: clone (or reuse) our own fork and pin it. One-command default,
  # mirroring the 203 team owning their fork.
  NIST_SRC="${DEFAULT_SRC}"
  if [[ ! -d "${NIST_SRC}/.git" ]]; then
    echo "Cloning engine fork ${ENGINE_REPO}"
    echo "  -> ${NIST_SRC}"
    git clone "${ENGINE_REPO}" "${NIST_SRC}"
  else
    git -C "${NIST_SRC}" fetch --quiet origin || true
  fi
  echo "Checking out pinned engine commit ${ENGINE_PINNED_COMMIT} ..."
  git -C "${NIST_SRC}" checkout --quiet "${ENGINE_PINNED_COMMIT}"
fi
NIST_SRC="$(cd "${NIST_SRC}" && pwd)"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet SDK not found on PATH. Install the .NET 8 SDK before building." >&2
  echo "It is often installed outside a non-login shell's PATH, e.g.:" >&2
  echo "  export PATH=\"/usr/local/share/dotnet:\$PATH\"" >&2
  exit 1
fi

# Verify the checkout is at the pinned commit.
SRC_COMMIT="$(git -C "${NIST_SRC}" rev-parse HEAD 2>/dev/null || echo "unknown")"
if [[ "${SRC_COMMIT}" != "${ENGINE_PINNED_COMMIT}" ]]; then
  echo "warning: ${NIST_SRC} is at ${SRC_COMMIT}," >&2
  echo "         but the pinned engine commit is ${ENGINE_PINNED_COMMIT}." >&2
  if [[ "${ALLOW_UNPINNED_ENGINE:-}" != "1" ]]; then
    echo "" >&2
    echo "Refusing to build an unpinned engine — it grades our vector sets, so a silent" >&2
    echo "version drift silently changes verdicts. Either:" >&2
    echo "  git -C ${NIST_SRC} checkout ${ENGINE_PINNED_COMMIT}" >&2
    echo "or, if the bump is deliberate, update ENGINE_PINNED_COMMIT in this script." >&2
    echo "To build anyway (one-off, not for a verdict you trust): ALLOW_UNPINNED_ENGINE=1" >&2
    exit 1
  fi
  echo "         ALLOW_UNPINNED_ENGINE=1 — building anyway." >&2
fi

# `|| true`: with `set -o pipefail`, find failing on a missing gen-val/ would kill the
# script here and the explanatory error below would never be reached.
runner_csproj="$(find "${NIST_SRC}/gen-val" -iname 'NIST.CVP.ACVTS.Generation.GenValApp.csproj' 2>/dev/null | head -n1 || true)"
orleans_csproj="$(find "${NIST_SRC}/gen-val" -iname 'NIST.CVP.ACVTS.Orleans.ServerHost.csproj' 2>/dev/null | head -n1 || true)"

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

# Record what actually got built. backend/nist-bin/ is gitignored, so without this
# there is no way to tell which engine the binaries on this machine came from.
cat > "${BIN_ROOT}/ENGINE_SOURCE.txt" <<EOF
NIST GenVal engine — build provenance

repository:     ${ENGINE_REPO}
pinned commit:  ${ENGINE_PINNED_COMMIT}
built from:     ${SRC_COMMIT}
source path:    ${NIST_SRC}
built at:       $(date -u +"%Y-%m-%dT%H:%M:%SZ")
dotnet:         $(dotnet --version 2>/dev/null || echo unknown)

Rebuild with scripts/nist/build-genval.sh. If "built from" differs from the pinned
commit, these binaries are NOT the engine this repo is pinned to.
EOF

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
