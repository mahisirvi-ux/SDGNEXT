import io
import csv
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from app.core.database import get_db
from app.models.domain import (
    Project, IntegrationTouchpoint, IDRActionLog, IDRFunctional,
    TeamMaster, DepartmentMaster,
)
from app.services.identity_validator import (
    list_active_members_with_dept,
    resolve_pending_with,
    enrich_owner_label,
)

router = APIRouter()


class ActionLogCreate(BaseModel):
    action_type: str
    action_by: str
    comment: str
    new_status: str = None
    pending_with: str = None  # Accepts empty string to clear the value
    open_pointers: str = None


# ============================================================
# Dropdown LOV — project-scoped identity model
# ============================================================
@router.get("/pending-options/{project_name}")
def get_pending_options_by_project(project_name: str, db: Session = Depends(get_db)):
    """Returns active team members for the Pending With dropdown, scoped to a project."""
    project = db.query(Project).filter(Project.project_name == project_name).first()
    project_id = project.id if project else None
    return list_active_members_with_dept(db, project_id=project_id)


@router.get("/pending-options")
def get_pending_options(db: Session = Depends(get_db)):
    """Fallback: Returns all active team members (no project filter).
    Kept for backward compatibility with older frontend code.
    """
    return list_active_members_with_dept(db, project_id=None)


# ============================================================
# Phase 1 task list — enrich owner labels with department context
# ============================================================
@router.get("/tasks/{project_name}")
def get_tasks_by_project(project_name: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        return []

    touchpoints = (
        db.query(IntegrationTouchpoint)
        .filter(IntegrationTouchpoint.project_id == project.id)
        .all()
        )

    # Per-request cache for owner-label enrichment, so a project with 100 rows
    # that all share 5 owners only hits team_master 5 times.
    enrich_cache = {}

    result = []
    for tp in touchpoints:
        func = tp.functional_discovery
        remarks_timeline = []
        pointers_timeline = []

        for log in tp.action_logs:
            created_str = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else ""

            if log.comment and len(remarks_timeline) < 3:
                remarks_timeline.append({
                    "action_by": log.action_by,
                    "comment": log.comment,
                    "created_at": created_str,
                })

            if log.open_pointer_history and len(pointers_timeline) < 3:
                pointers_timeline.append({
                    "action_by": log.action_by,
                    "comment": log.open_pointer_history,
                    "created_at": created_str,
                })

        # Enrich the display labels for the UI (raw values still go in too).
        owner_raw = func.owner if func else None
        mod_owner_raw = func.module_owner_functional if func else None
        tech_owner_raw = func.technical_owner if func else None
        pending_raw = func.pending_with if func else None

        result.append({
            "id": tp.id,
            "integration_touch_point": tp.name,
            "module": func.module if func else None,
            # Raw values (legacy contract — what existing FE code reads)
            "module_owner": mod_owner_raw,
            "technical_owner": tech_owner_raw,
            "owner": owner_raw,
            "pending_with": pending_raw,
            # Enriched 'with department' displays for the UI (project-scoped)
            "owner_display": enrich_owner_label(db, owner_raw, project_id=project.id, _cache=enrich_cache),
            "module_owner_display": enrich_owner_label(db, mod_owner_raw, project_id=project.id, _cache=enrich_cache),
            "technical_owner_display": enrich_owner_label(db, tech_owner_raw, project_id=project.id, _cache=enrich_cache),
            "pending_with_display": enrich_owner_label(db, pending_raw, project_id=project.id, _cache=enrich_cache),
            "business_flow": func.business_flow if func else None,
            "direction": func.integration_direction if func else None,
            "source_system": func.source_system if func else None,
            "target_system": func.target_system if func else None,
            "idr_status": func.idr_status if func and func.idr_status else "In-Progress",
                        "inputs": func.inputs if func else None,
            "expected_output": func.expected_output if func else None,
            "idr_signoff_date": func.idr_signoff_date if func else None,
            "open_pointers": func.open_pointers if func else None,
            "remarks_timeline": remarks_timeline,
            "pointers_timeline": pointers_timeline,
        })

    return result


# ============================================================
# Action log writer — validates pending_with
# ============================================================
@router.post("/tasks/{touchpoint_id}/log")
def add_action_log(touchpoint_id: int, log_data: ActionLogCreate,
                                      db: Session = Depends(get_db)):
    func_record = db.query(IDRFunctional).filter(
        IDRFunctional.touchpoint_id == touchpoint_id
    ).first()
    pointers_changed = False
    warnings = []

    if func_record:
        if log_data.new_status:
            func_record.idr_status = log_data.new_status
            if log_data.new_status == "Signed-Off" and not func_record.idr_signoff_date:
                func_record.idr_signoff_date = str(date.today())

        # --- Validate and persist Pending With (project-scoped) ---
        if log_data.pending_with is not None:
            if log_data.pending_with.strip() == "":
                func_record.pending_with = None  # clear
            else:
                # Resolve project_id from the touchpoint for scoped validation
                tp = db.query(IntegrationTouchpoint).filter(
                    IntegrationTouchpoint.id == touchpoint_id
                ).first()
                proj_id = tp.project_id if tp else None
                resolved, warn = resolve_pending_with(db, log_data.pending_with, project_id=proj_id)
                func_record.pending_with = resolved  # falls back to raw on miss
                if warn:
                    warnings.append(warn)

        if log_data.open_pointers is not None and func_record.open_pointers != log_data.open_pointers:
            pointers_changed = True
            func_record.open_pointers = log_data.open_pointers

    if log_data.comment or pointers_changed:
        db.add(IDRActionLog(
            touchpoint_id=touchpoint_id,
            action_type="Manual Update",
            action_by=log_data.action_by,
            comment=log_data.comment if log_data.comment else None,
            open_pointer_history=log_data.open_pointers if pointers_changed else None,
        ))

    db.commit()
    return {"message": "Update saved successfully", "warnings": warnings}


# ============================================================
# CSV Export (unchanged behavior)
# ============================================================
@router.get("/tasks/{project_name}/export")
def export_project_tasks(project_name: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    touchpoints = db.query(IntegrationTouchpoint).filter(
        IntegrationTouchpoint.project_id == project.id
    ).all()

    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([
        "Touchpoint Name", "Module", "Business Flow", "Technical Owner",
        "IDR Status", "Pending With", "Sign-Off Date", "Open Pointers",
    ])

    for tp in touchpoints:
        func = tp.functional_discovery
        if func:
            writer.writerow([
                tp.name or "",
                func.module or "",
                func.business_flow or "",
                func.technical_owner or "",
                func.idr_status or "In-Progress",
                func.pending_with or "",
                func.idr_signoff_date or "",
                func.open_pointers or "",
            ])

    stream.seek(0)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    date_str = date.today().strftime("%Y-%m-%d")
    response.headers["Content-Disposition"] = f"attachment; filename=SDGNEXT_{project_name}_Report_{date_str}.csv"
    return response