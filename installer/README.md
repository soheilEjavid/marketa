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
