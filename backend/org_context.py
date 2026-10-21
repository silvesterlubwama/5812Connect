"""Request-scoped organisation context.

Every request runs with exactly one organisation pinned in a ContextVar. The
org-scoped database proxy (org_scoped_db.py) reads this to decide which tenant's
rows a query may touch. Nothing in a router needs to remember to filter.
"""
from contextvars import ContextVar
from contextlib import contextmanager

_current_org: ContextVar = ContextVar("current_org_id", default=None)
_bypass: ContextVar = ContextVar("org_bypass", default=False)


# Collections that are genuinely platform-wide and carry no organisation_id.
# Keep this list short and justified — every entry is a hole in the wall.
UNSCOPED_COLLECTIONS = {
    "organizations",        # the tenant registry itself
    "org_exports",          # export manifests (carry org_id as a field, not a scope)
    "counters",             # sequence generators
    "app_config",           # platform build/runtime config
    "cron_runs",            # scheduler bookkeeping
    "public_endpoint_hits",  # per-IP rate limiting
    "login_attempts",       # per-IP brute-force throttle (pre-auth)
    "org_audit_log",        # platform actions; must outlive any one tenant
    "sessions",             # keyed by jti; resolved before org is known
    "password_reset_tokens",
}


class OrgScopeError(RuntimeError):
    """Raised when a tenant-scoped collection is queried with no organisation
    pinned. Failing loudly beats silently returning another tenant's rows."""


def set_current_org(org_id):
    return _current_org.set(org_id)


def get_current_org():
    return _current_org.get()


def reset_current_org(token):
    try:
        _current_org.reset(token)
    except ValueError:
        pass


def is_bypassed() -> bool:
    return _bypass.get()


@contextmanager
def org_bypass():
    """Escape hatch for the few places that must read across tenants:
    login (find the user before we know their org), the organisation registry,
    and migrations. Use sparingly and deliberately."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


@contextmanager
def org_as(org_id):
    """Pin a specific organisation for a block — used by cron jobs that must
    walk every tenant in turn, one isolated pass each."""
    token = _current_org.set(org_id)
    try:
        yield
    finally:
        _current_org.reset(token)
