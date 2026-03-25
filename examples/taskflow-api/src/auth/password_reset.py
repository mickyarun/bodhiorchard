"""Password reset flow — token generation, validation, and password update."""

import secrets
from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.service import hash_password


# In-memory reset tokens (use Redis in production)
_reset_tokens: dict[str, dict] = {}


def request_password_reset(db: Session, email: str) -> str | None:
    """Generate a password reset token and queue an email."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None  # Don't reveal if email exists

    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = {
        "user_id": user.id,
        "expires": datetime.now(UTC) + timedelta(hours=1),
    }
    # Queue email to worker (via notifications service)
    return token


def validate_reset_token(token: str) -> int | None:
    """Validate a reset token and return the user ID."""
    data = _reset_tokens.get(token)
    if not data:
        return None
    if datetime.now(UTC) > data["expires"]:
        del _reset_tokens[token]
        return None
    return data["user_id"]


def reset_password(db: Session, token: str, new_password: str) -> bool:
    """Reset a user's password using a valid token."""
    user_id = validate_reset_token(token)
    if user_id is None:
        return False

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False

    user.hashed_password = hash_password(new_password)
    db.commit()
    del _reset_tokens[token]
    return True
