"""iter395 adversarial probes (manual run): activity filter tagging after a
transfer, SVG logo XSS, activity total, hostname branding, logo content sniffing."""
import os, time, uuid, requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ORG_A = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
ORG_B = "ee79732c-1263-46a8-bf46-511c5fe812bf"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(i, p):
    db.login_attempts.delete_many({})
    r = requests.post(f"{API}/auth/login", json={"identifier": i, "password": p}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


H = lambda t: {"Authorization": f"Bearer {t}"}
o = login("owner@5812global.org", "Owner@5812!")
o = requests.post(f"{API}/organizations/{ORG_A}/enter", headers=H(o)).json()["token"]
b = login("admin@lubwamas.org", "Lubwama@2026")

# 1 activity filter tagging
for oid in (ORG_A, ORG_B):
    rows = requests.get(f"{API}/organizations/activity", params={"org_id": oid, "limit": 300}, headers=H(o)).json()["activity"]
    bad = [(x["action"], x["resource"], x["organization_id"]) for x in rows if x["organization_id"] != oid]
    print("filter", oid[:8], "rows", len(rows), "untagged/mis-tagged", len(bad), bad[:3])
all_ = requests.get(f"{API}/organizations/activity", params={"limit": 300}, headers=H(o)).json()
print("unfiltered rows w/o org name:", sum(1 for x in all_["activity"] if not x["organization_name"]),
      "actions:", {x["action"] for x in all_["activity"] if not x["organization_name"]})
print("total reported", all_["total"], "actual", db.audit_log.count_documents({}) + db.org_audit_log.count_documents({}))

# 2 SVG with script
svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.domain)</script></svg>'
r = requests.post(f"{API}/admin/system-settings/branding/logo", headers=H(b),
                  files={"file": ("x.svg", svg, "image/svg+xml")})
print("svg upload", r.status_code, r.text[:150])
if r.ok:
    u = r.json()["url"]; g = requests.get(u if u.startswith("http") else BASE + u)
    print("svg served", g.status_code, g.headers.get("content-type"), g.headers.get("content-security-policy"), b"<script>" in g.content)

# 3 HTML disguised as png
r = requests.post(f"{API}/admin/system-settings/branding/logo", headers=H(b),
                  files={"file": ("x.png", b"<html><script>alert(1)</script></html>", "image/png")})
print("html-as-png upload", r.status_code)
if r.ok:
    u = r.json()["url"]; g = requests.get(u if u.startswith("http") else BASE + u)
    print("served ct", g.headers.get("content-type"), "nosniff:", g.headers.get("x-content-type-options"))

# 4 hostname resolution (internal, Host header)
for host in ("new.lubwamas.org", "evil.example"):
    try:
        r = requests.get("http://localhost:8001/api/admin/system-settings/public", headers={"Host": host}, timeout=10)
        print("host", host, r.status_code, r.json()["branding"].get("app_name"))
    except Exception as e:
        print("host", host, "err", e)

# 5 public settings with owner token, and an expired-style token
r = requests.get(f"{API}/admin/system-settings/public", headers=H(o)).json()
print("owner public app_name", r["branding"]["app_name"])
