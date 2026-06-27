#!/bin/sh
# 58:12 Connect — Asterisk PBX container entrypoint.
#
# Pulls fresh pjsip.conf / extensions.conf / voicemail.conf from the FastAPI
# backend, writes them to /etc/asterisk, then starts (or HUP-reloads) asterisk.
# Runs on a configurable interval (PBX_RELOAD_INTERVAL, default 60s).
#
# Required env (set in docker-compose.yml):
#   PBX_API_URL          — e.g. http://localhost/api/pbx
#   PBX_TOKEN            — admin JWT (one-off; rotate via Admin → PBX → Token)
#   PBX_RELOAD_INTERVAL  — seconds between config polls (default 60)

set -e

PBX_API_URL="${PBX_API_URL:-http://localhost/api/pbx}"
PBX_RELOAD_INTERVAL="${PBX_RELOAD_INTERVAL:-60}"
LAST_HASH=""

pull_config() {
  if [ -z "$PBX_TOKEN" ]; then
    echo "[pbx-entrypoint] PBX_TOKEN not set — skipping config sync. Writing stub config."
    mkdir -p /etc/asterisk
    if [ ! -f /etc/asterisk/pjsip.conf ]; then
      cat > /etc/asterisk/pjsip.conf <<EOF
; Awaiting PBX_TOKEN — no SIP endpoints configured yet.
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
EOF
      echo "" > /etc/asterisk/extensions.conf
      echo "" > /etc/asterisk/voicemail.conf
    fi
    return
  fi
  for fname in pjsip.conf extensions.conf voicemail.conf; do
    tmpfile=$(mktemp)
    if curl -fsS -H "Authorization: Bearer $PBX_TOKEN" "$PBX_API_URL/config/$fname" -o "$tmpfile" 2>/dev/null; then
      if ! cmp -s "$tmpfile" "/etc/asterisk/$fname" 2>/dev/null; then
        mv "$tmpfile" "/etc/asterisk/$fname"
        echo "[pbx-entrypoint] $fname updated"
        return 0   # at least one file changed — caller should reload
      else
        rm -f "$tmpfile"
      fi
    else
      echo "[pbx-entrypoint] WARN: could not fetch $fname from $PBX_API_URL"
      rm -f "$tmpfile"
    fi
  done
  return 1   # nothing changed
}

reload_or_start_asterisk() {
  if pidof asterisk >/dev/null 2>&1; then
    echo "[pbx-entrypoint] reloading Asterisk..."
    asterisk -rx "core reload" || true
  else
    echo "[pbx-entrypoint] starting Asterisk..."
    asterisk -f -U asterisk -G asterisk &
  fi
}

# Initial pull + start
pull_config || true
reload_or_start_asterisk

# Reload loop
while true; do
  sleep "$PBX_RELOAD_INTERVAL"
  if pull_config; then
    reload_or_start_asterisk
  fi
done
