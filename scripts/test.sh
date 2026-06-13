#!/usr/bin/env bash
# NukiBlinker — interactive branch validation for the Mac.
#
# Workflow:
#   1. git fetch (prune)
#   2. pick a branch to test from a menu
#   3. checkout it, install deps, run lint + tests
#   4. if green, wait until the branch's PR is merged into main
#   5. on merge, switch to main, pull, and clean up the merged branch
#
# Usage:
#   ./scripts/test.sh                 # pick a branch interactively
#   ./scripts/test.sh feat/my-branch  # validate a specific branch directly

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

POLL_SECONDS=20

echo "=== NukiBlinker branch validation (Mac) ==="
echo "  Repo: $REPO_ROOT"

# ---------------------------------------------------------------------------
# 1. Fetch
# ---------------------------------------------------------------------------
echo ""
echo "[1/5] Fetching from origin (with prune)..."
git fetch --all --prune --quiet

# ---------------------------------------------------------------------------
# 2. Select branch
# ---------------------------------------------------------------------------
BRANCH="${1:-}"

if [ -z "$BRANCH" ]; then
  mapfile -t BRANCHES < <(
    git for-each-ref --format='%(refname:short)' refs/remotes/origin \
      | sed 's#^origin/##' \
      | grep -vE '^(HEAD|main)$' \
      | sort -u
  )

  if [ "${#BRANCHES[@]}" -eq 0 ]; then
    echo "  No feature branches on origin to test. Exiting."
    exit 0
  fi

  echo ""
  echo "[2/5] Select a branch to validate:"
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
  echo "[2/5] Validating requested branch: $BRANCH"
fi

echo "  -> Selected: $BRANCH"

# ---------------------------------------------------------------------------
# 3. Checkout + install + lint + tests
# ---------------------------------------------------------------------------
echo ""
echo "[3/5] Checking out $BRANCH..."
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo ""
echo "  Installing dependencies (make install)..."
make install

echo ""
echo "  Running lint (make lint)..."
if ! make lint; then
  echo ""
  echo "❌ Lint failed on $BRANCH. Fix it before merging."
  exit 1
fi

echo ""
echo "  Running tests (make test)..."
if ! make test; then
  echo ""
  echo "❌ Tests failed on $BRANCH. Fix them before merging."
  exit 1
fi

echo ""
echo "✅ Lint + tests passed on $BRANCH."

# ---------------------------------------------------------------------------
# 4. Wait for the PR to be merged into main
# ---------------------------------------------------------------------------
echo ""
echo "[4/5] Waiting for $BRANCH to be merged into main..."
echo "  (Checking every ${POLL_SECONDS}s — press Ctrl+C to stop and merge later.)"

is_merged() {
  # Prefer the GitHub PR state when gh is available; fall back to git ancestry.
  if command -v gh >/dev/null 2>&1; then
    local state
    state="$(gh pr view "$BRANCH" --json state --jq .state 2>/dev/null || echo "")"
    case "$state" in
      MERGED) return 0 ;;
      CLOSED)
        echo ""
        echo "⚠️  PR for $BRANCH is CLOSED without merge. Skipping cleanup."
        exit 2
        ;;
    esac
  fi
  # Fallback / extra check: branch tip is an ancestor of origin/main (merge/ff).
  git fetch --quiet origin main "$BRANCH" 2>/dev/null || git fetch --quiet origin main 2>/dev/null || true
  local tip
  tip="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")"
  [ -n "$tip" ] && git merge-base --is-ancestor "$tip" origin/main 2>/dev/null
}

until is_merged; do
  sleep "$POLL_SECONDS"
done

echo ""
echo "✅ $BRANCH is merged into main."

# ---------------------------------------------------------------------------
# 5. Clean up
# ---------------------------------------------------------------------------
echo ""
echo "[5/5] Cleaning up..."
git checkout main
git pull --ff-only
git fetch --prune

# Delete the local branch (force: a squash-merge leaves it "unmerged" to git).
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git branch -D "$BRANCH" && echo "  Deleted local branch $BRANCH"
fi

# Delete the remote branch if GitHub didn't auto-delete it on merge.
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git push origin --delete "$BRANCH" && echo "  Deleted remote branch $BRANCH" || true
fi

echo ""
echo "=== Done. Now on main, up to date, $BRANCH cleaned up. ==="
echo ""
