"""Audit: does every API path the frontend calls actually exist on the backend?

Catches the class of bug that keeps biting this app — a router gets dropped or
renamed and the UI silently keeps calling the old path, so a feature "works"
but moves no data (the 404 gets swallowed by a catch/allSettled).

Scans BOTH `services/api.js` and every inline `api.*()` / fetch() call in the
pages/components, normalises template literals to a wildcard, and diffs against
the live FastAPI route table.

    python3 /app/scripts/audit_api_paths.py           # dead paths only
    python3 /app/scripts/audit_api_paths.py --all     # also print the totals
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
import server  # noqa: E402

SRC = "/app/frontend/src"

routes = []
for r in server.app.routes:
    if hasattr(r, "methods"):
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$"
        for m in r.methods - {"HEAD", "OPTIONS"}:
            routes.append((m, re.compile(pattern)))


def normalise(path: str) -> str:
    p = path.split("?")[0]
    p = re.sub(r"\$\{[^}]+\}", "X", p)          # `${id}` → X
    p = re.sub(r"'\s*\+\s*\w+\s*\+?\s*'?", "X", p)  # ' + id + '
    if not p.startswith("/api"):
        p = "/api" + ("" if p.startswith("/") else "/") + p
    return p


def is_alive(method: str, path: str) -> bool:
    full = normalise(path)
    return any(m == method.upper() and rx.match(full) for m, rx in routes)


def scan_file(rel_path: str):
    """Yield (method, path, line_no) for every API call in one file."""
    text = open(os.path.join(SRC, rel_path)).read()
    for m in re.finditer(r"api\.(get|post|put|delete|patch)\(\s*[`'\"]([^`'\"]+)[`'\"]", text):
        yield m.group(1).upper(), m.group(2), text[:m.start()].count("\n") + 1
    # Raw fetch() straight at the backend URL
    for m in re.finditer(r"fetch\(\s*[`'\"]?\$\{?[A-Za-z_.]*BACKEND_URL\}?([^`'\"\s,)]+)", text):
        yield "GET", m.group(1), text[:m.start()].count("\n") + 1


files = subprocess.run(
    ["bash", "-c", f"cd {SRC} && ls **/*.jsx *.js **/*.js 2>/dev/null | sort -u"],
    capture_output=True, text=True,
).stdout.split()

total = 0
dead = []
for f in files:
    try:
        for method, path, line in scan_file(f):
            total += 1
            if not is_alive(method, path):
                dead.append((f, line, method, normalise(path)))
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        continue

print(f"scanned {total} API calls across {len(files)} files · {len(routes)} live routes")
print(f"DEAD: {len(dead)}\n")
by_file: dict = {}
for f, line, method, path in dead:
    by_file.setdefault(f, []).append((line, method, path))
for f in sorted(by_file):
    print(f"  {f}")
    for line, method, path in sorted(by_file[f]):
        print(f"      :{line:<5} {method:6} {path}")

sys.exit(1 if dead else 0)
