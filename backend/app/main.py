import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.migration_check import check_migration_drift
from app.db.session import engine

logger = logging.getLogger("marketa")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema is owned entirely by Alembic — no more create_all() silently
    # patching over a database that's missing a table/column. This only
    # logs; it never auto-fixes or blocks startup (see migration_check.py).
    check_migration_drift(engine)
    # TODO(security): remove this dev-only auth bypass once real role-based
    # permissions (frontend login flow + token wiring) are implemented.
    if settings.dev_disable_auth:
        banner = (
            "\n"
            + "!" * 78 + "\n"
            + "! DEV_DISABLE_AUTH IS ENABLED — ALL AUTHENTICATION IS BYPASSED.".ljust(77) + "!\n"
            + "! Every request is treated as the seeded 'admin' user. DO NOT enable".ljust(77) + "!\n"
            + "! this outside local development, and never in a deployed environment.".ljust(77) + "!\n"
            + "!" * 78
        )
        logger.warning(banner)
        print(banner)  # noqa: T201 - intentionally loud, must be impossible to miss
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Integrated store management API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
