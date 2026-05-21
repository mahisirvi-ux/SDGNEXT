from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.domain import User, Project, ProjectAssignment, IntegrationTouchpoint, IDRTechnical

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_project_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        projects = db.query(Project).all()
    else:
        assigned_ids = [a[0] for a in db.query(ProjectAssignment.project_id).filter(ProjectAssignment.user_id == user.id).all()]
        projects = db.query(Project).filter(Project.id.in_(assigned_ids)).all() if assigned_ids else []

    result = []
    for project in projects:
        stats = db.query(
            IDRTechnical.tech_status, func.count(IDRTechnical.id)
        ).join(
            IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
        ).filter(
            IntegrationTouchpoint.project_id == project.id
        ).group_by(IDRTechnical.tech_status).all()

        total = sum(count for _, count in stats)
        status_map = {s: c for s, c in stats}
        completed = status_map.get("Completed", 0)
        completion_pct = round((completed / total * 100) if total > 0 else 0)

        result.append({
            "id": project.id,
            "project_name": project.project_name,
            "total_touchpoints": total,
            "completed": completed,
            "in_progress": status_map.get("In Progress", 0),
            "scheduled": status_map.get("Scheduled", 0),
            "pending_workshop": status_map.get("Pending Workshop", 0) + status_map.get("Auto", 0),
            "delayed": status_map.get("Delayed", 0),
            "rescheduled": status_map.get("Rescheduled", 0),
            "completion_pct": completion_pct
        })

    return {"projects": result, "user": {"username": user.username, "role": user.role}}
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.domain import User, Project, ProjectAssignment, IntegrationTouchpoint, IDRTechnical

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_project_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns list of projects assigned to current user with completion stats.
    Admin sees all projects. Manager sees only assigned ones."""

    if user.role == "admin":
        projects = db.query(Project).all()
    else:
        assigned_ids = db.query(ProjectAssignment.project_id).filter(
            ProjectAssignment.user_id == user.id
        ).all()
        assigned_ids = [a[0] for a in assigned_ids]
        projects = db.query(Project).filter(Project.id.in_(assigned_ids)).all() if assigned_ids else []

    result = []
    for project in projects:
        # Get touchpoint counts by tech_status
        stats = db.query(
            IDRTechnical.tech_status,
            func.count(IDRTechnical.id)
        ).join(
            IntegrationTouchpoint, IDRTechnical.touchpoint_id == IntegrationTouchpoint.id
        ).filter(
            IntegrationTouchpoint.project_id == project.id
        ).group_by(IDRTechnical.tech_status).all()

        total = sum(count for _, count in stats)
        status_map = {status: count for status, count in stats}
        completed = status_map.get("Completed", 0)
        completion_pct = round((completed / total * 100) if total > 0 else 0)

        result.append({
            "id": project.id,
            "project_name": project.project_name,
            "total_touchpoints": total,
            "completed": completed,
            "in_progress": status_map.get("In Progress", 0),
            "scheduled": status_map.get("Scheduled", 0),
            "pending_workshop": status_map.get("Pending Workshop", 0) + status_map.get("Auto", 0),
            "delayed": status_map.get("Delayed", 0),
            "rescheduled": status_map.get("Rescheduled", 0),
            "completion_pct": completion_pct
        })

    return {"projects": result, "user": {"username": user.username, "role": user.role}}
