from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from io import BytesIO
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from app.core.database import engine, Base, SessionLocal, get_db
from app.models.domain import TeamMaster, DepartmentMaster
from app.services.identity_validator import enrich_owner_label
from app.core.mom_engine import generate_and_send_mom
from app.core.ai_agent import get_active_provider, set_active_provider
from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical, IDRActionLog, TechnicalDocument
# Import our new architecture
from app.api.routes import upload, projects, tasks, integrations, mom, followups, mocks
from app.core.email_engine import generate_and_send_daily_summary, send_followup_nudges, send_mom_pointer_nudges
import mimetypes
from datetime import date, datetime
from app.workshop_mailer import send_workshop_invites
from app.wud_engine import create_wud_word
from app.rgt_engine import generate_rgt
from app.core.email_dispatcher import send_rgt_invite
from sqlalchemy.orm import Session
from app.api.routes import crm as crm_router


# Force Windows/Python to recognize .js files correctly
mimetypes.add_type('application/javascript', '.js')
# 1. Auto-create database tables if they don't exist

Base.metadata.create_all(bind=engine)
scheduler = BackgroundScheduler()

# --- NEW: Lifespan to control startup and shutdown of background tasks ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs daily at 6:00 PM (18:00) for executives
    scheduler.add_job(generate_and_send_daily_summary, 'cron', hour=18, minute=0)

    # Follow-up nudges at 9:30 AM Mon-Fri
    scheduler.add_job(send_followup_nudges, 'cron', day_of_week='mon-fri', hour=9, minute=30)

    # MoM-pointer nudges at 9:35 AM Mon-Fri (after followup nudges finish)
    scheduler.add_job(send_mom_pointer_nudges, 'cron', day_of_week='mon-fri', hour=9, minute=35)

    # Daily metric snapshot - captures yesterday's counts at 00:15
    scheduler.add_job(_run_daily_snapshot_job, 'cron', hour=0, minute=15)

    scheduler.start()
    print("✅ Background Scheduler Started. Summaries at 6PM, Follow-up Nudges at 9:30AM (Mon-Fri).")

    yield

    scheduler.shutdown()
    print("🛑 Background Scheduler Stopped.")


def _run_daily_snapshot_job():
    """Cron wrapper for capture_daily_snapshot.
    Manages its own DB session and never raises."""
    from app.services.project_health import capture_daily_snapshot
    db = SessionLocal()
    try:
        result = capture_daily_snapshot(db)
        print(f"[Snapshot cron] {result}")
    except Exception as e:
        print(f"[Snapshot cron] FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

# 2. Initialize the app (Note the lifespan=lifespan addition here)
app = FastAPI(title="SDGNEXT Command Center - Enterprise Edition", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Include our modular API routes
app.include_router(upload.router)
app.include_router(projects.router) 
app.include_router(tasks.router)
app.include_router(integrations.router)
app.include_router(mom.router)
app.include_router(followups.router)
app.include_router(mocks.router)
app.include_router(crm_router.router)

# --- NEW: MANUAL TEST ROUTE ---
@app.get("/test-daily-email")
def test_email_engine():
    """Trigger this from the browser to instantly test your email credentials and layout."""
    generate_and_send_daily_summary()
    return {"message": "Email trigger fired. Check terminal for success/failure logs."}

@app.get("/test-followup-nudges")
def test_followup_nudges():
    """Trigger this from the browser to test the follow-up nudge engine."""
    send_followup_nudges()
    return {"message": "Follow-up nudge trigger fired. Check terminal for logs."}


@app.post("/admin/snapshot/capture")
def admin_capture_snapshot(target_date: str = None):
    """Dev: manually capture a snapshot. Pass YYYY-MM-DD query param
    to backfill a specific date; omit to snapshot yesterday. Idempotent."""
    from datetime import date as _date
    from app.services.project_health import capture_daily_snapshot
    db = SessionLocal()
    try:
        td = None
        if target_date:
            td = _date.fromisoformat(target_date)
        result = capture_daily_snapshot(db, target_date=td)
        return result
    finally:
        db.close()


@app.post("/admin/snapshot/backfill-today")
def admin_backfill_today():
    """Dev: write a snapshot for TODAY (not yesterday).
    Useful immediately post-deployment so sparklines have at least
    one data point on launch day."""
    from datetime import date as _date
    from app.services.project_health import capture_daily_snapshot
    db = SessionLocal()
    try:
        result = capture_daily_snapshot(db, target_date=_date.today())
        return result
    finally:
        db.close()

@app.post("/api/generate-mom")
async def trigger_mom_generation(background_tasks: BackgroundTasks):
    """
    Endpoint triggered by the frontend 'Generate MOM' button.
    Runs the AI generation and email sending in the background.
    """
    # Add the heavy AI + Email function to the background queue
    background_tasks.add_task(generate_and_send_mom)
    
    # Instantly return a success message to the frontend UI
    return {
        "status": "success", 
        "message": "MOM generation initiated! The AI is drafting the minutes and will email stakeholders shortly."
    }

# 4. Serve the Frontend (Ensure CSS and JS folders remain in your root directory)
if os.path.exists("css"):
    app.mount("/css", StaticFiles(directory="css"), name="css")
if os.path.exists("js"):
    app.mount("/js", StaticFiles(directory="js"), name="js")

@app.get("/")
async def read_landing():
    return FileResponse('landing.html')

@app.get("/project")
async def read_project_view():
    return FileResponse('index.html')

@app.get("/api/phase2/dashboard")
def get_phase2_dashboard(request: Request):
    """Fetches real data for the Phase 2 Technical IDR Board, filtered by project."""
    db = SessionLocal()
    try:
        # Resolve project from query param; fall back to first project if not provided
        from app.models.domain import Project
        project_name = request.query_params.get('project')
        if not project_name:
            first_proj = db.query(Project).first()
            project_name = first_proj.project_name if first_proj else None

        if not project_name:
            return {"data": []}

        project = db.query(Project).filter(Project.project_name == project_name).first()
        if not project:
            return {"data": []}

        results = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
                ).outerjoin(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IntegrationTouchpoint.project_id == project.id
        ).all()

        dashboard_data = []
        # Per-request enrichment cache so we don't hit team_master once per row
        owner_cache = {}
        for tp, func, tech in results:

            tech_owner = getattr(func, "owner", "Unassigned") or "Unassigned"
            # Try identity-master enrichment first (yields "Rahul (CBS)" when matched).
            enriched = enrich_owner_label(db, tech_owner, project_id=project.id, _cache=owner_cache)
            display_owner = enriched if enriched else tech_owner

            integration_type = tech.integration_type if tech and tech.integration_type else "unassigned"
            
            # --- INTELLIGENT STATUS CALCULATION (datetime-aware) ---
            tech_status = tech.tech_status if tech and tech.tech_status else "Auto"

                        # Preserve manually set statuses
            manual_statuses = ["Completed", "Rescheduled", "Pending Document", "rgt review", "In Progress"]
            
            if tech_status in manual_statuses:
                pass  # Keep as-is
            elif tech and tech.start_date and tech.end_date:
                now = datetime.now()
                start_dt = tech.start_date if isinstance(tech.start_date, datetime) else datetime.fromisoformat(str(tech.start_date))
                end_dt = tech.end_date if isinstance(tech.end_date, datetime) else datetime.fromisoformat(str(tech.end_date))

                if now > end_dt:
                    tech_status = "Delayed"
                elif now < start_dt:
                    tech_status = "Scheduled"
                else:
                    tech_status = "In Progress"
            else:
                tech_status = "Pending Workshop"

                        # --- DYNAMIC COLOR MAPPING ---
            status_class = "bg-amber-100 text-amber-700 border-amber-200"  # Pending Workshop
            if tech_status == "In Progress":
                status_class = "bg-blue-100 text-blue-700 border-blue-200"
            elif tech_status == "Scheduled":
                status_class = "bg-sky-100 text-sky-700 border-sky-200"
            elif tech_status == "Delayed":
                status_class = "bg-red-100 text-red-700 border-red-200"
            elif tech_status == "Completed":
                status_class = "bg-emerald-100 text-emerald-700 border-emerald-200"
            elif tech_status == "Rescheduled":
                status_class = "bg-purple-100 text-purple-700 border-purple-200"
            elif tech_status == "Pending Document":
                status_class = "bg-orange-100 text-orange-700 border-orange-200"
            elif tech_status == "rgt review":
                status_class = "bg-indigo-100 text-indigo-700 border-indigo-200"

            # Serialize datetimes as 'YYYY-MM-DD HH:MM' for the frontend.
            # The space (not 'T') keeps it human-readable; FE splits on it.
            start_str = tech.start_date.strftime("%Y-%m-%d %H:%M") if (tech and tech.start_date) else ""
            end_str   = tech.end_date.strftime("%Y-%m-%d %H:%M")   if (tech and tech.end_date)   else ""

            dashboard_data.append({
                "id": tp.id,
                "name": tp.name,
                "module": func.module or "Unknown",
                "source_system": getattr(func, "source_system", None) or "-",
                "integration": integration_type,
                "owner": display_owner, 
                "start": start_str,
                "end": end_str,
                "techStatus": tech_status,
                "statusClass": status_class,
                "techDetails": tech.technical_details if tech and tech.technical_details else {}
            })
            
        return {"data": dashboard_data}
    finally:
        db.close()


@app.put("/api/phase2/update/{touchpoint_id}")
async def update_tech_idr(touchpoint_id: int, request: Request):
    """Saves the Integration Type, Dates+Times, Source System, and Manual Status Overrides."""
    db = SessionLocal()
    try:
        data = await request.json()
        tech = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == touchpoint_id).first()
        func = db.query(IDRFunctional).filter(IDRFunctional.touchpoint_id == touchpoint_id).first() # <-- Added Functional Query

        # Parse start/end. Accepted formats:
        #   "YYYY-MM-DD HH:MM"   (preferred, what FE now sends)
        #   "YYYY-MM-DDTHH:MM"   (datetime-local fallback)
        #   "YYYY-MM-DD"         (legacy date-only -> treated as 00:00)
        def parse_dt(value):
            if not value or not str(value).strip():
                return None
            s = str(value).strip().replace("T", " ")
            # Accept "YYYY-MM-DD HH:MM[:SS]"
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unrecognized datetime format: {value!r}")

        clean_start = parse_dt(data.get("start"))
        clean_end = parse_dt(data.get("end"))

        # --- NEW: Update Source System ---
        new_source = data.get("source")
        if new_source is not None:
            new_source_clean = new_source.strip()
            
            # 1. Check if the user is actually changing the name
            old_source = getattr(func, "source_system", "") if func else ""
            
            if old_source != new_source_clean:
                # 2. It changed! Unlink the old Connection & Datasource IDs
                if tech and tech.technical_details:
                    current_td = dict(tech.technical_details)
                    
                    # Remove the locked IDs so the CRM generates new ones
                    current_td.pop("crmConnectionId", None)
                    current_td.pop("crmDatasourceId", None)
                    
                    tech.technical_details = current_td
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(tech, "technical_details")

            # 3. Save the new name
            if func:
                func.source_system = new_source_clean
            if tech and hasattr(tech, "source_system"):
                tech.source_system = new_source_clean
        
        # Accept manual status overrides for workflow-controlled statuses
        incoming_status = data.get("status", "Auto")
        allowed_manual = ["Completed", "Rescheduled", "Pending Document", "RGT Review" ,"rgt review", "Pending Workshop", "In Progress"]
        new_status = incoming_status if incoming_status in allowed_manual else "Auto"

        # --- Status date stamping logic ---
        # When status changes, stamp the transition date in technical_details.statusDates
        def stamp_status_date(td_dict, old_status, new_resolved_status):
            """Stamps today's date for the new status in statusDates.
            Also stamps all prior steps that don't have dates yet."""
            if not td_dict:
                td_dict = {}
            if "statusDates" not in td_dict:
                td_dict["statusDates"] = {}
            
            today_str = date.today().isoformat()
            
            # Map status values to statusDates keys
            status_to_key = {
                "Scheduled": "scheduled",
                "In Progress": "inProgress",
                "Pending Document": "discussionCompleted",
                "RGT Review": "documentReview",
                "rgt review": "documentReview",
                "Completed": "completed",
            }
                                        
            # Ordered steps for backfilling
            ordered_keys = ["scheduled", "rgtShared", "inProgress", "discussionCompleted", "documentReview", "completed"]
            
            key = status_to_key.get(new_resolved_status)
            if key:
                # Stamp current step
                if not td_dict["statusDates"].get(key):
                    td_dict["statusDates"][key] = today_str
                
                # Backfill all prior steps that don't have dates
                key_idx = ordered_keys.index(key) if key in ordered_keys else -1
                for i in range(key_idx):
                    prior_key = ordered_keys[i]
                    if not td_dict["statusDates"].get(prior_key):
                        td_dict["statusDates"][prior_key] = today_str

            return td_dict

        if tech:
            old_status = tech.tech_status
            tech.integration_type = data.get("integration")
            tech.start_date = clean_start
            tech.end_date = clean_end
            tech.tech_status = new_status

            from sqlalchemy.orm.attributes import flag_modified

            # Stamp status date when status changes
            if new_status != "Auto" and new_status != old_status:
                current_td = dict(tech.technical_details or {})
                current_td = stamp_status_date(current_td, old_status, new_status)
                # Also stamp 'scheduled' if start_date is being set
                if clean_start and not current_td.get("statusDates", {}).get("scheduled"):
                    current_td.setdefault("statusDates", {})["scheduled"] = clean_start.strftime("%Y-%m-%d")
                tech.technical_details = current_td
                flag_modified(tech, "technical_details")

            if "technical_details" in data:
                td = data.get("technical_details") or {}

                # Log discussion entry if provided
                new_discussion = td.pop("discussion", "").strip() if td else ""
                if new_discussion:
                    db.add(IDRActionLog(
                        touchpoint_id=touchpoint_id,
                        action_type="DISCUSSION",
                        action_by="User",
                        comment=new_discussion
                    ))

                # Log pointer/action entry if provided
                new_pointer = td.pop("pointers", "").strip() if td else ""
                if new_pointer:
                    db.add(IDRActionLog(
                        touchpoint_id=touchpoint_id,
                        action_type="POINTER",
                        action_by="User",
                        open_pointer_history=new_pointer
                    ))

                # MERGE incoming fields INTO existing technical_details
                # so that keys set by other processes (crmConnectionId,
                # rgtSharedAt, statusDates, etc.) are never lost.
                existing_td = dict(tech.technical_details or {})
                existing_td.update(td)

                # Preserve statusDates (deep merge - incoming doesn't overwrite existing dates)
                if tech.technical_details and tech.technical_details.get("statusDates"):
                    existing_td.setdefault("statusDates", {}).update(tech.technical_details["statusDates"])

                tech.technical_details = existing_td
                flag_modified(tech, "technical_details")
        else:
            td = data.get("technical_details", {})
            new_discussion = td.pop("discussion", "").strip() if td else ""
            new_pointer = td.pop("pointers", "").strip() if td else ""

            # Stamp status date for new records too
            if new_status != "Auto":
                td = stamp_status_date(td or {}, None, new_status)
            if clean_start:
                td = td or {}
                td.setdefault("statusDates", {})
                if not td["statusDates"].get("scheduled"):
                    td["statusDates"]["scheduled"] = clean_start.strftime("%Y-%m-%d")

            # Defensive fallback: this lazy-creation path remains for any legacy
            # data without an IDRTechnical row. Normal flow (CSV upload) now
            # eagerly creates the row in file_parser.py.
            tech = IDRTechnical(
                touchpoint_id=touchpoint_id,
                integration_type=data.get("integration"),
                start_date=clean_start,
                end_date=clean_end,
                tech_status=new_status,
                technical_details=td
            )
            db.add(tech)

            if new_discussion:
                db.add(IDRActionLog(
                    touchpoint_id=touchpoint_id,
                    action_type="DISCUSSION",
                    action_by="User",
                    comment=new_discussion
                ))
            if new_pointer:
                db.add(IDRActionLog(
                    touchpoint_id=touchpoint_id,
                    action_type="POINTER",
                    action_by="User",
                    open_pointer_history=new_pointer
                ))
        db.commit()
        return {"status": "success", "message": "Technical details updated"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

@app.post("/api/phase2/trigger-invites")
def trigger_manual_invites(project_id: int = Body(..., embed=True)):
    """Manually triggers workshop invite emails for tomorrow's scheduled
    workshops within the given project."""
    result = send_workshop_invites(project_id=project_id)
    return result


@app.get("/test-mom-pointer-nudges")
def test_mom_pointer_nudges_endpoint():
    """Manual trigger for MoM-pointer nudges (testing only)."""
    send_mom_pointer_nudges()
    return {"status": "triggered"}


# =========================================================================
# AI PROVIDER RUNTIME SWITCHING
# =========================================================================

@app.get("/api/admin/ai-provider")
def get_ai_provider():
    """Returns the currently active AI provider."""
    return {"status": "success", "active_provider": get_active_provider()}


@app.post("/api/admin/ai-provider")
def switch_ai_provider(provider: str = Body(..., embed=True)):
    """Switch AI provider at runtime. Body: {"provider": "openai" | "bedrock"}"""
    try:
        new_provider = set_active_provider(provider)
        return {
            "status": "success",
            "message": f"AI provider switched to: {new_provider.upper()}",
            "active_provider": new_provider
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# 1. Serve the new HTML Page
@app.get("/details")
def serve_details_page():
    """Serves the new standalone Details HTML page."""
    # Note: If your HTML files are in a specific folder like 'static' or 'templates', 
    # update this path (e.g., 'static/details.html')
    return FileResponse("details.html")

# 2. API to fetch a single Touchpoint's data
@app.get("/api/phase2/touchpoint/{tp_id}")
def get_single_touchpoint(tp_id: int):
    """Fetches full details for a single integration touchpoint."""
    db = SessionLocal()
    try:
        # Use outerjoin for Technical in case it hasn't been saved yet
        result = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).outerjoin(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IntegrationTouchpoint.id == tp_id
        ).first()

        if not result:
            return {"status": "error", "message": "Touchpoint not found"}

        tp, func, tech = result

        # Resolve project_name for frontend breadcrumb
        from app.models.domain import Project
        project = db.query(Project).filter(Project.id == tp.project_id).first()
        project_name = project.project_name if project else "Project"
        
        tech_owner = getattr(func, "owner", "Unassigned")
        tech_status = tech.tech_status if tech and tech.tech_status else "Auto"
        integration_type = tech.integration_type if tech and tech.integration_type else "unassigned"

        # Auto-calculate effective status (same logic as dashboard)
        manual_statuses = ["Completed", "Rescheduled", "Pending Document", "RGT Review", "rgt review", "In Progress"]
        effective_status = tech_status
        if tech_status not in manual_statuses:
            if tech and tech.start_date and tech.end_date:
                now = datetime.now()
                start_dt = tech.start_date if isinstance(tech.start_date, datetime) else datetime.fromisoformat(str(tech.start_date))
                end_dt = tech.end_date if isinstance(tech.end_date, datetime) else datetime.fromisoformat(str(tech.end_date))
                if now > end_dt:
                    effective_status = "Delayed"
                elif now < start_dt:
                    effective_status = "Scheduled"
                else:
                    effective_status = "In Progress"
            else:
                effective_status = "Pending Workshop"

        # Auto-stamp dates for auto-calculated statuses (lazy write-back)
        if tech and effective_status in ("Scheduled", "In Progress"):
            from sqlalchemy.orm.attributes import flag_modified
            td = dict(tech.technical_details or {})
            sd = td.setdefault("statusDates", {})
            changed = False
            if effective_status == "Scheduled" and not sd.get("scheduled") and tech.start_date:
                sd["scheduled"] = tech.start_date.strftime("%Y-%m-%d")
                changed = True
            if effective_status == "In Progress":
                if not sd.get("scheduled") and tech.start_date:
                    sd["scheduled"] = tech.start_date.strftime("%Y-%m-%d")
                    changed = True
                if not sd.get("inProgress"):
                    sd["inProgress"] = date.today().isoformat()
                    changed = True
            if changed:
                tech.technical_details = td
                flag_modified(tech, "technical_details")
                db.commit()

        # Enrich owner fields with department context
        owner_cache = {}
        owner_display = enrich_owner_label(db, tech_owner, project_id=tp.project_id, _cache=owner_cache)
        tech_owner_display = enrich_owner_label(db, getattr(func, "technical_owner", None), project_id=tp.project_id, _cache=owner_cache)
        mod_owner_display = enrich_owner_label(db, getattr(func, "module_owner_functional", None), project_id=tp.project_id, _cache=owner_cache)

        # Latest 5 discussion entries
        discussion_logs = db.query(IDRActionLog).filter(
            IDRActionLog.touchpoint_id == tp_id,
            IDRActionLog.action_type == "DISCUSSION"
        ).order_by(IDRActionLog.created_at.desc()).limit(5).all()

        # Latest 5 pointer/action entries
        pointer_logs = db.query(IDRActionLog).filter(
            IDRActionLog.touchpoint_id == tp_id,
            IDRActionLog.action_type.in_(["POINTER", "STATUS_CHANGE"])
        ).order_by(IDRActionLog.created_at.desc()).limit(5).all()

        formatted_discussions = ""
        for log in discussion_logs:
            date_str = log.created_at.strftime("%b %d, %Y %H:%M") if log.created_at else "Unknown"
            formatted_discussions += f"[{date_str}] {log.comment}\n\n"

        formatted_history = ""
        for log in pointer_logs:
            date_str = log.created_at.strftime("%b %d, %Y %H:%M") if log.created_at else "Unknown"
            entry = log.open_pointer_history or log.comment or ""
            formatted_history += f"[{date_str}] {entry}\n\n"

        raw_signoff = getattr(func, "idr_signoff_date", None)
        formatted_signoff = str(raw_signoff) if raw_signoff else "Pending"

        return {
            "status": "success",
            "data": {
                "id": tp.id,
                "project_id": tp.project_id,
                "project_name": project_name,
                "name": tp.name,
                "module": func.module or "Unknown",
                "owner": tech_owner,
                "integration": integration_type,
                
                "source": getattr(func, "source_system", "-"),
                "target": getattr(func, "target_system", "-"),
                
                # --- EXACT DATABASE COLUMN MAPPING ---
                # Using a fallback to lowercase 'input' just in case your model is strictly lowercase
                "input": getattr(func, "Input", getattr(func, "inputs", "-")), 
                "output": getattr(func, "expected_output", "-"),          
                                "signoff": formatted_signoff,                    
                # -------------------------------------
                
                "business_flow": getattr(func, "business_flow", "-"),
                "mod_owner": getattr(func, "module_owner_functional", None) or "-",
                "tech_owner_name": getattr(func, "technical_owner", None) or "-",
                "fallback": getattr(func, "business_fallback", "-"),
                "business_purpose": getattr(func, "business_req", "-"),
                # Enriched display labels with department
                "owner_display": owner_display,
                "tech_owner_display": tech_owner_display,
                                "mod_owner_display": mod_owner_display,
                
                "start": tech.start_date.strftime("%Y-%m-%d %H:%M") if (tech and tech.start_date) else "",
                "end":   tech.end_date.strftime("%Y-%m-%d %H:%M")   if (tech and tech.end_date)   else "",
                "techStatus": effective_status,
                "techDetails": tech.technical_details if tech and tech.technical_details else {},
                "pendingWith": (tech.pending_with if tech else "") or "",
                "discussion_log": formatted_discussions.strip(),
                "history_log": formatted_history.strip()
            }
        }
    finally:
        db.close()
@app.get("/api/phase2/touchpoint/{tp_id}/generate-wud")
def generate_wud_word_endpoint(tp_id: int):
    """Generates a Word Work Unit Document and returns it."""
    
    data_response = get_single_touchpoint(tp_id)
    if data_response.get("status") != "success":
        raise HTTPException(status_code=404, detail="Could not fetch data for WUD")
    
    tp_data = data_response["data"]
    
    if tp_data.get("integration", "").lower() != "api":
        raise HTTPException(status_code=400, detail="WUD Generation is currently only supported for API Integration Types.")

    try:
        # Call the new Word generator
        word_file = create_wud_word(tp_data)
        safe_name = tp_data.get("name", "Touchpoint").replace(" ", "_")

        # Stream the file with the exact MIME type for .docx
        return StreamingResponse(
            word_file,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={safe_name}_WUD.docx"}
        )
    except Exception as e:
        print(f"Backend Word Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/phase2/touchpoint/{tp_id}/documents")
def get_touchpoint_documents(tp_id: int):
    """Returns list of documents received for a touchpoint."""
    db = SessionLocal()
    try:
        docs = db.query(TechnicalDocument).filter(
            TechnicalDocument.touchpoint_id == tp_id
        ).order_by(TechnicalDocument.received_at.desc()).all()

        return {
            "status": "success",
            "documents": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "file_type": d.file_type,
                    "received_from": d.received_from or "",

                    "received_at": d.received_at.strftime("%b %d, %Y at %I:%M %p") if d.received_at else "",
                    "notes": d.notes or ""
                }
                for d in docs
            ]
        }
    finally:
        db.close()


@app.get("/api/phase2/document/{doc_id}/download")
def download_document(doc_id: int):
    """Downloads a stored document by ID."""
    import base64
    db = SessionLocal()
    try:
        doc = db.query(TechnicalDocument).filter(TechnicalDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_bytes = base64.b64decode(doc.file_data)
        buffer = BytesIO(file_bytes)
        buffer.seek(0)

        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return StreamingResponse(
            buffer,
            media_type=mime,
            headers={"Content-Disposition": f"attachment; filename={doc.filename}"}
        )
    finally:
        db.close()


# --- Graph API Admin Endpoints ---
@app.get("/admin/graph/health")
def admin_graph_health():
    """Dev: verify Graph credentials and report which permissions were
    granted. Use this to confirm setup before relying on email features."""
    from app.core.graph_mailer import graph_permission_check
    return graph_permission_check()


@app.post("/admin/graph/test-email")
def admin_graph_test_email(to_address: str):
    """Dev: send a single test email via Graph to verify end-to-end
    delivery."""
    from app.core.graph_mailer import send_graph_email
    result = send_graph_email(
        to_recipients=[to_address],
        subject="SDGNext || Graph API Test Email",
        html_body=(
            "<p>This is a test email sent via Microsoft Graph API. "
            "If you received it, the integration is working.</p>"
        )
    )
    return result