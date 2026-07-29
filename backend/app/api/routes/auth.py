from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import DatabaseSession
from app.models.entities import User
from app.services.auth import get_current_user, hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginInput(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginOutput(BaseModel):
    token: str
    user_id: int
    username: str
    full_name: str
    role: str


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.post("/login", response_model=LoginOutput)
async def login(data: LoginInput, database: DatabaseSession):
    from sqlalchemy import select
    user = database.scalar(select(User).where(User.username == data.username))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")
    token = create_access_token(user.id, user.role)
    return LoginOutput(token=token, user_id=user.id, username=user.username, full_name=user.full_name, role=user.role)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user