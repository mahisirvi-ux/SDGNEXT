import os
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from app.core.database import engine, Base, SessionLocal
from app.models.domain import TeamMaster
from app.core.mom_engine import generate_and_send_mom
from app.models.domain import IntegrationTouchpoint, IDRFunctional, IDRTechnical
from app.core.database import SessionLocal
# Import our new architecture
from app.api.routes import upload, projects, tasks
from app.core.email_engine import generate_and_send_daily_summary, generate_and_send_follow_ups
import mimetypes

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
    
    # NEW: Runs at 9:00 AM, Monday-Friday for the Bank teams
    scheduler.add_job(generate_and_send_follow_ups, 'cron', day_of_week='mon-fri', hour=9, minute=0) 
    
    scheduler.start()
    print("✅ Background Scheduler Started. Summaries at 6PM, Follow-ups at 9AM (Mon-Fri).")
    
    yield
    
    scheduler.shutdown()
    print("🛑 Background Scheduler Stopped.")

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

# --- NEW: MANUAL TEST ROUTE ---
@app.get("/test-daily-email")
def test_email_engine():
    """Trigger this from the browser to instantly test your email credentials and layout."""
    generate_and_send_daily_summary()
    return {"message": "Email trigger fired. Check terminal for success/failure logs."}

@app.get("/test-follow-ups")
def test_email_follow_ups():
    """Trigger this from the browser to instantly test the follow-up engine."""
    generate_and_send_follow_ups()
    return {"message": "Follow-up trigger fired. Check terminal for success/failure logs."}
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
async def read_index():
    return FileResponse('index.html')

@app.get("/api/phase2/dashboard")
def get_phase2_dashboard():
    """Fetches real data for the Phase 2 Technical IDR Board."""
    db = SessionLocal()
    try:
        # 1. Query the DB: Use idr_status and ilike() for safe, case-insensitive matching
        results = db.query(
            IntegrationTouchpoint, IDRFunctional, IDRTechnical
        ).join(
            IDRFunctional, IntegrationTouchpoint.id == IDRFunctional.touchpoint_id
        ).outerjoin(
            IDRTechnical, IntegrationTouchpoint.id == IDRTechnical.touchpoint_id
        ).filter(
            IDRFunctional.idr_status.ilike("%Signed-Off%")
        ).all()

        # 2. Format the data for the Javascript frontend
        dashboard_data = []
        for tp, func, tech in results:

            # 1. Grab Phase 2 source (if it was manually overridden)
            tech_source = tech.source_system if tech and tech.source_system else None
            
            # 2. Grab Phase 1 source using getattr (to prevent crashes if column name varies)
            # *Note: If your Phase 1 database column is named something else like 'source', 
            # change "source_system" below to match your database!
            func_source = getattr(func, "source_system", getattr(func, "source", "-"))
            
            # 3. If Tech source is empty or a dash, inherit the Phase 1 source!
            final_source = tech_source if tech_source and tech_source.strip() not in ["", "-"] else func_source
            tech_owner = getattr(func, "owner", "Unassigned")
            dept = getattr(func, "business_department", "")
            
            display_owner = f"{tech_owner} ({dept})" if dept else tech_owner
            # ------------------------------------------------
            integration_type = tech.integration_type if tech else "unassigned"
            tech_status = tech.tech_status if tech else "Pending Workshop"
            
            # Determine color pill based on status
            status_class = "bg-amber-100 text-amber-700 border-amber-200"
            if tech_status == "In Progress":
                status_class = "bg-blue-100 text-blue-700 border-blue-200"
            elif tech_status == "Signed-Off":
                status_class = "bg-emerald-100 text-emerald-700 border-emerald-200"

            dashboard_data.append({
                "id": tp.id,
                "name": tp.name,
                "module": func.module or "Unknown",
                "phase1Status": func.idr_status, # Updated to idr_status
                "integration": integration_type,
                "source": final_source,
                "owner": display_owner,
                "start": str(tech.start_date) if tech and tech.start_date else "-",
                "end": str(tech.end_date) if tech and tech.end_date else "-",
                "techStatus": tech_status,
                "statusClass": status_class,
                # --- NEW: Send the JSON details to the frontend ---
                "techDetails": tech.technical_details if tech and tech.technical_details else {}
            })
            
        return {"data": dashboard_data}

    except Exception as e:
        print(f"Error fetching Phase 2 data: {e}")
        return {"data": []}
    finally:
        db.close()

@app.put("/api/phase2/update/{touchpoint_id}")
async def update_tech_idr(touchpoint_id: int, request: Request):
    """Saves the Integration Type, Start Date, and End Date from the UI (Upsert Pattern)."""
    db = SessionLocal()
    try:
        data = await request.json()
        print(f"--- SAVING PHASE 2 DATA FOR TOUCHPOINT {touchpoint_id} ---")
        print(f"Payload Received: {data}")
        
        # 1. Look for the existing row
        tech = db.query(IDRTechnical).filter(IDRTechnical.touchpoint_id == touchpoint_id).first()
        
        # Clean the dates safely
        start_val = data.get("start")
        end_val = data.get("end")
        clean_start = start_val if start_val and start_val.strip() != "" else None
        clean_end = end_val if end_val and end_val.strip() != "" else None
        
        if tech:
            # 2A. ROW EXISTS: Update it
            tech.integration_type = data.get("integration")
            tech.start_date = clean_start
            tech.end_date = clean_end
            
            # --- NEW: Save the Technical Details JSON ---
            if "technical_details" in data:
                tech.technical_details = data.get("technical_details")
            # ------------------------------------------

            if tech.start_date and tech.tech_status == "Pending Workshop":
                tech.tech_status = "In Progress"
                
            print("Existing row found. Updating data...")
            
        else:
            # 2B. ROW DOES NOT EXIST: Create it instantly!
            print("Row not found in idr_technical. Creating a new one on the fly...")
            new_status = "In Progress" if clean_start else "Pending Workshop"
            
            tech = IDRTechnical(
                touchpoint_id=touchpoint_id,
                integration_type=data.get("integration"),
                start_date=clean_start,
                end_date=clean_end,
                tech_status=new_status,
                
                # --- NEW: Save the Technical Details JSON on creation ---
                technical_details=data.get("technical_details", {})
            )
            db.add(tech)

        # 3. Save to Postgres
        db.commit()
        print("Successfully saved to database!")
        return {"status": "success", "message": "Technical details updated"}
        
    except Exception as e:
        db.rollback()
        print(f"CRITICAL ERROR SAVING DATA: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()