from fastapi import APIRouter

from app.api.routes import (
    adjustments,
    audit,
    auth,
    categories,
    checks,
    customers,
    dashboard,
    health,
    inventory,
    loyalty,
    products,
    purchases,
    reports,
    sales,
    shifts,
    suppliers,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(categories.router)
api_router.include_router(customers.router)
api_router.include_router(dashboard.router)
api_router.include_router(suppliers.router)
api_router.include_router(sales.router)
api_router.include_router(purchases.router)
api_router.include_router(inventory.router)
api_router.include_router(reports.router)
api_router.include_router(adjustments.router)
api_router.include_router(audit.router)
api_router.include_router(checks.router)
api_router.include_router(shifts.router)
api_router.include_router(users.router)
api_router.include_router(loyalty.router)
