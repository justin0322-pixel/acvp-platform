#!/usr/bin/env bash
#
# fetch-nist-fixtures.sh
#
# Vendor the NIST ACVP golden test vectors into tests/fixtures/nist/.
# These are the READ-ONLY baseline used for test-driven development of the
# server-client layer and as the acceptance oracle for the FIPS 203/204 crypto
# teams. See the acvp-protocol skill (.claude/skills/acvp-protocol/SKILL.md).
#
# Usage (run from the repository root):
#   scripts/fetch-nist-fixtures.sh [git-ref]
#
# git-ref defaults to "master". Pass a release tag (e.g. v1.1.0.40) to pin a
# specific release for reproducibility.
#
# The script sparse-checks-out ONLY the five ML-KEM / ML-DSA mode folders
# (the ACVP-Server repo is large), copies them in, records the resolved commit
# in tests/fixtures/nist/SOURCE.md, and re-applies read-only permissions.

set -euo pipefail

REPO_URL="https://github.com/usnistgov/ACVP-Server.git"
REF="${1:-master}"
SRC_SUBDIR="gen-val/json-files"
DEST="tests/fixtures/nist"

MODES=(
  "ML-KEM-keyGen-FIPS203"
  "ML-KEM-encapDecap-FIPS203"
  "ML-DSA-keyGen-FIPS204"
  "ML-DSA-sigGen-FIPS204"
  "ML-DSA-sigVer-FIPS204"
)

command -v git >/dev/null || { echo "error: git is required." >&2; exit 1; }
if [[ ! -d ".git" ]]; then
  echo "error: run this from the repository root (no .git directory found here)." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SPARSE_PATHS=()
for m in "${MODES[@]}"; do SPARSE_PATHS+=("$SRC_SUBDIR/$m"); done

echo ">> Cloning $REPO_URL @ $REF (blobless + sparse) ..."
if git clone --depth 1 --filter=blob:none --sparse --branch "$REF" \
     "$REPO_URL" "$TMP/acvp" >/dev/null 2>&1; then
  :
else
  echo "   (ref is not a branch/tag; full blobless clone to resolve commit)"
  git clone --filter=blob:none --sparse "$REPO_URL" "$TMP/acvp" >/dev/null 2>&1
fi

pushd "$TMP/acvp" >/dev/null
git sparse-checkout set "${SPARSE_PATHS[@]}" >/dev/null
git checkout "$REF" >/dev/null 2>&1 || { echo "error: ref '$REF' not found." >&2; exit 1; }
COMMIT="$(git rev-parse HEAD)"
popd >/dev/null

echo ">> Copying ${#MODES[@]} modes into $DEST ..."
mkdir -p "$DEST"
for m in "${MODES[@]}"; do
  SRC="$TMP/acvp/$SRC_SUBDIR/$m"
  if [[ ! -d "$SRC" ]]; then
    echo "error: expected folder missing in NIST repo: $SRC_SUBDIR/$m" >&2
    exit 1
  fi
  [[ -d "$DEST/$m" ]] && chmod -R u+w "$DEST/$m"   # allow overwrite of prior read-only copy
  rm -rf "$DEST/$m"
  cp -R "$SRC" "$DEST/$m"
done

echo ">> Verifying fixtures ..."
MISSING=0
for m in "${MODES[@]}"; do
  for f in registration.json prompt.json internalProjection.json expectedResults.json validation.json; do
    if [[ ! -f "$DEST/$m/$f" ]]; then
      echo "   warning: missing $m/$f"
      MISSING=1
    fi
  done
done

# Record provenance into SOURCE.md (idempotent line replacements; portable sed).
DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -f "$DEST/SOURCE.md" ]]; then
  sed -i.bak \
    -e "s|^- \*\*Source ref\*\*:.*|- **Source ref**: \`$REF\`|" \
    -e "s|^- \*\*Pinned commit\*\*:.*|- **Pinned commit**: \`$COMMIT\`|" \
    -e "s|^- \*\*Fetched (UTC)\*\*:.*|- **Fetched (UTC)**: \`$DATE\`|" \
    "$DEST/SOURCE.md"
  rm -f "$DEST/SOURCE.md.bak"
fi

# Make the mode files read-only (golden baseline). Dirs and SOURCE.md stay writable.
for m in "${MODES[@]}"; do
  find "$DEST/$m" -type f -exec chmod a-w {} +
done

echo ">> Done."
echo "   Pinned commit: $COMMIT"
echo "   Modes:         ${#MODES[@]}"
if [[ "$MISSING" -eq 0 ]]; then
  echo "   Verification:  all core JSON files present"
else
  echo "   Verification:  some files missing (see warnings above)" >&2
fi
echo
echo "Fixtures are now READ-ONLY. Re-run this script anytime to update."
