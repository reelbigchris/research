"""Base abstractions for stream adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class StreamLine:
    """A single line read from a stream."""

    text: str
    timestamp: datetime
    stream_name: str


class StreamAdapter(ABC):
    """Abstract interface for all stream sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique stream identifier, e.g. 'installer', 'debug_shell'."""
        ...

    @abstractmethod
    async def readline(self) -> StreamLine | None:
        """Read the next line. Returns None on EOF/disconnect."""
        ...

    @abstractmethod
    async def write(self, data: str) -> None:
        """Write data to the stream (for bidirectional streams)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean shutdown."""
        ...


class StreamFactory(Protocol):
    """Protocol for creating stream adapters. Enables dependency injection."""

    async def create_subprocess_stream(
        self, name: str, cmd: list[str], cwd: str | None = None
    ) -> StreamAdapter: ...

    async def create_tcp_stream(
        self, name: str, host: str, port: int
    ) -> StreamAdapter: ...
