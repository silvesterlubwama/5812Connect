# Never bulk-delete from the live database

2026-10-21 (iter395) — while clearing test rows the live DB was hit with raw
`delete_many` queries built from name/email regexes. It removed the real primary
admin accounts (`admin@5812uganda.org`, `admin@5812global.org`), which had to be
restored by hand with their original ids so existing records stayed linked.

Rules from now on:
1. Never run `delete_many` against the live DB to clean test rows. Count first
   (`count_documents`), print the matching docs, and only then delete — or leave
   them alone. Test pollution is cosmetic; deleted real data is not.
2. Tests must clean up after themselves. Pollution found later belongs to the
   suite that made it, not to a cleanup script.
3. Before any destructive operation on a tenant, use the organisation export
   (`GET /api/organizations/{id}/export`) so there is a restore path.
4. Accounts to protect (restore with the SAME id if ever lost — records reference
   the id, not the email):
   - `admin@5812uganda.org` → id `9e76c0f3-4709-40c7-88f2-846963742632`
   - `admin@5812global.org` → id `2f9a94cf-7482-4e63-ab52-409505a19fc5`
   - `owner@5812global.org` (platform owner, `organization_id` deliberately null)
   - `admin@lubwamas.org` (Lubwamas tenant admin)
