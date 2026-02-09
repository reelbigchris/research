"""Reactive engine — the heart of the debug harness.

Watches multiple streams concurrently for pattern matches
and dispatches action sequences when rules fire.

Architecture:
- Stream reader tasks: one per watched stream, feed a unified asyncio.Queue
- Rule matcher: single task consuming the queue, evaluates all active rules per line
- Action runners: each fired rule's 'then' block runs in its own task
  (sequential within a rule, concurrent across rules)
"""

from __future__ import annotations

import asyncio
import logging
import re

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.schema import Rule
from debug_harness.streams.base import StreamAdapter, StreamLine
from debug_harness.streams.debug_shell import DebugShellClient

from .actions import execute_action_sequence

log = logging.getLogger(__name__)


class ReactiveEngine:
    """Executes reactive rules against concurrent output streams.

    Usage:
        engine = ReactiveEngine(rules, streams, debug_shell, artifacts)
        result = await engine.run()
        # result is one of: "steady_state", "abort", "timeout", "streams_exhausted"
    """

    def __init__(
        self,
        rules: list[Rule],
        streams: dict[str, StreamAdapter],
        debug_shell: DebugShellClient | None,
        artifacts: SessionArtifacts,
        timeout: float = 300.0,
    ):
        self._rules = rules
        self._streams = streams
        self._debug_shell = debug_shell
        self._artifacts = artifacts
        self._timeout = timeout

        self._abort_event = asyncio.Event()
        self._steady_state_event = asyncio.Event()
        self._line_queue: asyncio.Queue[StreamLine | None] = asyncio.Queue()
        self._fired_rules: set[str] = set()
        self._action_tasks: list[asyncio.Task] = []

        # Compile regex patterns
        self._compiled_patterns: dict[str, re.Pattern] = {}
        for rule in rules:
            self._compiled_patterns[rule.name] = re.compile(rule.watch.pattern)

    @property
    def abort_event(self) -> asyncio.Event:
        return self._abort_event

    @property
    def steady_state_event(self) -> asyncio.Event:
        return self._steady_state_event

    @property
    def fired_rules(self) -> list[str]:
        return list(self._fired_rules)

    async def run(self) -> str:
        """Run the reactive phase.

        Returns the reason for completion:
        - "steady_state": a rule fired the steady_state action
        - "abort": a rule fired the abort action
        - "timeout": reactive_timeout elapsed
        - "streams_exhausted": all streams reached EOF
        """
        tasks: list[asyncio.Task] = []

        try:
            # Start stream readers
            for stream in self._streams.values():
                task = asyncio.create_task(
                    self._read_stream(stream), name=f"reader:{stream.name}"
                )
                tasks.append(task)

            # Start the matcher
            match_task = asyncio.create_task(
                self._match_loop(), name="matcher"
            )
            tasks.append(match_task)

            # Start the deadline timer
            timer_task = asyncio.create_task(
                self._deadline_timer(), name="timer"
            )
            tasks.append(timer_task)

            # Wait for termination condition
            done_event = asyncio.Event()

            async def _watch_termination():
                while True:
                    if (
                        self._abort_event.is_set()
                        or self._steady_state_event.is_set()
                    ):
                        done_event.set()
                        return
                    await asyncio.sleep(0.05)

            watcher = asyncio.create_task(_watch_termination(), name="watcher")
            tasks.append(watcher)

            # Also stop if the matcher finishes (all streams exhausted)
            await asyncio.wait(
                [match_task, watcher],
                return_when=asyncio.FIRST_COMPLETED,
            )

        finally:
            # Cancel all tasks
            for task in tasks:
                if not task.done():
                    task.cancel()

            # Wait for action tasks to finish
            if self._action_tasks:
                await asyncio.gather(
                    *self._action_tasks, return_exceptions=True
                )

            # Cancel remaining
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Determine result
        if self._abort_event.is_set():
            return "abort"
        if self._steady_state_event.is_set():
            return "steady_state"
        return "streams_exhausted"

    async def _read_stream(self, stream: StreamAdapter) -> None:
        """Read lines from one stream and publish to the unified queue."""
        try:
            while not self._abort_event.is_set() and not self._steady_state_event.is_set():
                line = await stream.readline()
                if line is None:
                    break
                self._artifacts.log_line(line)
                await self._line_queue.put(line)
        except asyncio.CancelledError:
            pass
        finally:
            await self._line_queue.put(None)  # EOF sentinel

    async def _match_loop(self) -> None:
        """Consume lines from the queue and evaluate rules."""
        eof_count = 0
        total_streams = len(self._streams)

        try:
            while eof_count < total_streams:
                if self._abort_event.is_set() or self._steady_state_event.is_set():
                    break

                try:
                    line = await asyncio.wait_for(
                        self._line_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if line is None:
                    eof_count += 1
                    continue

                self._evaluate_rules(line)

        except asyncio.CancelledError:
            pass

    def _evaluate_rules(self, line: StreamLine) -> None:
        """Check all active rules against a line; fire matching ones."""
        for rule in self._rules:
            if rule.once and rule.name in self._fired_rules:
                continue

            if line.stream_name != rule.watch.stream:
                continue

            pattern = self._compiled_patterns[rule.name]
            if pattern.search(line.text):
                self._fired_rules.add(rule.name)
                log.info(
                    "Rule '%s' fired on %s: %s",
                    rule.name,
                    line.stream_name,
                    line.text[:100],
                )
                self._artifacts.log_event(
                    "rule_fired",
                    f"rule={rule.name} stream={line.stream_name} line={line.text[:200]}",
                )

                # Launch actions in a separate task
                task = asyncio.create_task(
                    self._run_rule_actions(rule),
                    name=f"actions:{rule.name}",
                )
                self._action_tasks.append(task)

    async def _run_rule_actions(self, rule: Rule) -> None:
        """Execute a rule's action sequence."""
        try:
            await execute_action_sequence(
                actions=rule.then,
                debug_shell=self._debug_shell,
                artifacts=self._artifacts,
                abort_event=self._abort_event,
                steady_state_event=self._steady_state_event,
                is_breakpoint_rule=rule.watch.is_breakpoint,
            )
        except Exception:
            log.exception("Error executing actions for rule '%s'", rule.name)
            self._artifacts.log_event(
                "action_error", f"rule={rule.name}"
            )

    async def _deadline_timer(self) -> None:
        """Enforce overall reactive phase timeout."""
        try:
            await asyncio.sleep(self._timeout)
            if (
                not self._abort_event.is_set()
                and not self._steady_state_event.is_set()
            ):
                log.warning("Reactive phase timed out after %ss", self._timeout)
                self._artifacts.log_event(
                    "timeout", f"{self._timeout}s elapsed"
                )
                self._abort_event.set()
        except asyncio.CancelledError:
            pass
