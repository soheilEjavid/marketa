from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class DuplicateCategoryNameError(ValueError):
    pass


def list_categories(database: Session, *, search: str | None = None) -> list[Category]:
    query = select(Category).order_by(Category.name)
    if search:
        query = query.where(Category.name.ilike(f"%{search.strip()}%"))
    return list(database.scalars(query))


def get_category(database: Session, category_id: int) -> Category | None:
    return database.get(Category, category_id)


def create_category(database: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump())
    database.add(category)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateCategoryNameError(
            f"Category '{data.name}' already exists"
        ) from error
    database.refresh(category)
    return category


def update_category(database: Session, category: Category, data: CategoryUpdate) -> Category:
    dump = data.model_dump(exclude_unset=True)
    for field, value in dump.items():
        setattr(category, field, value)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise DuplicateCategoryNameError(
            f"Category '{data.name}' already exists"
        ) from error
    database.refresh(category)
    return category
