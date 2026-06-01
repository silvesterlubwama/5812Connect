# 58:12 Connect — Self-hosted Desktop Bundle (Tauri)

Scaffold for the self-hosted desktop build of 58:12 Connect.

The bundle ships:
- **FastAPI backend** — PyInstaller-bundled, single binary.
- **Portable MongoDB** — one binary per platform.
- **Cloudflare Tunnel daemon** (`cloudflared`) — for optional remote access.
- **React frontend** — production-built, served by the Tauri webview at `http://127.0.0.1:8001/`.
- **EULA enforcement** — the `.exe` (NSIS) and `.dmg` installers display the agreement and refuse to install if the user does not accept.
- **Auto-update** — Tauri updater plugin scaffolded; turn on by setting `plugins.updater.active=true` in `tauri.conf.json` and pointing `endpoints` at your release server.
- **Code signing** — Apple Developer ID + Windows EV cert wiring is scaffolded as **no-op by default**. Set the matching env vars before `cargo tauri build` to enable signing.
- **Anonymous heartbeat** — opt-in daily POST to your HQ deploy with `install_id`, `version`, `user_count`. **No PII**. License key validation rides the same beacon.

Result on each platform:
- macOS → `58:12 Connect.app` + `.dmg` installer (EULA shown by macOS during install)
- Windows → `.msi` (WiX) + `.exe` (NSIS) installers (EULA shown via NSIS license page; the user MUST tick "I Accept")
- Linux → `.deb` + `.AppImage`

---

## Why a desktop bundle?

For partner orgs that need 58:12 Connect to run **fully offline** (no cloud dependency) or who already maintain on-prem infra. The bundle:

- Spawns `mongod` listening on `127.0.0.1:27017`
- Spawns the FastAPI backend on `127.0.0.1:8001`
- Opens a Tauri webview pointed at the local backend
- Optionally exposes the app over a **Cloudflare Named Tunnel** so remote staff can log in via a public hostname (e.g. `https://desktop.5812-global.org`) without opening firewall ports.

Data lives in `${app_data_dir}/mongo-data/` — survives upgrades and rides the existing `iter-150` backup tarball workflow. So an org can move data between desktop ↔ production cloud the exact same way they do today.

---

## Build prerequisites (NOT inside the Emergent preview container)

You need a real desktop OS to produce native installers. The Kubernetes preview can't cross-compile. Run these on the target OS (or in a CI runner):

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

> **One bundle per platform.** Drop the macOS `mongod` to build the `.dmg`, the Windows `mongod.exe` to build the `.msi`, etc. The build script will refuse to start if the binary is missing.

---

## Build command

```bash
cd /app
bash desktop/scripts/build-bundle.sh
```

Output: `desktop/src-tauri/target/release/bundle/{dmg,msi,nsis,deb,appimage}/`

---

## End User License Agreement (EULA)

The agreement text lives at `desktop/eula/EULA.txt` (plus a Markdown copy at
`desktop/eula/EULA.md`). Both `tauri.conf.json` and the build script pick it up
automatically:

- **macOS `.dmg`** — `bundle.macOS.license` field. macOS displays the agreement before the user can drag the app to /Applications. They must accept to continue.
- **Windows `.exe` (NSIS)** — `bundle.windows.nsis.license` field. NSIS shows a license page during install with a mandatory **"I accept"** radio button.
- **Windows `.msi` (WiX)** — `bundle.windows.wix.license` field expects a `.rtf`. Convert from `.txt` once with: `unoconv -f rtf desktop/eula/EULA.txt` and commit the resulting `EULA.rtf` next to it.

To customise the agreement text, edit `desktop/eula/EULA.txt` (and re-export to `.rtf` if you target WiX), then rebuild.

---

## Auto-updater

Tauri's `tauri-plugin-updater` is wired into `Cargo.toml` and `lib.rs`. The plugin is **disabled by default** (`plugins.updater.active=false` in `tauri.conf.json`). To enable:

### 1. Generate a signing keypair (once)

```bash
cargo tauri signer generate -w ~/.tauri/5812.key
# Outputs:
#   ~/.tauri/5812.key       (PRIVATE — keep on the build host / in CI secrets)
#   ~/.tauri/5812.key.pub   (PUBLIC — paste into tauri.conf.json)
```

### 2. Update `tauri.conf.json`

```json
"plugins": {
  "updater": {
    "active": true,
    "endpoints": [
      "https://hq.5812-global.org/releases/{{target}}/{{current_version}}"
    ],
    "dialog": true,
    "pubkey": "<paste-contents-of-5812.key.pub-here>"
  }
}
```

### 3. Sign release artifacts during build

Set these env vars before `cargo tauri build`:

```bash
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/5812.key)"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD='<the-key-password>'
```

Each release artifact (`.dmg.tar.gz`, `.msi.zip`, `.AppImage.tar.gz`) gets a matching `.sig` file. Upload both to your release server.

### 4. Release server JSON shape

Tauri queries the URL from step 2 and expects this JSON back:

```json
{
  "version": "0.2.0",
  "notes": "Bug fixes + new sales analytics tab.",
  "pub_date": "2026-07-01T12:00:00Z",
  "platforms": {
    "darwin-aarch64": {
      "signature": "<contents of *.sig file>",
      "url": "https://hq.5812-global.org/releases/0.2.0/58-12-Connect_0.2.0_aarch64.dmg.tar.gz"
    },
    "windows-x86_64": {
      "signature": "...",
      "url": "..."
    },
    "linux-x86_64": {
      "signature": "...",
      "url": "..."
    }
  }
}
```

A 5-line FastAPI route on the HQ backend can serve that JSON. If you don't need
auto-update yet, leave `active=false` and ship manual installers.

---

## Code signing

Both signing paths are scaffolded as **no-ops by default**. The build runs unsigned
unless the right env vars are set.

### macOS (Apple Developer ID)

Get an Apple Developer Program membership ($99/year), then in the Apple Developer portal:
1. Create a *Developer ID Application* certificate. Download + install it in your Keychain.
2. Get your Team ID from the membership page.
3. Generate an [app-specific password](https://support.apple.com/en-us/102654) for notarisation.

```bash
export APPLE_SIGNING_IDENTITY="Developer ID Application: 58:12 Global Inc (XXXXXXXXXX)"
export APPLE_ID="builds@5812-global.org"
export APPLE_PASSWORD="<the-app-specific-password>"
export APPLE_TEAM_ID="XXXXXXXXXX"
bash desktop/scripts/build-bundle.sh
```

The build will sign the `.app` and submit the `.dmg` for notarisation.

### Windows (EV code-signing certificate)

EV certificates require a hardware token (USB / cloud HSM) from a CA like DigiCert / Sectigo. Once installed in the Windows certificate store:

```cmd
:: Find the SHA1 thumbprint of your EV cert
certutil -store My
:: Then in PowerShell or CMD:
set WINDOWS_CERT_THUMBPRINT=<paste-sha1-thumbprint-no-spaces>
set WINDOWS_TIMESTAMP_URL=http://timestamp.digicert.com
bash desktop/scripts/build-bundle.sh
```

The build will sign the `.exe` and `.msi` outputs. Untick `bundle.windows.tsp` in
`tauri.conf.json` if your CA doesn't support RFC-3161 timestamping (almost all do).

> **No EV cert?** Builds will still work — they'll just trigger Microsoft Defender
> SmartScreen warnings on first launch. Users can still proceed via *More info →
> Run anyway*.

---

## License key + telemetry heartbeat

Self-hosted desktop installs report a **daily anonymous heartbeat** to a HQ
deployment so 58:12 Global can see deployment spread + nudge stragglers to
upgrade. The heartbeat carries:

- `install_id` — UUID4 generated on first config (NOT a hardware fingerprint)
- `license_key` — pasted by the admin (or empty for unlicensed pilots)
- `org_id`, `version`, `user_count`, `env`

**No PII.** No member names, document content, or chat data is transmitted.

### How it works

1. Admin opens `/admin → License & Telemetry` in the desktop app.
2. Pastes the `license_key` HQ issued, sets `hq_url` (defaults to `https://hq.5812-global.org`), opts-in to telemetry.
3. The desktop's scheduler runs every 24 h at 02:00 UTC and POSTs to `${hq_url}/api/telemetry/heartbeat`.
4. HQ stores the heartbeat in `db.telemetry_heartbeats` + upserts the install in `db.telemetry_installs`.
5. HQ returns the current license status (`valid` / `expired` / `blocked` / `invalid` / `unlicensed`). The desktop persists it locally so `/api/license/self` can serve the dashboard banner without re-calling HQ.

### Soft enforcement

A **blocked** or **expired** license shows an amber dismissible banner above the
app shell — the app **never** crashes or refuses to log in. Partner orgs are not
paying customers; we want to nudge, not punish.

### Issuing license keys (HQ side)

`/admin → License & Telemetry → HQ` lets system_admins issue keys:

- **Org name** — required (e.g. "Hope Centre Uganda")
- **Plan** — `standard` / `extended` / `trial`
- **Expires at** — optional ISO date

Keys are 32-char URL-safe tokens. HQ admins can also block / unblock / delete
keys, and view the live install roster (testid `license-tab-installs`).

### Privacy / opt-out

Admins can disable telemetry at any time from the same dialog. The opt-in is
also disclosed in the EULA section 3 ("Data & Privacy").

---

## Cloudflare Tunnel setup (remote access)

The bundled `cloudflared` daemon lets you expose the local app over a public
Cloudflare hostname **without** opening any firewall ports or buying a static IP.

### One-time prep on Cloudflare (web UI)

1. Sign in at https://one.dash.cloudflare.com → Networks → Tunnels → Create a tunnel
2. Choose connector type **Cloudflared**, give it a name (e.g. `5812-desktop-uganda`)
3. Cloudflare will show a one-line `cloudflared service install <TOKEN>` snippet — copy the **token**.
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

Click **Start Tunnel**. The Tauri shell calls the Rust command `start_cloudflare_tunnel(config_yaml)` which:
1. Writes the config to `${app_data_dir}/cloudflared/config.yml`
2. Spawns `cloudflared tunnel --config <that path> run`
3. Tracks the PID so it can be cleanly stopped on quit.

The dashboard's existing **Audit Trail** module logs the tunnel start/stop the same way it logs every other admin action.

---

## Architecture diagram

```
┌─────────────────────────────────────────────────┐
│  Tauri WebView  (http://127.0.0.1:8001/)        │
│   ↓ HTTP                                         │
│  FastAPI backend  ← spawned by Rust shell       │
│   ↓ Mongo wire protocol                          │
│  Portable mongod (127.0.0.1:27017)              │
│   ↳ data:    ${app_data_dir}/mongo-data/        │
│   ↳ uploads: ${app_data_dir}/uploads/           │
└────────────┬────────────────────────────────────┘
             │ (optional: every 24 h)
             ↓
┌─────────────────────────────────────────────────┐
│  HQ telemetry  →  POST /api/telemetry/heartbeat │
│   ↳ install roster on HQ admin dashboard        │
│   ↳ license validation                          │
└─────────────────────────────────────────────────┘
             │ (optional: always)
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
- **The Rust shell silently retries the backend health check for 20 s** before opening the webview. If the backend fails to come up, the window will still open but show an error page — check `${app_data_dir}/logs/`.
- **Auto-updater is disabled by default.** Flip `plugins.updater.active=true` after generating a signing key + uploading release artifacts.
- **Code signing is gated on env-var presence.** Builds without the env vars produce unsigned bundles that trigger Gatekeeper / SmartScreen warnings.

---

## How this maps to the cloud version

| Cloud (Kubernetes preview / production) | Desktop bundle |
|---|---|
| `MONGO_URL=mongodb://prod-cluster:27017` | `MONGO_URL=mongodb://127.0.0.1:27017` (local mongod) |
| `RESEND_API_KEY` from K8s secrets | Pasted by admin into Integrations UI (system_settings) |
| `EMERGENT_LLM_KEY` for OCR/AI | Same — admin pastes into Integrations UI |
| Cloudflare Workers / nginx ingress | `cloudflared` daemon spawned by the Rust shell |
| K8s liveness probe `/api/health` | Tauri's setup hook waits for the same endpoint |
| (none) | Daily heartbeat to HQ + soft license enforcement |

The same `iter-150` backup tarball moves data **either direction** so an org can pilot on desktop, then promote to cloud (or vice versa) without losing data.
