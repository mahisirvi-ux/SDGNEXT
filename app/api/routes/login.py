from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth import verify_password, create_access_token, get_current_user
from app.models.domain import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == req.username,
        User.is_active == True
    ).first()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"user_id": user.id, "role": user.role, "username": user.username})

    response = JSONResponse(content={
        "message": "Login successful",
        "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.role}
    })
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=43200, samesite="lax")
    return response


@router.post("/logout")
def logout():
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token")
    return response


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role}
