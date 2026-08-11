"""Create the first administrator, as the installer calls it.

`app/bootstrap.py` holds the logic and knows nothing about where a packaged
install keeps its files — correctly, since it is part of the application. This
is the thin wrapper that supplies the missing half: `prepare()` makes the data
directory the working directory *before* anything from `app` is imported,
because `app.core.config` reads `.env` relative to the working directory and
the installer runs this from the program directory, where there is no `.env`.

Calling `python -m app.bootstrap` straight from the installer looked
equivalent and was not: it came up with no SECRET_KEY and died in
configuration validation, which is a baffling way to be told that the
working directory is wrong.

Arguments are passed straight through to `app.bootstrap`:

    python create_admin.py --username owner --full-name "..." \
        --password-file "...\\admin-password.txt"
"""

import sys

import marketa_runtime

marketa_runtime.prepare()

from app.bootstrap import main  # noqa: E402  (must follow prepare())

if __name__ == "__main__":
    sys.exit(main())
