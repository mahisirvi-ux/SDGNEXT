from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func as sqla_func, case
from pydantic import BaseModel
from datetime import date, timedelta, datetime
from app.core.database import get_db
from app.models.domain import (
    Project, IntegrationTouchpoint, IDRTechnical, IDRActionLog,
    FollowUpItem, MomSession, DepartmentMaster, TeamMaster,
    DailyMetricSnapshot
)
from app.services.project_health import get_project_summaries, get_landing_summary

router = APIRouter()


class ProjectCreate(BaseModel):
    project_name: str

class CRMConfigUpdate(BaseModel):
    """Per-project CRM database configuration.

    Oracle example:
        {"host": "192.168.0.16", "port": 1521, "service": "CRMNEXTLOCAL",
         "user": "SIB_DEV_BUSINESSNEXT_AUG25", "password": "...", "schema": "SIB_DEV_BUSINESSNEXT_AUG25"}

    SQL Server example:
        {"host": "192.168.0.20", "port": 1433, "database": "RBL_PHASE4_DEVELOPMENT",
         "user": "sa", "password": "...", "schema": "dbo"}

    PostgreSQL example:
        {"host": "192.168.0.30", "port": 5432, "database": "crmnext_db",
         "user": "crm_user", "password": "...", "schema": "public"}
    """
    crm_db_type: str                # "oracle" | "sqlserver" | "postgres"
    crm_db_config: dict = {}        # credentials dict (schema-specific keys above)
@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    """Fetch all projects with enriched KPI data."""
    return get_project_summaries(db)


@router.get("/api/landing/summary")
def landing_summary(db: Session = Depends(get_db)):
    """Cross-project KPIs for the landing page."""
    return get_landing_summary(db)


@router.post("/projects")
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project container."""
    existing = db.query(Project).filter(Project.project_name == project.project_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project already exists")

    new_project = Project(project_name=project.project_name)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return {
        "id": new_project.id,
        "project_name": new_project.project_name,
        "created_at": new_project.created_at.isoformat() if new_project.created_at else None
    }


# ============================================================
# ANALYTICAL LANDING: SPARKLINES
# ============================================================

def _compute_current_metrics(db: Session, project_id: int, today: date) -> dict:
    """Compute today's live metric values for a single project."""
    tp_ids_q = db.query(IntegrationTouchpoint.id).filter(
        IntegrationTouchpoint.project_id == project_id
    ).subquery()

    open_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.touchpoint_id.in_(tp_ids_q),
        FollowUpItem.status == "OPEN"
    ).scalar() or 0

    overdue_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.touchpoint_id.in_(tp_ids_q),
        FollowUpItem.status == "OPEN",
        FollowUpItem.due_date.isnot(None),
        FollowUpItem.due_date < today
    ).scalar() or 0

    active_tps = db.query(sqla_func.count(IDRTechnical.id)).join(
        IntegrationTouchpoint,
        IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.tech_status.notin_(["Completed", "Cancelled"])
    ).scalar() or 0

    completed_ws = db.query(sqla_func.count(IDRTechnical.id)).join(
        IntegrationTouchpoint,
        IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.tech_status == "Completed"
    ).scalar() or 0

    return {
        "open_followups": open_fus,
        "overdue_followups": overdue_fus,
        "touchpoints_active": active_tps,
        "workshops_completed": completed_ws
    }


def _compute_trend(values: list) -> str:
    """Compare avg of last 3 values vs first 3. Returns 'up'/'down'/'flat'."""
    if len(values) < 6:
        return "flat"
    first3 = sum(values[:3]) / 3.0
    last3 = sum(values[-3:]) / 3.0
    val_range = max(values) - min(values)
    if val_range == 0:
        return "flat"
    diff_pct = abs(last3 - first3) / val_range
    if diff_pct < 0.10:
        return "flat"
    return "up" if last3 > first3 else "down"


@router.get("/api/landing/project-sparklines")
def get_project_sparklines(db: Session = Depends(get_db)):
    """Returns each project's last-14-day metrics for sparkline rendering."""
    today = date.today()
    cutoff = today - timedelta(days=14)

    # Batched snapshot query
    snaps = db.query(DailyMetricSnapshot).filter(
        DailyMetricSnapshot.snapshot_date >= cutoff
    ).order_by(
        DailyMetricSnapshot.project_id,
        DailyMetricSnapshot.snapshot_date
    ).all()

    # Group by project_id
    snap_map = {}  # project_id -> list of snapshot rows (date-ordered)
    for s in snaps:
        snap_map.setdefault(s.project_id, []).append(s)

    # All projects
    projects = db.query(
        Project.id, Project.project_name,
        sqla_func.count(IntegrationTouchpoint.id).label("tp_count")
    ).outerjoin(
        IntegrationTouchpoint, IntegrationTouchpoint.project_id == Project.id
    ).group_by(Project.id).all()

    result = []
    for proj_id, proj_name, tp_count in projects:
        current = _compute_current_metrics(db, proj_id, today)
        project_snaps = snap_map.get(proj_id, [])
        data_points = len(project_snaps)

        # Build sparkline arrays
        metrics = ["open_followups", "overdue_followups",
                   "touchpoints_active", "workshops_completed"]
        sparklines = {}
        trends = {}

        for m in metrics:
            if data_points == 0:
                sparklines[m] = [current[m]]
            else:
                sparklines[m] = [getattr(s, m) for s in project_snaps]
            trends[m] = _compute_trend(sparklines[m])

        result.append({
            "id": proj_id,
            "project_name": proj_name,
            "touchpoint_count": tp_count or 0,
            "current": current,
            "sparklines": sparklines,
            "data_points": data_points,
            "trend": trends
        })

    return {"window_days": 14, "projects": result}


# ============================================================
# ANALYTICAL LANDING: DRILLDOWN
# ============================================================

def _relative_time(ts: datetime) -> str:
    """Human-readable relative time from a timestamp."""
    if not ts:
        return ""
    now = datetime.now()
    diff = now - ts
    minutes = int(diff.total_seconds() / 60)
    hours = int(diff.total_seconds() / 3600)
    days = diff.days

    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if hours < 24:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return ts.strftime("%b %d")


@router.get("/api/landing/projects/{project_id}/drilldown")
def get_project_drilldown(project_id: int, db: Session = Depends(get_db)):
    """Returns drilldown details for a single project (lazy-loaded on expand)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Admin
    tp_count = db.query(sqla_func.count(IntegrationTouchpoint.id)).filter(
        IntegrationTouchpoint.project_id == project_id
    ).scalar() or 0

    dept_count = db.query(sqla_func.count(DepartmentMaster.dept_id)).filter(
        DepartmentMaster.project_id == project_id
    ).scalar() or 0

    team_count = db.query(sqla_func.count(TeamMaster.id)).join(
        DepartmentMaster, TeamMaster.dept_id == DepartmentMaster.dept_id
    ).filter(
        DepartmentMaster.project_id == project_id
    ).scalar() or 0

    # Health
    tp_ids_q = db.query(IntegrationTouchpoint.id).filter(
        IntegrationTouchpoint.project_id == project_id
    ).subquery()

    open_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.touchpoint_id.in_(tp_ids_q),
        FollowUpItem.status == "OPEN"
    ).scalar() or 0

    overdue_fus = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.touchpoint_id.in_(tp_ids_q),
        FollowUpItem.status == "OPEN",
        FollowUpItem.due_date.isnot(None),
        FollowUpItem.due_date < today
    ).scalar() or 0

    due_this_week = db.query(sqla_func.count(FollowUpItem.id)).filter(
        FollowUpItem.touchpoint_id.in_(tp_ids_q),
        FollowUpItem.status == "OPEN",
        FollowUpItem.due_date >= today,
        FollowUpItem.due_date <= week_end
    ).scalar() or 0

    last_mom = db.query(MomSession).join(
        IntegrationTouchpoint, MomSession.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        MomSession.status == "SENT"
    ).order_by(MomSession.sent_at.desc()).first()

    last_mom_date = None
    last_mom_age = None
    if last_mom and last_mom.sent_at:
        last_mom_date = last_mom.sent_at.strftime("%Y-%m-%d")
        last_mom_age = (today - last_mom.sent_at.date()).days if hasattr(last_mom.sent_at, 'date') else None

    workshops_this_week = db.query(sqla_func.count(IDRTechnical.id)).join(
        IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.start_date >= week_start,
        IDRTechnical.start_date <= week_end
    ).scalar() or 0

    completed_total = db.query(sqla_func.count(IDRTechnical.id)).join(
        IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.tech_status == "Completed"
    ).scalar() or 0

    active_total = db.query(sqla_func.count(IDRTechnical.id)).join(
        IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id,
        IDRTechnical.tech_status.notin_(["Completed", "Cancelled"])
    ).scalar() or 0

    # Recent activity (last 5)
    recent_logs = db.query(IDRActionLog, IntegrationTouchpoint).join(
        IntegrationTouchpoint, IDRActionLog.touchpoint_id == IntegrationTouchpoint.id
    ).filter(
        IntegrationTouchpoint.project_id == project_id
    ).order_by(IDRActionLog.created_at.desc()).limit(5).all()

    recent_activity = []
    for log, tp in recent_logs:
        recent_activity.append({
            "action_type": log.action_type or "Unknown",
            "action_by": log.action_by or "System",
            "comment": log.comment or "",
            "touchpoint_name": tp.name or "Unknown",
            "touchpoint_id": tp.id,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
            "relative_time": _relative_time(log.created_at)
        })

    return {
        "admin": {
            "id": project.id,
            "project_name": project.project_name,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "touchpoint_count": tp_count,
            "department_count": dept_count,
            "team_member_count": team_count
        },
        "health": {
            "open_followups": open_fus,
            "overdue_followups": overdue_fus,
            "due_this_week": due_this_week,
            "last_mom_date": last_mom_date,
            "last_mom_age_days": last_mom_age,
            "workshops_this_week": workshops_this_week,
            "workshops_completed_total": completed_total,
            "touchpoints_active": active_total,
            "touchpoints_completed": completed_total
        },
        "recent_activity": recent_activity
    }
@router.put("/api/projects/{project_id}/crm-config")
def update_project_crm_config(
    project_id: int,
    payload: CRMConfigUpdate,
    db: Session = Depends(get_db),
):
    """Save per-project CRM database type and credentials.

    Oracle projects already using ORACLE_* env vars can call this to
    explicitly configure their credentials, or leave crm_db_config empty
    to keep using the env-var fallback.

    Triggers a connectivity test before saving — returns 400 if the
    supplied credentials cannot open a connection.
    """
    from app.core.crm_db import get_crm_connection, get_crm_schema

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db_type = payload.crm_db_type.strip().lower()
    if db_type not in ("oracle", "sqlserver", "postgres"):
        raise HTTPException(
            status_code=400,
            detail="crm_db_type must be one of: oracle, sqlserver, postgres",
        )

    # Connectivity test before persisting
    test_conn = None
    try:
        test_conn = get_crm_connection(db_type, payload.crm_db_config)
        test_cursor = test_conn.cursor()
        # Lightweight probe: just verify the schema/table exists
        schema = get_crm_schema(db_type, payload.crm_db_config)
        probe_sql = f"SELECT 1 FROM {schema}.MASHUPCONNECTION WHERE 1=0"
        test_cursor.execute(probe_sql)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"CRM DB connectivity test failed: {e}",
        )
    finally:
        if test_conn:
            try:
                test_conn.close()
            except Exception:
                pass

    # Persist
    project.crm_db_type = db_type
    project.crm_db_config = payload.crm_db_config
    db.commit()
    db.refresh(project)

    return {
        "success": True,
        "project_id": project_id,
        "project_name": project.project_name,
        "crm_db_type": project.crm_db_type,
        "crm_db_config_keys": list(payload.crm_db_config.keys()),
        "message": f"CRM DB config saved for project '{project.project_name}' ({db_type.upper()}).",
    }


@router.get("/api/projects/{project_id}/crm-config")
def get_project_crm_config(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Return current CRM DB config for a project (password masked)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    config = dict(project.crm_db_config or {})
    # Mask password in response
    if "password" in config:
        config["password"] = "***"

    return {
        "project_id": project_id,
        "project_name": project.project_name,
        "crm_db_type": project.crm_db_type or "oracle",
        "crm_db_config": config,
        "using_env_fallback": (
            (project.crm_db_type or "oracle") == "oracle"
            and not (project.crm_db_config or {}).get("host")
        ),
    }