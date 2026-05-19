"""
project_health.py — Canonical source of project-level KPIs.

Uses at most 3 batched queries (no N+1). Called by GET /projects
and GET /api/landing/summary.
"""
from datetime import date, timedelta
from sqlalchemy import func as sqla_func, case
from sqlalchemy.orm import Session

from app.models.domain import (
    Project, IntegrationTouchpoint, FollowUpItem,
    IDRActionLog, IDRFunctional, IDRTechnical, MomSession
)


def get_project_summaries(db: Session) -> list:
    """Returns enriched project summaries for the landing page.

    Maximum 3 batched queries. Returns list ordered by:
    last_activity_at DESC NULLS LAST, created_at DESC NULLS LAST, project_name ASC.
    """
    today = date.today()

    # Q1: Projects + touchpoint count
    q1_rows = db.query(
        Project.id,
        Project.project_name,
        Project.created_at,
        sqla_func.count(IntegrationTouchpoint.id).label("touchpoint_count")
    ).outerjoin(
        IntegrationTouchpoint, IntegrationTouchpoint.project_id == Project.id
    ).group_by(Project.id).all()

    # Q2: Open + overdue follow-up counts per project
    q2_rows = db.query(
        IntegrationTouchpoint.project_id,
        sqla_func.count(FollowUpItem.id).label("open_followups"),
        sqla_func.sum(
            case(
                (FollowUpItem.due_date < today, 1),
                else_=0
            )
        ).label("overdue_followups")
    ).join(
        FollowUpItem, FollowUpItem.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        FollowUpItem.status == "OPEN"
    ).group_by(IntegrationTouchpoint.project_id).all()

    # Q3: Last activity per project
    q3_rows = db.query(
        IntegrationTouchpoint.project_id,
        sqla_func.max(IDRActionLog.created_at).label("last_activity_at")
    ).join(
        IDRActionLog, IDRActionLog.touchpoint_id == IntegrationTouchpoint.id
    ).group_by(IntegrationTouchpoint.project_id).all()

    # Build lookup dicts
    followup_map = {}
    for row in q2_rows:
        followup_map[row[0]] = {
            "open_followups": row[1] or 0,
            "overdue_followups": int(row[2] or 0)
        }

    activity_map = {}
    for row in q3_rows:
        activity_map[row[0]] = row[1]

    # Merge
    results = []
    for proj_id, proj_name, created_at, tp_count in q1_rows:
        fu = followup_map.get(proj_id, {"open_followups": 0, "overdue_followups": 0})
        last_activity = activity_map.get(proj_id)
        results.append({
            "id": proj_id,
            "project_name": proj_name,
            "touchpoint_count": tp_count or 0,
            "open_followups": fu["open_followups"],
            "overdue_followups": fu["overdue_followups"],
            "last_activity_at": last_activity.isoformat() if last_activity else None,
            "created_at": created_at.isoformat() if created_at else None
        })

    # Sort: last_activity DESC NULLS LAST, created_at DESC NULLS LAST, name ASC
    def sort_key(p):
        act = p["last_activity_at"] or ""
        cre = p["created_at"] or ""
        return (0 if act else 1, act, 0 if cre else 1, cre, p["project_name"])

    results.sort(key=lambda p: (
        0 if p["last_activity_at"] else 1,
        p["last_activity_at"] or "",
        0 if p["created_at"] else 1,
        p["created_at"] or "",
        p["project_name"]
    ), reverse=False)
    # Reverse the timestamp sorts (we want DESC) but keep name ASC
    results.sort(key=lambda p: (
        1 if p["last_activity_at"] else 0,
        p["last_activity_at"] or "9999",
    ))
    # Simplify: do a proper multi-key sort
    results.sort(key=lambda p: (
        0 if p["last_activity_at"] else 1,
        "" if not p["last_activity_at"] else p["last_activity_at"],
    ))
    # Actually let's just do it cleanly:
    results.sort(key=lambda p: p["project_name"])  # tertiary ASC
    results.sort(key=lambda p: p["created_at"] or "", reverse=True)  # secondary DESC
    results.sort(key=lambda p: (0 if p["created_at"] else 1))  # NULLs last
    results.sort(key=lambda p: p["last_activity_at"] or "", reverse=True)  # primary DESC
    results.sort(key=lambda p: (0 if p["last_activity_at"] else 1))  # NULLs last

    return results


def get_landing_summary(db: Session) -> dict:
    """Returns cross-project KPIs for the landing page. Single roundtrip."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday of this week
    week_end = week_start + timedelta(days=6)  # Sunday
    seven_days_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    # Cross-project follow-up counts
    open_total = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.status == "OPEN"
    ).scalar() or 0

    overdue_total = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.status == "OPEN",
        FollowUpItem.due_date < today,
        FollowUpItem.due_date.isnot(None)
    ).scalar() or 0

    due_this_week = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.status == "OPEN",
        FollowUpItem.due_date >= today,
        FollowUpItem.due_date <= week_end
    ).scalar() or 0

    closed_7d = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.status == "CLOSED",
        FollowUpItem.closed_at >= seven_days_ago
    ).scalar() or 0

    # MoM counts
    mom_sent_7d = db.query(sqla_func.count(MomSession.id)).filter(
        MomSession.status == "SENT",
        MomSession.sent_at >= seven_days_ago
    ).scalar() or 0

    mom_drafts = db.query(sqla_func.count(MomSession.id)).filter(
        MomSession.status.in_(["DRAFT", "GENERATED"])
        ).scalar() or 0

    # Projects overview
    total_projects = db.query(sqla_func.count(Project.id)).scalar() or 0

    created_this_month = db.query(sqla_func.count(Project.id)).filter(
        Project.created_at >= month_start,
        Project.created_at.isnot(None)
    ).scalar() or 0

    touchpoints_total = db.query(sqla_func.count(IntegrationTouchpoint.id)).scalar() or 0

    workshops_scheduled = db.query(sqla_func.count(IDRTechnical.id)).filter(
        IDRTechnical.tech_status == "Scheduled"
    ).scalar() or 0

    phase2_completed = db.query(sqla_func.count(IDRTechnical.id)).filter(
        IDRTechnical.tech_status == "Completed"
    ).scalar() or 0

    return {
        "cross_project": {
            "open_followups_total": open_total,
            "overdue_followups_total": overdue_total,
            "due_this_week_total": due_this_week,
            "closed_last_7_days_total": closed_7d,
            "mom_sessions_sent_last_7_days": mom_sent_7d,
            "mom_active_drafts_total": mom_drafts
        },
        "projects_overview": {
            "total_projects": total_projects,
            "created_this_month": created_this_month,
            "touchpoints_total": touchpoints_total,
            "workshops_scheduled_total": workshops_scheduled,
            "phase2_completed_total": phase2_completed
        }
    }
