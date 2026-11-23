"""
Cached quota status, so the local API can report it without a cloud round-trip.

The agent refreshes it on its own loop (at sign-in, after upload batches and
every ``REFRESH_SECONDS``); request handlers only read it.
"""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime


class QuotaCache:
    """Thread-safe holder of the last quota answer from the backend."""

    REFRESH_SECONDS = 5 * 60

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._host: str | None = None
        self._fetched_at: datetime | None = None
        self._last_attempt: float | None = None
        self._stale = True

    def store(self, quota_status: dict, host: str | None = None) -> None:
        """Remember a fresh /quota/status answer, fetched from ``host``.

        A snapshot for another host is None, so a refresh that finishes after the
        user switched environment cannot show the old server's numbers.
        """
        with self._lock:
            self._data = dict(quota_status)
            self._host = host
            self._fetched_at = datetime.now(UTC)
            self._stale = False

    def clear(self) -> None:
        """Forget everything (signed out, other environment)."""
        with self._lock:
            self._data = None
            self._host = None
            self._fetched_at = None
            self._last_attempt = None
            self._stale = True

    def mark_stale(self) -> None:
        """Ask for a refresh at the next opportunity (sign-in, after an upload batch)."""
        with self._lock:
            self._stale = True

    def note_attempt(self) -> None:
        """A refresh was attempted now (successful or not)."""
        with self._lock:
            self._last_attempt = self._clock()
            self._stale = False

    def refresh_due(self) -> bool:
        """True if marked stale, never attempted, or the last attempt is older than REFRESH_SECONDS."""
        with self._lock:
            if self._stale or self._last_attempt is None:
                return True
            return self._clock() - self._last_attempt >= self.REFRESH_SECONDS

    def snapshot(self, host: str | None = None) -> dict | None:
        """``{used, limit, remaining, reset_at, fetched_at}`` or None if never fetched
        (or, with ``host``, fetched from another host).

        ``limit`` -1 means unlimited; ``remaining`` is then None.
        """
        with self._lock:
            data, fetched_at, stored_host = self._data, self._fetched_at, self._host
        if data is None or fetched_at is None:
            return None
        if host is not None and stored_host is not None and stored_host != host:
            return None
        used = _as_int(data.get("used"), 0)
        limit = _as_int(data.get("limit"), 0)
        remaining = None if limit < 0 else max(0, limit - used)
        return {
            "used": used,
            "limit": limit,
            "remaining": remaining,
            "reset_at": iso_utc(data.get("reset_at"), naive_is_utc=True),
            "fetched_at": iso_utc(fetched_at),
        }


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def iso_utc(value: object, naive_is_utc: bool = False) -> str | None:
    """ISO 8601 UTC string ending in ``Z`` (seconds precision), or None.

    Accepts datetimes and ISO strings. Naive values are taken as local time (that
    is how the watcher records its timestamps), or as UTC with ``naive_is_utc``
    (the backend sends naive UTC).
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None and naive_is_utc:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
