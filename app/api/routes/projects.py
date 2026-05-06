from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.models.domain import Project

router = APIRouter()

# Schema for creating a project
class ProjectCreate(BaseModel):
    project_name: str

@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    """Fetch all projects for the UI dropdown"""
    return db.query(Project).all()

@router.post("/projects")
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project container"""
    existing = db.query(Project).filter(Project.project_name == project.project_name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Project already exists")
    
    new_project = Project(project_name=project.project_name)
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project