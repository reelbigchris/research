"""Action executors for the reactive engine.

Each action type has a corresponding async function that performs
the action given access to the debug shell client, artifacts, and events.
"""

from __future__ import annotations

import asyncio
import logging

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import Action
from debug_harness.streams.debug_shell import DebugShellClient

log = logging.getLogger(__name__)


class SessionAborted(Exception):
    """Raised when the session is aborted by a rule."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(reason)


async def execute_action(
    action: Action,
    debug_shell: DebugShellClient | None,
    artifacts: SessionArtifacts,
    abort_event: asyncio.Event,
    steady_state_event: asyncio.Event,
    is_breakpoint_rule: bool = False,
) -> None:
    """Execute a single action from a rule's 'then' block."""

    if action.action_type == "send_command":
        if debug_shell is None:
            log.warning("send_command action but no debug shell connected")
            return

        if is_breakpoint_rule:
            debug_shell.notify_breakpoint_hit()
            is_breakpoint_rule = False  # only for the first command in the block

        response = await debug_shell.send_command(
            action.command, timeout=action.timeout
        )

        artifacts.log_event(
            "action_send_command",
            f"stream={action.stream} cmd={action.command!r} response_len={len(response)}",
        )

        if action.capture_as:
            artifacts.save_capture(action.capture_as, response)

    elif action.action_type == "abort":
        reason = action.reason or "Abort triggered by rule"
        log.warning("Session abort: %s", reason)
        artifacts.log_event("abort", reason)
        abort_event.set()

    elif action.action_type == "steady_state":
        log.info("Reached steady state")
        artifacts.log_event("steady_state", "Reactive phase complete")
        steady_state_event.set()

    else:
        log.warning("Unknown action type: %s", action.action_type)
        artifacts.log_event("unknown_action", action.action_type)


async def execute_action_sequence(
    actions: list[Action],
    debug_shell: DebugShellClient | None,
    artifacts: SessionArtifacts,
    abort_event: asyncio.Event,
    steady_state_event: asyncio.Event,
    is_breakpoint_rule: bool = False,
) -> None:
    """Execute a sequence of actions from a rule's 'then' block.

    Actions run sequentially. Stops early if abort is triggered.
    """
    first = True
    for action in actions:
        if abort_event.is_set():
            break
        await execute_action(
            action,
            debug_shell,
            artifacts,
            abort_event,
            steady_state_event,
            is_breakpoint_rule=is_breakpoint_rule and first,
        )
        first = False
