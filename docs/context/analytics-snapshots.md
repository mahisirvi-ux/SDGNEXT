# Analytics Snapshots — SDGNEXT

## Purpose

Daily aggregated metrics per project, captured nightly, used to render
sparkline trends on the landing page.

## Schema: daily_metric_snapshots

One row per (project_id, snapshot_date). Tracks:

- `open_followups` — count of FollowUpItem with status='OPEN'
- `overdue_followups` — open items where due_date < snapshot_date
- `touchpoints_active` — IDRTechnical rows with tech_status NOT IN
  ('Completed', 'Cancelled')
- `workshops_completed` — IDRTechnical rows with tech_status = 'Completed'

UniqueConstraint on (project_id, snapshot_date) ensures idempotent upsert.
CASCADE on project_id so deleting a project removes its snapshots.

## Cron

Runs at **00:15 daily** via APScheduler. Captures yesterday's end-of-day
counts. Idempotent: re-running the same date updates the existing row.

Wrapper function: `_run_daily_snapshot_job()` in `app/main.py`.
Core logic: `capture_daily_snapshot()` in `app/services/project_health.py`.

## First-day deployment

Run `POST /admin/snapshot/backfill-today` to populate the first snapshot.
Without this, cards show empty sparklines (single dot) until midnight.

```bash
curl -X POST http://localhost:8000/admin/snapshot/backfill-today
```

## Window

Landing page reads the last **14 days**. Older snapshots are retained
(no pruning yet) in case the window expands.

## Trend computation

Compare avg(last 3 values) vs avg(first 3 values):

- difference > 10% of range → 'up' or 'down'
- otherwise → 'flat'
- fewer than 6 data points → always 'flat'

Trend arrow semantics depend on the metric:

- For "overdue": down = good (emerald), up = bad (amber)
- For others: neutral slate (informational, not judgmental)

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/landing/project-sparklines` | All projects with 14-day sparkline arrays |
| `GET /api/landing/projects/{id}/drilldown` | Admin, health, recent activity for one project |
| `POST /admin/snapshot/capture?target_date=YYYY-MM-DD` | Manual snapshot for a specific date |
| `POST /admin/snapshot/backfill-today` | Snapshot for today (deployment seed) |

## Future considerations

- Pruning snapshots older than 90 days
- Per-touchpoint sparklines (currently project-level only)
- User-configurable window length
- Time-window selector on the landing page ("Last 7 / 14 / 30 days")
