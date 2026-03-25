"""Authentication API endpoints — login, register, token refresh, logout."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from src.shared.database import get_db
from src.auth.service import (
    authenticate_user,
    register_user,
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    user = authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(db, user.id),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account and return tokens."""
    user = register_user(db, body.email, body.password, body.full_name)
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(db, user.id),
    )


@router.post("/logout")
def logout(refresh_token: str, db: Session = Depends(get_db)):
    """Revoke a refresh token."""
    revoked = revoke_refresh_token(db, refresh_token)
    if not revoked:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"detail": "Logged out"}
