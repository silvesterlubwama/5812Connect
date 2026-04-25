# 58:12 Connect - Product Requirements

## Overview
Multi-tenant CRM for 58:12 Global with WebRTC calling, unified comms, NFC badge management, and PBX integration.

## Latest Changes (Iteration 62 - Feb 2026)
- [x] Financial nav always visible for admins (even on "All Locations")
- [x] Financial summary, cashflow, donations, expenses, products, sales all respect campus filter
- [x] New financial records auto-set location_id from user's active campus
- [x] Cashflow chart filters by campus

## Previous (Iteration 61)
- Dashboard action widgets (overdue, pending, expiring, unassigned), email notifications

## Previous (Iterations 49-60)
- Safety features, wallet badges, cascade deletion, data events, templates, imports, badges, photos

## Architecture
- **Financial Campus Filter**: get_campus_filter() applied to all financial queries
- **Auto location_id**: Donations/expenses/products/sales auto-set from active_campus_id on creation
- **Nav Visibility**: Financial/Marketplace hide only when specific campus has feature disabled

## Test Reports: Iterations 49-62 all 100%
