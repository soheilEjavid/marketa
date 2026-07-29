from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services.categories import create_category, get_category, update_category


def test_update_category_partial_update_preserves_other_fields() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        category = create_category(database, CategoryCreate(name="Snacks", description="desc"))

        updated = update_category(database, category, CategoryUpdate(description="new desc"))
        assert updated.name == "Snacks"
        assert updated.description == "new desc"

        reloaded = get_category(database, category.id)
        assert reloaded.description == "new desc"
