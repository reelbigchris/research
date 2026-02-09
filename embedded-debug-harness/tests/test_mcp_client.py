"""Tests for the MCP control client."""

from __future__ import annotations

import asyncio

import pytest

from debug_harness.api.control_server import ControlServer
from debug_harness.mcp.control_client import ControlClient
from mocks.mock_subprocess import MockStreamFactory, ScriptedLine
from mocks.mock_tcp_server import MockDebugShellServer, MockTcpStream


class TestControlClient:
    @pytest.mark.asyncio
    async def test_get_status(self):
        """Client can get status from control server."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        host, port_str = addr.split(":")
        port = int(port_str)

        client = ControlClient(host=host, port=port)

        try:
            response = await client.get_status()
            assert response["status"] == "ok"
            assert response["state"] == "no_session"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_start_session_with_plan(self):
        """Client can start a session with an inline plan."""
        factory = MockStreamFactory()
        factory.script_subprocess("installer", [
            ScriptedLine("Installation complete", delay=0.05),
        ])

        shell_server = MockDebugShellServer()
        shell_port = await shell_server.start()

        tcp_stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", shell_port)
        factory.set_tcp_stream("debug_shell", tcp_stream)

        control = ControlServer(stream_factory=factory, port=0)
        addr = await control.start()
        host, port_str = addr.split(":")
        ctrl_port = int(port_str)

        client = ControlClient(host=host, port=ctrl_port)

        try:
            plan_dict = {
                "name": "client-test",
                "connections": {
                    "installer": {"command": ["./installer"]},
                    "debug_shell": {"host": "127.0.0.1", "port": shell_port},
                },
                "settings": {
                    "prompt_timeout": 5,
                    "command_timeout": 5,
                    "session_dir": "/tmp/test-sessions",
                },
                "reactive": {
                    "rules": [
                        {
                            "name": "complete",
                            "watch": {"stream": "installer", "pattern": "Installation complete"},
                            "then": [{"steady_state": True}],
                        }
                    ],
                    "reactive_timeout": 10,
                },
            }

            response = await client.start_session(plan=plan_dict)
            assert response["status"] == "ok"
            assert "session_id" in response

            # Wait for session to reach steady state
            await asyncio.sleep(1.0)

            status = await client.get_status()
            assert status["status"] == "ok"
            assert status["state"] in ("completed", "running")

        finally:
            await control.stop()
            await shell_server.stop()

    @pytest.mark.asyncio
    async def test_send_command_error_when_no_session(self):
        """send_command returns error when no session exists."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        host, port_str = addr.split(":")
        port = int(port_str)

        client = ControlClient(host=host, port=port)

        try:
            response = await client.send_command("bp 0x80004000")
            assert response["status"] == "error"
            assert "No active debug shell" in response["message"]
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_abort_session(self):
        """Client can abort a running session."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        host, port_str = addr.split(":")
        port = int(port_str)

        client = ControlClient(host=host, port=port)

        try:
            response = await client.abort()
            assert response["status"] == "ok"
            assert "No session to abort" in response["message"]
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_is_connected_tcp(self):
        """is_connected returns True when server is reachable via TCP."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        host, port_str = addr.split(":")
        port = int(port_str)

        client = ControlClient(host=host, port=port)

        try:
            # Should be connected
            assert await client.is_connected() is True

            # Stop server
            await server.stop()

            # Should not be connected
            assert await client.is_connected() is False
        finally:
            if server._server:
                await server.stop()

    @pytest.mark.asyncio
    async def test_get_captures_no_session(self):
        """get_captures returns error when no completed session exists."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        host, port_str = addr.split(":")
        port = int(port_str)

        client = ControlClient(host=host, port=port)

        try:
            response = await client.get_captures()
            assert response["status"] == "error"
            assert "No completed session" in response["message"]
        finally:
            await server.stop()
