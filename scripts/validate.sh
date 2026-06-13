#!/usr/bin/env bash
# NukiBlinker — pick a branch and validate it (lint + tests) on the Mac.
#
# Backs `make validate`. After the PR is merged on GitHub, run `make cleanup`
# to return to main and prune merged branches.
#
# Usage:
#   make validate                    # interactive branch picker
#   ./scripts/validate.sh feat/x     # validate a specific branch directly

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Validate branch (Mac) ==="

echo ""
echo "[1/4] Fetching from origin (with prune)..."
git fetch --all --prune --quiet

# --- Select branch ---------------------------------------------------------
BRANCH="${1:-}"

if [ -z "$BRANCH" ]; then
  # Portable array fill (macOS ships bash 3.2, which has no `mapfile`).
  BRANCHES=()
  while IFS= read -r line; do
    [ -n "$line" ] && BRANCHES+=("$line")
  done < <(
    git for-each-ref --format='%(refname:short)' refs/remotes/origin \
      | sed 's#^origin/##' \
      | grep -vE '^(HEAD|main)$' \
      | sort -u
  )

  if [ "${#BRANCHES[@]}" -eq 0 ]; then
    echo "  No feature branches on origin to validate. Exiting."
    exit 0
  fi

  echo ""
  echo "[2/4] Select a branch to validate:"
  PS3="Branch # (or Ctrl+C to abort): "
  select choice in "${BRANCHES[@]}"; do
    if [ -n "${choice:-}" ]; then
      BRANCH="$choice"
      break
    fi
    echo "  Invalid selection, try again."
  done
else
  echo ""
  echo "[2/4] Validating requested branch: $BRANCH"
fi

echo "  -> Selected: $BRANCH"

# --- Checkout + install + validate ----------------------------------------
echo ""
echo "[3/4] Checking out $BRANCH and installing deps..."
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
make install

echo ""
echo "[4/4] Running lint + tests (make run-tests)..."
if ! make run-tests; then
  echo ""
  echo "❌ Validation failed on $BRANCH. Fix it before merging."
  exit 1
fi

echo ""
echo "✅ $BRANCH validated (lint + tests passed)."
echo "   When the PR is merged on GitHub, run 'make cleanup'."
