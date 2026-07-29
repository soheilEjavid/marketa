from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(admin|cashier|manager|inventory_manager|accountant)$")


class UserRoleUpdate(BaseModel):
    is_active: bool
