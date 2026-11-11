#!/usr/bin/env python3
"""Generate backend/.env.example from app.config.Settings.

Usage (from the backend directory):
    python scripts/generate_env_example.py          # write .env.example
    python scripts/generate_env_example.py --check  # exit 1 with a diff if stale

Every Settings field becomes one upper-case variable, grouped by the comment
sections in app/config.py. Required fields come first. Fields whose default is
None are written commented out, because an empty value would override the
default with an empty string. Secrets always get placeholders, never real or
developer values.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BACKEND_DIR / "app" / "config.py"
OUTPUT_PATH = BACKEND_DIR / ".env.example"

sys.path.insert(0, str(BACKEND_DIR))

# Optional settings without a default that look like secrets get a placeholder.
SECRET_WORDS = ("key", "secret", "password", "token")

PLACEHOLDERS = {
    "secret_key": "change-me-generate-with-openssl-rand-hex-32",
    "database_url": "sqlite:///./rmirror.db",
    "postgres_user": "rmirror",
    "postgres_password": "change-me",
    "redis_url": "redis://localhost:6379/0",
    "s3_endpoint_url": "http://localhost:9000",
    "s3_access_key": "your-s3-access-key",
    "s3_secret_key": "your-s3-secret-key",
    "google_ai_api_key": "your-google-ai-api-key",
    "clerk_publishable_key": "pk_test_your_publishable_key",
    "clerk_secret_key": "sk_test_your_secret_key",
    "clerk_jwks_url": "https://your-app.clerk.accounts.dev/.well-known/jwks.json",
    "clerk_webhook_secret": "whsec_your_webhook_secret",
    "resend_api_key": "re_your_api_key",
    "admin_email": "admin@example.com",
    "notion_client_id": "your-notion-client-id",
    "notion_client_secret": "your-notion-client-secret",
    "notion_redirect_uri": "http://localhost:3000/integrations/notion/callback",
    "todoist_client_id": "your-todoist-client-id",
    "todoist_client_secret": "your-todoist-client-secret",
    "todoist_redirect_uri": "http://localhost:3000/integrations/todoist/callback",
    "integration_master_key": "generate-with-fernet-generate-key",
    "umami_url": "https://analytics.example.com",
    "umami_website_id": "your-umami-website-id",
}

# The template must be safe to copy to production, so DEBUG is always off.
FORCED = {"debug": "false"}


def _is_secret(name: str) -> bool:
    return any(word in name for word in SECRET_WORDS)


def _format_default(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _sections_from_source(source: str, field_names: set) -> dict:
    """Map field name -> comment text of the closest preceding section comment."""
    sections = {}
    current = "General"
    for line in source.splitlines():
        m = re.match(r"^    # (.+?)\s*$", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"^    (\w+)\s*:", line)
        if m and m.group(1) in field_names:
            sections[m.group(1)] = current
    return sections


def render() -> str:
    from app.config import Settings

    fields = Settings.model_fields
    sections = _sections_from_source(CONFIG_PATH.read_text(), set(fields))

    required = [n for n, f in fields.items() if f.is_required()]
    groups = {}
    for name in fields:
        if name in required:
            continue
        groups.setdefault(sections.get(name, "General"), []).append(name)

    lines = [
        "# rMirror Cloud backend environment template.",
        "# GENERATED from app/config.py by scripts/generate_env_example.py. Do not edit by hand;",
        "# run `python scripts/generate_env_example.py` after changing Settings.",
        "# Copy to .env. Commented-out variables are optional and unset by default.",
        "",
        "# Required",
    ]
    for name in required:
        lines.append(f"{name.upper()}={_value_for(name, fields[name])}")

    for title, names in groups.items():
        lines += ["", f"# {title}"]
        for name in names:
            field = fields[name]
            value = _value_for(name, field)
            prefix = "# " if field.default is None else ""
            lines.append(f"{prefix}{name.upper()}={value}")
    return "\n".join(lines) + "\n"


def _value_for(name: str, field) -> str:
    if name in FORCED:
        return FORCED[name]
    if name in PLACEHOLDERS:
        return PLACEHOLDERS[name]
    if field.default is None:
        return f"your-{name.replace('_', '-')}" if _is_secret(name) else ""
    return _format_default(field.default)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if .env.example is stale")
    args = parser.parse_args(argv)

    expected = render()
    if args.check:
        current = OUTPUT_PATH.read_text() if OUTPUT_PATH.exists() else ""
        if current == expected:
            return 0
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=".env.example (on disk)",
            tofile=".env.example (generated)",
        )
        sys.stdout.writelines(diff)
        print("\n.env.example is out of date; run: python scripts/generate_env_example.py")
        return 1

    OUTPUT_PATH.write_text(expected)
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
