"""Organisation-scoped MongoDB proxy.

Routers import `db` from deps and call it exactly as before. This proxy sits in
between and rewrites every operation so it can only see or touch rows belonging
to the organisation pinned on the current request:

  * reads  (find / find_one / count_documents / distinct / aggregate)
        -> filter is AND-ed with {"organization_id": <org>}
  * writes (insert / update / replace / delete)
        -> documents are stamped with the org, filters are AND-ed with it

A tenant-scoped collection accessed with no organisation pinned raises
OrgScopeError rather than quietly returning everything.
"""
from org_context import (
    UNSCOPED_COLLECTIONS,
    OrgScopeError,
    get_current_org,
    is_bypassed,
)

ORG_FIELD = "organization_id"

# iter394 — super_admin is a PLATFORM role that sits above every organisation.
# Individual routers guard it, but new routes keep appearing that take a role
# straight from the request body (users/import and guests/move-to-staff both
# did), so the rule is enforced here instead: no request path may create or
# promote one. Legitimate creation goes through scripts/create_super_admin.py,
# which holds a direct database handle and never passes through this proxy.
PLATFORM_ROLE = "super_admin"


def _reject_platform_role(collection_name, value):
    if collection_name != "users":
        return
    if isinstance(value, str) and value.lower() == PLATFORM_ROLE:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="The platform owner role cannot be assigned from inside an organisation",
        )

# Operations that never touch rows and so need no scoping.
_PASSTHROUGH = {
    "create_index", "create_indexes", "drop_index", "drop_indexes",
    "index_information", "list_indexes", "drop", "name", "full_name",
    "database", "codec_options", "watch", "estimated_document_count",
}


def _scope_filter(query, org):
    """AND the org constraint onto a query, never trusting a caller-supplied
    organization_id to widen the scope."""
    org_clause = {ORG_FIELD: org}
    if not query:
        return org_clause
    return {"$and": [query, org_clause]}


def _stamp(doc, org, collection_name=None):
    if isinstance(doc, dict):
        _reject_platform_role(collection_name, doc.get("role"))
        doc[ORG_FIELD] = org
    return doc


def _stamp_update(update, org, collection_name=None):
    """Make sure an upsert that creates a row stamps it with the org, and that
    nobody can move a row to another tenant via $set/$unset."""
    if not isinstance(update, dict):
        return update
    update = dict(update)
    for op in ("$set", "$setOnInsert"):
        if isinstance(update.get(op), dict):
            _reject_platform_role(collection_name, update[op].get("role"))
    _reject_platform_role(collection_name, update.get("role"))
    for op in ("$set", "$setOnInsert"):
        if op in update and isinstance(update[op], dict):
            update[op] = {k: v for k, v in update[op].items() if k != ORG_FIELD}
            if not update[op]:
                update.pop(op)
    if "$unset" in update and isinstance(update["$unset"], dict):
        update["$unset"] = {k: v for k, v in update["$unset"].items() if k != ORG_FIELD}
        if not update["$unset"]:
            update.pop("$unset")
    if any(k.startswith("$") for k in update):
        update["$setOnInsert"] = {**update.get("$setOnInsert", {}), ORG_FIELD: org}
    else:
        # whole-document replacement expressed as an update
        update[ORG_FIELD] = org
    return update


class OrgScopedCollection:
    def __init__(self, raw, name):
        self._raw = raw
        self._name = name

    def _org(self):
        org = get_current_org()
        if not org:
            raise OrgScopeError(
                f"Query on '{self._name}' with no organisation pinned. "
                "Wrap deliberate cross-tenant reads in org_bypass()."
            )
        return org

    # ---- reads ----
    def find(self, query=None, *args, **kwargs):
        return self._raw.find(_scope_filter(query, self._org()), *args, **kwargs)

    async def find_one(self, query=None, *args, **kwargs):
        return await self._raw.find_one(_scope_filter(query, self._org()), *args, **kwargs)

    async def count_documents(self, query=None, *args, **kwargs):
        return await self._raw.count_documents(_scope_filter(query or {}, self._org()), *args, **kwargs)

    async def distinct(self, key, query=None, *args, **kwargs):
        return await self._raw.distinct(key, _scope_filter(query, self._org()), *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        org = self._org()
        guarded = [{"$match": {ORG_FIELD: org}}] + list(pipeline or [])
        return self._raw.aggregate(guarded, *args, **kwargs)

    # ---- writes ----
    async def insert_one(self, document, *args, **kwargs):
        return await self._raw.insert_one(_stamp(document, self._org(), self._name), *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        org = self._org()
        return await self._raw.insert_many([_stamp(d, org, self._name) for d in documents], *args, **kwargs)

    async def update_one(self, query, update, *args, **kwargs):
        org = self._org()
        return await self._raw.update_one(
            _scope_filter(query, org), _stamp_update(update, org, self._name), *args, **kwargs
        )

    async def update_many(self, query, update, *args, **kwargs):
        org = self._org()
        return await self._raw.update_many(
            _scope_filter(query, org), _stamp_update(update, org, self._name), *args, **kwargs
        )

    async def replace_one(self, query, replacement, *args, **kwargs):
        org = self._org()
        return await self._raw.replace_one(
            _scope_filter(query, org), _stamp(dict(replacement), org, self._name), *args, **kwargs
        )

    async def find_one_and_update(self, query, update, *args, **kwargs):
        org = self._org()
        return await self._raw.find_one_and_update(
            _scope_filter(query, org), _stamp_update(update, org, self._name), *args, **kwargs
        )

    async def find_one_and_delete(self, query, *args, **kwargs):
        return await self._raw.find_one_and_delete(_scope_filter(query, self._org()), *args, **kwargs)

    async def delete_one(self, query, *args, **kwargs):
        return await self._raw.delete_one(_scope_filter(query, self._org()), *args, **kwargs)

    async def delete_many(self, query, *args, **kwargs):
        return await self._raw.delete_many(_scope_filter(query, self._org()), *args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._raw, item)


class OrgScopedDatabase:
    """Drop-in stand-in for a Motor database handle."""

    def __init__(self, raw):
        self._raw = raw
        self._cache = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, name):
        raw_collection = self._raw[name]
        if name in UNSCOPED_COLLECTIONS or is_bypassed():
            return raw_collection
        if name not in self._cache:
            self._cache[name] = OrgScopedCollection(raw_collection, name)
        return self._cache[name]

    @property
    def raw(self):
        return self._raw

    async def list_collection_names(self, *args, **kwargs):
        return await self._raw.list_collection_names(*args, **kwargs)

    @property
    def client(self):
        return self._raw.client
