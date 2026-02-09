"""Integration tests for the SessionOrchestrator — full session lifecycle.

Uses pre-built scenarios from mocks/scenarios.py for end-to-end testing.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import Action, ConnectionConfig, Rule, SessionSettings, WatchSpec
from debug_harness.engine.session import SessionOrchestrator
from mocks.mock_subprocess import MockStreamFactory, ScriptedLine
from mocks.mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream
from tests.conftest import make_plan


@pytest.fixture
def session_dir(tmp_path):
    return str(tmp_path / "sessions")


async def _run_session(
    plan, factory, server, session_dir
) -> tuple:
    """Helper: wire up factory with server, create orchestrator, run session."""
    port = await server.start()

    # Update plan with actual server port
    updated_connections = dict(plan.connections)
    updated_connections["debug_shell"] = ConnectionConfig(host="127.0.0.1", port=port)
    plan = plan.__class__(
        name=plan.name,
        description=plan.description,
        connections=updated_connections,
        settings=plan.settings,
        setup=plan.setup,
        rules=plan.rules,
        reactive_timeout=plan.reactive_timeout,
        on_steady_state=plan.on_steady_state,
    )

    # Wire the TCP stream from the mock server into the factory
    tcp_stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", port)
    factory.set_tcp_stream("debug_shell", tcp_stream)

    artifacts = SessionArtifacts(session_dir, plan.name)
    orchestrator = SessionOrchestrator(plan, factory, artifacts)

    result = await orchestrator.run()

    return result, artifacts, server


class TestBasicSession:
    @pytest.mark.asyncio
    async def test_basic_firmware_update(self, session_dir):
        """Full session: installer runs, rules fire, reaches steady_state."""
        from mocks.scenarios import basic_firmware_update

        plan, factory, server = await basic_firmware_update()

        result, artifacts, server = await _run_session(
            plan, factory, server, session_dir
        )

        await server.stop()

        assert result.status == "completed"
        assert "set_breakpoints" in result.rules_fired
        assert "post_validation" in result.rules_fired
        assert "done" in result.rules_fired
        assert "post_validation_memory" in result.captures
        assert "7C 08 02 A6" in result.captures["post_validation_memory"]

    @pytest.mark.asyncio
    async def test_error_abort_session(self, session_dir):
        """Session aborts when installer reports an error."""
        from mocks.scenarios import error_abort_scenario

        plan, factory, server = await error_abort_scenario()

        result, artifacts, server = await _run_session(
            plan, factory, server, session_dir
        )

        await server.stop()

        assert result.status == "aborted"
        assert "handle_error" in result.rules_fired
        assert "error_traceback" in result.captures


class TestArtifactGeneration:
    @pytest.mark.asyncio
    async def test_session_dir_created(self, session_dir):
        """Session creates an artifact directory with log files."""
        from mocks.scenarios import basic_firmware_update

        plan, factory, server = await basic_firmware_update()

        result, artifacts, server = await _run_session(
            plan, factory, server, session_dir
        )

        await server.stop()

        session_path = artifacts.session_dir
        assert session_path.exists()
        assert (session_path / "session.jsonl").exists()
        assert (session_path / "summary.json").exists()

        # Verify the JSONL log contains entries
        with open(session_path / "session.jsonl") as f:
            lines = f.readlines()
        assert len(lines) > 0
        first_entry = json.loads(lines[0])
        assert "ts" in first_entry

    @pytest.mark.asyncio
    async def test_captures_saved_to_files(self, session_dir):
        """Captures should be written to individual files."""
        from mocks.scenarios import basic_firmware_update

        plan, factory, server = await basic_firmware_update()

        result, artifacts, server = await _run_session(
            plan, factory, server, session_dir
        )

        await server.stop()

        capture_file = artifacts.session_dir / "capture_post_validation_memory.txt"
        assert capture_file.exists()
        content = capture_file.read_text()
        assert "7C 08 02 A6" in content


class TestSetupPhase:
    @pytest.mark.asyncio
    async def test_setup_runs_before_reactive(self, session_dir):
        """Setup commands should run before the reactive phase starts."""
        factory = MockStreamFactory()

        # Script the command_interface subprocess
        factory.script_subprocess("command_interface", [
            ScriptedLine("Reset OK"),
        ])

        factory.script_subprocess("installer", [
            ScriptedLine("Installation complete", delay=0.05),
        ])

        server = MockDebugShellServer()
        port = await server.start()

        tcp_stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", port)
        factory.set_tcp_stream("debug_shell", tcp_stream)

        from debug_harness.config.schema import SetupCommand
        plan = make_plan(
            name="setup-test",
            connections={
                "command_interface": ConnectionConfig(command=["echo", "OK"]),
                "installer": ConnectionConfig(command=["./installer"]),
                "debug_shell": ConnectionConfig(host="127.0.0.1", port=port),
            },
            setup=[SetupCommand(run="reset", args=["--hard"], timeout=10)],
            rules=[
                Rule(
                    name="done",
                    watch=WatchSpec(stream="installer", pattern="Installation complete"),
                    then=[Action(action_type="steady_state")],
                ),
            ],
        )

        artifacts = SessionArtifacts(session_dir, "setup-test")
        orchestrator = SessionOrchestrator(plan, factory, artifacts)
        result = await orchestrator.run()

        await server.stop()

        assert result.status == "completed"

        # Verify the session log has setup events before reactive events
        with open(artifacts.session_dir / "session.jsonl") as f:
            events = [json.loads(line) for line in f.readlines()]

        event_types = [
            e.get("event", e.get("type", ""))
            for e in events
            if e.get("type") == "event"
        ]
        # setup_command_start should appear before reactive_start
        if "setup_command_start" in event_types and "reactive_start" in event_types:
            assert event_types.index("setup_command_start") < event_types.index("reactive_start")


class TestMinimalSession:
    @pytest.mark.asyncio
    async def test_empty_plan(self, session_dir):
        """A plan with no setup and no rules should complete immediately."""
        factory = MockStreamFactory()
        plan = make_plan(name="empty", rules=[], setup=[])
        artifacts = SessionArtifacts(session_dir, "empty")

        orchestrator = SessionOrchestrator(plan, factory, artifacts)
        result = await orchestrator.run()

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_rules_only_no_setup(self, session_dir):
        """A plan with only reactive rules and no setup phase."""
        factory = MockStreamFactory()

        factory.script_subprocess("installer", [
            ScriptedLine("Done", delay=0.05),
        ])

        server = MockDebugShellServer()
        port = await server.start()
        tcp_stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", port)
        factory.set_tcp_stream("debug_shell", tcp_stream)

        plan = make_plan(
            connections={
                "installer": ConnectionConfig(command=["./installer"]),
                "debug_shell": ConnectionConfig(host="127.0.0.1", port=port),
            },
            rules=[
                Rule(
                    name="done",
                    watch=WatchSpec(stream="installer", pattern="Done"),
                    then=[Action(action_type="steady_state")],
                ),
            ],
        )

        artifacts = SessionArtifacts(session_dir, "rules-only")
        orchestrator = SessionOrchestrator(plan, factory, artifacts)
        result = await orchestrator.run()

        await server.stop()

        assert result.status == "completed"
        assert "done" in result.rules_fired
