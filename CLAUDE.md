# CLAUDE.md — Project Conventions for SDGNext

## Architecture Quick Reference

- **Backend:** FastAPI (Python), SQLAlchemy ORM, PostgreSQL
- **Frontend:** Vanilla JS + Tailwind CSS (no framework)
- **Pages:** `landing.html` (cross-project), `index.html` (project view), `details.html` (touchpoint detail)

## Key Conventions

### Single-Stage Workflow (2025-01)

- Phase 1 (Functional Discovery) UI is **removed**. The Workshop Board is
  the default view inside a project.
- Backend table `idr_functional_discovery` is retained as **metadata storage**,
  not a workflow gate. Don't reintroduce sign-off filters on the Workshop
  Board query.
- "Phase 2" and "Workshop Board" are the same thing — "Workshop Board" is
  the UI label, "Phase 2" is the backend identifier (API paths, table names,
  JS variable names).
- API path `/api/phase2/dashboard` is preserved for backward compatibility.
  Do NOT rename it.
- IDRTechnical rows are created **EAGERLY** at CSV upload time (see
  `file_parser.py` PART2_MAPPING). The lazy-creation path in `main.py` is a
  defensive fallback only for legacy data without an IDRTechnical row.

### Identity System

- Owner-like fields are free-text validated against `team_master` on write,
  enriched on read. Never add FK constraints from IDR tables to `team_master`.
- Always pass `project_id` to validator functions.
- See `docs/context/identity-system.md` for full rules.

### Out of Scope / Don't Do

- Don't rename `idr_functional_discovery` table
- Don't rename `/api/phase2/dashboard` endpoint
- Don't rename Python files or JS variable names referencing "phase2"
- Don't add a "Restore Phase 1" feature flag
- Don't reintroduce sign-off filters on the Workshop Board query
- Don't modify MoM, follow-up, or email engine behavior without explicit spec
- On fresh deployment, run `POST /admin/snapshot/backfill-today` to seed
  sparkline data. See `docs/context/analytics-snapshots.md`.

### File Organization

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app + Phase 2 endpoints |
| `app/core/graph_mailer.py` | Microsoft Graph API email transport (single send point) |
| `app/services/file_parser.py` | CSV upload processing |
| `app/services/project_health.py` | Landing page KPIs + daily snapshot capture |
| `app/services/identity_validator.py` | Name resolution |
| `js/app-dashboard.js` | Project view init + switchPhase logic |
| `js/tailwind-config.js` | UI design tokens (Tailwind runtime config) |
| `js/phase2_technical.js` | Workshop Board table + inline editing |
| `js/landing.js` | Landing page rendering (sparkline cards + drilldown) |

### UI Design Tokens

- Defined in `js/tailwind-config.js`, loaded after Tailwind CDN on all pages.
- Use token classes (`bg-primary`, `bg-shell`) over raw Tailwind colors for
  new components.
- See `docs/context/ui-tokens.md` for the full reference.

### Action Log Conventions

- `action_by` is a free-text label (currently `"User"` placeholder)
- `action_type` values: `DISCUSSION`, `POINTER`, `STATUS_CHANGE`,


  `MOM_SENT`, `MOM_NUDGE_SENT`, `FOLLOWUP_CLOSED`, `FOLLOWUP_REOPENED`,
  `Manual Update`, `WORKSHOP_INVITE_SENT`
  - Don't invent new action_types without documenting them

### Email Workflows

- **Transport:** Microsoft Graph API (OAuth2 client-credentials flow).
  All outbound email goes through `app/core/graph_mailer.py` →
  `send_graph_email()`. Credentials in `.env` (gitignored);
  `.env.example` documents the required keys. See
  `docs/context/email-transport.md` for full details.
- **Inbound mail** (`app/core/inbound_service.py`) still uses IMAP.
  Migrating inbound to Graph is separate future work — do NOT touch
  `inbound_service.py` for outbound email changes.
- **Diagnostics:** `GET /admin/graph/health` verifies Graph credentials;
  `POST /admin/graph/test-email?to_address=...` sends a test.
- **Daily summary (6 PM):** Technical delivery snapshot, cross-project.
  Shows Workshops Scheduled, Workshops Completed, Open Follow-ups,
  Overdue Follow-ups. Function: `generate_and_send_daily_summary()`.
- **Daily metric snapshot (00:15):** Captures yesterday's per-project
  aggregates into `daily_metric_snapshots` for landing-page sparklines.
  Function: `capture_daily_snapshot()` in `project_health.py`.
- **Follow-up nudges (9:30 AM Mon-Fri):** Per-owner grouped reminders

  from `FollowUpItem` table. ONLY processes manual follow-ups
  (source_mom_entry_id IS NULL). Function: `send_followup_nudges()`.
- **MoM-pointer nudges (9:35 AM Mon-Fri):** Per-touchpoint grouped reminders
  for MoM-SPAWNED follow-ups (source_mom_entry_id IS NOT NULL). Threaded
  onto the original MoM email via In-Reply-To/References headers anchored
  on the earliest MOM_SENT log for that touchpoint.
  Function: `send_mom_pointer_nudges()`.
- **Workshop invites (manual trigger):** Project-scoped. The 'Send Workshop
  Invites' button sends emails ONLY for the current project's touchpoints
  scheduled for tomorrow with `tech_status` not in (Completed, Document Review,
  Pending Document). Reschedule detection uses `WORKSHOP_INVITE_SENT` action
  log entries to track prior sends per touchpoint. Same-date re-triggers are
  skipped; status="Rescheduled" triggers a resend with a yellow body banner.
  Threading: subject is intentionally date-free (`Workshop Invite – {dept}`)
  so Gmail groups fresh + rescheduled into one conversation. In-Reply-To and
  References headers are rebuilt from the full chain of prior MSG_IDs stored
  in action logs. Function: `send_workshop_invites(project_id)`.
- **Legacy `generate_and_send_follow_ups`:** Removed (was filtering on
  `idr_status="Pending"` which is dead after single-stage workflow).
- Test endpoint: `/test-followup-nudges` (the old `/test-follow-ups` was
  removed alongside its function).

### Email Subject Convention

All outbound SDGNext emails (except global daily summary and the automated
cross-project MoM) use the format:

    {project_name} || {email-specific-subject}

Examples:
- "BOM || \U0001f4c5 Workshop Invite \u2013 CBS"
- "BOM || MoM: Email Gateway with Gupshup"
- "BOM || Follow-Up: Open Action Items [Rahul]"

Rationale: bank teams work across multiple SDGNext projects; the project
prefix makes inbox triage instant.

Threading: subject is stable per (project, dept) or (project, touchpoint).
Renaming a project mid-thread breaks Gmail threading \u2014 not currently
supported. The stable_part after "||" is unchanged from the pre-prefix
format (byte-identical) to preserve future threading consistency.

Excluded emails (no prefix):
- `\U0001f4ca SDGNext Daily Summary - {date}` \u2014 spans all projects
- `\U0001f4d1 Automated Project MOM - {date}` \u2014 spans all projects

### CRM Integration (Oracle)

Four Oracle tables are populated sequentially from the touchpoint
detail page:

1. **MASHUPCONNECTION** — via Save on API's Connection modal
2. **MASHUPWSCONNECTION** — via Save on API's Connection modal
3. **MASHUPDATASOURCE** — via Finish Configuration on EDS modal
4. **MASHUPDATASOURCEFIELD** — via Finish Configuration (one row
   per output parameter, child of MASHUPDATASOURCE)

IDs stored in PostgreSQL `technical_details` JSON:
- `crmConnectionId`: generated from MashupIdList ITEMID=1
- `crmDatasourceId`: generated from MashupIdList ITEMID=2
- FIELDID: generated from MashupIdList ITEMID=3 (per-field, not stored
  in PostgreSQL since multiple fields exist per touchpoint)

All inserts are idempotent per touchpoint (DELETE + re-INSERT with same ID
on subsequent pushes). Shared connections: touchpoints with the same
`uatUrl` reuse the same CONNECTIONID (checked via `_find_shared_connection_id`).

Endpoints (in `app/api/routes/crm.py`):
- `POST /api/crm/mashup/insert/{tp_id}` — MASHUPCONNECTION
- `POST /api/crm/mashupws/insert/{tp_id}` — MASHUPWSCONNECTION
- `POST /api/crm/datasource/insert/{tp_id}` — MASHUPDATASOURCE + MASHUPDATASOURCEFIELD

### Mock Services

A developer utility for stubbing bank APIs during integration testing.
Mocks are GLOBAL (not project-scoped) and served at `/mock-api/{method_name}`
via the catch-all endpoint in `app/api/routes/mocks.py`.

- **Uniqueness** enforced on `(method_name, http_method)` at both application
  and DB layers (`UniqueConstraint` + `IntegrityError` catch).
- **Triggered from** the touchpoint detail page when workshop status is
  "Completed" — see the "Generate Mock" button beside "Generate WUD".
- **Pre-fill source:** `techDetails.apiName` → slug, `techDetails.apiMethod`
  → HTTP method, `techDetails.apiRes` → payload.
- **Model:** `MockService` in `app/models/domain.py`.
- **Endpoints:** `POST /api/mocks/create`, `GET /api/mocks/list`,
  `ANY /mock-api/{method_name:path}` (catch-all serve).
- **No fallback:** If exact `(method_name, http_method)` doesn't match,
  returns 404. A GET-only mock will NOT accidentally serve a POST request.
- **Security note:** The `/mock-api` endpoint should NOT be exposed publicly
  in production. It has no authentication.
