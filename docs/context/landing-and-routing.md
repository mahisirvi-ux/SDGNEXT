# Landing Page & Routing

## Routing Map

| URL | Serves | Purpose |
|-----|--------|---------|
| `/` | `landing.html` | Cross-project landing page: KPIs + project list + create |
| `/project?id=X` | `index.html` | Project-scoped view (Workshop Board / Phase 3) |
| `/details?id=Y` | `details.html` | Touchpoint detail page (unchanged) |
| `/api/*` | FastAPI JSON | All API endpoints |
| `/css/*`, `/js/*` | Static files | Frontend assets |

## Landing Page — Analytical Sparkline View

The landing page shows a **project-centric analytical view**. Each project
renders as a card with 14-day sparkline trends for four key metrics:

- `open_followups`
- `overdue_followups`
- `touchpoints_active` (tech_status NOT IN Completed/Cancelled)
- `workshops_completed` (tech_status = Completed)

Sparklines read from `daily_metric_snapshots`, populated by a midnight cron
(00:15). "Current" values (the large numbers) are computed live at request
time via `_compute_current_metrics()` in `app/api/routes/projects.py`.

Clicking a card **expands an inline drilldown** (below the grid, not a modal)
with three sub-sections: Administrative, Health Snapshot, Recent Activity.
Only one project can be expanded at a time.

The "Open Project →" button inside the drilldown navigates to `/project?id=X`.

### Endpoints

| Endpoint | Purpose |
|----------|--------|
| `GET /api/landing/project-sparklines` | All projects + 14-day arrays + trends |
| `GET /api/landing/projects/{id}/drilldown` | Admin, health, last 5 activity entries |
| `GET /api/landing/summary` | **Legacy** — cross-project KPIs (still served, no longer used by landing.js) |
| `GET /projects` | **Legacy** — enriched project list (still used by index.html) |

## Canonical Source

`app/services/project_health.py` is the single source of truth for:
- Per-project summaries (touchpoint counts, follow-up counts, last activity)
- Cross-project KPIs

Do NOT reinvent aggregation logic elsewhere. Any new dashboard or report
should call these functions.

## Design Decisions

- **Active/Inactive status is deliberately deferred.** All projects render
  equally on the landing page. Do not introduce project status without an
  explicit decision.
- **Routing uses numeric `id` parameters**, never `project_name` in URLs.
  This avoids encoding issues with special characters.
- **Project.created_at** is nullable. Legacy rows have NULL. The UI omits
  "Created:" for these projects. `created_this_month` excludes NULLs.
- **No pagination** on the project list in this version. If growth exceeds
  ~500 projects, pagination should be added as a follow-up.

## Single-Stage Workflow

As of 2025-01, Phase 1 (Functional Discovery) is no longer a visible UI
surface. Uploaded CSV data is immediately available on the Workshop Board.
The `IDRFunctional` table is retained as the metadata store for touchpoints
— see `identity-system.md` for which fields it provides (module, owners,
business_flow, source/target systems, business_department).

Key facts:

- **"Phase 2" and "Workshop Board" are aliases.** "Workshop Board" is the
  user-facing UI label; "Phase 2" is the backend identifier (API paths,
  table names, JS variable names). Do NOT rename the API path
  `/api/phase2/dashboard` — it is preserved for backward compatibility.
- The sign-off gate (`IDRFunctional.idr_status ILIKE '%Signed-Off%'`) has
  been removed from the Workshop Board query. All touchpoints with an
  `IDRFunctional` row appear regardless of `idr_status` value.
- Old projects with `idr_status="In-Progress"` rows see those rows on the
  Workshop Board immediately — no migration script is needed.
- The legacy sign-off endpoint (`POST /tasks/{id}/log` with
  `new_status="Signed-Off"`) is preserved but unreachable from the UI.
  Do not reintroduce sign-off filters.
- The legacy email function `generate_and_send_follow_ups()` was removed.
  Daily follow-up reminders to bank contacts now flow exclusively through
  `send_followup_nudges()` (FollowUpItem-based, runs 9:30 AM Mon-Fri).
- The daily executive summary email (6 PM) was rebuilt to reflect
  technical-delivery metrics (Workshops Scheduled, Workshops Completed,
  Open Follow-ups, Overdue Follow-ups) instead of Phase 1 counters.

## Navigation Conventions

- **SDGNEXT wordmark** (top bar) is the universal "home" link on all pages.
  Click it from anywhere → navigates to `/` (landing page).
- **Project dropdown removed.** The project view top bar shows the project
  name as read-only text (pill-style `<span>`). Project switching happens
  exclusively through the landing page.
- **Hidden input shim** (`<input type="hidden" id="projectSelector">`):
  Maintains `.value` compatibility for 20+ existing JS call sites that read
  `projectSelector.value` for uploads, exports, and API calls. Future
  contributors should NOT remove this without refactoring all call sites.
- **details.html dynamic hrefs:** The back-arrow, close-icon, and phase nav
  links default to `/project` (placeholder). Once the touchpoint API response
  provides `project_id`, JS updates them to `/project?id={project_id}`. If
  the API hasn't responded yet, the placeholder redirects to `/` via the
  existing E1 fallback.

## CSV Upload Schema

Two column mappings in `app/services/file_parser.py`:

### PART1_MAPPING → IDRFunctional fields (touchpoint metadata)

| CSV Header | DB Column | Notes |
|-----------|-----------|-------|
| Integration Touch Point | (touchpoint name) | Required — rows without this are skipped |
| Module / Journey | module | |
| Module Owner (Functional) | module_owner_functional | Validated against team_master |
| Technical Owner (CRM) | technical_owner | Validated against team_master |
| Business Flow / Objective | business_flow | |
| Integration Direction | integration_direction | |
| Source System | source_system | |
| Target System | target_system | |
| Trigger Mechanism | trigger_mechanism | |
| UX Expectation | ux_expectation | |
| Business Fallback | business_fallback | |
| IDR Remarks / Notes | idr_remarks | |
| IDR Status | idr_status | Defaults to "Signed-Off" if absent |
| Inputs | inputs | |
| Expected Output | expected_output | |
| Owner | owner | Validated against team_master |
| IDR SignOff Date | idr_signoff_date | |
| Pending With | pending_with | Validated against team_master |
| Open Pointers | open_pointers | |

### PART2_MAPPING → IDRTechnical fields (Workshop Board pre-population)

Added 2025-01. All three columns are **OPTIONAL**.

| CSV Header | DB Column | Format | Notes |
|-----------|-----------|--------|-------|
| Integration Type | integration_type | Text | Normalized to lowercase if matches canonical set (api/database/batch). Unknown values stored as-is with warning. |
| Start Time | start_date | Datetime | ISO or dd/mm/yyyy. Parsed with `dayfirst=True` (Indian convention). |
| End Time | end_date | Datetime | Same format rules as Start Time. |

### Behavior on upload

- **IDRFunctional** row created per PART1_MAPPING.
- **IDRTechnical** row created eagerly with PART2 fields populated if
  columns present. `tech_status` defaults to "Pending Workshop" (model
  default; not settable from CSV).
- **Re-upload destroys all data** attached to existing touchpoints (FK
  CASCADE). This includes IDRTechnical, IDRActionLog, MomSession,
  FollowUpItem, etc.
- Date parsing failures emit a warning and store NULL (upload continues).
- Unknown integration types emit a warning and store the raw value.

### Parking-lot items (NOT in scope)

- "Append" or "upsert by touchpoint name" upload mode (avoids destruction).
- Filter dropdown missing "batch" option (`index.html` line 198).
- Validation that start_date < end_date.
