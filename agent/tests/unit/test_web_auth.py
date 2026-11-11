"""
Tests for the local web UI sign-in callback and request guard.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.config import Config
from app.logging_config import RedactQuerySecretsFilter
from app.sync.cloud_sync import CloudSync
from app.web import routes
from app.web.app import create_app

PORT = 5556  # matches test_config
BASE_URL = f"http://localhost:{PORT}"
LIVE_KEY = "pk_live_example"
TEST_KEY = "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"


@pytest.fixture
def save_mock():
    # Never write the real config file from tests
    with patch.object(Config, "save", autospec=True) as save:
        yield save


@pytest.fixture
def config(test_config_with_token, save_mock):
    test_config_with_token.api.use_clerk_auth = True
    return test_config_with_token


@pytest.fixture
def cloud_sync(config):
    return CloudSync(config)


@pytest.fixture
def app(config, cloud_sync):
    flask_app = create_app(config, cloud_sync, agent=None)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def no_register():
    with patch.object(routes, "register_agent_with_backend", new=AsyncMock()) as mocked:
        yield mocked


def _clerk_config_response(key: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"clerk_publishable_key": key}
    return resp


def _start_bridge(client, key: str = LIVE_KEY):
    with patch.object(routes.httpx, "get", return_value=_clerk_config_response(key)):
        return client.get("/auth/bridge", base_url=BASE_URL)


def _state_from_live_bridge(client) -> str:
    resp = _start_bridge(client)
    assert resp.status_code == 302
    location = urlparse(resp.headers["Location"])
    callback = parse_qs(location.query)["callback"][0]
    parsed = urlparse(callback)
    assert parsed.scheme == "http"
    assert parsed.netloc == f"localhost:{PORT}"
    assert parsed.path == "/auth/callback"
    return parse_qs(parsed.query)["state"][0]


def _backend_returning(status: int):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


class TestBridgeState:
    def test_live_bridge_puts_encoded_state_in_callback(self, client):
        resp = _start_bridge(client)
        assert resp.status_code == 302
        raw_query = urlparse(resp.headers["Location"]).query
        # The callback parameter is fully URL-encoded so its own query survives
        assert raw_query.startswith("callback=http%3A%2F%2Flocalhost")
        assert "%3Fstate%3D" in raw_query
        state = _state_from_live_bridge(client)
        assert len(state) >= 32

    def test_each_bridge_visit_gets_a_new_state(self, client):
        assert _state_from_live_bridge(client) != _state_from_live_bridge(client)

    def test_local_bridge_template_carries_state(self, client, app):
        resp = _start_bridge(client, key=TEST_KEY)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "'?state=' + encodeURIComponent(AUTH_STATE)" in html
        store = app.config["AUTH_STATES"]
        (state,) = list(store._states)
        assert f'var AUTH_STATE = "{state}";' in html


class TestCallback:
    def _callback(self, client, **params):
        return client.get("/auth/callback", query_string=params, base_url=BASE_URL)

    def test_missing_state_is_rejected(self, client, config, mock_keychain, no_register, save_mock):
        resp = self._callback(client, token="attacker-token")
        assert resp.status_code == 400
        assert config.api.token == "test-jwt-token"
        mock_keychain.store_token.assert_not_called()
        save_mock.assert_not_called()

    def test_wrong_state_is_rejected(self, client, config, mock_keychain, no_register):
        _state_from_live_bridge(client)
        resp = self._callback(client, state="not-the-state", token="attacker-token")
        assert resp.status_code == 400
        assert config.api.token == "test-jwt-token"
        mock_keychain.store_token.assert_not_called()

    def test_expired_state_is_rejected(self, client, config, mock_keychain, no_register):
        state = _state_from_live_bridge(client)
        later = routes.time.monotonic() + routes.AUTH_STATE_TTL_SECONDS + 1
        with patch.object(routes.time, "monotonic", return_value=later):
            resp = self._callback(client, state=state, token="new-token")
        assert resp.status_code == 400
        assert config.api.token == "test-jwt-token"
        mock_keychain.store_token.assert_not_called()

    def test_invalid_token_is_rejected(self, client, config, cloud_sync, mock_keychain, no_register, save_mock):
        state = _state_from_live_bridge(client)
        cloud_sync.client, seen = _backend_returning(401)
        resp = self._callback(client, state=state, token="bad-token")
        assert resp.status_code == 401
        assert "Could not verify" in resp.get_data(as_text=True)
        assert seen and seen[0].headers["Authorization"] == "Bearer bad-token"
        assert config.api.token == "test-jwt-token"
        assert cloud_sync.authenticated is False
        mock_keychain.store_token.assert_not_called()
        save_mock.assert_not_called()

    def test_backend_unreachable_is_rejected(self, client, config, cloud_sync, mock_keychain, no_register):
        state = _state_from_live_bridge(client)
        with patch.object(routes, "verify_agent_token", new=AsyncMock(return_value=False)):
            resp = self._callback(client, state=state, token="new-token")
        assert resp.status_code == 401
        assert config.api.token == "test-jwt-token"
        mock_keychain.store_token.assert_not_called()

    def test_valid_state_and_token_signs_in(self, client, config, cloud_sync, mock_keychain, no_register, save_mock):
        state = _state_from_live_bridge(client)
        cloud_sync.client, seen = _backend_returning(200)
        resp = self._callback(client, state=state, token="new-token")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/dashboard")
        assert seen[0].url.path.endswith("/sync/stats")
        assert seen[0].headers["Authorization"] == "Bearer new-token"
        assert config.api.token == "new-token"
        assert cloud_sync.authenticated is True
        mock_keychain.store_token.assert_called_once()
        save_mock.assert_called_once()
        no_register.assert_awaited_once()

    def test_state_is_single_use(self, client, config, cloud_sync, mock_keychain, no_register):
        state = _state_from_live_bridge(client)
        with patch.object(routes, "verify_agent_token", new=AsyncMock(return_value=True)):
            first = self._callback(client, state=state, token="new-token")
            second = self._callback(client, state=state, token="other-token")
        assert first.status_code == 302
        assert second.status_code == 400
        assert config.api.token == "new-token"

    def test_callback_allowed_as_cross_site_navigation(self, client, cloud_sync, no_register):
        state = _state_from_live_bridge(client)
        with patch.object(routes, "verify_agent_token", new=AsyncMock(return_value=True)):
            resp = client.get(
                "/auth/callback",
                query_string={"state": state, "token": "new-token"},
                base_url=BASE_URL,
                headers={"Sec-Fetch-Site": "cross-site", "Referer": "https://dashboard.example/agent"},
            )
        assert resp.status_code == 302


class TestVerifyAgentToken:
    def test_true_on_200(self, cloud_sync):
        cloud_sync.client, _ = _backend_returning(200)
        assert asyncio.run(routes.verify_agent_token(cloud_sync, "t")) is True

    def test_false_on_401(self, cloud_sync):
        cloud_sync.client, _ = _backend_returning(401)
        assert asyncio.run(routes.verify_agent_token(cloud_sync, "t")) is False

    def test_false_on_network_error(self, cloud_sync):
        def handler(request):
            raise httpx.ConnectError("unreachable", request=request)

        cloud_sync.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert asyncio.run(routes.verify_agent_token(cloud_sync, "t")) is False


class TestRequestGuard:
    @pytest.mark.parametrize("host", ["evil.example", f"evil.example:{PORT}", "localhost", "localhost:1234"])
    def test_foreign_host_is_rejected(self, client, host):
        resp = client.get("/health", base_url=f"http://{host}")
        assert resp.status_code == 403

    @pytest.mark.parametrize("host", [f"localhost:{PORT}", f"127.0.0.1:{PORT}"])
    def test_loopback_host_is_allowed(self, client, host):
        resp = client.get("/health", base_url=f"http://{host}")
        assert resp.status_code == 200

    def test_bare_names_allowed_on_port_80(self, config, cloud_sync):
        config.web.port = 80
        flask_app = create_app(config, cloud_sync)
        resp = flask_app.test_client().get("/health", base_url="http://localhost")
        assert resp.status_code == 200

    def test_cross_origin_post_is_rejected(self, client, cloud_sync):
        cloud_sync.authenticated = True
        with patch("app.sync.initial_sync.InitialSync") as initial_sync:
            resp = client.post(
                "/api/sync/initial", base_url=BASE_URL, headers={"Origin": "https://evil.example"}
            )
        assert resp.status_code == 403
        initial_sync.assert_not_called()

    def test_other_local_port_origin_is_rejected(self, client):
        resp = client.post("/api/sync/trigger", base_url=BASE_URL, headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 403

    def test_null_origin_is_rejected(self, client):
        resp = client.post("/api/sync/trigger", base_url=BASE_URL, headers={"Origin": "null"})
        assert resp.status_code == 403

    def test_cross_site_fetch_metadata_is_rejected(self, client):
        resp = client.post("/api/sync/trigger", base_url=BASE_URL, headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403

    @pytest.mark.parametrize("origin", [f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"])
    def test_same_origin_post_is_allowed(self, client, origin):
        resp = client.post(
            "/api/sync/trigger",
            base_url=BASE_URL,
            headers={"Origin": origin, "Sec-Fetch-Site": "same-origin"},
        )
        assert resp.status_code == 200

    def test_post_without_origin_is_allowed(self, client):
        resp = client.post("/api/sync/trigger", base_url=BASE_URL)
        assert resp.status_code == 200


class TestAccessLogRedaction:
    def test_token_and_state_are_redacted(self):
        record = logging.LogRecord(
            "werkzeug", logging.INFO, __file__, 1,
            '%s - - [%s] %s', ("127.0.0.1", "date", '"GET /auth/callback?state=abc&token=secret.jwt HTTP/1.1" 302 -'),
            None,
        )
        assert RedactQuerySecretsFilter().filter(record) is True
        message = record.getMessage()
        assert "secret.jwt" not in message
        assert "abc" not in message
        assert "/auth/callback?state=[REDACTED]&token=[REDACTED] HTTP/1.1" in message

    def test_other_lines_untouched(self):
        record = logging.LogRecord(
            "werkzeug", logging.INFO, __file__, 1, '%s "%s"', ("127.0.0.1", "GET /api/status"), None
        )
        RedactQuerySecretsFilter().filter(record)
        assert record.getMessage() == '127.0.0.1 "GET /api/status"'

    def test_filter_installed_on_werkzeug_logger(self, app):
        werkzeug_logger = logging.getLogger("werkzeug")
        filters = [f for f in werkzeug_logger.filters if isinstance(f, RedactQuerySecretsFilter)]
        assert len(filters) == 1

