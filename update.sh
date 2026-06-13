#!/usr/bin/env bash
# NukiBlinker — one-command update for the Mini PC (production).
#
# Pulls the latest code + image and restarts the container. Run this from the
# project directory on the Mini PC (where docker-compose.yml and config.yaml live):
#
#   ./update.sh
#
# Assumes the GHCR image flow (docker-compose.yml uses `image:`). If you build
# locally instead, set BUILD=1:  BUILD=1 ./update.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

BUILD="${BUILD:-0}"

echo "=== Updating NukiBlinker ==="
echo "  Dir: $REPO_ROOT"

# 1. Latest code
echo ""
echo "[1/4] Pulling latest code..."
git pull --ff-only

# 2. Make sure the event-log volume directory exists (logs/event_log.db lives here)
mkdir -p logs

# 3. Refresh the image
echo ""
if [ "$BUILD" = "1" ]; then
  echo "[2/4] Building image locally..."
  docker compose build
else
  echo "[2/4] Pulling latest image from registry..."
  docker compose pull
fi

# 4. Restart
echo ""
echo "[3/4] Restarting container..."
docker compose up -d

# 5. Prune dangling images to reclaim disk
echo ""
echo "[4/4] Pruning dangling images..."
docker image prune -f >/dev/null || true

echo ""
echo "=== Updated and restarted ==="
echo "  Health: curl -s localhost:8080/health"
echo "  Logs:   docker compose logs -f --tail 50"
echo ""
