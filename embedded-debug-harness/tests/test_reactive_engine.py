"""Tests for the reactive engine — the heart of the harness.

Tests cross-stream pattern matching, action dispatch, breakpoint handling,
abort, steady_state, and timeout behavior using mock streams and a mock
debug shell server.
"""

from __future__ import annotations

import asyncio

import pytest

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import Action, Rule, WatchSpec
from debug_harness.engine.reactive import ReactiveEngine
from debug_harness.streams.debug_shell import DebugShellClient
from mocks.mock_subprocess import MockSubprocessStream, ScriptedLine
from mocks.mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream


@pytest.fixture
def artifacts(tmp_path):
    return SessionArtifacts(str(tmp_path), "reactive-test")


async def _make_shell(server_port: int) -> tuple[MockTcpStream, DebugShellClient]:
    """Helper to create a connected debug shell client."""
    stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", server_port)
    client = DebugShellClient(stream, prompt_timeout=5.0, command_timeout=5.0)
    await client.connect_and_sync()
    return stream, client


class TestBasicRuleMatching:
    @pytest.mark.asyncio
    async def test_installer_pattern_triggers_debug_command(self, artifacts):
        """When installer emits a matching line, the rule sends a debug shell command."""
        server = MockDebugShellServer()
        server.on_command("bp 0x80004000", MockResponse("Breakpoint set at 0x80004000"))
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Initializing..."),
                ScriptedLine("Step 3: code loaded at 0x80004000", delay=0.05),
            ])

            # Set up the debug shell queue bridge
            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))

            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="set_bp",
                    watch=WatchSpec(stream="installer", pattern="Step 3.*code loaded"),
                    then=[
                        Action(action_type="send_command", stream="debug_shell", command="bp 0x80004000"),
                    ],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=5.0,
            )

            result = await engine.run()

            assert "set_bp" in engine.fired_rules
            assert "bp 0x80004000" in server.commands_received

        finally:
            await stream.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_no_match_no_fire(self, artifacts):
        """Rules that don't match should not fire."""
        server = MockDebugShellServer()
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Step 1: Something else"),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="never_fires",
                    watch=WatchSpec(stream="installer", pattern="NONEXISTENT PATTERN"),
                    then=[
                        Action(action_type="send_command", stream="debug_shell", command="bp 0x1234"),
                    ],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=2.0,
            )

            result = await engine.run()

            assert "never_fires" not in engine.fired_rules
            assert len(server.commands_received) == 0

        finally:
            await stream.close()
            await server.stop()


class TestMultipleRules:
    @pytest.mark.asyncio
    async def test_two_rules_fire_independently(self, artifacts):
        """Two rules watching different patterns should both fire."""
        server = MockDebugShellServer()
        server.on_command("bp 0x80001000", MockResponse("Breakpoint set"))
        server.on_command("bp 0x80002000", MockResponse("Breakpoint set"))
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Step 1: Loading", delay=0.05),
                ScriptedLine("Step 2: Erasing", delay=0.05),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="bp_step1",
                    watch=WatchSpec(stream="installer", pattern="Step 1"),
                    then=[Action(action_type="send_command", stream="debug_shell", command="bp 0x80001000")],
                ),
                Rule(
                    name="bp_step2",
                    watch=WatchSpec(stream="installer", pattern="Step 2"),
                    then=[Action(action_type="send_command", stream="debug_shell", command="bp 0x80002000")],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=5.0,
            )

            await engine.run()

            assert "bp_step1" in engine.fired_rules
            assert "bp_step2" in engine.fired_rules
            assert "bp 0x80001000" in server.commands_received
            assert "bp 0x80002000" in server.commands_received

        finally:
            await stream.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_one_shot_rule_fires_once(self, artifacts):
        """A once=True rule should only fire on the first match."""
        server = MockDebugShellServer()
        server.on_command("log", MockResponse("logged"))
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Step 1: first", delay=0.05),
                ScriptedLine("Step 1: duplicate", delay=0.05),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="once_only",
                    watch=WatchSpec(stream="installer", pattern="Step 1"),
                    then=[Action(action_type="send_command", stream="debug_shell", command="log")],
                    once=True,
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=3.0,
            )

            await engine.run()

            # The command should have been sent exactly once
            assert server.commands_received.count("log") == 1

        finally:
            await stream.close()
            await server.stop()


class TestSteadyState:
    @pytest.mark.asyncio
    async def test_steady_state_completes_engine(self, artifacts):
        """A steady_state action should cause the engine to return 'steady_state'."""
        server = MockDebugShellServer()
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Installation complete", delay=0.05),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="done",
                    watch=WatchSpec(stream="installer", pattern="Installation complete"),
                    then=[Action(action_type="steady_state")],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=5.0,
            )

            result = await engine.run()
            assert result == "steady_state"

        finally:
            await stream.close()
            await server.stop()


class TestAbort:
    @pytest.mark.asyncio
    async def test_abort_stops_engine(self, artifacts):
        """An abort action should cause the engine to return 'abort'."""
        server = MockDebugShellServer()
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("ERROR: device fault", delay=0.05),
                ScriptedLine("This line should not matter", delay=0.5),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="handle_error",
                    watch=WatchSpec(stream="installer", pattern="ERROR"),
                    then=[Action(action_type="abort", reason="Device fault")],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=5.0,
            )

            result = await engine.run()
            assert result == "abort"

        finally:
            await stream.close()
            await server.stop()


class TestCapture:
    @pytest.mark.asyncio
    async def test_capture_as_saves_output(self, artifacts):
        """capture_as should save the command response to artifacts."""
        server = MockDebugShellServer()
        server.on_command(
            "md 0x80004000 256",
            MockResponse("80004000: 7C 08 02 A6 94 21 FF F0"),
        )
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            installer = MockSubprocessStream("installer", [
                ScriptedLine("Step 5: validation complete", delay=0.05),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="capture_mem",
                    watch=WatchSpec(stream="installer", pattern="validation complete"),
                    then=[
                        Action(
                            action_type="send_command",
                            stream="debug_shell",
                            command="md 0x80004000 256",
                            capture_as="post_validation_memory",
                        ),
                    ],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=5.0,
            )

            await engine.run()

            # Wait a moment for the action task to complete
            await asyncio.sleep(0.2)

            assert "post_validation_memory" in artifacts.captures
            assert "7C 08 02 A6" in artifacts.captures["post_validation_memory"]

        finally:
            await stream.close()
            await server.stop()


class TestTimeout:
    @pytest.mark.asyncio
    async def test_engine_timeout(self, artifacts):
        """If no steady_state or abort happens, the engine should timeout."""
        server = MockDebugShellServer()
        port = await server.start()

        try:
            stream, client = await _make_shell(port)

            # Installer that never completes
            installer = MockSubprocessStream("installer", [
                ScriptedLine("Step 1: Starting", delay=0.05),
            ])

            shell_queue: asyncio.Queue = asyncio.Queue()
            client.add_line_callback(lambda line: shell_queue.put_nowait(line))
            from debug_harness.engine.session import _QueueStreamAdapter
            shell_adapter = _QueueStreamAdapter("debug_shell", shell_queue)

            rules = [
                Rule(
                    name="never_fires",
                    watch=WatchSpec(stream="installer", pattern="NEVER"),
                    then=[Action(action_type="steady_state")],
                ),
            ]

            engine = ReactiveEngine(
                rules=rules,
                streams={"installer": installer, "debug_shell": shell_adapter},
                debug_shell=client,
                artifacts=artifacts,
                timeout=1.0,  # short timeout
            )

            result = await engine.run()
            assert result == "abort"  # timeout triggers abort

        finally:
            await stream.close()
            await server.stop()
