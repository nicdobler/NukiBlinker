#!/bin/bash
# Delete local branches whose remote tracking branch is gone.
# Usage: ./scripts/cleanup-branches.sh [--dry-run]

set -e

DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
fi

echo ""
echo "[*] Fetching and pruning remotes..."
git fetch --prune

GONE_BRANCHES=$(git branch -vv | grep ': gone]' | awk '{print $1}' | sed 's/^\*//')

if [ -z "$GONE_BRANCHES" ]; then
    echo "[OK] No hay ramas locales con remote eliminado."
    exit 0
fi

COUNT=$(echo "$GONE_BRANCHES" | wc -l | tr -d ' ')
echo ""
echo "[i] Ramas locales sin remote ($COUNT):"
echo "$GONE_BRANCHES" | while read -r branch; do
    echo "   - $branch"
done

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "[!] Dry run - no se borro nada."
    exit 0
fi

echo ""

echo "$GONE_BRANCHES" | while read -r branch; do
    printf "[x] Eliminando %s... " "$branch"

    if git branch -D "$branch" 2>/dev/null; then
        echo "OK"
    else
        echo "ERROR"
    fi
done

echo ""
echo "[OK] Limpieza completada."
