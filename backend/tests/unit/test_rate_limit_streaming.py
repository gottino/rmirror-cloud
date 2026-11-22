"""Streamed responses pass through the rate-limit middleware intact.

slowapi's ASGI middleware re-sent the response start before every body chunk,
so only the first chunk of a StreamingResponse reached the client (page PDFs
arrived as their first line, 9 bytes).
"""

from io import BytesIO

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.middleware.rate_limit import RateLimitMiddleware, install_rate_limiting

PDF_LIKE = b"%PDF-1.4\n" + b"line of content\n" * 500 + b"%%EOF\n"


def _app() -> FastAPI:
    app = FastAPI()
    install_rate_limiting(app)

    @app.get("/stream")
    async def stream():
        # BytesIO iterates line by line: one body message per line.
        return StreamingResponse(BytesIO(PDF_LIKE), media_type="application/pdf")

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    return app


def test_streaming_response_arrives_complete():
    resp = TestClient(_app()).get("/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == PDF_LIKE


def test_single_body_response_still_works():
    resp = TestClient(_app()).get("/plain")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_app_uses_the_fixed_middleware():
    from app.main import app

    assert any(m.cls is RateLimitMiddleware for m in app.user_middleware)
