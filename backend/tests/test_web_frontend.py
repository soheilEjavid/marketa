"""The bundled-frontend routes, and the API paths they must keep their hands off.

The failure this file mostly exists to prevent: a catch-all that answers
for `/api/v1/<typo>` with 200 and the HTML shell. Every caller then reads
a success status and falls over while parsing markup as JSON, which is a
long way from the "404, no such endpoint" the mistake deserves.
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app import web


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A stand-in for what the build script copies into `app/static/`."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        "<title>MARKETA</title><div id=root></div>", encoding="utf-8"
    )
    (static / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.ico").write_bytes(b"\x00icon")
    # A secret sitting beside the bundle, as it does in a real install —
    # the traversal test below aims at this file.
    (tmp_path / ".env").write_text("SECRET_KEY=not-for-the-public", encoding="utf-8")
    monkeypatch.setattr(web, "_STATIC_DIR", static)
    return static


@pytest.fixture
def client(bundle):
    app = FastAPI()
    router = APIRouter()

    @router.get("/sales")
    async def sales() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router, prefix="/api/v1")
    web.mount_frontend(app)
    return TestClient(app)


def test_declared_api_route_still_answers(client):
    response = client.get("/api/v1/sales")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unknown_api_path_is_a_json_404_not_the_html_shell(client):
    response = client.get("/api/v1/salez")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "MARKETA" not in response.text


def test_unknown_api_version_is_also_refused(client):
    # /api/v2/... matches no declared route and must not be treated as a
    # client-side page just because the prefix is unfamiliar.
    assert client.get("/api/v2/sales").status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/api", "/api/v1"])
def test_framework_paths_are_reserved(path):
    assert web._is_reserved_path(path) is True


@pytest.mark.parametrize("path", ["/customers", "/reports/margin", "/"])
def test_application_paths_are_not_reserved(path):
    assert web._is_reserved_path(path) is False


def test_client_side_route_gets_the_uncached_shell(client):
    response = client.get("/reports/margin")
    assert response.status_code == 200
    assert "<div id=root></div>" in response.text
    # Stale shells point at asset filenames an update has already deleted.
    assert response.headers["cache-control"] == "no-store"


def test_hashed_assets_are_served_from_the_mount(client):
    response = client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_real_bundled_file_is_served_as_itself(client):
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content == b"\x00icon"


def test_traversal_out_of_the_bundle_is_refused(bundle):
    # An HTTP client would normalize "../" away before it ever reached the
    # route, so this aims at the resolver the route depends on.
    assert web._bundled_file("../.env") is None
    assert web._bundled_file("assets/../../.env") is None
    assert web._bundled_file("assets/index-abc123.js") is not None


def test_nothing_is_mounted_without_a_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "_STATIC_DIR", tmp_path / "absent")
    app = FastAPI()
    before = len(app.routes)
    web.mount_frontend(app)
    assert web.frontend_index() is None
    assert len(app.routes) == before
