import io
import os
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles # Add this
from fastapi.responses import FileResponse # Add this

# --- DATABASE CONFIGURATION ---
# Replace 'user', 'password', 'localhost', and 'dbname' with your actual PostgreSQL credentials
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:root@localhost:5432/sdgnext"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- SQLALCHEMY MODELS ---

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(100), unique=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    tasks = relationship("IntegrationTask", back_populates="project", cascade="all, delete")

class IntegrationTask(Base):
    __tablename__ = "integration_tasks"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    
    sr_no = Column(Integer)
    module = Column(String(100))
    source_system = Column(String(100))
    target_system = Column(String(100))
    integration_touch_point = Column(Text)
    unique_integration_flag = Column(String(50))
    orchestration = Column(String(100))
    interface_type = Column(String(100))
    job_status = Column(String(100))
    input_details = Column(Text)
    expected_output = Column(Text)
    api_available = Column(String(50))
    api_received = Column(String(50))
    is_mock_available = Column(String(50))
    module_owner = Column(String(100))
    tech_discussion_completed = Column(String(100))
    crm_comments = Column(Text)
    bank_comments = Column(Text)
    pending_on = Column(String(100))
    wud_status = Column(String(100))
    wud_shared_date = Column(String(50))
    wud_signoff_date = Column(String(50))
    assigned_resource = Column(String(100))
    start_date = Column(String(50))
    end_date = Column(String(50))
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="tasks")

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- PYDANTIC SCHEMAS (For API Data Validation) ---

class TaskUpdate(BaseModel):
    module: Optional[str] = None
    integration_touch_point: Optional[str] = None
    job_status: Optional[str] = None
    assigned_resource: Optional[str] = None
    pending_on: Optional[str] = None
    crm_comments: Optional[str] = None
    # Add other fields as needed for UI editing

class ProjectCreate(BaseModel):
    project_name: str

# --- FASTAPI APP SETUP ---

app = FastAPI(title="SDGNEXT Command Center API")

# Enable CORS for your Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API ENDPOINTS ---

@app.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()

@app.post("/projects")
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    db_project = Project(project_name=project.project_name)
    db.add(db_project)
    try:
        db.commit()
        db.refresh(db_project)
    except Exception:
        raise HTTPException(status_code=400, detail="Project already exists")
    return db_project

@app.post("/upload-csv/{project_name}")
async def upload_csv(project_name: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Find the project by its name
    project = db.query(Project).filter(Project.project_name == project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))

    # Helper mapping to handle specific CSV header spacing
    mapping = {
        'Sr#': 'sr_no',
        'Module': 'module',
        'Source System': 'source_system',
        'Target System': 'target_system',
        'Integration Touch Point': 'integration_touch_point',
        'Unique Integration Flag': 'unique_integration_flag',
        'Orchestration': 'orchestration',
        'Interface Type': 'interface_type',
        'Job Status ': 'job_status',
        'Input': 'input_details',
        'Expected Output': 'expected_output',
        'API Available': 'api_available',
        'API Received': 'api_received',
        'Is Mock Available': 'is_mock_available',
        'Module Owner': 'module_owner',
        'Technical discussion Completed': 'tech_discussion_completed',
        'CRM Comments': 'crm_comments',
        'Bank Comments': 'bank_comments',
        'Pending On': 'pending_on',
        'WUD Status': 'wud_status',
        'WUD SHARED  DATE': 'wud_shared_date',
        'WUD Sign Off Date': 'wud_signoff_date',
        'Assigned Resource': 'assigned_resource',
        'Start Date': 'start_date',
        'End Date': 'end_date'
    }

    # 2. Clear existing tasks for this project using project.id
    db.query(IntegrationTask).filter(IntegrationTask.project_id == project.id).delete()

    tasks_to_add = []
    for _, row in df.iterrows():
        # CRITICAL FIX: We must use project.id from the database record here
        task_data = {"project_id": project.id} 
        
        for csv_header, db_field in mapping.items():
            if csv_header in df.columns:
                val = row[csv_header]
                # Handle NaN values from Pandas safely
                task_data[db_field] = str(val) if pd.notna(val) else None
            else:
                task_data[db_field] = None
        
        tasks_to_add.append(IntegrationTask(**task_data))

    db.add_all(tasks_to_add)
    db.commit()
    return {"message": f"Successfully uploaded {len(tasks_to_add)} tasks."}

@app.get("/tasks/{project_name}")
def get_tasks_by_project(project_name: str, db: Session = Depends(get_db)):
    # Safely join and filter by the string name
    return db.query(IntegrationTask).join(Project).filter(Project.project_name == project_name).all()
@app.patch("/tasks/{task_id}")
def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(IntegrationTask).filter(IntegrationTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = task_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_task, key, value)
    
    db.commit()
    db.refresh(db_task)
    return db_task

# 1. Mount the CSS, JS, and Images folders
# This assumes your folders are named 'css', 'js' and are in the same directory as main.py
if os.path.exists("css"):
    app.mount("/css", StaticFiles(directory="css"), name="css")
if os.path.exists("js"):
    app.mount("/js", StaticFiles(directory="js"), name="js")

# 2. Serve the index.html at the root URL
@app.get("/")
async def read_index():
    return FileResponse('index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)