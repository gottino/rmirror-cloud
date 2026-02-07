"""Tests for structured JSON logging and request context middleware.

Covers:
- JSONFormatter output shape and field inclusion
- configure_logging() sets levels correctly
- RequestContextMiddleware generates/preserves X-Request-ID
- Request timing (duration_ms) is reported
- Context vars (request_id, user_id) propagate to log records
- /health endpoint returns database and sync queue status
"""

import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.logging_config import JSONFormatter, configure_logging
from app.middleware.request_context import (
    RequestContextMiddleware,
    request_id_var,
    user_id_var,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(db_session: Session | None = None) -> FastAPI:
    """Create a minimal FastAPI app with RequestContextMiddleware registered."""

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    @app.get("/log-extra")
    async def log_extra():
        """Endpoint that logs with extra fields so we can assert context var propagation."""
        lgr = logging.getLogger("test.endpoint")
        lgr.info("inside request", extra={"event": "test.log"})
        return {"ok": True}

    if db_session is not None:
        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

    return app


# ---------------------------------------------------------------------------
# JSONFormatter tests
# ---------------------------------------------------------------------------

class TestJSONFormatter:
    """Tests for the JSON log formatter."""

    def test_output_is_valid_json(self):
        """Every formatted record must be parseable JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"

    def test_required_fields_present(self):
        """Output must contain timestamp, level, service, logger, message."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test", level=logging.WARNING, pathname="", lineno=0,
            msg="warn msg", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))

        assert "timestamp" in parsed
        assert parsed["level"] == "WARNING"
        assert parsed["service"] == "backend"
        assert parsed["logger"] == "app.test"
        assert parsed["message"] == "warn msg"

    def test_extra_fields_included(self):
        """Extra fields passed via logging `extra=` must appear in output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="sync done", args=(), exc_info=None,
        )
        # Simulate extra= fields (logger.info("x", extra={...}) sets attrs on record)
        record.event = "sync.done"
        record.queue_id = 42
        record.duration_ms = 123.4

        parsed = json.loads(formatter.format(record))
        assert parsed["event"] == "sync.done"
        assert parsed["queue_id"] == 42
        assert parsed["duration_ms"] == 123.4

    def test_extra_fields_not_present_when_unset(self):
        """Optional fields should be absent (not null) when not set on the record."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="basic", args=(), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        for field in ("event", "queue_id", "notebook_uuid", "page_uuid"):
            assert field not in parsed

    def test_exception_info_included(self):
        """When exc_info is set, the output must contain an 'exception' field."""
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="error occurred", args=(), exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "boom" in parsed["exception"]

    def test_context_var_request_id_auto_included(self):
        """request_id from ContextVar should appear automatically."""
        formatter = JSONFormatter()
        token = request_id_var.set("ctx-req-123")
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="msg", args=(), exc_info=None,
            )
            parsed = json.loads(formatter.format(record))
            assert parsed["request_id"] == "ctx-req-123"
        finally:
            request_id_var.reset(token)

    def test_context_var_user_id_auto_included(self):
        """user_id from ContextVar should appear automatically."""
        formatter = JSONFormatter()
        token = user_id_var.set(7)
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="msg", args=(), exc_info=None,
            )
            parsed = json.loads(formatter.format(record))
            assert parsed["user_id"] == 7
        finally:
            user_id_var.reset(token)

    def test_context_vars_absent_when_empty(self):
        """When context vars are at defaults, they should not appear."""
        formatter = JSONFormatter()
        tok_r = request_id_var.set("")
        tok_u = user_id_var.set(None)
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="msg", args=(), exc_info=None,
            )
            parsed = json.loads(formatter.format(record))
            assert "request_id" not in parsed
            assert "user_id" not in parsed
        finally:
            request_id_var.reset(tok_r)
            user_id_var.reset(tok_u)

    def test_message_formatting_with_args(self):
        """getMessage() should interpolate args into the message."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="count=%d name=%s", args=(5, "alice"), exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "count=5 name=alice"


# ---------------------------------------------------------------------------
# configure_logging tests
# ---------------------------------------------------------------------------

class TestConfigureLogging:
    """Tests for the configure_logging() setup function."""

    def _cleanup_root(self, original_handlers, original_level):
        """Restore root logger state after test."""
        root = logging.getLogger()
        root.handlers = original_handlers
        root.setLevel(original_level)

    def test_sets_info_level_by_default(self):
        root = logging.getLogger()
        orig_handlers = root.handlers[:]
        orig_level = root.level
        try:
            configure_logging(debug=False)
            assert root.level == logging.INFO
        finally:
            self._cleanup_root(orig_handlers, orig_level)

    def test_sets_debug_level_when_debug(self):
        root = logging.getLogger()
        orig_handlers = root.handlers[:]
        orig_level = root.level
        try:
            configure_logging(debug=True)
            assert root.level == logging.DEBUG
        finally:
            self._cleanup_root(orig_handlers, orig_level)

    def test_installs_json_formatter(self):
        root = logging.getLogger()
        orig_handlers = root.handlers[:]
        orig_level = root.level
        try:
            configure_logging()
            assert len(root.handlers) == 1
            assert isinstance(root.handlers[0].formatter, JSONFormatter)
        finally:
            self._cleanup_root(orig_handlers, orig_level)

    def test_quiets_noisy_loggers(self):
        root = logging.getLogger()
        orig_handlers = root.handlers[:]
        orig_level = root.level
        try:
            configure_logging()
            assert logging.getLogger("httpx").level == logging.WARNING
            assert logging.getLogger("httpcore").level == logging.WARNING
            assert logging.getLogger("urllib3").level == logging.WARNING
        finally:
            self._cleanup_root(orig_handlers, orig_level)


# ---------------------------------------------------------------------------
# RequestContextMiddleware tests
# ---------------------------------------------------------------------------

class TestRequestContextMiddleware:
    """Tests for the X-Request-ID middleware."""

    def test_generates_request_id_when_absent(self):
        """Middleware should generate a UUID request ID if none provided."""
        client = TestClient(_make_app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        req_id = resp.headers.get("X-Request-ID")
        assert req_id is not None
        assert len(req_id) == 36  # UUID format

    def test_preserves_client_request_id(self):
        """If X-Request-ID is sent by client, middleware should preserve it."""
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Request-ID": "client-abc-123"})
        assert resp.headers["X-Request-ID"] == "client-abc-123"

    def test_different_requests_get_different_ids(self):
        """Each request without a client ID should get a unique generated ID."""
        client = TestClient(_make_app())
        id1 = client.get("/ping").headers["X-Request-ID"]
        id2 = client.get("/ping").headers["X-Request-ID"]
        assert id1 != id2

    def test_request_logging_includes_structured_fields(self):
        """The middleware's access log should include event, method, path, status_code, duration_ms."""
        app = _make_app()
        client = TestClient(app)

        with patch("app.middleware.request_context.logger") as mock_logger:
            client.get("/ping")
            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args
            extra = call_kwargs.kwargs.get("extra") or call_kwargs[1].get("extra")
            assert extra["event"] == "http.request"
            assert extra["method"] == "GET"
            assert extra["path"] == "/ping"
            assert extra["status_code"] == 200
            assert "duration_ms" in extra

    def test_duration_ms_is_non_negative(self):
        """duration_ms should be a non-negative number."""
        app = _make_app()
        client = TestClient(app)

        with patch("app.middleware.request_context.logger") as mock_logger:
            client.get("/ping")
            extra = mock_logger.info.call_args.kwargs.get("extra") or mock_logger.info.call_args[1].get("extra")
            assert extra["duration_ms"] >= 0

    def test_user_id_var_reset_per_request(self):
        """user_id_var should be None at the start of each request."""
        app = _make_app()

        captured_user_ids = []

        @app.get("/capture-uid")
        async def capture_uid():
            captured_user_ids.append(user_id_var.get())
            return {"uid": user_id_var.get()}

        client = TestClient(app)

        # Set user_id from a previous context — middleware should reset it
        user_id_var.set(999)
        client.get("/capture-uid")
        # Inside the request handler, user_id should have been reset to None
        assert captured_user_ids[-1] is None


# ---------------------------------------------------------------------------
# Health endpoint integration test
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for the expanded /health endpoint."""

    def test_health_returns_database_ok(self, db: Session):
        """Health endpoint should report database=ok when DB is reachable."""
        from app.main import app

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["database"] == "ok"
        finally:
            app.dependency_overrides.clear()

    def test_health_returns_sync_queue_counts(self, db: Session):
        """Health endpoint should include sync_queue with pending/failed counts."""
        from app.main import app

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.get("/health")
            data = resp.json()
            assert "sync_queue" in data
            assert "pending" in data["sync_queue"]
            assert "failed" in data["sync_queue"]
            assert isinstance(data["sync_queue"]["pending"], int)
            assert isinstance(data["sync_queue"]["failed"], int)
        finally:
            app.dependency_overrides.clear()

    def test_health_has_request_id_header(self, db: Session):
        """Health response should include X-Request-ID from middleware."""
        from app.main import app

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert "X-Request-ID" in resp.headers
        finally:
            app.dependency_overrides.clear()

    def test_health_preserves_client_request_id(self, db: Session):
        """Health endpoint should echo back client-provided X-Request-ID."""
        from app.main import app

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.get("/health", headers={"X-Request-ID": "health-check-99"})
            assert resp.headers["X-Request-ID"] == "health-check-99"
        finally:
            app.dependency_overrides.clear()

    def test_health_degraded_on_db_failure(self):
        """Health should report degraded status when database query fails."""
        from app.main import app
        from unittest.mock import MagicMock

        mock_db = MagicMock(spec=Session)
        mock_db.execute.side_effect = Exception("DB unreachable")
        # query().filter().count() chain for sync queue
        mock_query = MagicMock()
        mock_query.filter.return_value.count.return_value = 0
        mock_db.query.return_value = mock_query

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["database"] == "error"
        finally:
            app.dependency_overrides.clear()
