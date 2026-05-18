# Landing Page & Routing

## Routing Map

| URL | Serves | Purpose |
|-----|--------|---------|
| `/` | `landing.html` | Cross-project landing page: KPIs + project list + create |
| `/project?id=X` | `index.html` | Project-scoped view (Phase 1/2/3 boards) |
| `/details?id=Y` | `details.html` | Touchpoint detail page (unchanged) |
| `/api/*` | FastAPI JSON | All API endpoints |
| `/css/*`, `/js/*` | Static files | Frontend assets |

## Cross-Project KPIs (`GET /api/landing/summary`)

### Row 1 — Operational

| KPI | Derivation |
|-----|-----------|
| Open Follow-Ups | `COUNT(FollowUpItem) WHERE status = 'OPEN'` across all projects |
| Overdue | `COUNT(FollowUpItem) WHERE status = 'OPEN' AND due_date < today` |
| Due This Week | `COUNT(FollowUpItem) WHERE status = 'OPEN' AND due_date BETWEEN today AND end_of_week` |
| Closed (7 Days) | `COUNT(FollowUpItem) WHERE status = 'CLOSED' AND closed_at >= 7_days_ago` |
| MoM Drafts | `COUNT(MomSession) WHERE status IN ('DRAFT', 'GENERATED')` |

### Row 2 — Administrative

| KPI | Derivation |
|-----|-----------|
| Total Projects | `COUNT(Project)` |
| Added This Month | `COUNT(Project) WHERE created_at >= first_day_of_current_month AND created_at IS NOT NULL` |
| Touchpoints | `COUNT(IntegrationTouchpoint)` across all projects |
| Phase 1 Done | `COUNT(IDRFunctional) WHERE idr_status ILIKE '%Signed-Off%'` |
| Phase 2 Done | `COUNT(IDRTechnical) WHERE tech_status = 'Completed'` |

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
