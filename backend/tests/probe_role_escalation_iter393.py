# iter393 escalation probe: can an ordinary org admin mint a super_admin (platform-wide) via user-management APIs?
import sys
import uuid

import requests

sys.path.insert(0, "/app/backend/tests")
from tenant_probe_common import API, destroy_org, h, login, make_org, mdb  # noqa: E402

org, hb, body = make_org("Esc")
d = mdb()
try:
    me = requests.get(f"{API}/auth/me", headers=hb, timeout=30).json()
    uid = me.get("id") or me.get("user", {}).get("id")
    print("owner role", me.get("role"))
    # a) self-promote
    r = requests.put(f"{API}/admin/users/{uid}", json={"role": "super_admin"}, headers=hb, timeout=30)
    print("PUT self role=super_admin", r.status_code, r.text[:150], "->", d.users.find_one({"id": uid})["role"])
    # b) create a user with super_admin role
    em = f"t393esc{uuid.uuid4().hex[:6]}@example.test"
    for path in ("/admin/users", "/users"):
        r = requests.post(f"{API}{path}", json={"name": "TEST esc", "email": em, "role": "super_admin", "password": "Esc@2026!xx"}, headers=hb, timeout=30)
        print("POST", path, r.status_code, r.text[:150])
    u = d.users.find_one({"email": em})
    print("created user role:", u and u.get("role"), "org:", u and u.get("organization_id"))
    # c) profile update
    r = requests.put(f"{API}/auth/profile", json={"role": "super_admin", "organization_id": None}, headers=hb, timeout=30)
    print("PUT /auth/profile", r.status_code, r.text[:100], "->", d.users.find_one({"id": uid}).get("role"))
    # d) try registry with whatever we have now
    t = login({"identifier": body["owner_email"], "password": body["owner_password"]}, cache=False)
    r = requests.get(f"{API}/organizations", headers=h(t["token"]), timeout=30) if t.get("token") else None
    print("registry after attempts:", r and r.status_code, (r.text[:120] if r is not None else t))
    if u:
        t2 = login({"identifier": em, "password": "Esc@2026!xx"}, cache=False)
        print("minted user login:", t2.get("status"), str(t2)[:200])
        if t2.get("token"):
            print("minted user registry:", requests.get(f"{API}/organizations", headers=h(t2["token"]), timeout=30).status_code)
finally:
    d.users.update_many({"email": {"$regex": "^t393esc"}}, {"$set": {"role": "staff"}})
    d.users.update_many({"organization_id": org["id"]}, {"$set": {"role": "admin"}})
    print("cleanup", destroy_org(org))
    d.users.delete_many({"email": {"$regex": "^t393esc"}})
