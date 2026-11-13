"""Fail when settings that production needs are missing.

Run from the backend directory (deploy.sh pipes it into
`poetry run python -`), so that `app.config` and `.env` are found:

    poetry run python scripts/check_config.py

Prints the NAMES of missing settings, never their values. Exit code 0 when
everything is present, 1 otherwise.
"""

import os
import sys

# Used only when the deployed code is older than the shared list in app.config
# (deploy.sh runs this script against the CURRENT code before switching to the
# new commit). The new code is checked again, with the shared list, after install.
FALLBACK_REQUIRED = [
    "SECRET_KEY",
    "CLERK_JWKS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_WEBHOOK_SECRET",
    "GOOGLE_AI_API_KEY",
    "INTEGRATION_MASTER_KEY",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET_NAME",
]


def missing_settings(settings) -> list[str]:
    """Return the names of required settings that are empty or unsuitable.

    The list of required settings lives in app.config (shared with start-up).
    Code deployed before that list existed is checked against FALLBACK_REQUIRED.
    """
    missing = []
    database_url = str(getattr(settings, "database_url", "") or "")
    if not database_url or database_url.startswith("sqlite"):
        missing.append("DATABASE_URL (must not be SQLite)")
    try:
        from app.config import config_problems
    except ImportError:
        for name in FALLBACK_REQUIRED:
            value = getattr(settings, name.lower(), None)
            if value is None or not str(value).strip():
                missing.append(name)
        return missing
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
