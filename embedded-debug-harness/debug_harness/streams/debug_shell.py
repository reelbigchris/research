"""Debug shell client with VxWorks prompt state machine.

Handles the three prompt quirks:
1. No auto-prompt on connect — must send \\n to elicit ->
2. Normal command: send command, read until ->
3. Breakpoint hit: no prompt after break notification — must send \\n to re-sync
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto

from .base import StreamAdapter, StreamLine

log = logging.getLogger(__name__)


class PromptState(Enum):
    DISCONNECTED = auto()
    AWAITING_INITIAL_PROMPT = auto()
    READY = auto()
    COMMAND_SENT = auto()
    BREAKPOINT_HIT = auto()


class PromptTimeout(Exception):
    """Raised when the debug shell prompt does not appear within the timeout."""


class CommandTimeout(Exception):
    """Raised when a command response does not complete within the timeout."""


class ConnectionLost(Exception):
    """Raised when the debug shell TCP connection drops."""


PROMPT_MARKER = "-> "


class DebugShellClient:
    """High-level client for the VxWorks debug shell.

    Wraps a StreamAdapter and implements the prompt state machine.
    Provides send_command() which handles the prompt dance automatically.

    The underlying stream's readline() must be able to return the prompt
    as a distinct StreamLine (text == '-> ').
    """

    def __init__(
        self,
        stream: StreamAdapter,
        prompt_timeout: float = 10.0,
        command_timeout: float = 30.0,
    ):
        self._stream = stream
        self._prompt_timeout = prompt_timeout
        self._command_timeout = command_timeout
        self._state = PromptState.DISCONNECTED
        self._lock = asyncio.Lock()  # serialize command sends
        self._line_callbacks: list = []  # callbacks for reactive engine

    @property
    def state(self) -> PromptState:
        return self._state

    @property
    def stream(self) -> StreamAdapter:
        """Access the underlying stream (for the reactive engine to read from)."""
        return self._stream

    def add_line_callback(self, callback) -> None:
        """Register a callback invoked for every line read from the shell.

        Used by the reactive engine to watch for patterns on the debug shell stream.
        """
        self._line_callbacks.append(callback)

    async def connect_and_sync(self) -> None:
        """Perform initial prompt synchronization after TCP connect.

        Sends a bare \\n and waits for the -> prompt.
        """
        self._state = PromptState.AWAITING_INITIAL_PROMPT
        log.info("Debug shell: sending initial \\n to sync prompt")
        await self._stream.write("\n")
        await self._wait_for_prompt(self._prompt_timeout)
        self._state = PromptState.READY
        log.info("Debug shell: prompt synced, state=READY")

    async def send_command(
        self, command: str, timeout: float | None = None
    ) -> str:
        """Send a command to the debug shell and return the response.

        Handles the breakpoint quirk: if in BREAKPOINT_HIT state,
        sends \\n first to re-elicit the prompt before the command.

        Returns everything between the command echo and the next -> prompt.
        """
        timeout = timeout or self._command_timeout

        async with self._lock:
            if self._state == PromptState.BREAKPOINT_HIT:
                log.info("Debug shell: re-syncing prompt after breakpoint")
                await self._stream.write("\n")
                await self._wait_for_prompt(self._prompt_timeout)

            self._state = PromptState.COMMAND_SENT
            log.debug("Debug shell: sending command: %s", command)
            await self._stream.write(command + "\n")
            response = await self._read_until_prompt(timeout)
            self._state = PromptState.READY
            log.debug("Debug shell: response: %s", response[:200])
            return response

    def notify_breakpoint_hit(self) -> None:
        """Called by the reactive engine when a breakpoint pattern is detected.

        Transitions to BREAKPOINT_HIT state so the next send_command()
        knows to re-sync the prompt.
        """
        log.info("Debug shell: breakpoint hit, state=BREAKPOINT_HIT")
        self._state = PromptState.BREAKPOINT_HIT

    async def _wait_for_prompt(self, timeout: float) -> None:
        """Read lines until the -> prompt appears, or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise PromptTimeout(
                    f"Debug shell prompt not received within {timeout}s"
                )
            try:
                line = await asyncio.wait_for(
                    self._stream.readline(), timeout=remaining
                )
            except asyncio.TimeoutError:
                raise PromptTimeout(
                    f"Debug shell prompt not received within {timeout}s"
                )

            if line is None:
                raise ConnectionLost("Debug shell disconnected while waiting for prompt")

            self._notify_callbacks(line)

            if _is_prompt(line.text):
                return

    async def _read_until_prompt(self, timeout: float) -> str:
        """Read response lines until the -> prompt, return the response text."""
        lines: list[str] = []
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                partial = "\n".join(lines)
                raise CommandTimeout(
                    f"No prompt after command within {timeout}s. "
                    f"Partial response: {partial[:500]}"
                )
            try:
                line = await asyncio.wait_for(
                    self._stream.readline(), timeout=remaining
                )
            except asyncio.TimeoutError:
                partial = "\n".join(lines)
                raise CommandTimeout(
                    f"No prompt after command within {timeout}s. "
                    f"Partial response: {partial[:500]}"
                )

            if line is None:
                raise ConnectionLost("Debug shell disconnected during command")

            self._notify_callbacks(line)

            if _is_prompt(line.text):
                break

            lines.append(line.text)

        return "\n".join(lines)

    def _notify_callbacks(self, line: StreamLine) -> None:
        """Forward every line to registered callbacks (for reactive engine)."""
        for cb in self._line_callbacks:
            cb(line)

    async def close(self) -> None:
        await self._stream.close()


def _is_prompt(text: str) -> bool:
    """Check if a line is the debug shell prompt."""
    stripped = text.strip()
    return stripped == "->" or stripped == "-> " or text.rstrip() == "-> "
