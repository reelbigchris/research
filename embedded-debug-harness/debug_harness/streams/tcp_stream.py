"""Real TCP stream adapter using asyncio.open_connection."""

from __future__ import annotations

import asyncio
from datetime import datetime

from .base import StreamAdapter, StreamLine


class TcpStream(StreamAdapter):
    """Wraps an asyncio TCP connection.

    Reads data and splits on newlines and the '-> ' prompt marker,
    similar to MockTcpStream.
    """

    def __init__(
        self,
        name: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self._name = name
        self._reader = reader
        self._writer = writer
        self._closed = False
        self._buffer = ""

    @classmethod
    async def connect(cls, name: str, host: str, port: int) -> TcpStream:
        reader, writer = await asyncio.open_connection(host, port)
        return cls(name, reader, writer)

    @property
    def name(self) -> str:
        return self._name

    async def readline(self) -> StreamLine | None:
        if self._closed:
            return None

        try:
            while True:
                # Check for prompt marker in buffer
                prompt_pos = self._buffer.find("-> ")
                newline_pos = self._buffer.find("\n")

                if prompt_pos != -1:
                    if newline_pos != -1 and newline_pos < prompt_pos:
                        line = self._buffer[:newline_pos]
                        self._buffer = self._buffer[newline_pos + 1 :]
                        if line:
                            return StreamLine(
                                text=line,
                                timestamp=datetime.now(),
                                stream_name=self._name,
                            )
                        continue

                    before = self._buffer[:prompt_pos].strip()
                    self._buffer = self._buffer[prompt_pos + 3 :]
                    if before:
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

                chunk = await self._reader.read(4096)
                if not chunk:
                    if self._buffer:
                        remaining = self._buffer
                        self._buffer = ""
                        return StreamLine(
                            text=remaining,
                            timestamp=datetime.now(),
                            stream_name=self._name,
                        )
                    return None
                self._buffer += chunk.decode(errors="replace")

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
