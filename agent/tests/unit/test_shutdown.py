"""SIGTERM / SIGINT handling: the same clean shutdown in every mode, and one log line."""

import logging
import signal
from unittest.mock import MagicMock, patch

import pytest

from app.agent_loop import AgentLoop
from app.main import Agent, setup_signal_handlers


def _installed_handler(agent, quit_app=None):
    handlers = {}
    with patch("app.main.signal.signal", side_effect=lambda sig, h: handlers.__setitem__(sig, h)):
        setup_signal_handlers(agent, quit_app=quit_app)
    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}
    return handlers[signal.SIGTERM]


def test_tray_mode_quits_the_app_instead_of_sys_exit():
    """sys.exit() inside the AppKit run loop does not end the process: quit the app."""
    agent = MagicMock()
    order = []
    agent.shutdown.side_effect = lambda: order.append("shutdown")
    quit_app = MagicMock(side_effect=lambda: order.append("quit"))
    handler = _installed_handler(agent, quit_app=quit_app)

    handler(signal.SIGTERM, None)  # must not raise SystemExit

    assert order == ["shutdown", "quit"]


def test_foreground_mode_exits():
    agent = MagicMock()
    handler = _installed_handler(agent)

    with pytest.raises(SystemExit) as exc_info:
        handler(signal.SIGTERM, None)

    assert exc_info.value.code == 0
    agent.shutdown.assert_called_once()


def test_signal_is_logged(caplog):
    handler = _installed_handler(MagicMock(), quit_app=MagicMock())
    with caplog.at_level(logging.INFO, logger="app.main"):
        handler(signal.SIGTERM, None)
    assert "SIGTERM" in caplog.text


def test_shutdown_logs_agent_stopped_once(test_config, caplog):
    agent = Agent(test_config, agent_loop=AgentLoop())
    with caplog.at_level(logging.INFO, logger="app.main"):
        agent.shutdown()
        agent.shutdown()
    assert caplog.text.count("Agent stopped") == 1
