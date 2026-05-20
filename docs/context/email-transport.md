# Email Transport — SDGNext

## Current transport

Microsoft Graph API (since the Graph migration PR).
All outbound email flows through `app/core/graph_mailer.py` →
`send_graph_email()`.

## Authentication

OAuth2 client-credentials flow. App registration in Azure AD
(BusinessNEXT tenant). Credentials in `.env`:

- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `GRAPH_SENDER_MAILBOX`

Token cached in-memory, refreshed ~5 min before expiry.

## Sender

All email sends as `delivery@businessnext.com` (a service mailbox).
Requires an Exchange Application Access Policy scoping the app
registration to this mailbox.

## Threading

**Approach 1 (primary):** `internetMessageHeaders` carries standard
RFC 5322 headers (`Message-ID`, `In-Reply-To`, `References`) directly.
Graph API v1.0 accepts these. Clients (Outlook, Gmail) use them for
native threading.

**Approach 2 (safety net):** Subjects are intentionally stable and
date-free per (project, department) or (project, touchpoint). Even if
Graph were to strip custom headers, subject-based threading groups
conversations correctly.

## Send sites (8 total, 4 files)

| File | Function | Threading? |
|------|----------|------------|
| `app/core/mom_engine.py` | `generate_and_send_mom()` | No |
| `app/core/mom_engine.py` | `send_touchpoint_mom()` | Message-ID |
| `app/core/email_engine.py` | `generate_and_send_daily_summary()` | No |
| `app/core/email_engine.py` | `send_followup_nudges()` | In-Reply-To + References |
| `app/core/email_engine.py` | `_send_mom_pointer_email()` | Message-ID + In-Reply-To + References |
| `app/workshop_mailer.py` | `_send_dept_email()` | Message-ID + In-Reply-To + References |
| `app/core/email_dispatcher.py` | `send_rgt_invite()` | No (has attachment) |

## Diagnostics

- `GET /admin/graph/health` — verifies token + lists granted
  permissions from JWT claims
- `POST /admin/graph/test-email?to_address=...` — sends a test email

## NOT migrated

Inbound mail reading (`inbound_service.py`) still uses IMAP. Migrating
inbound to Graph is future work.

## Setup for a new deployment

1. Copy `.env.example` to `.env`
2. Fill in the four `GRAPH_*` values from Azure portal
3. Confirm via `GET /admin/graph/health`
4. Send a test: `POST /admin/graph/test-email?to_address=you@example.com`
