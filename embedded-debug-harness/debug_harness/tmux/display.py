"""tmux session management for operator observability.

Creates a tmux session with two panes:
- Left: command interface + installer stdout
- Right: debug shell I/O

The harness works without tmux; this is purely for human observation.
"""

from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)


class TmuxDisplay:
    """Manages a tmux session with split panes for session observation."""

    def __init__(self, session_name: str = "debug"):
        self._session = session_name
        self._panes: dict[str, str] = {}
        self._available = shutil.which("tmux") is not None

    @property
    def available(self) -> bool:
        return self._available

    async def setup(self) -> bool:
        """Create tmux session with split panes. Returns False if tmux unavailable."""
        if not self._available:
            log.warning("tmux not found, display disabled")
            return False

        try:
            # Kill existing session if any
            await self._run_tmux(
                "kill-session", "-t", self._session, ignore_errors=True
            )

            # Create new session
            await self._run_tmux(
                "new-session",
                "-d",
                "-s",
                self._session,
                "-x",
                "200",
                "-y",
                "50",
            )

            # Split horizontally
            await self._run_tmux("split-window", "-h", "-t", self._session)

            # Get pane IDs
            panes_output = await self._run_tmux(
                "list-panes", "-t", self._session, "-F", "#{pane_id}"
            )
            pane_ids = panes_output.strip().split("\n")
            if len(pane_ids) >= 2:
                self._panes["left"] = pane_ids[0]
                self._panes["right"] = pane_ids[1]

            # Set titles
            if "left" in self._panes:
                await self._run_tmux(
                    "select-pane",
                    "-t",
                    self._panes["left"],
                    "-T",
                    "Command Interface / Installer",
                )
            if "right" in self._panes:
                await self._run_tmux(
                    "select-pane",
                    "-t",
                    self._panes["right"],
                    "-T",
                    "Debug Shell",
                )

            log.info("tmux session '%s' created", self._session)
            return True

        except Exception:
            log.exception("Failed to create tmux session")
            self._available = False
            return False

    async def write_left(self, text: str) -> None:
        """Write text to the left pane (command interface / installer)."""
        await self._write_to_pane("left", text)

    async def write_right(self, text: str) -> None:
        """Write text to the right pane (debug shell)."""
        await self._write_to_pane("right", text)

    async def _write_to_pane(self, pane_name: str, text: str) -> None:
        if not self._available:
            return
        pane_id = self._panes.get(pane_name)
        if not pane_id:
            return
        # Use send-keys to display text (safe for arbitrary content)
        for line in text.split("\n"):
            safe = line.replace("'", "'\\''")
            await self._run_tmux(
                "send-keys",
                "-t",
                pane_id,
                f"echo '{safe}'",
                "Enter",
                ignore_errors=True,
            )

    async def teardown(self) -> None:
        """Kill the tmux session."""
        if self._available:
            await self._run_tmux(
                "kill-session", "-t", self._session, ignore_errors=True
            )

    async def _run_tmux(
        self, *args: str, ignore_errors: bool = False
    ) -> str:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0 and not ignore_errors:
            raise RuntimeError(
                f"tmux {' '.join(args)} failed: {stderr.decode()}"
            )
        return stdout.decode()
