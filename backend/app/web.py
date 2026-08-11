"""Serving the built frontend from the API process.

A shop install is one process on one port: uvicorn serves both `/api/v1`
and the React bundle, so the shopkeeper starts one thing and opens one
address. The build script copies `frontend/dist/` into `app/static/`;
that directory is not in the repo, so in development none of this
activates and `npm run dev` keeps serving :5173 with its own proxy.

The catch-all that makes client-side routing work is the delicate part.
It must never answer for an API path: a request to a misspelled endpoint
has to come back as a JSON 404, not as 200 with the HTML shell, or every
caller — the frontend's own `api.ts` included — sees "success" and then
fails while parsing markup, which is a genuinely confusing way to debug
a typo. `_is_reserved_path` is that guard, and it runs before anything
else in the fallback.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Prefixes the SPA fallback must never answer for. `/api` is listed
# independently of the configured prefix so that a request to a wrong or
# future version (`/api/v2/sales`) still 404s as JSON rather than being
# handed the HTML shell.
_RESERVED_PREFIXES = (
    settings.api_v1_prefix,
    "/api",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def frontend_index() -> Path | None:
    """The bundled `index.html`, or None when no frontend was packaged."""
    index = _STATIC_DIR / "index.html"
    return index if index.is_file() else None


def _is_reserved_path(path: str) -> bool:
    for prefix in _RESERVED_PREFIXES:
        prefix = prefix.rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _bundled_file(relative_path: str) -> Path | None:
    """A real file inside the bundle for this URL path, or None.

    Resolves before comparing so that `../` in the URL cannot walk out of
    the static directory and serve, say, the `.env` file sitting beside it.
    """
    candidate = (_STATIC_DIR / relative_path).resolve()
    if not candidate.is_relative_to(_STATIC_DIR.resolve()):
        return None
    return candidate if candidate.is_file() else None


def _index_response(index: Path) -> FileResponse:
    # The shell must not be cached: after an update it is the one file that
    # has the same URL as before but points at newly hashed asset names, so
    # a cached copy would ask for JS/CSS that the update deleted.
    return FileResponse(index, headers={"Cache-Control": "no-store"})


def mount_frontend(app: FastAPI) -> None:
    """Attach the bundled frontend. No-op when nothing was packaged.

    Call this *after* `include_router`, so that every declared API route is
    matched before the catch-all is even consulted.
    """
    index = frontend_index()
    if index is None:
        return

    # Hashed filenames, so these are safe to cache hard and cheap to serve
    # through StaticFiles rather than the fallback below.
    app.mount(
        "/assets",
        StaticFiles(directory=_STATIC_DIR / "assets"),
        name="assets",
    )

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def spa_fallback(spa_path: str) -> FileResponse:
        if _is_reserved_path("/" + spa_path):
            raise HTTPException(status_code=404, detail="Not Found")
        # Anything genuinely in the bundle (favicon, manifest) is served as
        # itself; every other path is a client-side route.
        bundled = _bundled_file(spa_path) if spa_path else None
        if bundled is not None:
            return FileResponse(bundled)
        return _index_response(index)
