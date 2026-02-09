"""Mock VxWorks debug shell TCP server with prompt quirk simulation.

Simulates the three key quirks:
1. No auto-prompt on connect — client must send \\n to get ->
2. Normal commands: response text followed by "\\n-> "
3. Breakpoint hit: emits break text WITHOUT a trailing -> prompt
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from debug_harness.streams.base import StreamAdapter, StreamLine


@dataclass
class MockResponse:
    """Canned response for a debug shell command."""

    output: str
    include_prompt: bool = True  # send -> after output
    delay: float = 0.0  # delay before responding


@dataclass
class BreakpointEvent:
    """A breakpoint that fires after a specific command completes."""

    trigger_after: str  # fire after this command
    text: str  # breakpoint notification text (e.g. "Break at 0x80004000")
    delay: float = 0.1  # delay before breakpoint appears
    fired: bool = False


class MockDebugShellServer:
    """TCP server simulating a VxWorks debug shell.

    Usage:
        server = MockDebugShellServer()
        server.on_command("bp 0x80004000", MockResponse("Breakpoint set at 0x80004000"))
        server.schedule_breakpoint("go", "Break at 0x80004000")
        port = await server.start()
        # ... connect client ...
        await server.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._host = host
        self._port = port
        self._command_responses: dict[str, MockResponse] = {}
        self._breakpoint_events: list[BreakpointEvent] = []
        self._server: asyncio.Server | None = None
        self._connections: list[asyncio.StreamWriter] = []
        self._commands_received: list[str] = []
        self._on_command_callback: Callable[[str], None] | None = None
        self._default_response = MockResponse(output="", include_prompt=True)

    def on_command(self, command: str, response: MockResponse) -> None:
        """Register a canned response for a command."""
        self._command_responses[command.strip()] = response

    def schedule_breakpoint(
        self, trigger_after: str, breakpoint_text: str, delay: float = 0.1
    ) -> None:
        """Schedule a breakpoint notification after a command completes."""
        self._breakpoint_events.append(
            BreakpointEvent(
                trigger_after=trigger_after.strip(),
                text=breakpoint_text,
                delay=delay,
            )
        )

    def set_command_callback(self, callback: Callable[[str], None]) -> None:
        """Set a callback invoked for each command received."""
        self._on_command_callback = callback

    @property
    def commands_received(self) -> list[str]:
        return list(self._commands_received)

    async def start(self) -> int:
        """Start the server, return the assigned port."""
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        addr = self._server.sockets[0].getsockname()
        self._port = addr[1]
        return self._port

    async def stop(self) -> None:
        """Stop the server and close all connections."""
        for writer in self._connections:
            if not writer.is_closing():
                writer.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle one client connection with VxWorks prompt protocol."""
        self._connections.append(writer)

        # Quirk 1: Do NOT send prompt on connect. Wait for client to send \n.

        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                command = data.decode().strip()

                if command == "":
                    # Client sent bare \n — respond with prompt
                    writer.write(b"\n-> ")
                    await writer.drain()
                    continue

                self._commands_received.append(command)
                if self._on_command_callback:
                    self._on_command_callback(command)

                response = self._command_responses.get(
                    command, self._default_response
                )

                if response.delay > 0:
                    await asyncio.sleep(response.delay)

                if response.output:
                    writer.write(response.output.encode())
                if response.include_prompt:
                    writer.write(b"\n-> ")
                await writer.drain()

                # Check for breakpoint events triggered by this command
                for bp in self._breakpoint_events:
                    if bp.trigger_after == command and not bp.fired:
                        bp.fired = True
                        await asyncio.sleep(bp.delay)
                        # Quirk 3: breakpoint text WITHOUT trailing ->
                        writer.write(bp.text.encode() + b"\n")
                        await writer.drain()

        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if not writer.is_closing():
                writer.close()


class MockTcpStream(StreamAdapter):
    """StreamAdapter that connects to a MockDebugShellServer (or any TCP server).

    This is the client side — used by DebugShellClient in tests.
    Reads data character-by-character to detect the -> prompt without
    requiring newline-delimited framing.
    """

    def __init__(self, name: str, host: str, port: int):
        self._name = name
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._closed = False
        self._buffer = ""

    @classmethod
    async def connect(cls, name: str, host: str, port: int) -> MockTcpStream:
        stream = cls(name, host, port)
        stream._reader, stream._writer = await asyncio.open_connection(host, port)
        return stream

    @property
    def name(self) -> str:
        return self._name

    async def readline(self) -> StreamLine | None:
        """Read until newline or '-> ' prompt marker.

        Returns lines one at a time. The prompt line '-> ' is returned
        as its own StreamLine so the debug shell client can detect it.
        """
        if self._closed or self._reader is None:
            return None

        try:
            while True:
                # Check if buffer already contains a complete unit
                prompt_pos = self._buffer.find("-> ")
                newline_pos = self._buffer.find("\n")

                if prompt_pos != -1:
                    # Prompt found — return everything before it, then the prompt
                    if newline_pos != -1 and newline_pos < prompt_pos:
                        # Newline comes first
                        line = self._buffer[:newline_pos]
                        self._buffer = self._buffer[newline_pos + 1 :]
                        if line:  # skip empty lines from \n\n
                            return StreamLine(
                                text=line,
                                timestamp=datetime.now(),
                                stream_name=self._name,
                            )
                        continue
                    # Return text before prompt if any, then prompt itself
                    before = self._buffer[:prompt_pos].strip()
                    self._buffer = self._buffer[prompt_pos + 3 :]
                    if before:
                        # Re-inject prompt for next read
                        self._buffer = "-> " + self._buffer
                        return StreamLine(
                            text=before,
                            timestamp=datetime.now(),
                            stream_name=self._name,
                        )
                    return StreamLine(
                        text="-> ",
                        timestamp=datetime.now(),
                        stream_name=self._name,
                    )

                if newline_pos != -1:
                    line = self._buffer[:newline_pos]
                    self._buffer = self._buffer[newline_pos + 1 :]
                    if line:
                        return StreamLine(
                            text=line,
                            timestamp=datetime.now(),
                            stream_name=self._name,
                        )
                    continue

                # Need more data
                chunk = await self._reader.read(4096)
                if not chunk:
                    # EOF
                    if self._buffer:
                        remaining = self._buffer
                        self._buffer = ""
                        return StreamLine(
                            text=remaining,
                            timestamp=datetime.now(),
                            stream_name=self._name,
                        )
                    return None
                self._buffer += chunk.decode()

        except (ConnectionResetError, BrokenPipeError, OSError):
            return None

    async def write(self, data: str) -> None:
        if self._writer and not self._closed:
            self._writer.write(data.encode())
            await self._writer.drain()

    async def close(self) -> None:
        self._closed = True
        if self._writer and not self._writer.is_closing():
            self._writer.close()
