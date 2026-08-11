# The Windows installer

One `.exe` that installs MARKETA on a shop's PC with no internet connection
and no pre-installed Python. Built from Linux/WSL.

```bash
sudo apt install nsis        # once
./installer/build.sh         # -> installer/dist/MARKETA-Setup-<version>.exe
```

Options: `--skip-frontend` (reuse an existing `frontend/dist`),
`--payload-only` (assemble but don't compile), `--with-postgres` (see below).

## What ships, and what deliberately doesn't

The payload is about 53MB and compresses to a ~14MB installer:

| | |
|---|---|
| `python/` | CPython 3.12.10 embeddable, plus every dependency wheel |
| `app/` | the backend, **minus `seed.py`** |
| `app/static/` | the built React interface |
| `alembic/` | the full migration chain |
| `*.py`, `MARKETA.vbs` | the Windows entry points, from `installer/runtime/` |

**`seed.py` is excluded.** It fabricates a year of trading and ships
well-known logins (`admin`/`Admin@123` and friends), which in a real shop is
a security hole rather than a convenience. A shop starts with an empty
database and the single admin account the wizard creates. `build.sh` asserts
the exclusion, so it cannot quietly come back.

**`psycopg` is excluded by default.** A shop install runs on SQLite, and the
PostgreSQL driver is 14MB of the payload. Pass `--with-postgres` if a
particular deployment needs it.

**`tzdata` is included.** Windows has no IANA time-zone database, so without
that wheel `zoneinfo` cannot resolve `Asia/Tehran`, `config.py`'s validator
rejects it, and the app refuses to start — taking the entire business-day
layer with it.

## The layout on the shop's machine

```
C:\Program Files\MARKETA\        the program — replaced wholesale by an update
C:\ProgramData\MARKETA\          the shop's own data — never touched
    marketa.db                   the database
    .env                         SECRET_KEY, database path, clock settings
    logs\                        rotating logs; the server runs windowless
    backups\                     the last 10 pre-migration snapshots
```

That split is the whole reason an update is safe. The wizard refuses a data
folder placed inside the program folder, because the update deletes the
program folder outright.

## What an update does

Re-run a newer `MARKETA-Setup-*.exe` over an existing install. In order:

1. `stop.py` stops the running server — Windows will not overwrite a `.pyd`
   that a live process holds open.
2. The program folder is replaced. The data folder is not.
3. `configure.py` finds the existing `.env` and **leaves it alone**, keeping
   the SECRET_KEY, the database path and the shop's clock settings.
4. `migrate.py` snapshots the database with SQLite's backup API, then runs
   `alembic upgrade head`. **If the migration fails it restores the snapshot,
   reports it and stops the install.** This matters because
   `db/migration_check.py` only *logs* schema drift and never blocks startup:
   without the restore, a half-migrated database would come up and misbehave
   quietly.
5. The admin-account page is skipped, because a database with users is not a
   fresh install.

Before shipping an update to a shop, run the new migrations against a copy of
that shop's real database. A migration that is clean on an empty schema can
still trip over a unique constraint on real data.

## Runtime entry points (`installer/runtime/`)

| | |
|---|---|
| `marketa_runtime.py` | shared: puts the program dir on `sys.path`, makes the data dir the CWD (`app.core.config` reads `.env` relative to CWD), sets up rotating logs |
| `launch.py` | starts uvicorn on 127.0.0.1 and opens the browser once the port answers; a second click just opens another tab |
| `configure.py` | writes `.env` once, and records where the data dir is |
| `migrate.py` | backup → `alembic upgrade head` → restore on failure |
| `stop.py` | stops the server, refusing to kill a reused PID that now belongs to something else |
| `MARKETA.vbs` | what the shortcuts run, so no console window appears |

The server listens on loopback only. One shop, one till, one machine — there
is no reason for the whole ledger to be reachable from the neighbourhood's
wifi with only a login page in front of it.

## The window

MARKETA opens as a standalone window — no address bar, no tabs — using
Chromium's `--app=` mode through the Edge that ships with Windows 10/11.
That costs the payload nothing: no second runtime, no Node build step.
Chrome is the fallback; if neither exists the default browser is used
instead. `appwindow.py` finds the browser through the `App Paths` registry
key rather than a hardcoded directory, because on a real machine Edge sits
under `Program Files (x86)` while Chrome sits under `Program Files`.

Three things about it are load-bearing:

- **A dedicated `--user-data-dir`.** Without one, launching `msedge --app`
  while Edge is already running hands the window to the existing browser and
  the process we spawned exits immediately with status 0. Anything waiting on
  it to learn when the window closed would conclude the shopkeeper had closed
  it a second after startup. Measured: seven Edge processes running, our
  process gone within six seconds.
- **`--disable-features=Translate,…`.** Edge otherwise floats a "Translate
  page from Persian?" bubble over the till every time it opens. One stray
  click and the shop is running a machine-translated cash register.
- **A favicon.** Chromium takes the window and taskbar icon from the page's
  icon. A custom `.lnk` icon does not change it — the taskbar button belongs
  to the running window, not to whatever launched it. Hence
  `frontend/public/favicon.svg`, which also gives the browser tab an icon in
  ordinary development.

**Closing the window stops the server.** The package is built so the shop
starts one thing, so it should stop one thing; a server left running behind a
closed window is invisible and would need a second shortcut to be rid of. The
shutdown is uvicorn's graceful one, so a sale that is mid-request finishes.
The exception is the default-browser fallback: a tab closing is not something
we can observe, so there the server stays up and "Stop MARKETA" is the way
out.

**Clicking the shortcut twice gives one window** — the second launch raises
the existing one rather than opening another.

## Self-tests, on the machine that matters

`installer/tests/` ships inside the payload, so any installed copy can be
checked from the shop's own machine. From the install directory:

```bat
chcp 65001
python\python.exe tests\selftest.py          :: runtime, wheels, tzdata, bcrypt
python\python.exe tests\httpcheck.py 8000    :: HTTP surface of a running server
python\python.exe tests\edgecheck.py         :: PID reuse, stale PIDs, port conflicts
python\python.exe tests\windowcheck.py       :: the app window, start to close
```

(`chcp 65001` because the console is cp1252 by default and these print
Persian.)

They exist because a Linux dry run cannot see the things that actually broke.
All three of these were found by running them on real Windows:

1. **The payload root was not importable.** A `._pth` file *replaces* the
   normal `sys.path` computation, including the rule that puts a script's own
   directory (or, for `-m`, the working directory) on the path. Every entry
   point died with `No module named 'marketa_runtime'`, and
   `-m app.bootstrap` with `No module named 'app'`. Fixed by the `..` line in
   the generated `_pth`, which `build.sh` now asserts is there.
2. **The first-admin step ran in the wrong directory.** `app.core.config`
   reads `.env` relative to the working directory, and the installer runs from
   the program directory where there is none — so it came up with no
   SECRET_KEY and died in configuration validation. Hence `create_admin.py`,
   which calls `prepare()` before importing anything from `app`.
3. **`tasklist` reports "nothing matched" on stdout, with exit code 0.**
   `stop.py` read that sentence as an image name, so a server that had died
   without cleaning up produced "this PID belongs to INFO: No tasks are
   running…, not MARKETA" and a failure exit instead of quietly tidying the
   stale file away.

## Known limits

- **Unsigned.** Windows SmartScreen will warn on first run; the shopkeeper
  has to choose "More info → Run anyway". A code-signing certificate is an
  annual cost.
- **Not a Windows service.** It runs as a normal program from a shortcut,
  optionally at login. A till that is switched on and used by one person all
  day does not need more.
- **Single machine.** Two PCs sharing one database would need PostgreSQL and
  a network setup; that is a different project.
- The port is `MARKETA_PORT` in `.env`, default 8000. Change it only if
  something else on the machine already uses it.
- To have the shop's day end at 3am rather than midnight, set
  `STORE_DAY_BOUNDARY_HOUR=3` in `.env` — see `app/core/store_time.py`.

## Building notes

The dependency set is resolved with `uv`, not `pip`. `pip --platform` only
changes which wheel *tags* are acceptable; it still evaluates environment
markers against the build machine, so `sys_platform != "win32"` stays true,
it insists on `uvloop`, and `uvloop` has no Windows wheel at all —
`ResolutionImpossible`. `uv --python-platform windows` evaluates the markers
for the target, which is the entire job.

The Python runtime download is pinned by SHA-256 in `build.sh`, so every
later build is byte-identical to the one that was vetted. That pins the
artifact; it is not independent proof of provenance (python.org no longer
publishes MD5 sums on its release pages — for that, verify the `.sigstore`
bundle published alongside the zip).
