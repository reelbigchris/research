"""Pre-built mock scenarios for common test cases.

Each function returns a configured MockStreamFactory ready to use
with a SessionOrchestrator. Also provides helpers for creating
session plans programmatically.
"""

from __future__ import annotations

from debug_harness.config.schema import (
    Action,
    ConnectionConfig,
    Rule,
    SessionPlan,
    SessionSettings,
    WatchSpec,
)

from .mock_subprocess import MockStreamFactory, ScriptedLine
from .mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream


async def basic_firmware_update(
    *,
    install_delay: float = 0.05,
    shell_host: str = "127.0.0.1",
) -> tuple[SessionPlan, MockStreamFactory, MockDebugShellServer]:
    """Create a basic firmware update scenario.

    Installer emits 5 steps then "Installation complete".
    Debug shell responds to bp, md, and i commands.

    Returns (plan, factory, mock_server) — caller must start the server
    and wire the TCP stream before running.
    """
    factory = MockStreamFactory()

    factory.script_subprocess("installer", [
        ScriptedLine("Installer v2.1 starting...", delay=install_delay),
        ScriptedLine("Step 1: Initializing connection", delay=install_delay),
        ScriptedLine("Step 2: Erasing flash sectors", delay=install_delay),
        ScriptedLine("Step 3: code loaded at 0x80004000", delay=install_delay),
        ScriptedLine("Step 4: Running validation", delay=install_delay),
        ScriptedLine("Step 5: validation complete", delay=install_delay),
        ScriptedLine("Installation complete", delay=install_delay),
    ])

    factory.script_subprocess("command_interface", [
        ScriptedLine("OK"),
    ])

    server = MockDebugShellServer(host=shell_host)
    server.on_command("bp 0x80004000", MockResponse("Breakpoint set at 0x80004000"))
    server.on_command("bp 0x80008000", MockResponse("Breakpoint set at 0x80008000"))
    server.on_command("md 0x80004000 256", MockResponse(
        "80004000: 7C 08 02 A6 94 21 FF F0\n"
        "80004008: BF C1 00 08 3C 60 80 00"
    ))
    server.on_command("r r3", MockResponse("r3 = 0x00000001"))
    server.on_command("go", MockResponse(""))
    server.on_command("i", MockResponse(
        "NAME          ENTRY       TID    PRI   STATUS\n"
        "tRootTask     0x80002000  0x01   0     READY\n"
        "tLogTask      0x80003000  0x02   1     READY"
    ))
    server.on_command("md 0x80000000 4096", MockResponse(
        "80000000: 00 00 00 00 00 00 00 00\n"
        "80000008: 7C 08 02 A6 94 21 FF F0"
    ))

    plan = SessionPlan(
        name="basic-firmware-update",
        description="Test scenario: basic firmware update with breakpoints",
        connections={
            "installer": ConnectionConfig(command=["./installer"]),
            "debug_shell": ConnectionConfig(host=shell_host, port=0),
        },
        settings=SessionSettings(
            prompt_timeout=5.0,
            command_timeout=10.0,
            session_dir="./test-sessions",
        ),
        rules=[
            Rule(
                name="set_breakpoints",
                watch=WatchSpec(stream="installer", pattern="Step 3.*code loaded"),
                then=[
                    Action(action_type="send_command", stream="debug_shell", command="bp 0x80004000"),
                    Action(action_type="send_command", stream="debug_shell", command="bp 0x80008000"),
                ],
            ),
            Rule(
                name="post_validation",
                watch=WatchSpec(stream="installer", pattern="Step 5.*validation complete"),
                then=[
                    Action(
                        action_type="send_command",
                        stream="debug_shell",
                        command="md 0x80004000 256",
                        capture_as="post_validation_memory",
                    ),
                ],
            ),
            Rule(
                name="done",
                watch=WatchSpec(stream="installer", pattern="Installation complete"),
                then=[Action(action_type="steady_state")],
            ),
        ],
        reactive_timeout=30.0,
    )

    return plan, factory, server


async def breakpoint_hit_scenario(
    *,
    shell_host: str = "127.0.0.1",
) -> tuple[SessionPlan, MockStreamFactory, MockDebugShellServer]:
    """Create a scenario that exercises breakpoint hit handling.

    After the "go" command, the mock server emits a breakpoint notification
    (without prompt). The session plan has a rule that watches for the break
    and sends register read + continue commands.
    """
    factory = MockStreamFactory()

    factory.script_subprocess("installer", [
        ScriptedLine("Step 1: Loading code", delay=0.05),
        ScriptedLine("Step 2: Starting execution", delay=0.2),
        ScriptedLine("Installation complete", delay=0.5),
    ])

    server = MockDebugShellServer(host=shell_host)
    server.on_command("bp 0x80004000", MockResponse("Breakpoint set at 0x80004000"))
    server.on_command("go", MockResponse(""))
    server.schedule_breakpoint(
        trigger_after="go",
        breakpoint_text="Break at 0x80004000, task: tRootTask",
        delay=0.05,
    )
    server.on_command("r r3", MockResponse("r3 = 0x00000042"))
    server.on_command("c", MockResponse(""))

    plan = SessionPlan(
        name="breakpoint-hit-test",
        connections={
            "installer": ConnectionConfig(command=["./installer"]),
            "debug_shell": ConnectionConfig(host=shell_host, port=0),
        },
        settings=SessionSettings(prompt_timeout=5.0, command_timeout=10.0),
        rules=[
            Rule(
                name="set_bp",
                watch=WatchSpec(stream="installer", pattern="Step 1"),
                then=[
                    Action(action_type="send_command", stream="debug_shell", command="bp 0x80004000"),
                    Action(action_type="send_command", stream="debug_shell", command="go"),
                ],
            ),
            Rule(
                name="handle_break",
                watch=WatchSpec(
                    stream="debug_shell",
                    pattern="Break at 0x80004000",
                    is_breakpoint=True,
                ),
                then=[
                    Action(
                        action_type="send_command",
                        stream="debug_shell",
                        command="r r3",
                        capture_as="r3_at_break",
                    ),
                    Action(action_type="send_command", stream="debug_shell", command="c"),
                ],
            ),
            Rule(
                name="done",
                watch=WatchSpec(stream="installer", pattern="Installation complete"),
                then=[Action(action_type="steady_state")],
            ),
        ],
        reactive_timeout=15.0,
    )

    return plan, factory, server


async def error_abort_scenario(
    *,
    shell_host: str = "127.0.0.1",
) -> tuple[SessionPlan, MockStreamFactory, MockDebugShellServer]:
    """Create a scenario where the installer errors out, triggering abort."""
    factory = MockStreamFactory()

    factory.script_subprocess("installer", [
        ScriptedLine("Step 1: Initializing", delay=0.05),
        ScriptedLine("ERROR: Device not responding", delay=0.1),
        ScriptedLine("Step 2: This should not be processed", delay=0.05),
    ])

    server = MockDebugShellServer(host=shell_host)
    server.on_command("tt", MockResponse(
        "tRootTask: exception at 0x80005000\n"
        "  r0 = 0x00000000  r1 = 0xFFFFFFFF"
    ))

    plan = SessionPlan(
        name="error-abort-test",
        connections={
            "installer": ConnectionConfig(command=["./installer"]),
            "debug_shell": ConnectionConfig(host=shell_host, port=0),
        },
        settings=SessionSettings(prompt_timeout=5.0, command_timeout=10.0),
        rules=[
            Rule(
                name="handle_error",
                watch=WatchSpec(stream="installer", pattern="ERROR"),
                then=[
                    Action(
                        action_type="send_command",
                        stream="debug_shell",
                        command="tt",
                        capture_as="error_traceback",
                    ),
                    Action(action_type="abort", reason="Installer error"),
                ],
            ),
            Rule(
                name="done",
                watch=WatchSpec(stream="installer", pattern="Installation complete"),
                then=[Action(action_type="steady_state")],
            ),
        ],
        reactive_timeout=10.0,
    )

    return plan, factory, server
