#!/usr/bin/env bash
# 58:12 Connect — desktop build helper.
#
# Bundles the FastAPI backend (PyInstaller) + portable MongoDB + cloudflared,
# then runs `cargo tauri build`. Optionally signs the resulting installers if
# the matching env vars are set.
#
# REQUIREMENTS on the build host (NOT inside the Emergent preview container):
#   • Rust 1.78+ + cargo
#   • cargo-tauri:                    cargo install tauri-cli@^2
#   • PyInstaller:                    pip install pyinstaller==6.10.0
#   • Portable MongoDB binary:        https://www.mongodb.com/try/download/community (server, "tgz")
#   • cloudflared binary:             https://github.com/cloudflare/cloudflared/releases
#   • Platform Tauri deps:            https://v2.tauri.app/start/prerequisites/
#
# CODE SIGNING (optional — leave unset to produce unsigned dev bundles):
#   APPLE_SIGNING_IDENTITY="Developer ID Application: 58:12 Global Inc (XXXXXXXXXX)"
#   APPLE_ID="builds@5812-global.org"
#   APPLE_PASSWORD="<app-specific-password>"
#   APPLE_TEAM_ID="XXXXXXXXXX"
#   WINDOWS_CERT_THUMBPRINT="<sha1-thumbprint-of-EV-cert-in-Cert-store>"
#   WINDOWS_TIMESTAMP_URL="http://timestamp.digicert.com"
#
# AUTO-UPDATE SIGNING (optional — set if you want signed update artifacts):
#   TAURI_SIGNING_PRIVATE_KEY="<path-to-or-contents-of-tauri-signing-key>"
#   TAURI_SIGNING_PRIVATE_KEY_PASSWORD="<key-password>"
#
#   Generate a fresh signing key once with:
#     cargo tauri signer generate -w ~/.tauri/5812.key
#   Then put the PUBLIC key into tauri.conf.json → plugins.updater.pubkey
#
# Output:
#   • macOS:   desktop/src-tauri/target/release/bundle/dmg/58:12 Connect_*.dmg
#   • Windows: desktop/src-tauri/target/release/bundle/{msi,nsis}/58:12 Connect_*.{msi,exe}
#   • Linux:   desktop/src-tauri/target/release/bundle/{deb,appimage}/...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
RESOURCES="$ROOT/desktop/resources"

echo "==> Bundling FastAPI backend with PyInstaller"
cd "$BACKEND"
pyinstaller --onefile --name server \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.loops" \
  --hidden-import "uvicorn.loops.auto" \
  --hidden-import "uvicorn.protocols" \
  --hidden-import "uvicorn.protocols.http" \
  --hidden-import "uvicorn.protocols.http.auto" \
  --hidden-import "uvicorn.protocols.websockets" \
  --hidden-import "uvicorn.protocols.websockets.auto" \
  --hidden-import "uvicorn.lifespan" \
  --hidden-import "uvicorn.lifespan.on" \
  --collect-all "emergentintegrations" \
  --collect-all "weasyprint" \
  --collect-all "resend" \
  server.py

mkdir -p "$RESOURCES/backend"
cp dist/server "$RESOURCES/backend/server"
chmod +x "$RESOURCES/backend/server"

echo "==> Bundling frontend (production build)"
cd "$ROOT/frontend"
yarn install --frozen-lockfile
yarn build
mkdir -p "$ROOT/desktop/dist"
cp -r build/* "$ROOT/desktop/dist/"

echo "==> Verifying portable MongoDB & cloudflared are present"
for required in "$RESOURCES/mongo/mongod" "$RESOURCES/cloudflared/cloudflared"; do
  if [ ! -f "$required" ]; then
    echo "MISSING: $required"
    echo "Drop the portable binary for the target platform, then re-run."
    exit 1
  fi
  chmod +x "$required"
done

echo "==> Verifying EULA exists"
if [ ! -f "$ROOT/desktop/eula/EULA.txt" ]; then
  echo "MISSING: $ROOT/desktop/eula/EULA.txt"
  exit 1
fi

# ============================================================
# Code-signing env-var detection
# ============================================================
if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
  echo "==> Apple code-signing identity detected — bundles will be signed"
  export APPLE_SIGNING_IDENTITY
  [ -n "${APPLE_ID:-}" ] && export APPLE_ID
  [ -n "${APPLE_PASSWORD:-}" ] && export APPLE_PASSWORD
  [ -n "${APPLE_TEAM_ID:-}" ] && export APPLE_TEAM_ID
else
  echo "==> APPLE_SIGNING_IDENTITY not set — macOS bundle will be unsigned (Gatekeeper will warn end users)"
fi

if [ -n "${WINDOWS_CERT_THUMBPRINT:-}" ]; then
  echo "==> Windows EV cert thumbprint detected — bundles will be signed"
  # tauri.conf.json reads tauri.bundle.windows.certificateThumbprint at build time;
  # the simplest portable way to inject is via the env var picked up by tauri-cli.
  export TAURI_BUNDLE_WINDOWS_CERTIFICATE_THUMBPRINT="$WINDOWS_CERT_THUMBPRINT"
  [ -n "${WINDOWS_TIMESTAMP_URL:-}" ] && export TAURI_BUNDLE_WINDOWS_TIMESTAMP_URL="$WINDOWS_TIMESTAMP_URL"
else
  echo "==> WINDOWS_CERT_THUMBPRINT not set — Windows bundle will be unsigned (SmartScreen will warn end users)"
fi

if [ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]; then
  echo "==> Tauri update-artifact signing detected — .sig files will be produced"
  export TAURI_SIGNING_PRIVATE_KEY
  [ -n "${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}" ] && export TAURI_SIGNING_PRIVATE_KEY_PASSWORD
fi

echo "==> Building the Tauri bundle"
cd "$ROOT/desktop"
cargo tauri build

echo "==> DONE. Bundles in desktop/src-tauri/target/release/bundle/"
ls -la "$ROOT/desktop/src-tauri/target/release/bundle/" 2>/dev/null || true
