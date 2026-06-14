#!/usr/bin/env bash
# NukiBlinker — one-command update for the Mini PC (production).
#
# Pulls the latest code + image and restarts the container. Run this from the
# project directory on the Mini PC (where docker-compose.yml, config.yaml and
# secrets.yaml live):
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

# 2. Make sure bind-mounted paths exist on the host BEFORE `docker compose up`,
#    otherwise Docker creates a *directory* in their place.
#    - logs/ : event-log volume (logs/event_log.db lives here)
#    - secrets.yaml : secrets file split out of config.yaml (#123)
mkdir -p logs

# Repair a Docker bind-mount artifact (#129): if a previous `up` ran before
# secrets.yaml existed as a file, Docker created an empty *directory* in its
# place, which crash-loops the container (IsADirectoryError). Stop the stack
# and replace the directory with a file so the mount is recreated correctly.
if [ -d secrets.yaml ]; then
  echo "  secrets.yaml is a directory (Docker bind-mount artifact, #129) — repairing."
  docker compose down 2>/dev/null || true
  rmdir secrets.yaml 2>/dev/null || rm -rf secrets.yaml
fi
if [ -d config.yaml ]; then
  echo "  config.yaml is a directory (Docker bind-mount artifact, #129) — repairing."
  docker compose down 2>/dev/null || true
  rmdir config.yaml 2>/dev/null || rm -rf config.yaml
fi

if [ ! -f secrets.yaml ]; then
  # Create an EMPTY secrets file (not a copy of secrets.example.yaml). On an
  # existing install the real secrets may still be inline in config.yaml; an
  # empty secrets.yaml lets those load unchanged and migrate to secrets.yaml on
  # the next save. Copying the example would overlay placeholder tokens and
  # clobber the real ones (#123).
  echo "  secrets.yaml not found — creating an empty one (#123)."
  echo "  Existing inline secrets in config.yaml migrate automatically on next save."
  printf '# NukiBlinker secrets (#123). Managed by the web UI; safe to leave empty.\n' > secrets.yaml
fi

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
