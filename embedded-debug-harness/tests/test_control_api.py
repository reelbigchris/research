"""Tests for the control server API."""

from __future__ import annotations

import asyncio
import json

import pytest

from debug_harness.api.control_server import ControlServer
from mocks.mock_subprocess import MockStreamFactory, ScriptedLine
from mocks.mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream


async def _send_request(port: int, method: str, params: dict | None = None) -> dict:
    """Send a JSON request to the control server and return the response."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    request = json.dumps({"method": method, "params": params or {}})
    writer.write(request.encode())
    await writer.drain()

    data = await reader.read(65536)
    writer.close()
    return json.loads(data.decode())


class TestControlServer:
    @pytest.mark.asyncio
    async def test_get_status_no_session(self):
        """get_status with no session running returns no_session."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        port = int(addr.split(":")[1])

        try:
            response = await _send_request(port, "get_status")
            assert response["status"] == "ok"
            assert response["state"] == "no_session"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_unknown_method(self):
        """Unknown method returns error."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        port = int(addr.split(":")[1])

        try:
            response = await _send_request(port, "nonexistent")
            assert response["status"] == "error"
            assert "Unknown method" in response["message"]
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_start_session_with_inline_plan(self):
        """Start a session with an inline plan dict."""
        factory = MockStreamFactory()
        factory.script_subprocess("installer", [
            ScriptedLine("Done", delay=0.05),
        ])

        shell_server = MockDebugShellServer()
        shell_port = await shell_server.start()

        tcp_stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", shell_port)
        factory.set_tcp_stream("debug_shell", tcp_stream)

        control = ControlServer(stream_factory=factory, port=0)
        addr = await control.start()
        ctrl_port = int(addr.split(":")[1])

        try:
            plan_dict = {
                "name": "api-test",
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
                            "name": "done",
                            "watch": {"stream": "installer", "pattern": "Done"},
                            "then": [{"steady_state": True}],
                        }
                    ],
                    "reactive_timeout": 10,
                },
            }

            response = await _send_request(ctrl_port, "start_session", {"plan": plan_dict})
            assert response["status"] == "ok"
            assert "session_id" in response

            # Wait for session to complete
            await asyncio.sleep(1.0)

            status = await _send_request(ctrl_port, "get_status")
            assert status["status"] == "ok"
            # Session should have completed by now
            assert status["state"] in ("completed", "running")

        finally:
            await control.stop()
            await shell_server.stop()

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Sending invalid JSON returns error."""
        factory = MockStreamFactory()
        server = ControlServer(stream_factory=factory, port=0)
        addr = await server.start()
        port = int(addr.split(":")[1])

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"not json")
            await writer.drain()

            data = await reader.read(65536)
            writer.close()

            response = json.loads(data.decode())
            assert response["status"] == "error"
        finally:
            await server.stop()
