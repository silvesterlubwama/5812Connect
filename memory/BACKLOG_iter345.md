# Backlog captured 2026-06 (user mega-list)

## A. Portal / Members (P0)
1. Staff + members cannot view/edit their family (staff profile OR member portal). Family view must include spouse, children, guardians.
2. Member portal must NOT show chat. Add non-staff filter to portal nav.
   - Member-only nav: Events, Family (view/edit), Tickets, Badge, Account statements (sales/events), Profile download.
   - Staff-who-are-also-members keep timecards, receipts, expenses etc.
3. Tickets do not show for RSVP'd / ticketed events.
4. Store ticket info on badge profile → member with access badge who RSVP'd/ticketed is flagged "ticketed" at kiosk/checkpoint scan using badge only.
5. Staff logged into main app only see profile settings — add link to their own member portal.

## B. Notifications / Dashboard (P0)
6. Cleared notifications return later with stale links → must be hard-erased.
7. Overdue task digest (email + dashboard) shows stale data.
8. All dashboard info mostly stale/incorrect — especially financial + tasks.

## C. Badges (P1)
9. Badge differs across admin / profile / portal. Portal version is canonical. Footer details must not be hidden.
10. Print / download / save-to-wallet drops QR + photo.

## D. Finance (P0/P1)
11. Purchase order drafts fully editable; submissions PDF-printable with letterhead (logo + location name, e.g. "Zimba Farm").
12. Stale vendors survived the finance reset. Wire vendors + donors correctly into finance.
13. Some finance report types return an error when clicked.
14. Account drill-down: selecting an account in Banking or CoA shows transactions for/against it in a period, with backward month paging for self-audit.
15. Make finance high-end + error-free: exercise transfers, income, assets, expenses, splits, banking, vendors, sales, events, receipts, products, depreciation/appreciation.

## E. Uploads (P1)
16. Receipt scan must accept file/photo upload, not camera-only.
17. Dashboard universal upload button: non-AI detection of file type → user confirms → routes to correct flow (receipt, school report, etc.). Audit ALL upload endpoints.

## F. Tasks / Boards (P1)
18. Boards return archived tasks then hide on refresh.
19. Remove done/archived dated tasks from calendar.
20. Sub-location boards not showing — should bypass campus filter and appear.

## G. Misc (P2)
21. Consumables tracking sheet doesn't actually print.

## H. Online payments (deferred by user)
- Provider: Flutterwave / Uganda mobile money (MTN/Airtel). Keys later via app settings (Financial APIs vault).
- Keep both checkout options: "Pay now" and "Pay on collection".
- On success: mark "Paid online — awaiting staff confirmation", email receipt, reserve stock immediately, appear in Sales for staff confirm → then post to `1030 Online Payments`.
- NOT auto-posting to ledger.
