import io
import csv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.models.domain import Project, IntegrationTouchpoint, IDRActionLog, IDRFunctional
from datetime import date
from fastapi.responses import StreamingResponse
from app.models.domain import TeamMaster

router = APIRouter()

class ActionLogCreate(BaseModel):
    action_type: str
    action_by: str
    comment: str
    new_status: str = None
    pending_with: str = None # Accepts empty string to clear the value
    open_pointers: str = None

# --- NEW: Fetch Unique Dropdown Options ---
@router.get("/pending-options")
def get_pending_options(db: Session = Depends(get_db)):
    """Fetches the Master LOV for the Pending With dropdown."""
    # Query only active teams from the NEW master table
    teams = db.query(TeamMaster).filter(TeamMaster.is_active == True).order_by(TeamMaster.team_name).all()
    
    # Return just a list of the names for the frontend dropdown
    return [team.team_name for team in teams]

@router.get("/tasks/{project_name}")
def get_tasks_by_project(project_name: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project: return []

    touchpoints = db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.project_id == project.id).all()
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
                    "created_at": created_str
                })
            
            if log.open_pointer_history and len(pointers_timeline) < 3:
                pointers_timeline.append({
                    "action_by": log.action_by,
                    "comment": log.open_pointer_history,
                    "created_at": created_str
                })

        result.append({
            "id": tp.id,
            "integration_touch_point": tp.name,
            "module": func.module if func else None,
            "module_owner": func.module_owner_functional if func else None,
            "technical_owner": func.technical_owner if func else None,
            "business_flow": func.business_flow if func else None,
            "direction": func.integration_direction if func else None,
            "source_system": func.source_system if func else None,
            "target_system": func.target_system if func else None,
            "idr_status": func.idr_status if func and func.idr_status else "In-Progress",
            "inputs": func.inputs if func else None,
            "expected_output": func.expected_output if func else None,
            "business_department": func.business_department if func else None,
            "owner": func.owner if func else None,
            "idr_signoff_date": func.idr_signoff_date if func else None,
            "pending_with": func.pending_with if func else None,
            "open_pointers": func.open_pointers if func else None,
            "remarks_timeline": remarks_timeline,     
            "pointers_timeline": pointers_timeline    
        })
        
    return result

@router.post("/tasks/{touchpoint_id}/log")
def add_action_log(touchpoint_id: int, log_data: ActionLogCreate, db: Session = Depends(get_db)):
    
    func_record = db.query(IDRFunctional).filter(IDRFunctional.touchpoint_id == touchpoint_id).first()
    pointers_changed = False
    
    if func_record:
        if log_data.new_status:
            func_record.idr_status = log_data.new_status
            if log_data.new_status == "Signed-Off" and not func_record.idr_signoff_date:
                func_record.idr_signoff_date = str(date.today())

        # --- UPDATED: Allow clearing out the Pending With column ---
        if log_data.pending_with is not None:
            if log_data.pending_with == "":
                func_record.pending_with = None  # Saves as null in DB
            else:
                func_record.pending_with = log_data.pending_with
            
        if log_data.open_pointers is not None and func_record.open_pointers != log_data.open_pointers:
            pointers_changed = True
            func_record.open_pointers = log_data.open_pointers

    if log_data.comment or pointers_changed:
        new_log = IDRActionLog(
            touchpoint_id=touchpoint_id,
            action_type="Manual Update",
            action_by=log_data.action_by,
            comment=log_data.comment if log_data.comment else None,
            open_pointer_history=log_data.open_pointers if pointers_changed else None
        )
        db.add(new_log)

    db.commit()
    return {"message": "Update saved successfully"}
    # --- NEW: EXPORT REPORT TO ANY LOCATION ---
@router.get("/tasks/{project_name}/export")
def export_project_tasks(project_name: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project: 
        raise HTTPException(status_code=404, detail="Project not found")

    touchpoints = db.query(IntegrationTouchpoint).filter(IntegrationTouchpoint.project_id == project.id).all()
    
    # Create an in-memory string buffer for the CSV
    stream = io.StringIO()
    writer = csv.writer(stream)
    
    # Write the CSV Headers
    writer.writerow([
        "Touchpoint Name", "Module", "Business Flow", "Technical Owner", 
        "IDR Status", "Pending With", "Sign-Off Date", "Open Pointers"
    ])
    
    # Write the Data Rows
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
                func.open_pointers or ""
            ])
            
    # Reset buffer position to the beginning
    stream.seek(0)
    
    # Stream the file to the browser prompting the "Save As" dialog
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    date_str = date.today().strftime("%Y-%m-%d")
    response.headers["Content-Disposition"] = f"attachment; filename=SDGNEXT_{project_name}_Report_{date_str}.csv"
    
    return response