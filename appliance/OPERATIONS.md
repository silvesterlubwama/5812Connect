# Running 58:12 Connect on your own Ubuntu box

Two things people ask for: **how do I update it** and **how do I wire the web
addresses through Cloudflare**. Both, step by step. Everything below is run on
the Ubuntu box over SSH unless it says "in Cloudflare" or "in the app".

The stack lives in `/opt/connect/appliance` and is five containers:
`mongo`, `backend`, `caddy` (serves the app + proxies `/api`), optional
`cloudflared` (the tunnel), optional `coturn`.

---

## A. Update the app

### A1. One-time check before your first update after October 2026

The API now refuses to start without `SECRET_KEY` (it used to fall back to a
public placeholder — anyone could forge an admin login). Make sure your `.env`
has it, reusing this box's existing secret so nobody gets logged out:

```bash
cd /opt/connect/appliance
grep -q '^SECRET_KEY=' .env || \
  printf '\nSECRET_KEY=%s\n' "$(grep '^JWT_SECRET=' .env | head -1 | cut -d= -f2-)" >> .env
grep -c '^SECRET_KEY=' .env      # must print 1
```

If `JWT_SECRET` is somehow empty, use `openssl rand -hex 48` instead — but then
everyone has to sign in again and any saved PIN must be re-entered.

### A2. Back up first (always)

```bash
cd /opt/connect/appliance
sudo docker compose exec -T mongo mongodump --archive --gzip --db connect \
  > "backups/connect-$(date +%F-%H%M).archive.gz"
ls -lh backups/ | tail -3
```

Uploads and nightly backups already live in `./data/uploads` and `./data/backups`.
For a belt-and-braces copy of one organisation only, use the app:
**Organisations → Export** (a JSON file you can re-import later).

### A3. Pull the new version

The published images (`ghcr.io/silvesterlubwama/connect-*:latest`) are built by
GitHub Actions on pushes to `main`/`master` and on `v*` tags. Day-to-day work
happens on the `5812` branch, which does **not** publish — so pick one:

**Option 1 — ship a release (recommended).** In GitHub, merge `5812` into `main`
(or push a tag such as `v1.4.0`). Wait for the "Publish appliance images" action
to go green, then on the box:

```bash
cd /opt/connect/appliance
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
```

**Option 2 — build on the box from source** (no GitHub Actions needed; slower,
needs ~2 GB free and a few minutes, and a Pi will take considerably longer):

```bash
cd /opt/connect
sudo git pull
sudo docker build -f appliance/Dockerfile.backend  -t connect-backend:local  .
sudo docker build -f appliance/Dockerfile.frontend -t connect-frontend:local .
cd appliance
# point the stack at your local builds
grep -q '^BACKEND_IMAGE='  .env || echo 'BACKEND_IMAGE=connect-backend:local'   | sudo tee -a .env
grep -q '^FRONTEND_IMAGE=' .env || echo 'FRONTEND_IMAGE=connect-frontend:local' | sudo tee -a .env
sudo docker compose up -d
```

### A4. Confirm it actually came up

```bash
cd /opt/connect/appliance
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/healthz      # 200
curl -s http://localhost/api/health                                     # JSON, not HTML
sudo docker compose logs --tail=40 backend | grep -i -E 'error|secret|startup'
```

`/api/health` returning **HTML** means the request never reached the backend —
you are looking at the static app shell (see section C3).

### A5. If an update goes wrong

```bash
cd /opt/connect/appliance
# go back to the previous image you had, e.g.
echo 'BACKEND_IMAGE=ghcr.io/silvesterlubwama/connect-backend:v1.3.0'  | sudo tee -a .env
echo 'FRONTEND_IMAGE=ghcr.io/silvesterlubwama/connect-frontend:v1.3.0' | sudo tee -a .env
sudo docker compose up -d
# and if data needs restoring:
sudo docker compose exec -T mongo mongorestore --archive --gzip --drop < backups/<file>.archive.gz
```

---

## B. Cloudflare Tunnel — one tunnel, many addresses

The box never needs an open port or a static IP: `cloudflared` dials out to
Cloudflare, and Cloudflare sends traffic back down that connection.

### B1. Create the tunnel (in Cloudflare)

1. <https://one.dash.cloudflare.com> → **Networks → Tunnels → Create a tunnel**.
2. Connector: **Cloudflared**. Name it something you will recognise, e.g.
   `5812-uganda-main`.
3. Copy the **token** on the install screen (a long string). Ignore the install
   commands they show — the compose stack runs the connector for you.

### B2. Give the box the token

```bash
cd /opt/connect/appliance
sudo nano .env
#   CLOUDFLARED_TOKEN=<paste the token>
#   COMPOSE_PROFILES=tunnel
sudo docker compose --profile tunnel up -d
sudo docker compose logs --tail=20 cloudflared     # expect "Registered tunnel connection"
```

The tunnel should show **Healthy** in the Cloudflare dashboard.

### B3. Add each web address (in Cloudflare)

In the tunnel → **Public Hostnames → Add a public hostname**, once per address:

| Field | Value |
|---|---|
| Subdomain | leave blank for the apex, or `www`, `personal`, `new`… |
| Domain | `5812uganda.org` (or `lubwamas.org`) |
| Path | leave blank |
| Service type | **HTTP** |
| URL | `caddy:80` |

Add at minimum:

- `5812uganda.org` → `caddy:80`
- `www.5812uganda.org` → `caddy:80`

and then one per organisation, e.g. `personal.5812uganda.org`,
`new.lubwamas.org`. Cloudflare creates the DNS record for you — you do not add
an A record by hand. For a domain Cloudflare does not manage yet, add the site
to your Cloudflare account first (Websites → Add a site, then change the
nameservers at your registrar).

**Service must be `caddy:80`, not `localhost:80`.** `cloudflared` runs inside
Docker, so `localhost` is the connector container, not Caddy.

### B4. Clear anything else claiming the same hostname

If the address currently serves an old site, something else in Cloudflare owns
it. Check and remove, in this order:

1. **Workers & Pages** → your project → **Custom domains** — remove
   `5812uganda.org` / `www.5812uganda.org` if listed. This is the usual cause of
   "the site loads but logging in gives an error": a static copy of the app is
   being served and `POST /api/auth/login` hits nothing (you see `405`, and
   `/api/health` returns HTML).
2. **DNS → Records** — delete any leftover `A`/`AAAA`/`CNAME` for that name that
   does not point at the tunnel (`<uuid>.cfargotunnel.com`).
3. **Rules → Redirect Rules / Page Rules** — remove redirects for that hostname.

Then re-check from your laptop (not the box):

```bash
curl -I https://5812uganda.org/healthz                    # 200, server: Caddy-ish
curl -s https://5812uganda.org/api/health                 # JSON, NOT HTML
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://5812uganda.org/api/auth/login \
  -H 'Content-Type: application/json' -d '{"identifier":"x","password":"y"}'   # 401, never 405
```

`401` is the right answer here — it means the backend received the request and
rejected the fake credentials. `405` means you are still talking to a static site.

### B5. SSL mode

Cloudflare → **SSL/TLS → Overview → Full**. Do not use *Flexible* (it causes
redirect loops with Caddy) and do not use *Full (strict)* with the tunnel unless
you have given Caddy a certificate — the tunnel leg is already encrypted.

---

## B6. The platform owner on a new server

A fresh server seeds the owner on first boot from its own `.env`:

```bash
cd /opt/connect/appliance
grep '^OWNER_EMAIL=' .env            # who the owner is
sudo docker compose exec backend python scripts/create_super_admin.py --list
```

`--list` shows every owner, which organisation they are currently inside and when
the account was made. Passwords are hashed and cannot be read back; set a new one
with:

```bash
sudo docker compose exec backend python scripts/create_super_admin.py \
  --email silvesterlubwama@icloud.com --password 'a-new-passphrase'
```

Installing with your own owner password instead of a generated one:

```bash
OWNER_PASSWORD='a-long-passphrase' sudo -E bash install.sh
```

The owner value is used **once**, only when no owner exists — it is not a standing
reset, so an old `.env` cannot be used to take over a running server.

## B7. Where the owner password lives, and moving an organisation

**Setting or changing the owner password** — one file, one command:

| Where | What |
|---|---|
| This server | `/opt/connect/appliance/.env` → `OWNER_PASSWORD` (plus `OWNER_EMAIL`, `OWNER_NAME`). Read **once**, on first boot, when no owner exists. |
| Change it later | `sudo docker compose exec backend python scripts/create_super_admin.py --email <owner@…> --password '<new>'` |
| See the owners | `sudo docker compose exec backend python scripts/create_super_admin.py --list` |
| Emergent-hosted copy | the app key `OWNER_PASSWORD`, set from the chat's secure card |

It is never in the code or the image. Keep `.env` at `chmod 600`.

**Moving a whole organisation to another installation** — in the app, as the owner:

1. **Organisations → Export** on the organisation. A JSON file downloads containing
   every row *and* every uploaded file (logos, scans, photos).
2. On the other installation: **Organisations → Import organisation** and choose
   that file.
3. The copy arrives as a **separate** organisation: new id, no web address, never the
   default one, and its people sign in only once you assign it an address and they have
   accounts there. The original is untouched — exporting never moves or deletes.
4. Then delete the original if you are migrating: suspend it first, then delete and type
   its slug to confirm. **Export again immediately before deleting** — a delete keeps no copy.

A very large organisation produces a large file (58:12 Global is ~13 MB of rows plus its
files). If an upload is rejected for size, raise the proxy body limit, or move the
database and `./data/uploads` folder directly:

```bash
# on the old box
sudo docker compose exec -T mongo mongodump --archive --gzip --db connect > move.archive.gz
sudo tar czf uploads.tar.gz -C data uploads
# on the new box, after installing
sudo docker compose exec -T mongo mongorestore --archive --gzip --drop < move.archive.gz
sudo tar xzf uploads.tar.gz -C data
sudo docker compose restart backend
```

That moves **everything**, including all organisations; the export/import route is for
moving **one** organisation out of several.

## C. Point each organisation at its own address

Once the hostname reaches the box, tell the app which organisation owns it:

1. Sign in as the platform owner (`owner@5812global.org`).
2. **Organisations → Address** on that organisation.
3. Enter the hostnames, comma separated, no `https://`:
   `new.lubwamas.org, lubwamas.org`
4. Save.

From then on that address opens straight into that organisation with its own
logo, colours, sign-in screen and wording (**Settings → Branding &
Navigation**), and people sign in against that organisation only. An address can
belong to exactly one organisation.

Addresses you have **not** assigned fall back to the default organisation
(58:12 Global), so the main site keeps working while you set the others up.

### C3. Quick diagnosis table

| Symptom | Cause | Fix |
|---|---|---|
| `/api/health` returns HTML | request never reaches the backend | B4 — something else owns the hostname |
| Login returns `405` | static copy of the app is being served | B4 |
| `404` on everything | hostname not added to the tunnel | B3 |
| `502`/`530` | tunnel down or wrong service URL | `docker compose logs cloudflared`, service must be `caddy:80` |
| Redirect loop | Cloudflare SSL set to *Flexible* | B5 — set *Full* |
| Right site, wrong organisation | hostname not assigned, or typo | C — check it is listed under the correct organisation |
| Everyone logged out after update | `SECRET_KEY` changed | expected once; A1 keeps it stable in future |

---

## D. Routine operations

| Task | Command (in `/opt/connect/appliance`) |
|---|---|
| Status | `sudo docker compose ps` |
| Logs (follow) | `sudo docker compose logs -f backend` |
| Restart one service | `sudo docker compose restart backend` |
| Stop everything (keeps data) | `sudo docker compose down` |
| Disk usage | `du -sh data/*` |
| Free old images | `sudo docker image prune -f` |
| Manual backup | see A2 |

Never run `docker compose down -v` — the `-v` destroys the database.
