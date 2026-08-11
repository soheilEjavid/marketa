import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.config import settings
from app.db.migration_check import check_migration_drift
from app.db.session import engine
from app.web import frontend_index, mount_frontend

logger = logging.getLogger("marketa")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema is owned entirely by Alembic — no more create_all() silently
    # patching over a database that's missing a table/column. This only
    # logs; it never auto-fixes or blocks startup (see migration_check.py).
    check_migration_drift(engine)
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


# response_model=None: the return type is a union of a file response and a
# plain dict, and without this FastAPI tries to build a response model out of
# FileResponse and refuses at import time.
@app.get("/", response_model=None)
async def root() -> FileResponse | dict[str, str]:
    # A packaged install serves the shop's interface here; a bare API
    # checkout (no bundled frontend) keeps answering with the name/docs
    # pointer it always did.
    index = frontend_index()
    if index is not None:
        return FileResponse(index, headers={"Cache-Control": "no-store"})
    return {"name": settings.app_name, "docs": "/docs"}


# Last, deliberately: the SPA catch-all must be the lowest-priority route
# in the application, consulted only once every API route has missed.
mount_frontend(app)
