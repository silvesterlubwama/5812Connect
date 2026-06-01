#!/usr/bin/env bash
# 58:12 Connect — one-line appliance installer.
#
# Usage on a fresh Ubuntu 22.04+ / Debian 12 / Raspberry Pi OS box:
#
#   curl -fsSL https://raw.githubusercontent.com/5812-global/connect/main/appliance/install.sh | sudo bash
#
# Or after cloning:
#
#   cd appliance && sudo bash install.sh
#
# What it does:
#   1. Installs Docker Engine + docker compose plugin (skipped if present).
#   2. Drops the appliance into /opt/connect (configurable).
#   3. Generates fresh JWT_SECRET and NFC_SECRET_KEY into .env (preserved on re-run).
#   4. Pulls the latest images from GHCR.
#   5. Brings the stack up + waits for /healthz.
#   6. Prints the LAN IP + URL.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/connect}"
REPO="${CONNECT_REPO:-https://github.com/5812-global/connect.git}"
BRANCH="${CONNECT_BRANCH:-main}"

log()   { printf '\033[1;36m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
err()   { printf '\033[1;31mxx %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" = "0" ] || err "Run as root (use sudo)."

# ── 1. Docker ────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine + compose plugin…"
    curl -fsSL https://get.docker.com | sh
else
    log "Docker already installed — $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
    err "docker compose plugin missing. Re-run get.docker.com or install manually."
fi

# ── 2. Source ────────────────────────────────────────────────────
if [ ! -d "$INSTALL_DIR/.git" ]; then
    log "Cloning $REPO@$BRANCH → $INSTALL_DIR"
    git clone --branch "$BRANCH" --depth 1 "$REPO" "$INSTALL_DIR"
else
    log "Updating existing checkout in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
fi

APPLIANCE="$INSTALL_DIR/appliance"
cd "$APPLIANCE"

# ── 3. .env ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
    log "Generating fresh .env (secrets randomised) — edit before production use."
    cp .env.example .env
    JWT=$(openssl rand -hex 48)
    NFC=$(openssl rand -hex 32)
    # Portable sed — works on both GNU and BSD sed.
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$JWT|" .env
    sed -i.bak "s|^NFC_SECRET_KEY=.*|NFC_SECRET_KEY=$NFC|" .env
    rm -f .env.bak
else
    log ".env already exists — leaving it alone."
fi

# ── 4. Pull + start ──────────────────────────────────────────────
log "Pulling latest images…"
docker compose pull

log "Starting stack (this may take a minute on first run)…"
docker compose up -d

# ── 5. Wait for /healthz ─────────────────────────────────────────
log "Waiting for /healthz…"
for i in $(seq 1 60); do
    if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
        break
    fi
    sleep 2
    [ "$i" = 60 ] && warn "/healthz didn't respond within 2 minutes — check 'docker compose logs'"
done

# ── 6. Show URLs ─────────────────────────────────────────────────
LAN_IP="$(hostname -I | awk '{print $1}')"
cat <<EOM

────────────────────────────────────────────────────────────────────
  58:12 Connect appliance is up.

  LAN access:
    http://${LAN_IP}
    http://$(hostname -s).local        (mDNS, where supported)

  Useful commands:
    sudo docker compose -f $APPLIANCE/docker-compose.yml ps
    sudo docker compose -f $APPLIANCE/docker-compose.yml logs -f
    sudo docker compose -f $APPLIANCE/docker-compose.yml restart
    sudo docker compose -f $APPLIANCE/docker-compose.yml down

  Edit $APPLIANCE/.env to enable:
    - Public TLS hostname (SITE_DOMAIN)
    - Cloudflare Tunnel for remote access (CLOUDFLARED_TOKEN)
    - Email / OCR / Sentry integrations

  Default admin login:
    Email:    admin@5812uganda.org
    Password: Admin@5812
  >>> Rotate this password under Settings → Security before going live. <<<
────────────────────────────────────────────────────────────────────
EOM
