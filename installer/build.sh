#!/usr/bin/env bash
#
# Build the offline Windows installer for MARKETA, from Linux/WSL.
#
# The product of this script is a single .exe that needs no network and no
# administrator-installed Python on the shop's machine: the interpreter, every
# dependency wheel and the built frontend all travel inside it. The shop is on
# the other end of an Iranian consumer connection — an installer that starts
# downloading prerequisites is an installer that fails at the till.
#
# Two things about the payload are deliberate:
#
#   * app/seed.py is excluded. It fabricates a year of trading and ships
#     well-known logins; a real shop starts empty, with the one admin account
#     the wizard creates.
#   * psycopg is excluded by default. A shop install runs on SQLite, and the
#     PostgreSQL driver is 14MB of a 45MB payload. Pass --with-postgres if a
#     particular deployment needs it.
#
# Usage:
#   ./installer/build.sh [--with-postgres] [--skip-frontend] [--payload-only]
#
set -euo pipefail

readonly PYTHON_VERSION="3.12.10"
# Pinned so that every later build is byte-identical to the one vetted here.
# This proves the artifact has not changed; it is not an independent proof of
# provenance (python.org no longer publishes MD5 sums on its release pages —
# for that, verify the .sigstore bundle alongside the zip).
readonly PYTHON_EMBED_SHA256="4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
readonly PYTHON_EMBED_ZIP="python-${PYTHON_VERSION}-embed-amd64.zip"
readonly PYTHON_EMBED_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_EMBED_ZIP}"
# The _pth filename tracks the interpreter's major.minor, e.g. python312._pth.
readonly PYTHON_PTH="python$(echo "$PYTHON_VERSION" | cut -d. -f1,2 | tr -d .)._pth"

readonly INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(dirname "$INSTALLER_DIR")"
readonly BACKEND_DIR="$REPO_ROOT/backend"
readonly FRONTEND_DIR="$REPO_ROOT/frontend"
readonly CACHE_DIR="$INSTALLER_DIR/cache"
readonly BUILD_DIR="$INSTALLER_DIR/build"
readonly PAYLOAD_DIR="$BUILD_DIR/payload"
readonly DIST_DIR="$INSTALLER_DIR/dist"

WITH_POSTGRES=0
SKIP_FRONTEND=0
PAYLOAD_ONLY=0

for argument in "$@"; do
    case "$argument" in
        --with-postgres) WITH_POSTGRES=1 ;;
        --skip-frontend) SKIP_FRONTEND=1 ;;
        --payload-only) PAYLOAD_ONLY=1 ;;
        -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "Unknown option: $argument" >&2; exit 2 ;;
    esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die() { printf '\033[31merror:\033[0m %s\n' "$1" >&2; exit 1; }

# ── Tools ────────────────────────────────────────────────────────────────
step "Checking build tools"

for tool in curl rsync; do
    command -v "$tool" >/dev/null || die "$tool is not installed."
done
if [[ $PAYLOAD_ONLY -eq 0 ]]; then
    command -v makensis >/dev/null || die "makensis is not installed (sudo apt install nsis)."
fi
if [[ $SKIP_FRONTEND -eq 0 ]]; then
    command -v npm >/dev/null || die "npm is not installed, and --skip-frontend was not passed."
fi

# uv, not pip, resolves the dependency set: pip's --platform changes only
# which wheel tags are acceptable and still evaluates environment markers
# against *this* machine, so `sys_platform != "win32"` stays true and it
# insists on uvloop, which has no Windows wheel at all. uv evaluates the
# markers for the target platform, which is the whole job here.
UV="$BACKEND_DIR/.venv/bin/uv"
if [[ ! -x "$UV" ]]; then
    if command -v uv >/dev/null; then
        UV="$(command -v uv)"
    else
        echo "uv not found; installing it into the backend virtualenv."
        "$BACKEND_DIR/.venv/bin/python" -m pip install --quiet uv || die "could not install uv."
    fi
fi
"$UV" --version >/dev/null || die "uv is not working."

HOST_PYTHON="$BACKEND_DIR/.venv/bin/python"
[[ -x "$HOST_PYTHON" ]] || die "backend/.venv is missing; create it before building."

# ── Python runtime ───────────────────────────────────────────────────────
step "Fetching the embeddable Python runtime"

mkdir -p "$CACHE_DIR"
if [[ ! -f "$CACHE_DIR/$PYTHON_EMBED_ZIP" ]]; then
    curl -sSL --retry 8 --retry-delay 2 -o "$CACHE_DIR/$PYTHON_EMBED_ZIP" "$PYTHON_EMBED_URL" \
        || die "could not download $PYTHON_EMBED_URL"
fi
actual_sha="$(sha256sum "$CACHE_DIR/$PYTHON_EMBED_ZIP" | cut -d' ' -f1)"
if [[ "$actual_sha" != "$PYTHON_EMBED_SHA256" ]]; then
    die "checksum mismatch for $PYTHON_EMBED_ZIP
  expected $PYTHON_EMBED_SHA256
  got      $actual_sha
Delete installer/cache/$PYTHON_EMBED_ZIP and rebuild; if it still differs,
do not ship the result."
fi
echo "Verified $PYTHON_EMBED_ZIP against its pinned checksum."

# ── Frontend ─────────────────────────────────────────────────────────────
if [[ $SKIP_FRONTEND -eq 0 ]]; then
    step "Building the frontend"
    (cd "$FRONTEND_DIR" && npm run build)
fi
[[ -f "$FRONTEND_DIR/dist/index.html" ]] || die "frontend/dist/index.html is missing; build the frontend."

# ── Payload ──────────────────────────────────────────────────────────────
step "Assembling the payload"

rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR/python"
# Python's own zipfile rather than unzip(1): one less thing for whoever
# builds this to have to install, and the archive holds Windows files whose
# permission bits nothing here cares about.
"$HOST_PYTHON" -m zipfile -e "$CACHE_DIR/$PYTHON_EMBED_ZIP" "$PAYLOAD_DIR/python"

# The embeddable runtime starts with an isolated sys.path listing only its own
# stdlib zip. Adding site-packages and turning `site` back on is what lets it
# import the dependencies below; without this it cannot even find fastapi.
#
# `..` — the payload root, one level up from python.exe — matters just as
# much and is easy to miss. A ._pth file *replaces* the normal sys.path
# computation, and that includes the rule that would otherwise put a script's
# own directory (or, for `-m`, the working directory) on the path. Without
# this line, running `python\python.exe migrate.py` from the payload root
# fails with "No module named 'marketa_runtime'", and `-m app.bootstrap` with
# "No module named 'app'" — both verified on Windows.
cat > "$PAYLOAD_DIR/python/$PYTHON_PTH" <<PTH
python$(echo "$PYTHON_VERSION" | cut -d. -f1,2 | tr -d .).zip
.
..
Lib\\site-packages
import site
PTH

step "Installing Windows dependencies"

REQUIREMENTS="$BUILD_DIR/requirements-windows.txt"
mkdir -p "$BUILD_DIR"
# pyproject.toml stays the single source of truth for the dependency set, so
# that adding one there cannot silently be forgotten here.
"$HOST_PYTHON" - "$BACKEND_DIR/pyproject.toml" "$WITH_POSTGRES" > "$REQUIREMENTS" <<'PY'
import sys
import tomllib

pyproject_path, with_postgres = sys.argv[1], sys.argv[2] == "1"
with open(pyproject_path, "rb") as handle:
    dependencies = tomllib.load(handle)["project"]["dependencies"]

for requirement in dependencies:
    if not with_postgres and requirement.lower().startswith("psycopg"):
        continue
    print(requirement)
PY
echo "Dependency set:"
sed 's/^/  /' "$REQUIREMENTS"

"$UV" pip install \
    --target "$PAYLOAD_DIR/python/Lib/site-packages" \
    --python-platform windows \
    --python-version "$(echo "$PYTHON_VERSION" | cut -d. -f1,2)" \
    --only-binary :all: \
    --no-compile \
    --quiet \
    -r "$REQUIREMENTS" \
    || die "could not assemble the Windows dependency set."

step "Copying the application"

# --exclude seed.py: see the note at the top of this file. __pycache__ would
# ship Linux-built .pyc files that Windows would ignore but still carry.
rsync -a \
    --exclude='seed.py' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='static/' \
    "$BACKEND_DIR/app/" "$PAYLOAD_DIR/app/"
rsync -a --exclude='__pycache__/' --exclude='*.pyc' \
    "$BACKEND_DIR/alembic/" "$PAYLOAD_DIR/alembic/"
cp "$BACKEND_DIR/alembic.ini" "$PAYLOAD_DIR/alembic.ini"

# The built interface, served by the API process itself (app/web.py).
mkdir -p "$PAYLOAD_DIR/app/static"
rsync -a "$FRONTEND_DIR/dist/" "$PAYLOAD_DIR/app/static/"

# The Windows entry points.
cp "$INSTALLER_DIR/runtime/"*.py "$PAYLOAD_DIR/"
cp "$INSTALLER_DIR/runtime/MARKETA.vbs" "$PAYLOAD_DIR/"

# The self-tests travel with the package on purpose. They are a few KB, they
# import nothing that is not already here, and when a shop says "it stopped
# working" they answer — from that machine, not from a guess — whether the
# runtime, the port and the database are healthy.
mkdir -p "$PAYLOAD_DIR/tests"
cp "$INSTALLER_DIR/tests/"*.py "$PAYLOAD_DIR/tests/"

# ── Sanity checks ────────────────────────────────────────────────────────
step "Checking the payload"

[[ ! -e "$PAYLOAD_DIR/app/seed.py" ]] || die "seed.py leaked into the payload."
[[ -f "$PAYLOAD_DIR/app/static/index.html" ]] || die "the frontend bundle is missing."
[[ -f "$PAYLOAD_DIR/python/pythonw.exe" ]] || die "pythonw.exe is missing."
[[ -d "$PAYLOAD_DIR/python/Lib/site-packages/fastapi" ]] || die "fastapi is missing."
[[ -d "$PAYLOAD_DIR/python/Lib/site-packages/tzdata" ]] || die "tzdata is missing (Asia/Tehran would not resolve)."
[[ -f "$PAYLOAD_DIR/app/bootstrap.py" ]] || die "bootstrap.py is missing."
[[ -f "$PAYLOAD_DIR/create_admin.py" ]] || die "create_admin.py is missing."
[[ -f "$PAYLOAD_DIR/tests/selftest.py" ]] || die "the self-tests are missing."
grep -qx '\.\.' "$PAYLOAD_DIR/python/$PYTHON_PTH" \
    || die "the payload root is not on the embedded interpreter's path (see the _pth note above)."
[[ -f "$PAYLOAD_DIR/alembic/env.py" ]] || die "the migration chain is missing."
if find "$PAYLOAD_DIR/python/Lib/site-packages" -name '*.so' -print -quit | grep -q .; then
    die "Linux shared objects in the payload — the dependency set was resolved for the wrong platform."
fi
echo "Payload looks right ($(du -sh "$PAYLOAD_DIR" | cut -f1))."

if [[ $PAYLOAD_ONLY -eq 1 ]]; then
    step "Done (payload only)"
    echo "$PAYLOAD_DIR"
    exit 0
fi

# ── Installer ────────────────────────────────────────────────────────────
step "Compiling the installer"

VERSION="$("$HOST_PYTHON" - "$BACKEND_DIR/pyproject.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    print(tomllib.load(handle)["project"]["version"])
PY
)"

mkdir -p "$DIST_DIR"
makensis -V2 \
    "-DVERSION=$VERSION" \
    "-DPAYLOAD_DIR=$PAYLOAD_DIR" \
    "-DDIST_DIR=$DIST_DIR" \
    "$INSTALLER_DIR/marketa.nsi" \
    || die "makensis failed."

step "Done"
ls -lh "$DIST_DIR"/MARKETA-Setup-*.exe
