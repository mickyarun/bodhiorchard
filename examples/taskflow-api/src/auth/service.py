"""Authentication service — JWT creation, password hashing, token refresh."""

from datetime import datetime, timedelta, UTC

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.auth.models import User, RefreshToken

SECRET_KEY = "taskflow-dev-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, role: str) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(db: Session, user_id: int) -> str:
    """Create a long-lived refresh token and persist it."""
    import secrets

    token_value = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db_token = RefreshToken(user_id=user_id, token=token_value, expires_at=expires)
    db.add(db_token)
    db.commit()
    return token_value


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Verify credentials and return the user if valid."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def register_user(db: Session, email: str, password: str, full_name: str) -> User:
    """Create a new user account."""
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def revoke_refresh_token(db: Session, token: str) -> bool:
    """Revoke a refresh token (logout)."""
    db_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not db_token:
        return False
    db_token.revoked = True
    db.commit()
    return True
