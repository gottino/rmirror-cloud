"""Sign-out and 401 handling against a fake in-memory keyring (no real keychain)."""

from unittest.mock import MagicMock

import httpx
import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from app.config import APIConfig, Config
from app.sync.cloud_sync import AuthenticationRequiredError, CloudSync

API_URL = "http://test-api.rmirror.io/api/v1"
KEYCHAIN_USER = "test-api.rmirror.io"


class InMemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError("not found")
        del self.store[(service, username)]


@pytest.fixture
def fake_keyring(monkeypatch, tmp_path):
    backend = InMemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    monkeypatch.setattr(Config, "get_default_config_path", staticmethod(lambda: tmp_path / "config.yaml"))
    yield backend
    keyring.set_keyring(previous)


def _signed_in_config(backend) -> Config:
    config = Config(api=APIConfig(url=API_URL, use_clerk_auth=True))
    config.api.token = "secret-token"
    assert backend.store, "token should have been stored in the fake keychain"
    return config


def _signed_in_sync(backend) -> CloudSync:
    sync = CloudSync(_signed_in_config(backend))
    sync.authenticated = True
    sync.user_email = "a@example.com"
    sync.user_id = 1
    return sync


def _http_error(status: int) -> httpx.HTTPStatusError:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status
    response.text = "Unauthorized"
    return httpx.HTTPStatusError(str(status), request=MagicMock(), response=response)


def test_sign_out_deletes_stored_token(fake_keyring):
    sync = _signed_in_sync(fake_keyring)

    sync.logout()

    assert fake_keyring.store == {}
    assert sync.authenticated is False
    assert sync.user_email is None and sync.user_id is None
    assert sync.config.api._token is None
    assert sync.config.api.token is None
    # A restart builds a fresh config: it must start signed out
    fresh = Config(api=APIConfig(url=API_URL, use_clerk_auth=True))
    assert fresh.api.token is None
    assert CloudSync(fresh).authenticated is False


async def test_sign_out_stops_uploads(fake_keyring, tmp_path):
    sync = _signed_in_sync(fake_keyring)
    sync.logout()
    rm_file = tmp_path / "page.rm"
    rm_file.write_bytes(b"x")

    with pytest.raises(AuthenticationRequiredError):
        await sync.upload_file(rm_file, "nb", "rm")
    await sync.close()


async def test_401_signs_out_and_deletes_token(fake_keyring, tmp_path):
    sync = _signed_in_sync(fake_keyring)
    sync.client = httpx.AsyncClient(timeout=30.0)
    rm_file = tmp_path / "page.rm"
    rm_file.write_bytes(b"x")

    async def always_401(*args, **kwargs):
        raise _http_error(401)

    sync.client.post = always_401
    sync.client.get = always_401
    try:
        with pytest.raises(AuthenticationRequiredError):
            await sync.upload_file(rm_file, "nb", "rm")
    finally:
        await sync.close()

    assert sync.authenticated is False
    assert fake_keyring.store == {}
    assert sync.config.api.token is None
    assert Config(api=APIConfig(url=API_URL, use_clerk_auth=True)).api.token is None


async def test_401_on_user_info_signs_out(fake_keyring):
    sync = _signed_in_sync(fake_keyring)
    sync.client = httpx.AsyncClient(timeout=30.0)

    async def always_401(*args, **kwargs):
        raise _http_error(401)

    sync.client.get = always_401
    try:
        with pytest.raises(AuthenticationRequiredError):
            await sync.get_user_info()
    finally:
        await sync.close()

    assert sync.authenticated is False
    assert fake_keyring.store == {}
