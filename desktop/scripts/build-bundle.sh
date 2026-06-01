#!/usr/bin/env bash
# 58:12 Connect — desktop build helper.
#
# This script bundles the FastAPI backend (PyInstaller), drops a portable MongoDB,
# and a cloudflared binary into desktop/resources/, then runs `cargo tauri build`.
#
# REQUIREMENTS on the build host (NOT inside the Emergent preview container):
#   • Rust 1.78+ + cargo
#   • cargo-tauri:                    cargo install create-tauri-app tauri-cli@^2
#   • PyInstaller:                    pip install pyinstaller==6.10.0
#   • Portable MongoDB binary:        https://www.mongodb.com/try/download/community (server, "tgz")
#   • cloudflared binary:             https://github.com/cloudflare/cloudflared/releases
#   • Platform-specific Tauri deps:   https://v2.tauri.app/start/prerequisites/
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
# --onefile produces a single binary; --add-data carries email templates / static assets.
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

echo "==> Building the Tauri bundle"
cd "$ROOT/desktop"
cargo tauri build

echo "==> DONE. Bundles in desktop/src-tauri/target/release/bundle/"
ls -la "$ROOT/desktop/src-tauri/target/release/bundle/"
