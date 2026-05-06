import os
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from app.core.database import engine, Base, SessionLocal
from app.models.domain import TeamMaster
from app.core.mom_engine import generate_and_send_mom

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