"""Fail when settings that production needs are missing.

Run from the backend directory (deploy.sh pipes it into
`poetry run python -`), so that `app.config` and `.env` are found:

    poetry run python scripts/check_config.py

Prints the NAMES of missing settings, never their values. Exit code 0 when
everything is present, 1 otherwise.
"""

import os
import sys


def missing_settings(settings) -> list[str]:
    """Return the names of required settings that are empty or unsuitable.

    The list of required settings lives in app.config (shared with start-up).
    """
    from app.config import config_problems

    missing = []
    database_url = str(getattr(settings, "database_url", "") or "")
    if not database_url or database_url.startswith("sqlite"):
        missing.append("DATABASE_URL (must not be SQLite)")
    missing.extend(config_problems(settings)[0])
    return missing


def main() -> int:
    # When run as a file, sys.path[0] is scripts/; the app lives one level up.
    # When piped to `python -`, the current directory is already on the path.
    sys.path.insert(0, os.getcwd())
    from pydantic import ValidationError

    from app.config import get_settings

    try:
        settings = get_settings()
    except ValidationError as exc:
        # Only the field names: the error text can contain input values.
        names = sorted({str(err["loc"][0]).upper() for err in exc.errors() if err.get("loc")})
        print("Config check FAILED: invalid or missing settings: " + ", ".join(names))
        return 1

    missing = missing_settings(settings)
    if missing:
        print("Config check FAILED: missing settings: " + ", ".join(missing))
        return 1
    print("Config check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
