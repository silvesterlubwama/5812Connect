# iter393 broad leak scan: a fresh empty tenant B calls every parameterless GET route; any org-A record id in the body = leak
import json
import re
import sys
import time

import requests

sys.path.insert(0, "/app/backend/tests")
from tenant_probe_common import API, A_ORG, mdb, make_org, destroy_org  # noqa: E402

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SKIP = ("/api/organizations", "/api/auth/logout", "/api/ws", "/api/public/", "/api/health", "/api/export", "/api/backup")


def a_ids():
    d = mdb()
    ids = {A_ORG}
    for c in d.list_collection_names():
        for r in d[c].find({"organization_id": A_ORG}, {"_id": 0, "id": 1}).limit(3000):
            if isinstance(r.get("id"), str):
                ids.add(r["id"])
    return ids


def main():
    ids = a_ids()
    print("A ids:", len(ids))
    spec = requests.get(f"{API.rsplit('/api',1)[0]}/api/openapi.json", timeout=30)
    if spec.status_code != 200:
        spec = json.load(open("/tmp/oa.json"))
    else:
        spec = spec.json()
    paths = [p for p, v in spec["paths"].items() if "get" in v and "{" not in p and not p.startswith(SKIP)]
    print("GET routes:", len(paths))
    org, hb, body = make_org("Scan")
    print("org B", org["id"], org["slug"])
    leaks, errors = [], []
    try:
        for i, p in enumerate(paths):
            t = time.time()
            try:
                r = requests.get(API.rsplit("/api", 1)[0] + p, headers=hb, timeout=25)
            except Exception as e:
                errors.append((p, str(e)[:80]))
                continue
            if r.status_code >= 500:
                errors.append((p, r.status_code, r.text[:120]))
            found = set(UUID.findall(r.text)) & ids
            if found:
                leaks.append((p, r.status_code, len(found), list(found)[:3]))
            dt = time.time() - t
            if dt < 0.12:
                time.sleep(0.12 - dt)
    finally:
        print("cleanup", destroy_org(org))
    print("\nLEAKS:")
    for l in leaks:
        print(" ", l)
    print("\n5xx/ERR:")
    for e in errors:
        print(" ", e)
    json.dump({"leaks": leaks, "errors": errors}, open("/tmp/iter393_scan.json", "w"), indent=1)


if __name__ == "__main__":
    main()
