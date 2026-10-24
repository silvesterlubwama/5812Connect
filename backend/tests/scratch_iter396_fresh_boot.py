"""Boot the real app against an empty database and report what happens.

Run by test_iter396_google_passkey_bootstrap.py. Keeping it as a separate
process is the point: the app reads MONGO_URL/DB_NAME at import time, so a
fresh-deployment check cannot share the test process.

Prints a single line: RESULT {json}
"""
import json
import os
import socket
import subprocess
import sys
import time
import uuid

import requests
from pymongo import MongoClient

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..")

ENV = {}
with open(os.path.join(BACKEND, ".env")) as fh:
    for line in fh:
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.strip().partition("=")
            ENV[k] = v

MONGO_URL = os.environ.get("MONGO_URL") or ENV["MONGO_URL"]
SCRATCH = f"iter396_freshboot_{uuid.uuid4().hex[:8]}"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.update({k: v for k, v in ENV.items() if k not in env})
    env["MONGO_URL"] = MONGO_URL
    env["DB_NAME"] = SCRATCH
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    result = {"scratch_db": SCRATCH}
    try:
        for _ in range(90):
            try:
                if requests.get(f"{base}/api/health", timeout=2).status_code == 200:
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                result["error"] = "server exited: " + (proc.stdout.read()[-1500:] if proc.stdout else "")
                print("RESULT " + json.dumps(result))
                return
            time.sleep(1)
        else:
            result["error"] = "server never became healthy"
            print("RESULT " + json.dumps(result))
            return

        time.sleep(3)  # let the startup bootstrap finish

        db = MongoClient(MONGO_URL)[SCRATCH]
        result["orgs"] = [
            [o.get("name"), o.get("slug"), bool(o.get("is_default")), o.get("status")]
            for o in db.organizations.find({}, {"_id": 0})
        ]
        result["owners"] = [
            [(u.get("email") or "").lower(), u.get("organization_id")]
            for u in db.users.find({"role": "super_admin"}, {"_id": 0})
        ]

        # the public auth surface that used to 500 with no organisation
        codes = {}
        codes["google_bad_session"] = requests.post(
            f"{base}/api/auth/google-session", json={"session_id": "bogus"}, timeout=20).status_code
        codes["passkey_begin"] = requests.post(
            f"{base}/api/webauthn/authenticate/begin", json={}, timeout=20).status_code
        codes["passkey_begin_email"] = requests.post(
            f"{base}/api/webauthn/authenticate/begin",
            json={"email": "nobody@example.org"}, timeout=20).status_code
        codes["public_settings"] = requests.get(
            f"{base}/api/admin/system-settings/public", timeout=20).status_code
        codes["login_bad"] = requests.post(
            f"{base}/api/auth/login", json={"identifier": "nobody@example.org", "password": "x"},
            timeout=20).status_code
        result["codes"] = codes

        owner_email = os.environ.get("OWNER_EMAIL") or ENV.get("OWNER_EMAIL", "")
        owner_password = os.environ.get("OWNER_PASSWORD") or ENV.get("OWNER_PASSWORD", "")
        r = requests.post(f"{base}/api/auth/login",
                          json={"identifier": owner_email, "password": owner_password}, timeout=30)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        result["owner_login"] = {
            "status": r.status_code,
            "requires_org_selection": bool(body.get("requires_org_selection")),
            "signed_in": bool(body.get("token")),
            "orgs": len(body.get("organizations") or []),
        }
    except Exception as e:  # noqa: BLE001 — the point is to report, not to raise
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        MongoClient(MONGO_URL).drop_database(SCRATCH)
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
