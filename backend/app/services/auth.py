from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User

# TODO(security): remove this dev-only auth bypass once real role-based
# permissions (frontend login flow + token wiring) are implemented.
_DEV_BYPASS_USERNAME = "admin"

security_scheme = HTTPBearer(auto_error=False)


class Role(StrEnum):
    ADMIN = "admin"
    CASHIER = "cashier"
    MANAGER = "manager"
    INVENTORY_MANAGER = "inventory_manager"
    ACCOUNTANT = "accountant"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    # No fallback to the old unsalted-SHA256 scheme: every seeded user was
    # re-hashed to bcrypt as part of this upgrade (see seed.py / the
    # one-time re-hash performed on existing installs). A hash in the old
    # format simply won't verify — that account needs its password reset.
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # Not a valid bcrypt hash (e.g. still the legacy "sha256$..." format).
        return False


def create_access_token(user_id: int, role: str) -> str:
    """Issue a signed JWT (HS256) with standard sub/iat/exp claims plus role."""
    now = datetime.now(UTC)
    expiry = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": expiry}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT. Returns {user_id, role} or raises."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = int(payload["sub"])
        role = payload["role"]
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"user_id": user_id, "role": role}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    database: Session = Depends(get_db),
) -> User:
    # TODO(security): remove this dev-only auth bypass once real role-based
    # permissions (frontend login flow + token wiring) are implemented.
    if settings.dev_disable_auth:
        bypass_user = database.scalar(
            select(User).where(User.username == _DEV_BYPASS_USERNAME)
        )
        if bypass_user is not None and bypass_user.is_active:
            return bypass_user
        return User(
            id=0,
            username="dev-bypass",
            password_hash="",
            full_name="Dev Auth Bypass",
            role="admin",
            is_active=True,
        )
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(credentials.credentials)
    user = database.get(User, payload["user_id"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_role(*roles: str):
    """Dependency factory: require one of the given roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' not authorized. Required: {', '.join(roles)}",
            )
        return current_user
    return _check