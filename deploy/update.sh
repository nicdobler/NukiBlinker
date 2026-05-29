#!/usr/bin/env bash
# NukiBlinker — Update to latest version
# Usage: bash ~/nukiblinker/deploy/update.sh

set -euo pipefail

INSTALL_DIR="$HOME/nukiblinker"
cd "$INSTALL_DIR"

echo "=== Updating NukiBlinker ==="

git pull --ff-only
docker compose pull
docker compose up -d

echo ""
echo "=== Updated and restarted ==="
echo "  Logs: docker compose logs -f"
echo ""
