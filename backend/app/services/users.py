from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import User
from app.schemas.users import UserCreate
from app.services.auth import hash_password


class DuplicateUsernameError(ValueError):
    pass


def list_users(database: Session, *, active_only: bool = True) -> list[User]:
    query = select(User).order_by(User.full_name)
    if active_only:
        query = query.where(User.is_active.is_(True))
    return list(database.scalars(query))


def get_user(database: Session, user_id: int) -> User | None:
    return database.get(User, user_id)


def create_user(database: Session, data: UserCreate) -> User:
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        is_active=True,
    )
    database.add(user)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateUsernameError("Username is already in use") from error
    database.refresh(user)
    return user


def set_user_active(database: Session, user: User, is_active: bool) -> User:
    user.is_active = is_active
    database.commit()
    database.refresh(user)
    return user
