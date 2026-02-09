"""Load and validate a session plan from YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .schema import (
    Action,
    ConnectionConfig,
    Rule,
    SessionPlan,
    SessionSettings,
    SetupCommand,
    WatchSpec,
)


class ConfigError(Exception):
    """Raised when a session plan is invalid."""


def load_plan(path: str | Path) -> SessionPlan:
    """Load a session plan from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return parse_plan_dict(raw)


def parse_plan_dict(raw: dict[str, Any]) -> SessionPlan:
    """Parse a session plan from a raw dictionary (already loaded from YAML or JSON)."""
    if not isinstance(raw, dict):
        raise ConfigError("Session plan must be a YAML mapping")

    # Support both top-level and nested under 'session' key
    session = raw.get("session", raw)

    name = session.get("name")
    if not name:
        raise ConfigError("Session plan must have a 'name' field")

    description = session.get("description", "")

    # Parse connections
    connections = {}
    for conn_name, conn_data in session.get("connections", {}).items():
        connections[conn_name] = _parse_connection(conn_name, conn_data)

    # Parse settings
    settings = _parse_settings(session.get("settings", {}))

    # Parse setup commands
    setup = [_parse_setup_command(s) for s in session.get("setup", [])]

    # Parse reactive rules
    reactive = session.get("reactive", {})
    rules = [_parse_rule(r) for r in reactive.get("rules", [])]
    reactive_timeout = float(reactive.get("reactive_timeout", 300.0))

    # Parse on_steady_state actions
    on_steady_state = [
        _parse_action(a) for a in session.get("on_steady_state", [])
    ]

    return SessionPlan(
        name=name,
        description=description,
        connections=connections,
        settings=settings,
        setup=setup,
        rules=rules,
        reactive_timeout=reactive_timeout,
        on_steady_state=on_steady_state,
    )


def _parse_connection(name: str, data: dict[str, Any]) -> ConnectionConfig:
    if not isinstance(data, dict):
        raise ConfigError(f"Connection '{name}' must be a mapping")
    return ConnectionConfig(
        command=data.get("command"),
        cwd=data.get("cwd"),
        host=data.get("host"),
        port=data.get("port"),
    )


def _parse_settings(data: dict[str, Any]) -> SessionSettings:
    if not isinstance(data, dict):
        return SessionSettings()
    return SessionSettings(
        prompt_timeout=float(data.get("prompt_timeout", 10.0)),
        command_timeout=float(data.get("command_timeout", 30.0)),
        session_dir=data.get("session_dir", "./sessions"),
        tmux_session=data.get("tmux_session", "debug"),
    )


def _parse_setup_command(data: dict[str, Any]) -> SetupCommand:
    if not isinstance(data, dict):
        raise ConfigError(f"Setup command must be a mapping, got: {type(data)}")
    run = data.get("run")
    if not run:
        raise ConfigError("Setup command must have a 'run' field")
    return SetupCommand(
        run=run,
        args=data.get("args", []),
        timeout=float(data.get("timeout", 30.0)),
        expect_exit_code=data.get("expect_exit_code"),
    )


def _parse_rule(data: dict[str, Any]) -> Rule:
    if not isinstance(data, dict):
        raise ConfigError(f"Rule must be a mapping, got: {type(data)}")

    name = data.get("name")
    if not name:
        raise ConfigError("Rule must have a 'name' field")

    watch_data = data.get("watch")
    if not watch_data:
        raise ConfigError(f"Rule '{name}' must have a 'watch' field")
    watch = _parse_watch(name, watch_data)

    then_data = data.get("then", [])
    if not isinstance(then_data, list):
        raise ConfigError(f"Rule '{name}' 'then' must be a list")
    then = [_parse_action(a) for a in then_data]

    return Rule(
        name=name,
        watch=watch,
        then=then,
        once=data.get("once", True),
    )


def _parse_watch(rule_name: str, data: dict[str, Any]) -> WatchSpec:
    if not isinstance(data, dict):
        raise ConfigError(f"Rule '{rule_name}' watch must be a mapping")

    stream = data.get("stream")
    if not stream:
        raise ConfigError(f"Rule '{rule_name}' watch must have a 'stream' field")

    pattern = data.get("pattern")
    if not pattern:
        raise ConfigError(f"Rule '{rule_name}' watch must have a 'pattern' field")

    # Validate the regex compiles
    try:
        re.compile(pattern)
    except re.error as e:
        raise ConfigError(
            f"Rule '{rule_name}' has invalid regex pattern '{pattern}': {e}"
        )

    return WatchSpec(
        stream=stream,
        pattern=pattern,
        is_breakpoint=bool(data.get("is_breakpoint", False)),
    )


def _parse_action(data: dict[str, Any]) -> Action:
    """Parse a single action from the 'then' list.

    Supports two formats:
    1. Expanded: {"send_command": {"stream": "debug_shell", "command": "bp 0x80004000"}}
    2. Direct:   {"action_type": "send_command", "stream": "debug_shell", "command": "..."}
    """
    if not isinstance(data, dict):
        raise ConfigError(f"Action must be a mapping, got: {type(data)}")

    # Check for shorthand action types as top-level keys
    if "send_command" in data:
        inner = data["send_command"]
        if isinstance(inner, dict):
            return Action(
                action_type="send_command",
                stream=inner.get("stream"),
                command=inner.get("command"),
                capture_as=inner.get("capture_as"),
                timeout=_opt_float(inner.get("timeout")),
            )
        else:
            raise ConfigError(f"send_command value must be a mapping, got: {type(inner)}")

    if "abort" in data:
        inner = data["abort"]
        reason = inner.get("reason", "") if isinstance(inner, dict) else str(inner)
        return Action(action_type="abort", reason=reason)

    if "steady_state" in data:
        return Action(action_type="steady_state")

    if "debug_shell" in data:
        # Shorthand from the spec: {"debug_shell": "bp 0x80004000"}
        command = data["debug_shell"]
        return Action(
            action_type="send_command",
            stream="debug_shell",
            command=command,
            capture_as=data.get("capture_as"),
            timeout=_opt_float(data.get("timeout")),
        )

    # Direct format
    if "action_type" in data:
        return Action(
            action_type=data["action_type"],
            stream=data.get("stream"),
            command=data.get("command"),
            capture_as=data.get("capture_as"),
            reason=data.get("reason"),
            timeout=_opt_float(data.get("timeout")),
        )

    # Handle "action" key from the spec format
    if "action" in data:
        return Action(action_type=data["action"], reason=data.get("reason"))

    raise ConfigError(f"Cannot determine action type from: {data}")


def _opt_float(val: Any) -> float | None:
    if val is None:
        return None
    return float(val)
