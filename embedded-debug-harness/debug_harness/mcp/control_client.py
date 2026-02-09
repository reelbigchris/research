"""Client for connecting to the debug harness ControlServer."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from pathlib import Path

log = logging.getLogger(__name__)


class ControlClient:
    """Client for communicating with the debug harness ControlServer.

    Connects to a Unix socket or TCP port and sends JSON-RPC style requests.
    """

    def __init__(self, socket_path: str | None = None, host: str = "127.0.0.1", port: int = 0):
        self.socket_path = socket_path
        self.host = host
        self.port = port

    async def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a request to the control server and return the response."""
        request = {"method": method, "params": params or {}}
        request_data = json.dumps(request).encode()

        if self.socket_path:
            # Unix domain socket
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
        else:
            # TCP socket
            reader, writer = await asyncio.open_connection(self.host, self.port)

        try:
            writer.write(request_data)
            await writer.drain()

            response_data = await reader.read(65536)
            if not response_data:
                raise ConnectionError("No response from control server")

            response = json.loads(response_data.decode())
            return response
        finally:
            writer.close()
            await writer.wait_closed()

    async def start_session(self, plan: dict | None = None, config_path: str | None = None) -> dict:
        """Start a debug session with the given plan or config file path."""
        params = {}
        if plan:
            params["plan"] = plan
        elif config_path:
            params["config_path"] = config_path
        else:
            raise ValueError("Must provide either plan or config_path")

        return await self._send_request("start_session", params)

    async def get_status(self) -> dict:
        """Get the current session status."""
        return await self._send_request("get_status")

    async def send_command(self, command: str) -> dict:
        """Send a command to the debug shell."""
        return await self._send_request("send_command", {"command": command})

    async def get_capture(self, name: str) -> dict:
        """Get a specific capture by name."""
        return await self._send_request("get_capture", {"name": name})

    async def get_captures(self) -> dict:
        """Get all captures from the session."""
        return await self._send_request("get_captures")

    async def abort(self) -> dict:
        """Abort the current session."""
        return await self._send_request("abort")

    async def is_connected(self) -> bool:
        """Check if the control server is reachable."""
        try:
            if self.socket_path:
                # Check if Unix socket exists
                return Path(self.socket_path).exists()
            else:
                # Try to connect to TCP port
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                try:
                    sock.connect((self.host, self.port))
                    sock.close()
                    return True
                except (socket.timeout, ConnectionRefusedError):
                    return False
        except Exception as e:
            log.debug(f"Connection check failed: {e}")
            return False
