from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.auth import require_admin, hash_password
from app.models.domain import User, Project, ProjectAssignment

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "manager"


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.username).all()
    return [{"id": u.id, "username": u.username, "email": u.email, "role": u.role, "is_active": u.is_active} for u in users]


@router.post("/users")
def create_user(req: CreateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter((User.username == req.username) | (User.email == req.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    user = User(username=req.username, email=req.email, password_hash=hash_password(req.password), role=req.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User created", "id": user.id, "username": user.username}


@router.put("/users/{user_id}")
def update_user(user_id: int, req: UpdateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.email is not None:
        user.email = req.email
    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password is not None:
        user.password_hash = hash_password(req.password)
    db.commit()
    return {"message": "User updated"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}


class AssignProjectRequest(BaseModel):
    user_id: int
    project_id: int


@router.get("/assignments")
def list_assignments(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    assignments = db.query(ProjectAssignment, User, Project).join(
        User, ProjectAssignment.user_id == User.id
    ).join(Project, ProjectAssignment.project_id == Project.id).all()
    return [{"id": a.id, "user_id": a.user_id, "username": u.username, "project_id": a.project_id, "project_name": p.project_name} for a, u, p in assignments]


@router.post("/assignments")
def assign_project(req: AssignProjectRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(ProjectAssignment).filter(ProjectAssignment.user_id == req.user_id, ProjectAssignment.project_id == req.project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already assigned")
    db.add(ProjectAssignment(user_id=req.user_id, project_id=req.project_id))
    db.commit()
    return {"message": "Project assigned"}


@router.delete("/assignments/{assignment_id}")
def remove_assignment(assignment_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.query(ProjectAssignment).filter(ProjectAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
    return {"message": "Assignment removed"}


@router.get("/projects")
def list_all_projects(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.project_name).all()
    return [{"id": p.id, "project_name": p.project_name} for p in projects]
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db
from app.core.auth import require_admin, hash_password
from app.models.domain import User, Project, ProjectAssignment

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ======================== USER MANAGEMENT ========================

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "manager"


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.username).all()
    return [
        {"id": u.id, "username": u.username, "email": u.email, "role": u.role, "is_active": u.is_active}
        for u in users
    ]


@router.post("/users")
def create_user(req: CreateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(User).filter(
        (User.username == req.username) | (User.email == req.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        role=req.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User created", "id": user.id, "username": user.username}


@router.put("/users/{user_id}")
def update_user(user_id: int, req: UpdateUserRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.email is not None:
        user.email = req.email
    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password is not None:
        user.password_hash = hash_password(req.password)

    db.commit()
    return {"message": "User updated"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}


# ======================== PROJECT ASSIGNMENT ========================

class AssignProjectRequest(BaseModel):
    user_id: int
    project_id: int


@router.get("/assignments")
def list_assignments(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    assignments = db.query(ProjectAssignment, User, Project).join(
        User, ProjectAssignment.user_id == User.id
    ).join(
        Project, ProjectAssignment.project_id == Project.id
    ).all()

    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "username": u.username,
            "project_id": a.project_id,
            "project_name": p.project_name
        }
        for a, u, p in assignments
    ]


@router.post("/assignments")
def assign_project(req: AssignProjectRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(ProjectAssignment).filter(
        ProjectAssignment.user_id == req.user_id,
        ProjectAssignment.project_id == req.project_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already assigned")

    assignment = ProjectAssignment(user_id=req.user_id, project_id=req.project_id)
    db.add(assignment)
    db.commit()
    return {"message": "Project assigned"}


@router.delete("/assignments/{assignment_id}")
def remove_assignment(assignment_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    a = db.query(ProjectAssignment).filter(ProjectAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
    return {"message": "Assignment removed"}


# ======================== PROJECTS LIST (for admin dropdown) ========================

@router.get("/projects")
def list_all_projects(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.project_name).all()
    return [{"id": p.id, "project_name": p.project_name} for p in projects]
