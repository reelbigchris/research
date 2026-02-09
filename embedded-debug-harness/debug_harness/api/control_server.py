"""JSON-over-Unix-socket control API for MCP server integration.

The control server exposes a simple request/response protocol:
- start_session: begin executing a session plan
- get_status: query current session state
- send_command: send a command to the debug shell (requires steady_state)
- get_capture: retrieve a named capture
- get_captures: retrieve all captures
- get_session_log: retrieve the session log path
- abort: abort the current session
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.loader import load_plan, parse_plan_dict
from debug_harness.config.schema import SessionResult
from debug_harness.streams.base import StreamFactory

log = logging.getLogger(__name__)


class ControlServer:
    """Local control server for MCP integration.

    Listens on a Unix domain socket or TCP port and accepts
    JSON request/response pairs.
    """

    def __init__(
        self,
        stream_factory: StreamFactory,
        socket_path: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self._factory = stream_factory
        self._socket_path = socket_path
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._session = None  # SessionOrchestrator
        self._session_task: asyncio.Task | None = None
        self._session_result: SessionResult | None = None
        self._session_id: str | None = None

    async def start(self) -> str:
        """Start the control server. Returns the address (socket path or host:port)."""
        if self._socket_path:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)
            self._server = await asyncio.start_unix_server(
                self._handle_client, path=self._socket_path
            )
            log.info("Control server listening on %s", self._socket_path)
            return self._socket_path
        else:
            self._server = await asyncio.start_server(
                self._handle_client, self._host, self._port
            )
            addr = self._server.sockets[0].getsockname()
            self._port = addr[1]
            log.info("Control server listening on %s:%d", self._host, self._port)
            return f"{self._host}:{self._port}"

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._socket_path and os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

    async def serve_forever(self) -> None:
        if self._server:
            async with self._server:
                await self._server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await reader.read(65536)
            if not data:
                return

            request = json.loads(data.decode())
            method = request.get("method", "")
            params = request.get("params", {})

            handler = {
                "start_session": self._handle_start_session,
                "get_status": self._handle_get_status,
                "send_command": self._handle_send_command,
                "get_capture": self._handle_get_capture,
                "get_captures": self._handle_get_captures,
                "abort": self._handle_abort,
            }.get(method)

            if handler:
                response = await handler(params)
            else:
                response = {"status": "error", "message": f"Unknown method: {method}"}

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except json.JSONDecodeError:
            writer.write(json.dumps({"status": "error", "message": "Invalid JSON"}).encode())
            await writer.drain()
        except Exception as e:
            writer.write(json.dumps({"status": "error", "message": str(e)}).encode())
            await writer.drain()
        finally:
            writer.close()

    async def _handle_start_session(self, params: dict) -> dict:
        from debug_harness.engine.session import SessionOrchestrator

        if self._session_task and not self._session_task.done():
            return {"status": "error", "message": "Session already running"}

        if "config_path" in params:
            plan = load_plan(params["config_path"])
        elif "plan" in params:
            plan = parse_plan_dict(params["plan"])
        else:
            return {"status": "error", "message": "Provide config_path or plan"}

        self._session_id = uuid.uuid4().hex[:8]
        artifacts = SessionArtifacts(
            plan.settings.session_dir, plan.name
        )
        self._session = SessionOrchestrator(plan, self._factory, artifacts)
        self._session_result = None

        async def _run():
            self._session_result = await self._session.run()

        self._session_task = asyncio.create_task(_run())

        return {"status": "ok", "session_id": self._session_id}

    async def _handle_get_status(self, params: dict) -> dict:
        if not self._session:
            return {"status": "ok", "state": "no_session"}

        if self._session_result:
            return {
                "status": "ok",
                "state": self._session_result.status,
                "rules_fired": self._session_result.rules_fired,
                "captures": list(self._session_result.captures.keys()),
            }

        return {
            "status": "ok",
            "state": "running",
            "steady_state": self._session.is_steady_state,
        }

    async def _handle_send_command(self, params: dict) -> dict:
        if not self._session or not self._session.debug_shell:
            return {"status": "error", "message": "No active debug shell"}

        cmd = params.get("command", "")
        if not cmd:
            return {"status": "error", "message": "No command provided"}

        try:
            response = await self._session.debug_shell.send_command(cmd)
            return {"status": "ok", "response": response}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _handle_get_capture(self, params: dict) -> dict:
        if not self._session_result:
            return {"status": "error", "message": "No completed session"}
        name = params.get("name", "")
        content = self._session_result.captures.get(name)
        if content is None:
            return {"status": "error", "message": f"No capture named '{name}'"}
        return {"status": "ok", "name": name, "content": content}

    async def _handle_get_captures(self, params: dict) -> dict:
        if not self._session_result:
            return {"status": "error", "message": "No completed session"}
        return {"status": "ok", "captures": self._session_result.captures}

    async def _handle_abort(self, params: dict) -> dict:
        if self._session_task and not self._session_task.done():
            self._session_task.cancel()
            return {"status": "ok", "message": "Session abort requested"}
        return {"status": "ok", "message": "No session to abort"}
