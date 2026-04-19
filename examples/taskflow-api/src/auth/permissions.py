"""Role-based permission checks for TaskFlow."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.auth.service import decode_access_token

security = HTTPBearer()

ROLE_HIERARCHY = {"admin": 3, "member": 2, "viewer": 1}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Extract and validate the current user from the JWT token."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return {"user_id": int(payload["sub"]), "role": payload.get("role", "member")}


def require_role(minimum_role: str):
    """Dependency that enforces a minimum role level."""
    min_level = ROLE_HIERARCHY.get(minimum_role, 0)

    def checker(current_user: dict = Depends(get_current_user)):
        user_level = ROLE_HIERARCHY.get(current_user["role"], 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role} role or higher",
            )
        return current_user

    return checker
