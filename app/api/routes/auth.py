"""
app/api/routes/auth.py
──────────────────────
Authentication endpoints:
  POST /api/auth/login      – exchange username+password for JWT
  POST /api/auth/register   – create a new user (admin-only or first-run)
  GET  /api/auth/me         – return current user profile
  PUT  /api/auth/me/password – change own password
  GET  /api/auth/users       – list all users (admin only)
  PUT  /api/auth/users/{id}/toggle – activate / deactivate (admin only)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
)
from app.models.domain import UserMaster

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False


class RegisterRequest(BaseModel):
    full_name: str
    username: str
    email: str
    password: str
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        allowed = {"admin", "manager", "viewer"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    username: str
    email: str
    role: str
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_to_out(u: UserMaster) -> dict:
    return {
        "id":            u.id,
        "full_name":     u.full_name,
        "username":      u.username,
        "email":         u.email,
        "role":          u.role,
        "is_active":     u.is_active,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at":    u.created_at.isoformat()    if u.created_at    else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/first-run")
def first_run_check(db: Session = Depends(get_db)):
    """Public endpoint: returns whether any users exist.
    Used by login.html to decide whether to show the Setup tab."""
    count = db.query(UserMaster).count()
    return {"first_run": count == 0}


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Exchange credentials for a JWT access token.
    Returns: { token, token_type, user }
    """
    user = (
        db.query(UserMaster)
        .filter(UserMaster.username == payload.username.strip().lower())
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact an administrator.",
        )

    # Stamp last login
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token({"sub": user.username, "role": user.role})

    return {
        "token":      token,
        "token_type": "bearer",
        "user":       _user_to_out(user),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new user account.
    - If NO users exist yet → open registration (first-run bootstrap).
    - Otherwise → admin JWT required.
    """
    # First-run: allow open registration
    total = db.query(UserMaster).count()
    if total > 0:
        # Require an admin token for subsequent registrations
        # (We call get_current_user manually here to keep the endpoint signature clean)
        from fastapi.security import HTTPBearer
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Ask an admin to create your account via /api/auth/admin/create-user",
        )

    username = payload.username.strip().lower()
    email    = payload.email.strip().lower()

    if db.query(UserMaster).filter(UserMaster.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(UserMaster).filter(UserMaster.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # First user is always admin
    role = "admin" if total == 0 else payload.role

    user = UserMaster(
        full_name       = payload.full_name.strip(),
        username        = username,
        email           = email,
        hashed_password = hash_password(payload.password),
        role            = role,
        is_active       = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.username, "role": user.role})
    return {
        "message":    "Account created successfully",
        "token":      token,
        "token_type": "bearer",
        "user":       _user_to_out(user),
    }


@router.post("/admin/create-user", status_code=status.HTTP_201_CREATED)
def admin_create_user(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    current_user: UserMaster = Depends(require_admin),
):
    """Admin-only: create any user with any role."""
    username = payload.username.strip().lower()
    email    = payload.email.strip().lower()

    if db.query(UserMaster).filter(UserMaster.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(UserMaster).filter(UserMaster.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = UserMaster(
        full_name       = payload.full_name.strip(),
        username        = username,
        email           = email,
        hashed_password = hash_password(payload.password),
        role            = payload.role,
        is_active       = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User created", "user": _user_to_out(user)}


@router.get("/me")
def get_me(current_user: UserMaster = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {"user": _user_to_out(current_user)}


@router.put("/me/password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    """Change the logged-in user's own password."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: UserMaster = Depends(require_admin),
):
    """Admin only: list all users in the user_master table."""
    users = db.query(UserMaster).order_by(UserMaster.created_at.desc()).all()
    return {"users": [_user_to_out(u) for u in users]}


@router.put("/users/{user_id}/toggle")
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserMaster = Depends(require_admin),
):
    """Admin only: activate or deactivate a user account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    user = db.query(UserMaster).filter(UserMaster.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active
    db.commit()
    return {
        "message":   f"User {'activated' if user.is_active else 'deactivated'}",
        "is_active": user.is_active,
    }


@router.put("/users/{user_id}/role")
def change_user_role(
    user_id: int,
    role: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: UserMaster = Depends(require_admin),
):
    """Admin only: change a user's role."""
    allowed = {"admin", "manager", "viewer"}
    if role not in allowed:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(allowed)}")

    user = db.query(UserMaster).filter(UserMaster.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    db.commit()
    return {"message": f"Role updated to '{role}'", "user": _user_to_out(user)}
