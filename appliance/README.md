# 58:12 Connect — Appliance Deployment

A self-contained docker-compose stack that runs the entire 58:12 Connect application on any Linux box (mini PC, Raspberry Pi 5, VPS, on-prem server).

Partner orgs get a **single LAN URL** that everyone in the office browses to from their own phones / laptops / Chromebooks. Optionally, a Cloudflare Tunnel exposes the same instance over a public hostname for remote staff — no firewall rules, no static IP.

---

## What you get

- **MongoDB 7** (datafiles persisted in `./data/mongo/`)
- **FastAPI backend** (uploads + nightly backups persisted in `./data/uploads/` + `./data/backups/`)
- **Caddy** front-door: serves the built React SPA, reverse-proxies `/api/*`, auto-provisions Let's Encrypt TLS when a public domain is set
- **Cloudflared** daemon (opt-in via `COMPOSE_PROFILES=tunnel`) — remote access without opening ports

---

## Hardware sizing

| Org size | Box | Cost (USD) | Notes |
|---|---|---|---|
| ≤ 5 staff, ≤ 200 members | Raspberry Pi 5 (8 GB) + SD/SSD | ~$120 | Boots in ~60 s |
| ≤ 25 staff, ≤ 5 k members | Intel N100 mini PC (8 GB / 256 GB SSD) | ~$200 | Sweet spot for most partners |
| ≤ 100 staff, ≤ 50 k members | Any x86 box with 16 GB RAM | $400+ | Plus daily backup to S3 |
| Higher | Move to a VPS or the cloud build | — | Same compose file works on Hetzner / DigitalOcean |

---

## Quickstart (single command)

On a fresh **Ubuntu 22.04+ / Debian 12 / Raspberry Pi OS** install:

```bash
curl -fsSL https://raw.githubusercontent.com/5812-global/connect/main/appliance/install.sh | sudo bash
```

That script:

1. Installs Docker + the compose plugin.
2. Clones the repo to `/opt/connect`.
3. Generates random `JWT_SECRET` and `NFC_SECRET_KEY` in `.env`.
4. Pulls the latest published images from GHCR.
5. Starts the stack.
6. Prints the LAN IP + login URL.

~5 minutes on the first run, ~30 seconds for re-runs.

---

## Manual install (if you want to read what's happening first)

```bash
# 1. Get Docker
curl -fsSL https://get.docker.com | sudo sh

# 2. Get the appliance directory only (sparse-checkout is faster than full clone)
sudo git clone --depth 1 https://github.com/5812-global/connect.git /opt/connect
cd /opt/connect/appliance

# 3. Generate secrets
sudo cp .env.example .env
sudo sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 48)|" .env
sudo sed -i "s|^NFC_SECRET_KEY=.*|NFC_SECRET_KEY=$(openssl rand -hex 32)|" .env

# 4. Optionally fill in SITE_DOMAIN, CLOUDFLARED_TOKEN, RESEND_API_KEY, etc.
sudo nano .env

# 5. Bring it up
sudo docker compose up -d
```

LAN users browse to `http://<box-ip>` from any device.

Default admin: `admin@5812uganda.org` / `Admin@5812` — **rotate this in Settings → Security on first login.**

---

## Adding remote access (Cloudflare Tunnel)

1. Sign in at <https://one.dash.cloudflare.com> → Networks → Tunnels → Create a tunnel.
2. Choose **Cloudflared**, name it e.g. `5812-uganda-field-office`.
3. Copy the **token** Cloudflare shows.
4. Under *Public Hostnames* add `<your-subdomain>.5812-global.org` → service `http://caddy:80`.
5. On the appliance:

```bash
sudo nano /opt/connect/appliance/.env
# Set:  CLOUDFLARED_TOKEN=<paste>
# Set:  COMPOSE_PROFILES=tunnel
sudo docker compose -f /opt/connect/appliance/docker-compose.yml up -d
```

Remote users now reach the appliance at `https://<your-subdomain>.5812-global.org`.

---

## Public-internet TLS (without Cloudflare Tunnel)

If the appliance has a public IP and a real domain:

1. Point an A-record at the box's IP.
2. Open ports 80 + 443 on the firewall.
3. In `.env`:

```
SITE_DOMAIN=connect.example.org
ACME_EMAIL=admin@example.org
```

4. `sudo docker compose up -d` — Caddy auto-provisions Let's Encrypt.

---

## Operations cookbook

| Task | Command |
|---|---|
| View live logs | `sudo docker compose -f /opt/connect/appliance/docker-compose.yml logs -f` |
| Restart everything | `sudo docker compose ... restart` |
| Pull new images + restart | `sudo docker compose ... pull && sudo docker compose ... up -d` |
| Backup data | `sudo tar -czf connect-backup-$(date +%F).tgz -C /opt/connect/appliance data` |
| Restore data | `sudo tar -xzf connect-backup-YYYY-MM-DD.tgz -C /opt/connect/appliance/` |
| Wipe everything (irreversible!) | `sudo docker compose ... down -v && sudo rm -rf /opt/connect/appliance/data` |

The existing in-app `/admin → Backup & Restore` flow still works inside the appliance — it writes to `./data/backups/` (persisted) so the tarballs survive container restarts.

---

## Updating to a new version

```bash
cd /opt/connect
sudo git pull
cd appliance
sudo docker compose pull
sudo docker compose up -d
```

Images are version-tagged (`v0.1.0`, `v0.2.0`, …) and the `latest` tag tracks the newest stable release. To pin a specific version, set `BACKEND_IMAGE` / `FRONTEND_IMAGE` in `.env`.

---

## Architecture diagram

```
  Phone, Chromebook, Windows PC (LAN)
                ↓ HTTP/HTTPS
  ┌──────────────────────────────────┐
  │ Caddy (port 80 / 443)            │  ← TLS termination + SPA serve
  │  ├ /        →  /srv (React build) │
  │  ├ /api/*   →  backend:8001       │
  │  └ /ws/*    →  backend:8001 (WS)  │
  └──────────────┬───────────────────┘
                 │ Docker internal net
                 ↓
  ┌──────────────────────────────────┐
  │ FastAPI backend (port 8001)      │
  └──────────────┬───────────────────┘
                 │ MongoDB wire protocol
                 ↓
  ┌──────────────────────────────────┐
  │ MongoDB 7 (port 27017, internal) │
  │   data → /data/db (host volume)  │
  └──────────────────────────────────┘

  ┌──────────────────────────────────┐  (optional)
  │ cloudflared daemon               │
  │   outbound HTTPS to CF edge      │
  │   → https://<sub>.example.org    │
  └──────────────────────────────────┘
```

---

## Why this instead of the Tauri desktop bundle?

| | Tauri desktop bundle | Docker appliance |
|---|---|---|
| Install effort | One installer per device per OS | One install per office |
| Hardware budget | Per-device | One $200 box per office |
| Multi-user access | One device at a time | Whole LAN simultaneously |
| Phone / Chromebook support | No | Yes (any browser) |
| Certificate hassle | Mac + Windows code-sign certs | Zero (Linux server) |
| Offline ops | Yes | Yes (LAN works without internet) |
| Remote access | Cloudflare Tunnel from the install | Cloudflare Tunnel from the appliance |
| Updates | Per-device auto-updater | `docker compose pull && up -d` once |

Most welfare orgs are better served by the appliance. The Tauri build remains useful for single-operator setups (one social-worker laptop in the field), but for **organisations**, this is the right architecture.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose pull` fails with 401 | Images are private — `docker login ghcr.io` with a personal access token first. |
| Web UI loads but every API call returns 502 | Backend container crashed. `docker compose logs backend` for the stack trace. |
| LAN reach fine, Cloudflare URL 502 | Tunnel didn't pick up — check `docker compose logs cloudflared` for the auth error. |
| `mongod` complains about journal corruption | SD card on a Pi died mid-write. Restore from `/admin → Backup & Restore`. Recommend SSD over SD for Pi deployments. |
| Caddy can't acquire LE cert | `SITE_DOMAIN` doesn't resolve to this box, OR port 80 isn't reachable from the internet. Use HTTP-only + Cloudflare Tunnel instead. |
| First page-load is slow (~5 s) | React bundle is large on first hit — subsequent hits use Caddy's `Cache-Control` + `zstd/gzip` and load in < 200 ms. |
