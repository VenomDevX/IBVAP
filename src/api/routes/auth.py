"""
IBVAP — Auth Routes
Login, token generation, and user management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional

from src.api.auth import (
    verify_password, hash_password, create_access_token,
    require_auth, require_admin
)
from src.database.db import get_database
from src.database.repository import Repository

router = APIRouter()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"
    full_name: str = ""


@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return JWT token."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    user = repo.get_user(form_data.username)
    session.close()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(data={"sub": user.username, "role": user.role})

    return LoginResponse(
        access_token=token,
        username=user.username,
        role=user.role,
    )


@router.get("/me")
async def get_current_user_info(user: dict = Depends(require_auth)):
    """Get current user information."""
    return user


@router.post("/users")
async def create_user(user_data: UserCreate, admin: dict = Depends(require_admin)):
    """Create a new user (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    existing = repo.get_user(user_data.username)
    if existing:
        session.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    repo.create_user(
        user_data.username,
        hash_password(user_data.password),
        user_data.role,
        user_data.full_name,
    )
    repo.create_audit_log("create_user", admin["username"],
                          {"new_user": user_data.username, "role": user_data.role})
    session.close()

    return {"message": f"User {user_data.username} created", "role": user_data.role}
