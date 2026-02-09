"""Real subprocess stream adapter using asyncio.create_subprocess_exec."""

from __future__ import annotations

import asyncio
from datetime import datetime

from .base import StreamAdapter, StreamLine


class SubprocessStream(StreamAdapter):
    """Wraps an asyncio subprocess, exposing stdout as an async line iterator."""

    def __init__(self, name: str, process: asyncio.subprocess.Process):
        self._name = name
        self._process = process
        self._closed = False

    @classmethod
    async def create(
        cls, name: str, cmd: list[str], cwd: str | None = None
    ) -> SubprocessStream:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        return cls(name, process)

    @property
    def name(self) -> str:
        return self._name

    async def readline(self) -> StreamLine | None:
        if self._closed or self._process.stdout is None:
            return None
        line_bytes = await self._process.stdout.readline()
        if not line_bytes:
            return None
        text = line_bytes.decode(errors="replace").rstrip("\n\r")
        return StreamLine(
            text=text,
            timestamp=datetime.now(),
            stream_name=self._name,
        )

    async def write(self, data: str) -> None:
        if self._process.stdin and not self._closed:
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()

    async def close(self) -> None:
        self._closed = True
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._process.kill()
            except ProcessLookupError:
                pass

    @property
    def exit_code(self) -> int | None:
        return self._process.returncode
