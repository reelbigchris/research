"""Mock subprocess stream that emits scripted lines with configurable delays."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from debug_harness.streams.base import StreamAdapter, StreamLine


@dataclass
class ScriptedLine:
    """A line to emit from a mock subprocess, with optional delay before emission."""

    text: str
    delay: float = 0.0  # seconds to wait before emitting


class MockSubprocessStream(StreamAdapter):
    """Emits pre-scripted lines with configurable delays. Simulates a subprocess."""

    def __init__(self, name: str, script: list[ScriptedLine]):
        self._name = name
        self._script = script
        self._index = 0
        self._closed = False
        self._exit_code = 0

    @property
    def name(self) -> str:
        return self._name

    async def readline(self) -> StreamLine | None:
        if self._index >= len(self._script) or self._closed:
            return None
        entry = self._script[self._index]
        self._index += 1
        if entry.delay > 0:
            await asyncio.sleep(entry.delay)
        return StreamLine(
            text=entry.text,
            timestamp=datetime.now(),
            stream_name=self._name,
        )

    async def write(self, data: str) -> None:
        pass  # subprocess stdin — not used for installer

    async def close(self) -> None:
        self._closed = True

    @property
    def exit_code(self) -> int:
        return self._exit_code


class MockStreamFactory:
    """Injectable factory that returns mock streams instead of real subprocesses/TCP."""

    def __init__(self):
        self._subprocess_scripts: dict[str, list[ScriptedLine]] = {}
        self._tcp_streams: dict[str, StreamAdapter] = {}

    def script_subprocess(self, name: str, lines: list[ScriptedLine]) -> None:
        """Register a scripted output sequence for a named subprocess."""
        self._subprocess_scripts[name] = lines

    def set_tcp_stream(self, name: str, stream: StreamAdapter) -> None:
        """Register a pre-built stream adapter for a named TCP connection."""
        self._tcp_streams[name] = stream

    async def create_subprocess_stream(
        self, name: str, cmd: list[str], cwd: str | None = None
    ) -> StreamAdapter:
        script = self._subprocess_scripts.get(name, [])
        return MockSubprocessStream(name, script)

    async def create_tcp_stream(
        self, name: str, host: str, port: int
    ) -> StreamAdapter:
        if name in self._tcp_streams:
            return self._tcp_streams[name]
        # Return an empty stream if not configured
        return MockSubprocessStream(name, [])
