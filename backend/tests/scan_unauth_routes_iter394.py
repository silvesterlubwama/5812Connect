# iter394 — audit: list every HTTP route whose dependency tree contains NO auth dependency
import sys, os, collections
sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
from server import app  # noqa
from fastapi.routing import APIRoute

AUTH_NAMES = ("get_current_user", "require_", "get_optional_user", "verify_", "current_user", "get_portal", "get_customer", "optional_user")


def names(dep, acc):
    if dep.call is not None:
        acc.add(getattr(dep.call, "__name__", str(dep.call)))
    for d in dep.dependencies:
        names(d, acc)
    return acc


by_mod = collections.defaultdict(list)
for r in app.routes:
    if not isinstance(r, APIRoute):
        continue
    ns = names(r.dependant, set())
    if not any(any(a in n for a in AUTH_NAMES) for n in ns):
        mod = r.endpoint.__module__
        by_mod[mod].append(f"{','.join(sorted(r.methods))} {r.path}")
for m in sorted(by_mod):
    print(f"== {m} ({len(by_mod[m])})")
    for p in by_mod[m]:
        print("   ", p)
print("TOTAL", sum(len(v) for v in by_mod.values()))
