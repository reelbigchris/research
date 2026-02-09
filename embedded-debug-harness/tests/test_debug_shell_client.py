"""Tests for the DebugShellClient prompt state machine.

Uses MockDebugShellServer to simulate VxWorks prompt quirks.
"""

from __future__ import annotations

import asyncio

import pytest

from debug_harness.streams.debug_shell import (
    CommandTimeout,
    DebugShellClient,
    PromptState,
    PromptTimeout,
)
from mocks.mock_tcp_server import MockDebugShellServer, MockResponse, MockTcpStream


@pytest.fixture
async def shell_env():
    """Set up a mock debug shell server and connected client."""
    server = MockDebugShellServer()
    port = await server.start()

    stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", port)
    client = DebugShellClient(stream, prompt_timeout=5.0, command_timeout=5.0)

    yield server, client

    await stream.close()
    await server.stop()


class TestConnectAndSync:
    @pytest.mark.asyncio
    async def test_initial_sync(self, shell_env):
        """After connect, sending \\n should elicit -> and transition to READY."""
        server, client = shell_env
        assert client.state == PromptState.DISCONNECTED

        await client.connect_and_sync()
        assert client.state == PromptState.READY

    @pytest.mark.asyncio
    async def test_no_prompt_timeout(self):
        """If the server never sends a prompt, connect_and_sync should timeout."""

        # Create a server that accepts connections but never sends data
        async def _hold_connection(reader, writer):
            # Hold the connection open but never respond
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(
            _hold_connection,
            "127.0.0.1",
            0,
        )
        port = server.sockets[0].getsockname()[1]

        stream = await MockTcpStream.connect("debug_shell", "127.0.0.1", port)
        client = DebugShellClient(stream, prompt_timeout=0.5, command_timeout=1.0)

        with pytest.raises(PromptTimeout):
            await client.connect_and_sync()

        await stream.close()
        server.close()


class TestSendCommand:
    @pytest.mark.asyncio
    async def test_basic_command(self, shell_env):
        """Send a command and receive the response."""
        server, client = shell_env
        server.on_command("i", MockResponse(
            "NAME          ENTRY\ntRootTask     0x80002000"
        ))

        await client.connect_and_sync()
        response = await client.send_command("i")

        assert "tRootTask" in response
        assert client.state == PromptState.READY

    @pytest.mark.asyncio
    async def test_multiple_commands(self, shell_env):
        """Send multiple commands sequentially."""
        server, client = shell_env
        server.on_command("bp 0x80004000", MockResponse("Breakpoint set at 0x80004000"))
        server.on_command("bp 0x80008000", MockResponse("Breakpoint set at 0x80008000"))

        await client.connect_and_sync()

        r1 = await client.send_command("bp 0x80004000")
        assert "Breakpoint set" in r1

        r2 = await client.send_command("bp 0x80008000")
        assert "0x80008000" in r2

    @pytest.mark.asyncio
    async def test_command_timeout(self, shell_env):
        """If the server never sends a prompt after a command, timeout."""
        server, client = shell_env
        # Register a response that doesn't include the prompt
        server.on_command("hang", MockResponse("partial output", include_prompt=False))

        await client.connect_and_sync()

        with pytest.raises(CommandTimeout):
            await client.send_command("hang", timeout=0.5)


class TestBreakpointHandling:
    @pytest.mark.asyncio
    async def test_breakpoint_resync(self, shell_env):
        """After a breakpoint hit, send_command should send \\n first to re-sync."""
        server, client = shell_env
        server.on_command("go", MockResponse(""))
        server.schedule_breakpoint(
            trigger_after="go",
            breakpoint_text="Break at 0x80004000, task: tRootTask",
            delay=0.05,
        )
        server.on_command("r r3", MockResponse("r3 = 0x00000001"))

        await client.connect_and_sync()

        # Send "go" — this will complete (prompt received),
        # then the server emits the breakpoint text asynchronously.
        await client.send_command("go")

        # Simulate the reactive engine detecting the breakpoint
        # and notifying the client
        await asyncio.sleep(0.15)  # wait for breakpoint text to arrive
        client.notify_breakpoint_hit()
        assert client.state == PromptState.BREAKPOINT_HIT

        # Now send another command — should re-sync first
        response = await client.send_command("r r3")
        assert "r3 = 0x00000001" in response
        assert client.state == PromptState.READY


class TestConcurrentAccess:
    @pytest.mark.asyncio
    async def test_lock_serializes_commands(self, shell_env):
        """Two concurrent send_command calls should be serialized by the lock."""
        server, client = shell_env
        server.on_command("cmd1", MockResponse("result1", delay=0.1))
        server.on_command("cmd2", MockResponse("result2", delay=0.1))

        await client.connect_and_sync()

        # Send both commands concurrently
        r1, r2 = await asyncio.gather(
            client.send_command("cmd1"),
            client.send_command("cmd2"),
        )

        # Both should succeed (lock prevents interleaving)
        assert "result1" in r1 or "result2" in r1
        assert "result1" in r2 or "result2" in r2

        # Server should have received both commands
        assert len(server.commands_received) == 2


class TestLineCallbacks:
    @pytest.mark.asyncio
    async def test_callback_receives_lines(self, shell_env):
        """Line callbacks should receive all lines read from the shell."""
        server, client = shell_env
        server.on_command("i", MockResponse("line1\nline2\nline3"))

        received_lines = []
        client.add_line_callback(lambda line: received_lines.append(line.text))

        await client.connect_and_sync()
        await client.send_command("i")

        # Should have received the prompt line(s) and response lines
        texts = [l for l in received_lines if l.strip() and l.strip() != "->"]
        assert any("line1" in t for t in texts)
