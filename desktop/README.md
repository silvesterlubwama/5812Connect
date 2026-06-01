# 58:12 Connect — Self-hosted Desktop Bundle (Tauri)

This directory contains the **scaffold** for the self-hosted desktop build of 58:12 Connect.

The bundle ships:
- **FastAPI backend** (PyInstaller-bundled, single binary)
- **Portable MongoDB** (one binary per platform)
- **Cloudflare Tunnel daemon** (`cloudflared` — for optional remote access)
- **React frontend** (production-built, served by the Tauri webview at `http://127.0.0.1:8001/`)

Result on each platform:
- macOS → `58:12 Connect.app` + `.dmg` installer
- Windows → `.msi` + `.exe` (NSIS) installers
- Linux → `.deb` + `.AppImage`

---

## Why a desktop bundle?

For partner orgs that need the system to run **fully offline** (no cloud dependency) or who
already maintain on-prem infra. The bundle:
- Spawns `mongod` listening on `127.0.0.1:27017`
- Spawns the FastAPI backend on `127.0.0.1:8001`
- Opens a Tauri webview pointed at the local backend
- Optionally exposes the app over a **Cloudflare Named Tunnel** so remote staff can log in
  via a public hostname (e.g. `https://desktop.5812-global.org`) without opening firewall ports.

Data lives in `${app_data_dir}/mongo-data/` — survives upgrades and is included in the
existing `iter-150` backup tarball workflow. So an org can move data between desktop ↔
production cloud the exact same way they do today.

---

## Build prerequisites (NOT inside the Emergent preview container)

You need a real desktop OS to produce native installers. The Kubernetes preview can't
cross-compile. Run these commands on the target OS (or in a CI runner):

| Dep | Install command |
|---|---|
| Rust 1.78+ | `curl https://sh.rustup.rs -sSf \| sh` |
| Tauri CLI v2 | `cargo install tauri-cli@^2` |
| PyInstaller 6.x | `pip install pyinstaller==6.10.0` |
| **macOS extras** | `xcode-select --install` |
| **Windows extras** | [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| **Linux extras** | `sudo apt install libwebkit2gtk-4.1-dev build-essential libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev` |

Then drop these into `desktop/resources/`:

| Resource | Where to get it |
|---|---|
| `desktop/resources/mongo/mongod` | https://www.mongodb.com/try/download/community → "Server" → tarball → extract `bin/mongod` |
| `desktop/resources/cloudflared/cloudflared` | https://github.com/cloudflare/cloudflared/releases — pick the platform-matching binary |

> **One bundle per platform.** Drop the macOS `mongod` to build the `.dmg`, the Windows
> `mongod.exe` to build the `.msi`, etc. The build script will refuse to start if the binary
> is missing.

---

## Build command

```bash
cd /app
bash desktop/scripts/build-bundle.sh
```

Output: `desktop/src-tauri/target/release/bundle/{dmg,msi,nsis,deb,appimage}/`

---

## First-run setup (end users)

1. **Install** the platform-matching installer (`.dmg`, `.msi`, `.AppImage`).
2. **Launch** "58:12 Connect". The app will:
   - Spawn `mongod` (port 27017, bound to `127.0.0.1`)
   - Spawn the bundled FastAPI backend (port 8001, bound to `127.0.0.1`)
   - Open the webview at `http://127.0.0.1:8001/`
3. **Sign in** with the seed admin: `admin@5812uganda.org` / `Admin@5812` and rotate the
   password under Settings → Security.
4. **Optional remote access** — see *Cloudflare Tunnel setup* below.

---

## Cloudflare Tunnel setup (remote access)

The bundled `cloudflared` daemon lets you expose the local app over a public Cloudflare
hostname **without** opening any firewall ports or buying a static IP.

### One-time prep on Cloudflare (web UI)

1. Sign in at https://one.dash.cloudflare.com → Networks → Tunnels → Create a tunnel
2. Choose connector type **Cloudflared**, give it a name (e.g. `5812-desktop-uganda`)
3. Cloudflare will show a one-line `cloudflared service install <TOKEN>` snippet — copy
   the **token** (everything after `install`).
4. Under **Public Hostnames**, add a hostname:
   - Subdomain: `desktop` (or whatever)
   - Domain: `5812-global.org`
   - Type: `HTTP`
   - URL: `localhost:8001`

### Inside the desktop app (Settings → Remote Access)

Paste a tunnel config like:

```yaml
tunnel: <TUNNEL-UUID-FROM-CLOUDFLARE>
credentials-file: /Users/you/.cloudflared/<TUNNEL-UUID>.json
ingress:
  - hostname: desktop.5812-global.org
    service: http://127.0.0.1:8001
  - service: http_status:404
```

Click **Start Tunnel**. The Tauri shell calls the Rust command
`start_cloudflare_tunnel(config_yaml)` which:
1. Writes the config to `${app_data_dir}/cloudflared/config.yml`
2. Spawns `cloudflared tunnel --config <that path> run`
3. Tracks the PID so it can be cleanly stopped on quit.

The dashboard's existing **Audit Trail** module logs the tunnel start/stop the same way it
logs every other admin action.

---

## Architecture diagram

```
┌─────────────────────────────────────────────────┐
│  Tauri WebView  (http://127.0.0.1:8001/)        │
│   ↓ HTTP                                         │
│  FastAPI backend  ← spawned by Rust shell       │
│   ↓ Mongo wire protocol                          │
│  Portable mongod (127.0.0.1:27017)              │
│   ↳ data:   ${app_data_dir}/mongo-data/         │
│   ↳ uploads: ${app_data_dir}/uploads/           │
└────────────┬────────────────────────────────────┘
             │ (optional)
             │ tunnels via
             ↓
┌─────────────────────────────────────────────────┐
│  cloudflared daemon                             │
│   ↓ outbound HTTPS to Cloudflare edge           │
│  https://desktop.5812-global.org  ←──────remote │
│                                       browser   │
└─────────────────────────────────────────────────┘
```

---

## Limitations of the scaffold

- **Cross-compilation is not done here.** Build on each target OS (or use a CI matrix).
- **Auto-update is not configured.** Tauri supports an `updater` plugin; wire it up if you
  want push-style upgrades — see https://v2.tauri.app/plugin/updater/.
- **No code signing yet.** The build will produce unsigned bundles. Production signing
  needs an Apple Developer ID / a Windows EV cert. Both are organisational decisions.
- **The Rust shell silently retries the backend health check for 20 s** before opening the
  webview. If the backend fails to come up, the window will still open but show an error
  page — check `${app_data_dir}/logs/`.

---

## How this maps to the cloud version

| Cloud (Kubernetes preview / production) | Desktop bundle |
|---|---|
| `MONGO_URL=mongodb://prod-cluster:27017` | `MONGO_URL=mongodb://127.0.0.1:27017` (local mongod) |
| `RESEND_API_KEY` from K8s secrets | Pasted by admin into Integrations UI (system_settings) |
| `EMERGENT_LLM_KEY` for OCR/AI | Same — admin pastes into Integrations UI |
| Cloudflare Workers / nginx ingress | `cloudflared` daemon spawned by the Rust shell |
| K8s liveness probe `/api/health` | Tauri's setup hook waits for the same endpoint |

The same `iter-150` backup tarball moves data **either direction** so an org can pilot on
desktop, then promote to cloud (or vice versa) without losing data.
