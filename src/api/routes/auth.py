"""
IBVAP — Auth Routes
Login, token generation, user management, and signups.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List

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
    allowed_areas: List[str] = []


class UserResponse(BaseModel):
    username: str
    role: str
    full_name: str
    is_active: bool
    allowed_areas: List[str]


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"
    full_name: str = ""
    allowed_areas: List[str] = []


class UserSignup(BaseModel):
    username: str
    password: str
    full_name: str = ""


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_areas: Optional[List[str]] = None


@router.post("/signup", response_model=UserResponse)
async def signup(user_data: UserSignup):
    """Register a new user. The first user becomes an admin automatically."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    existing = repo.get_user(user_data.username)
    if existing:
        session.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    # If this is the first user, make them admin. Otherwise, operator.
    user_count = repo.count_users()
    role = "admin" if user_count == 0 else "operator"
    
    # Operators could be inactive by default for security, but we leave active for now
    is_active = True

    new_user = repo.create_user(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        role=role,
        full_name=user_data.full_name,
        is_active=is_active
    )
    
    response = UserResponse(
        username=new_user.username,
        role=new_user.role,
        full_name=new_user.full_name,
        is_active=new_user.is_active,
        allowed_areas=new_user.allowed_areas
    )
    session.close()
    return response


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
        allowed_areas=user.allowed_areas
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(require_auth)):
    """Get current user information."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    db_user = repo.get_user(user["username"])
    session.close()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return UserResponse(
        username=db_user.username,
        role=db_user.role,
        full_name=db_user.full_name,
        is_active=db_user.is_active,
        allowed_areas=db_user.allowed_areas
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(admin: dict = Depends(require_admin)):
    """List all users (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)
    
    users = repo.get_all_users()
    session.close()
    
    return [
        UserResponse(
            username=u.username,
            role=u.role,
            full_name=u.full_name,
            is_active=u.is_active,
            allowed_areas=u.allowed_areas
        ) for u in users
    ]


@router.post("/users", response_model=UserResponse)
async def create_user(user_data: UserCreate, admin: dict = Depends(require_admin)):
    """Create a new user (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    existing = repo.get_user(user_data.username)
    if existing:
        session.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = repo.create_user(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        full_name=user_data.full_name,
        allowed_areas=user_data.allowed_areas
    )
    repo.create_audit_log("create_user", admin["username"],
                          {"new_user": user_data.username, "role": user_data.role})
    
    response = UserResponse(
        username=new_user.username,
        role=new_user.role,
        full_name=new_user.full_name,
        is_active=new_user.is_active,
        allowed_areas=new_user.allowed_areas
    )
    session.close()
    return response


@router.put("/users/{username}", response_model=UserResponse)
async def update_user(username: str, update_data: UserUpdate, admin: dict = Depends(require_admin)):
    """Update a user's role, status, or allowed areas (admin only)."""
    db = get_database()
    session = db.get_session()
    repo = Repository(session)

    user = repo.get_user(username)
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found")

    if update_data.role is not None:
        user.role = update_data.role
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    if update_data.allowed_areas is not None:
        user.allowed_areas = update_data.allowed_areas

    session.commit()
    
    repo.create_audit_log("update_user", admin["username"], {"updated_user": username})
    
    response = UserResponse(
        username=user.username,
        role=user.role,
        full_name=user.full_name,
        is_active=user.is_active,
        allowed_areas=user.allowed_areas
    )
    session.close()
    return response
