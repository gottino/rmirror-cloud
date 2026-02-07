"""Centralized JSON logging configuration for the backend."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record):
        # Import here to avoid circular imports at module load time
        from app.middleware.request_context import request_id_var, user_id_var

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "backend",
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Auto-include request_id and user_id from context vars
        req_id = request_id_var.get()
        if req_id:
            log_entry["request_id"] = req_id
        uid = user_id_var.get()
        if uid is not None:
            log_entry["user_id"] = uid

        # Include extra fields if set on the record
        for field in (
            "request_id", "user_id", "event", "notebook_uuid", "page_uuid",
            "queue_id", "duration_ms", "status_code", "method", "path",
            "target", "error", "retry_count", "batch_size",
            "input_bytes", "output_chars", "model",
        ):
            val = getattr(record, field, None)
            if val is not None:
                log_entry[field] = val

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def configure_logging(debug: bool = False):
    """Set up JSON-formatted logging for the entire application.

    Args:
        debug: If True, set log level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
