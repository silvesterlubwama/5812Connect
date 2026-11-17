#!/usr/bin/env python3
"""58:12 shop print helper.

Collects receipts from 58:12 and sends them to the printer on this shop's
network. Run it once on any computer or Raspberry Pi at the shop:

    python3 print-helper.py

It sets itself to start again whenever the machine boots, so nobody has to
remember. To stop that:

    python3 print-helper.py --uninstall

Nothing to install — it only uses what Python ships with.
"""
import base64
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "__API__"
TOKEN = "__TOKEN__"

APP = "5812-print-helper"
UA = "58-12-print-helper/1.0"            # the default agent is turned away by the firewall
LOCK_PORT = 54812                       # one helper per machine
HOME = os.path.expanduser(f"~/.local/share/{APP}")
INSTALLED = os.path.join(HOME, "print-helper.py")
UNIT = os.path.expanduser(f"~/.config/systemd/user/{APP}.service")
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/com.5812.print-helper.plist")


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=30)


def only_one():
    """Hold a local port for as long as we run. A second copy — from the
    keep-alive timer, or someone double-clicking — bows out instead of
    printing everything twice."""
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", LOCK_PORT))
        guard.listen(1)
    except OSError:
        print("The print helper is already running on this computer.")
        sys.exit(0)
    return guard


def copy_self():
    os.makedirs(HOME, exist_ok=True)
    here = os.path.abspath(__file__)
    if here != INSTALLED:
        shutil.copyfile(here, INSTALLED)
        os.chmod(INSTALLED, 0o755)
    return INSTALLED


def install_systemd(script):
    os.makedirs(os.path.dirname(UNIT), exist_ok=True)
    with open(UNIT, "w") as fh:
        fh.write(f"""[Unit]
Description=58:12 shop print helper
After=network-online.target

[Service]
ExecStart={sys.executable} {script}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""")
    run("systemctl", "--user", "daemon-reload")
    enabled = run("systemctl", "--user", "enable", "--now", f"{APP}.service")
    if enabled.returncode != 0:
        raise RuntimeError(enabled.stderr.strip() or "systemd refused")
    # Keeps it running when nobody is logged in — needs a password on some
    # systems, so a failure here is not fatal.
    run("loginctl", "enable-linger", os.environ.get("USER", ""))
    return "it will start with the machine (systemd)"


def install_launchd(script):
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w") as fh:
        fh.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.5812.print-helper</string>
  <key>ProgramArguments</key>
  <array><string>{sys.executable}</string><string>{script}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
""")
    run("launchctl", "unload", PLIST)
    loaded = run("launchctl", "load", PLIST)
    if loaded.returncode != 0:
        raise RuntimeError(loaded.stderr.strip() or "launchctl refused")
    return "it will start when you log in (launchd)"


def install_cron(script):
    """Last resort: @reboot in this user's crontab, plus a five-minute check.
    The lock above makes the repeat harmless."""
    current = run("crontab", "-l")
    lines = [ln for ln in (current.stdout or "").splitlines() if APP not in ln]
    lines += [
        f"@reboot {sys.executable} {script} >/dev/null 2>&1 # {APP}",
        f"*/5 * * * * {sys.executable} {script} >/dev/null 2>&1 # {APP}",
    ]
    written = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                             capture_output=True, text=True, timeout=30)
    if written.returncode != 0:
        raise RuntimeError(written.stderr.strip() or "crontab refused")
    return "it will start at every reboot (cron)"


def install():
    script = copy_self()
    attempts = ([install_launchd] if platform.system() == "Darwin" else [install_systemd]) + [install_cron]
    for attempt in attempts:
        try:
            how = attempt(script)
            print(f"Set to start again by itself: {how}.")
            print(f"Copied to {script}")
            return
        except Exception as exc:                            # noqa: BLE001 - try the next way
            last = exc
    print(f"Could not set it to start on its own ({last}).")
    print("It will still print for as long as this window stays open.")


def uninstall():
    run("systemctl", "--user", "disable", "--now", f"{APP}.service")
    for path in (UNIT, PLIST):
        if os.path.exists(path):
            if path == PLIST:
                run("launchctl", "unload", path)
            os.remove(path)
    current = run("crontab", "-l")
    if current.returncode == 0:
        lines = [ln for ln in current.stdout.splitlines() if APP not in ln]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=30)
    print("The print helper will no longer start on its own.")


def call(path, payload=None):
    url = f"{API}/screens/{TOKEN}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read() or "null")


def send(job):
    with socket.create_connection((job["host"], int(job.get("port") or 9100)), timeout=5) as sock:
        sock.sendall(base64.b64decode(job["data_b64"]))
        time.sleep(0.4)


def main():
    if "--uninstall" in sys.argv:
        uninstall()
        return
    guard = only_one()                                      # noqa: F841 - held for the whole run
    if "--no-install" not in sys.argv:
        install()
    print("58:12 print helper running.")
    print(f"Talking to {API}")
    while True:
        try:
            for job in call("/print-jobs") or []:
                ok, err = True, ""
                try:
                    send(job)
                    print(f"Printed {job.get('title')} on {job.get('host')}")
                except Exception as exc:                     # noqa: BLE001 - report anything
                    ok, err = False, str(exc)
                    print(f"Could not print {job.get('title')}: {err}")
                try:
                    call(f"/print-jobs/{job['id']}", {"ok": ok, "error": err})
                except urllib.error.URLError:
                    print("Could not report back to 58:12")
        except urllib.error.URLError:
            print("Waiting for 58:12...")
            time.sleep(5)
        time.sleep(2)


if __name__ == "__main__":
    main()
