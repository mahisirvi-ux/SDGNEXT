from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.models.domain import Project
from app.services.project_health import get_project_summaries, get_landing_summary

router = APIRouter()


class ProjectCreate(BaseModel):
    project_name: str


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