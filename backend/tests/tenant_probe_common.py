# Shared helpers for iter393 adversarial tenant-isolation probes (public URL + direct Mongo canaries)
import json
import os
import time
import uuid

import requests
from pymongo import MongoClient


def _env(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
MONGO = _env("/app/backend/.env", "MONGO_URL")
DBN = _env("/app/backend/.env", "DB_NAME")

SUPER = {"identifier": "owner@5812global.org", "password": "Owner@5812!"}
A_ADMIN = {"identifier": "admin@5812uganda.org", "password": "Admin@5812"}
LUB_ADMIN = {"identifier": "admin@lubwamas.org", "password": "Lubwama@2026"}
A_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"

TOKFILE = "/tmp/iter393_tokens.json"


def mdb():
    return MongoClient(MONGO)[DBN]


def clear_throttle():
    d = mdb()
    d.login_attempts.delete_many({})
    d.public_endpoint_hits.delete_many({})


def _load():
    try:
        return json.load(open(TOKFILE))
    except Exception:
        return {}


def login(creds, cache=True):
    toks = _load()
    k = creds["identifier"]
    if cache and k in toks:
        r = requests.get(f"{API}/auth/me", headers=h(toks[k]["token"]), timeout=20)
        if r.status_code == 200:
            return toks[k]
    clear_throttle()
    for _ in range(3):
        r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
        if r.status_code == 429:
            time.sleep(20)
            continue
        break
    out = {"status": r.status_code, **(r.json() if r.headers.get("content-type", "").startswith("application/json") else {})}
    if r.status_code == 200 and cache:
        toks[k] = out
        json.dump(toks, open(TOKFILE, "w"))
    return out


def h(token):
    return {"Authorization": f"Bearer {token}"}


def super_into(org_id):
    """Super admin enters an org; returns headers for the fresh token."""
    s = login(SUPER)
    r = requests.post(f"{API}/organizations/{org_id}/enter", headers=h(s["token"]), timeout=30)
    assert r.status_code == 200, r.text
    return h(r.json()["token"])


def make_org(label):
    s = login(SUPER)
    slug = f"t393{uuid.uuid4().hex[:8]}"
    body = {"name": f"TEST_iter393 {label}", "slug": slug,
            "owner_email": f"{slug}@example.test", "owner_name": f"{label} Admin",
            "owner_password": "Tenant@2026!"}
    r = requests.post(f"{API}/organizations", json=body, headers=h(s["token"]), timeout=60)
    assert r.status_code == 200, r.text
    org = r.json()["organization"]
    tok = login({"identifier": body["owner_email"], "password": body["owner_password"]})
    assert tok.get("token"), tok
    return org, h(tok["token"]), body


def destroy_org(org):
    s = login(SUPER)
    requests.post(f"{API}/organizations/{org['id']}/status", json={"status": "suspended"}, headers=h(s["token"]), timeout=30)
    r = requests.delete(f"{API}/organizations/{org['id']}", params={"confirm": org["slug"]}, headers=h(s["token"]), timeout=120)
    return r.status_code
