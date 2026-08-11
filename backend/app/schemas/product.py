from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ProductBase(BaseModel):
    barcode: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=100)
    purchase_price: Decimal = Field(default=Decimal("0"), ge=0)
    sale_price: Decimal = Field(ge=0)
    min_sale_price: Decimal | None = Field(default=None, ge=0)
    stock_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    low_stock_threshold: Decimal = Field(default=Decimal("0"), ge=0)
    # Sold by weight: the POS asks for a decimal weight rather than
    # stepping whole units, and quantities are shown to three decimals.
    # `unit` is the label that weight is displayed in.
    is_weighted: bool = False
    unit: str | None = Field(default=None, max_length=30)
    packaging_unit_label: str | None = Field(default=None, max_length=40)
    packaging_unit_quantity: Decimal | None = Field(default=None, gt=0)
    image_url: str | None = None
    description: str | None = None
    expiration_date: date | None = None
    category_id: int | None = None
    is_active: bool = True
    # Manager override of the automatic loyalty earn rate — null lets
    # services/loyalty.py compute it (margin-proportional + dead-stock
    # boost); 0 exempts the product; any other value replaces it outright.
    loyalty_point_multiplier: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "barcode", "sku", "brand", "unit", "packaging_unit_label", "image_url", "description",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class ProductCreate(ProductBase):
    @model_validator(mode="after")
    def opening_stock_needs_a_cost(self) -> "ProductCreate":
        """Stock on the shelf has to have cost something.

        purchase_price defaults to zero, so a product could be entered with
        an opening quantity and no cost at all. Nothing complains at the
        time — but that zero becomes the cost basis for those units, and the
        next delivery blends against it (see
        products.weighted_average_cost), understating the cost of the line
        from then on and quietly inflating its margin.
        """
        if self.stock_quantity and self.stock_quantity > 0 and self.purchase_price <= 0:
            raise ValueError(
                "A product entered with opening stock needs a purchase price — "
                "those units cost something, and without it every later "
                "delivery averages against zero."
            )
        return self


class ProductUpdate(BaseModel):
    # Deliberately no stock_quantity field here — stock must only ever
    # change through a purchase, a sale, or POST /adjustments/stock, all of
    # which log an InventoryTransaction. ProductCreate still allows setting
    # an initial stock_quantity (a brand-new product has no history to log
    # against yet).
    barcode: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=100)
    purchase_price: Decimal | None = Field(default=None, ge=0)
    sale_price: Decimal | None = Field(default=None, ge=0)
    min_sale_price: Decimal | None = Field(default=None, ge=0)
    low_stock_threshold: Decimal | None = Field(default=None, ge=0)
    is_weighted: bool | None = None
    unit: str | None = Field(default=None, max_length=30)
    packaging_unit_label: str | None = Field(default=None, max_length=40)
    packaging_unit_quantity: Decimal | None = Field(default=None, gt=0)
    image_url: str | None = None
    description: str | None = None
    expiration_date: date | None = None
    category_id: int | None = None
    is_active: bool | None = None
    loyalty_point_multiplier: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "barcode", "sku", "brand", "unit", "packaging_unit_label", "image_url", "description",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    # ── Dual-price management ──────────────────────────────────────────
    is_dual_priced: bool | None = None
    old_purchase_price: Decimal | None = None
    old_sale_price: Decimal | None = None
    old_price_stock_estimate: Decimal | None = Field(default=None, ge=0)
    collapse_to_tier: Literal["old", "new"] | None = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    # ── Dual-price fields (read-only) ──────────────────────────────────
    is_dual_priced: bool = False
    old_purchase_price: Decimal | None = None
    old_sale_price: Decimal | None = None
    old_price_stock_estimate: Decimal | None = Field(default=None, ge=0)
    dual_price_started_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

