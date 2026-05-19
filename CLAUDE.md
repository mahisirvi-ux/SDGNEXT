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

### File Organization

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app + Phase 2 endpoints |
| `app/services/file_parser.py` | CSV upload processing |
| `app/services/project_health.py` | Landing page KPIs |
| `app/services/identity_validator.py` | Name resolution |
| `js/app-dashboard.js` | Project view init + switchPhase logic |
| `js/phase2_technical.js` | Workshop Board table + inline editing |
| `js/landing.js` | Landing page rendering |

### Action Log Conventions

- `action_by` is a free-text label (currently `"User"` placeholder)
- `action_type` values: `DISCUSSION`, `POINTER`, `STATUS_CHANGE`,


  `MOM_SENT`, `MOM_NUDGE_SENT`, `FOLLOWUP_CLOSED`, `FOLLOWUP_REOPENED`,
  `Manual Update`, `WORKSHOP_INVITE_SENT`
  - Don't invent new action_types without documenting them

### Email Workflows

- **Daily summary (6 PM):** Technical delivery snapshot, cross-project.
  Shows Workshops Scheduled, Workshops Completed, Open Follow-ups,
  Overdue Follow-ups. Function: `generate_and_send_daily_summary()`.
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
