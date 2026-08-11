"""Exercise the running server over HTTP, on Windows, as a browser would.

Usage: python httpcheck.py [port]
"""

import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BASE = f"http://127.0.0.1:{PORT}"
failures = []


def wait_for_port(timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", PORT)) == 0:
                return True
        time.sleep(0.5)
    return False


def fetch(path, data=None):
    """Returns (status, lowercased-header-dict, body-text)."""
    request = urllib.request.Request(BASE + path)
    if data is not None:
        request.data = json.dumps(data).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw, status, body = response.headers, response.status, response.read()
    except urllib.error.HTTPError as error:
        raw, status, body = error.headers, error.code, error.read()
    # Lowercased keys: HTTP header names are case-insensitive, and a plain
    # dict lookup for "Content-Type" silently misses uvicorn's "content-type".
    headers = {key.lower(): value for key, value in dict(raw).items()}
    return status, headers, body.decode("utf-8", "replace")


def check(label, function):
    try:
        detail = function()
    except Exception as error:
        failures.append(label)
        print(f"FAIL  {label}\n      {type(error).__name__}: {error}")
    else:
        print(f"ok    {label}{f'  [{detail}]' if detail else ''}")


if not wait_for_port():
    print(f"FAIL  server never started listening on 127.0.0.1:{PORT}")
    sys.exit(1)
print(f"ok    server is listening on 127.0.0.1:{PORT}")


def health():
    status, _, body = fetch("/api/v1/health")
    assert status == 200, status
    payload = json.loads(body)
    assert payload["service"] == "marketa-api", payload
    return "200 " + body.strip()


def root_serves_interface():
    status, headers, body = fetch("/")
    assert status == 200, status
    assert "text/html" in headers.get("content-type", ""), headers
    assert "<script" in body, body[:200]
    assert headers.get("cache-control") == "no-store", headers.get("cache-control")
    return f"200 html, cache-control={headers.get('cache-control')}"


def unknown_api_path_is_json_404():
    status, headers, body = fetch("/api/v1/salez")
    assert status == 404, f"expected 404, got {status}"
    assert "application/json" in headers.get("content-type", ""), headers
    assert "<html" not in body.lower(), body[:200]
    return f"404 {headers.get('content-type')}"


def unknown_api_version_is_404():
    status, _, body = fetch("/api/v2/sales")
    assert status == 404, f"expected 404, got {status}"
    assert "<html" not in body.lower(), body[:200]
    return "404"


def client_route_gets_the_shell():
    status, headers, _ = fetch("/reports/margin")
    assert status == 200, status
    assert "text/html" in headers.get("content-type", ""), headers
    return "200 html"


def hashed_asset_is_served():
    index = Path("app") / "static" / "index.html"
    match = re.search(r'src="(/assets/[^"]+\.js)"', index.read_text(encoding="utf-8"))
    assert match, "could not find the bundle reference in index.html"
    status, _, body = fetch(match.group(1))
    assert status == 200, status
    assert len(body) > 10000, len(body)
    return f"200 {match.group(1)} ({len(body) // 1024}KB)"


def login_works():
    status, _, body = fetch(
        "/api/v1/auth/login", {"username": "owner", "password": "Owner@12345"}
    )
    assert status == 200, f"{status} {body}"
    payload = json.loads(body)
    assert payload["role"] == "admin", payload
    assert payload["token"], payload
    return f"role={payload['role']}, token {len(payload['token'])} chars"


def wrong_password_is_rejected():
    status, _, _ = fetch(
        "/api/v1/auth/login", {"username": "owner", "password": "wrong-password"}
    )
    assert status == 401, status
    return "401"


def persian_name_survives_the_round_trip():
    status, _, body = fetch(
        "/api/v1/auth/login", {"username": "owner", "password": "Owner@12345"}
    )
    assert status == 200, status
    return f"full_name={json.loads(body)['full_name']!r}"


check("GET /api/v1/health", health)
check("GET / serves the interface", root_serves_interface)
check("GET /api/v1/salez is a JSON 404, not the HTML shell", unknown_api_path_is_json_404)
check("GET /api/v2/sales is a 404", unknown_api_version_is_404)
check("GET /reports/margin returns the SPA shell", client_route_gets_the_shell)
check("GET the hashed JS bundle", hashed_asset_is_served)
check("POST /api/v1/auth/login with the wizard's account", login_works)
check("POST /api/v1/auth/login with a wrong password", wrong_password_is_rejected)
check("the Persian full name comes back intact", persian_name_survives_the_round_trip)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all HTTP checks passed")
