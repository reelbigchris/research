"""Shared test fixtures for the debug harness test suite."""

from __future__ import annotations

import asyncio

import pytest

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import (
    Action,
    ConnectionConfig,
    Rule,
    SessionPlan,
    SessionSettings,
    WatchSpec,
)
from mocks.mock_subprocess import MockStreamFactory, ScriptedLine
from mocks.mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream


@pytest.fixture
def mock_factory():
    """A fresh MockStreamFactory for dependency injection."""
    return MockStreamFactory()


@pytest.fixture
def tmp_session_dir(tmp_path):
    """Temporary directory for session artifacts."""
    return str(tmp_path / "sessions")


@pytest.fixture
def artifacts(tmp_session_dir):
    """SessionArtifacts writing to a temp directory."""
    return SessionArtifacts(tmp_session_dir, "test")


@pytest.fixture
async def mock_shell_server():
    """A MockDebugShellServer that is started and cleaned up automatically."""
    server = MockDebugShellServer()
    port = await server.start()
    yield server, port
    await server.stop()


def make_plan(
    *,
    name: str = "test-plan",
    rules: list[Rule] | None = None,
    setup: list | None = None,
    connections: dict[str, ConnectionConfig] | None = None,
    settings: SessionSettings | None = None,
    reactive_timeout: float = 10.0,
    on_steady_state: list[Action] | None = None,
) -> SessionPlan:
    """Helper to build a SessionPlan with sensible defaults for testing."""
    return SessionPlan(
        name=name,
        description="Test plan",
        connections=connections or {
            "installer": ConnectionConfig(command=["./installer"]),
            "debug_shell": ConnectionConfig(host="127.0.0.1", port=0),
        },
        settings=settings or SessionSettings(
            prompt_timeout=5.0,
            command_timeout=10.0,
            session_dir="./test-sessions",
        ),
        setup=setup or [],
        rules=rules or [],
        reactive_timeout=reactive_timeout,
        on_steady_state=on_steady_state or [],
    )
