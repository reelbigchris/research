"""Frozen dataclasses representing a parsed session plan."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectionConfig:
    """Connection parameters for a single component."""

    # For subprocess-based components (command_interface, installer)
    command: list[str] | None = None
    cwd: str | None = None

    # For TCP-based components (debug_shell)
    host: str | None = None
    port: int | None = None


@dataclass(frozen=True)
class SetupCommand:
    """A sequential command to run during the setup phase."""

    run: str
    args: list[str] = field(default_factory=list)
    timeout: float = 30.0
    expect_exit_code: int | None = None


@dataclass(frozen=True)
class WatchSpec:
    """Specifies what stream and pattern a rule watches for."""

    stream: str  # stream name: "installer", "debug_shell"
    pattern: str  # regex pattern to match against output lines
    is_breakpoint: bool = False  # hint: prompt won't appear after this match


@dataclass(frozen=True)
class Action:
    """A single action within a rule's 'then' block."""

    action_type: str  # "send_command", "abort", "steady_state"
    stream: str | None = None  # target stream for send_command
    command: str | None = None  # command text for send_command
    capture_as: str | None = None  # save output under this name
    reason: str | None = None  # reason for abort
    timeout: float | None = None  # per-command timeout override


@dataclass(frozen=True)
class Rule:
    """A reactive rule: watch a stream for a pattern, then execute actions."""

    name: str
    watch: WatchSpec
    then: list[Action]
    once: bool = True  # fire only once by default


@dataclass(frozen=True)
class SessionSettings:
    """Global session settings with defaults."""

    prompt_timeout: float = 10.0
    command_timeout: float = 30.0
    session_dir: str = "./sessions"
    tmux_session: str | None = "debug"


@dataclass(frozen=True)
class SessionPlan:
    """Complete parsed session plan."""

    name: str
    description: str = ""
    connections: dict[str, ConnectionConfig] = field(default_factory=dict)
    settings: SessionSettings = field(default_factory=SessionSettings)
    setup: list[SetupCommand] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    reactive_timeout: float = 300.0
    on_steady_state: list[Action] = field(default_factory=list)


@dataclass
class SessionResult:
    """Result of executing a session plan."""

    status: str  # "completed", "aborted", "error", "timeout"
    captures: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    rules_fired: list[str] = field(default_factory=list)
