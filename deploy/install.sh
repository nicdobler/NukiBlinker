#!/usr/bin/env bash
# NukiBlinker — Mini PC install script
# Usage: curl -sSL <raw-url>/deploy/install.sh | bash
#   or:  bash deploy/install.sh

set -euo pipefail

INSTALL_DIR="$HOME/nukiblinker"
REPO="https://github.com/nicdobler/NukiBlinker.git"

echo "=== NukiBlinker installer ==="

# 1. Prerequisites
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo ">> Docker installed. You may need to log out and back in for group changes."
fi

if ! command -v docker compose &>/dev/null; then
    echo "ERROR: docker compose not available. Install Docker Compose v2."
    exit 1
fi

# 2. Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --ff-only
else
    echo "Cloning repository..."
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Config file
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"
    echo ""
    echo ">> config.yaml created from example. Edit it before starting:"
    echo "   nano $INSTALL_DIR/config.yaml"
    echo ""
    echo "   At minimum, set:"
    echo "     nuki.bridge_ip, nuki.api_token"
    echo "     hue.bridge_ip, hue.api_key, hue.lights"
    echo ""
fi

# 4. Create homekit persist dir
mkdir -p "$INSTALL_DIR/homekit"

# 5. Pull and start
echo "Pulling latest image..."
cd "$INSTALL_DIR"
docker compose pull
docker compose up -d

echo ""
echo "=== NukiBlinker is running ==="
echo "  Web UI:  http://localhost:8080/"
echo "  Logs:    docker compose logs -f"
echo "  Stop:    docker compose down"
echo "  Config:  $INSTALL_DIR/config.yaml"
echo ""
