"""Session orchestrator — manages the full lifecycle of a debug session.

Phase 1: Setup — run command_interface commands sequentially
Phase 2: Reactive — start installer + debug shell concurrently, run reactive rules
Phase 3: Steady state — harness ready for interactive commands via control API
"""

from __future__ import annotations

import asyncio
import logging

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import SessionPlan, SessionResult
from debug_harness.streams.base import StreamAdapter, StreamFactory, StreamLine
from debug_harness.streams.debug_shell import DebugShellClient

from .actions import execute_action_sequence
from .reactive import ReactiveEngine

log = logging.getLogger(__name__)


class SessionOrchestrator:
    """Top-level controller for a debugging session.

    Accepts a SessionPlan and a StreamFactory (real or mock),
    executes the plan through all phases, and returns the result.
    """

    def __init__(
        self,
        plan: SessionPlan,
        stream_factory: StreamFactory,
        artifacts: SessionArtifacts,
    ):
        self._plan = plan
        self._factory = stream_factory
        self._artifacts = artifacts
        self._abort_event = asyncio.Event()
        self._steady_state_event = asyncio.Event()
        self._streams: dict[str, StreamAdapter] = {}
        self._debug_shell: DebugShellClient | None = None
        self._engine: ReactiveEngine | None = None

    @property
    def debug_shell(self) -> DebugShellClient | None:
        return self._debug_shell

    @property
    def is_steady_state(self) -> bool:
        return self._steady_state_event.is_set()

    async def run(self) -> SessionResult:
        """Execute the full session plan and return the result."""
        fired_rules: list[str] = []

        try:
            # Phase 1: Setup
            if self._plan.setup:
                log.info("Phase 1: Running setup commands")
                self._artifacts.log_event("phase", "setup_start")
                await self._run_setup_phase()
                self._artifacts.log_event("phase", "setup_complete")

            # Phase 2: Reactive
            if self._plan.rules:
                log.info("Phase 2: Starting reactive phase")
                self._artifacts.log_event("phase", "reactive_start")
                result_reason = await self._run_reactive_phase()
                self._artifacts.log_event(
                    "phase", f"reactive_complete: {result_reason}"
                )

                if self._engine:
                    fired_rules = self._engine.fired_rules

                if result_reason == "abort":
                    return SessionResult(
                        status="aborted",
                        captures=self._artifacts.captures,
                        rules_fired=fired_rules,
                    )

                if result_reason == "timeout":
                    return SessionResult(
                        status="timeout",
                        captures=self._artifacts.captures,
                        error=f"Reactive phase timed out after {self._plan.reactive_timeout}s",
                        rules_fired=fired_rules,
                    )

            # Phase 3: Steady state actions
            if self._plan.on_steady_state and self._debug_shell:
                log.info("Phase 3: Running steady-state actions")
                self._artifacts.log_event("phase", "steady_state_actions")
                await execute_action_sequence(
                    actions=self._plan.on_steady_state,
                    debug_shell=self._debug_shell,
                    artifacts=self._artifacts,
                    abort_event=self._abort_event,
                    steady_state_event=self._steady_state_event,
                )

            return SessionResult(
                status="completed",
                captures=self._artifacts.captures,
                rules_fired=fired_rules,
            )

        except Exception as e:
            log.exception("Session error")
            return SessionResult(
                status="error",
                captures=self._artifacts.captures,
                error=str(e),
                rules_fired=fired_rules,
            )

        finally:
            await self._cleanup()

    async def _run_setup_phase(self) -> None:
        """Run command_interface commands sequentially."""
        conn = self._plan.connections.get("command_interface")
        if not conn or not conn.command:
            log.info("No command_interface connection configured, running commands as no-ops")
            for cmd in self._plan.setup:
                self._artifacts.log_event(
                    "setup_command", f"{cmd.run} {cmd.args} (no connection)"
                )
            return

        for cmd in self._plan.setup:
            full_cmd = conn.command + [cmd.run] + cmd.args
            log.info("Setup: running %s", full_cmd)
            self._artifacts.log_event("setup_command_start", str(full_cmd))

            stream = await self._factory.create_subprocess_stream(
                name="command_interface",
                cmd=full_cmd,
                cwd=conn.cwd,
            )
            self._streams["command_interface"] = stream

            # Read all output
            while True:
                line = await stream.readline()
                if line is None:
                    break
                self._artifacts.log_line(line)

            await stream.close()
            self._artifacts.log_event("setup_command_done", str(full_cmd))

    async def _run_reactive_phase(self) -> str:
        """Start installer and debug shell, run reactive rules.

        Returns the completion reason from the reactive engine.
        """
        streams: dict[str, StreamAdapter] = {}

        # Start installer if configured
        installer_conn = self._plan.connections.get("installer")
        if installer_conn and installer_conn.command:
            installer_stream = await self._factory.create_subprocess_stream(
                name="installer",
                cmd=installer_conn.command,
                cwd=installer_conn.cwd,
            )
            streams["installer"] = installer_stream
            self._streams["installer"] = installer_stream
        else:
            # Create a mock installer stream from factory anyway
            # (tests may have scripted it without a connection config)
            installer_stream = await self._factory.create_subprocess_stream(
                name="installer", cmd=[]
            )
            streams["installer"] = installer_stream
            self._streams["installer"] = installer_stream

        # Connect debug shell if configured
        shell_conn = self._plan.connections.get("debug_shell")
        if shell_conn and shell_conn.host and shell_conn.port:
            tcp_stream = await self._factory.create_tcp_stream(
                name="debug_shell",
                host=shell_conn.host,
                port=shell_conn.port,
            )
        else:
            tcp_stream = await self._factory.create_tcp_stream(
                name="debug_shell", host="127.0.0.1", port=0
            )

        self._streams["debug_shell"] = tcp_stream
        self._debug_shell = DebugShellClient(
            stream=tcp_stream,
            prompt_timeout=self._plan.settings.prompt_timeout,
            command_timeout=self._plan.settings.command_timeout,
        )

        # Sync the debug shell prompt
        await self._debug_shell.connect_and_sync()

        # Note: don't add debug_shell to the reactive engine's watched streams.
        # The debug shell is driven by the engine via send_command, not watched
        # as a raw stream. However, we DO need to watch it for breakpoint patterns.
        # The DebugShellClient forwards lines to callbacks which the engine
        # can use. But for simpler architecture, we add a separate reader.
        # Actually — we need the debug shell in the streams dict so rules
        # watching "debug_shell" can match against its output.

        # For debug shell: we need a stream adapter that the engine reads from.
        # The DebugShellClient reads from the underlying stream, so we can't
        # also have the engine read from it directly (double-read problem).
        #
        # Solution: use a "tee" approach. The DebugShellClient registers
        # a line callback. The engine creates an async queue-based adapter
        # that receives lines via that callback.
        shell_queue: asyncio.Queue[StreamLine | None] = asyncio.Queue()

        def _on_shell_line(line: StreamLine) -> None:
            shell_queue.put_nowait(line)

        self._debug_shell.add_line_callback(_on_shell_line)

        # Create a queue-based stream adapter for the reactive engine
        shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)
        streams["debug_shell"] = shell_adapter

        # Create and run the reactive engine
        self._engine = ReactiveEngine(
            rules=self._plan.rules,
            streams=streams,
            debug_shell=self._debug_shell,
            artifacts=self._artifacts,
            timeout=self._plan.reactive_timeout,
        )

        return await self._engine.run()

    async def _cleanup(self) -> None:
        """Close all streams."""
        for stream in self._streams.values():
            try:
                await stream.close()
            except Exception:
                pass
        self._artifacts.close()


class _QueueStreamAdapter(StreamAdapter):
    """StreamAdapter backed by an asyncio.Queue, fed by callbacks.

    Used to bridge DebugShellClient's line callbacks into the
    reactive engine's stream reading model.
    """

    def __init__(self, name: str, queue: asyncio.Queue[StreamLine | None]):
        self._name = name
        self._queue = queue
        self._closed = False

    @property
    def name(self) -> str:
        return self._name

    async def readline(self) -> StreamLine | None:
        if self._closed:
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            if self._closed:
                return None
            # Return a sentinel that makes the engine keep trying
            # Actually, we should keep waiting. But we need to not
            # block forever either. The engine handles None as EOF.
            # Let's use a longer timeout and rely on the engine's
            # own termination conditions.
            return await self._queue.get()

    async def write(self, data: str) -> None:
        pass  # Writing goes through DebugShellClient, not this adapter

    async def close(self) -> None:
        self._closed = True
        await self._queue.put(None)
