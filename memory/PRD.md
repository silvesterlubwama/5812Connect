# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 58 - Feb 2026)
- [x] Wallet badge: POST /api/members/{id}/wallet-badge generates shareable token, GET /api/wallet-badge/{token} public page
- [x] WalletBadgePage at /badge/:token — mobile-optimized dark badge with QR, country outline, save-to-home instructions
- [x] UnifiedBadge "Wallet" button now generates and opens shareable badge URL
- [x] Cascade deletion cleanup on all delete endpoints:
  - Member: removes from tasks assignees, boards tagged_members, unlinks user
  - Family: unlinks children and guests family_id
  - Guest: removes from children parent_ids
  - Child: removes from location resident_ids
  - User: cascades to tasks, boards, members, guests
- [x] Frontend dataEvents.js event bus for cross-component data refresh after mutations
- [x] AdminPage + TasksPage subscribe to data-changed events for auto-refresh

## Previous (Iterations 49-57)
- Venue CRUD, group types, import fixes, badge fixes, country outlines, timezone expansion
- User directory, outreach location/venue, recurrence options, portal fix, guest delete, kiosk lock
- QR camera, hooks, type hints, badges (NFC/country/footer), templates, photos, parent search

## Architecture
- **Wallet Badges**: wallet_badges collection, public GET at /api/wallet-badge/{token}
- **Cascade Deletion**: Inline cleanup in each delete endpoint (no background tasks)
- **Data Events**: services/dataEvents.js — emit('data-changed', {collection, id, action}) / on()
- **User Directory**: /api/admin/users/directory bypasses campus
- **Route Ordering**: Static before dynamic

## Test Reports: Iterations 49-58 all 100%

## Pending
- Future: Wave H5 SDK upgrade, server.py modularization
