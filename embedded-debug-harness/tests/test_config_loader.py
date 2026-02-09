"""Tests for YAML config loading and validation."""

from __future__ import annotations

import pytest

from debug_harness.config.loader import ConfigError, load_plan, parse_plan_dict
from debug_harness.config.schema import SessionPlan


class TestParseBasic:
    def test_minimal_plan(self):
        raw = {"session": {"name": "test"}}
        plan = parse_plan_dict(raw)
        assert plan.name == "test"
        assert plan.rules == []
        assert plan.setup == []

    def test_missing_name_raises(self):
        with pytest.raises(ConfigError, match="name"):
            parse_plan_dict({"session": {}})

    def test_top_level_format(self):
        """Support name at top level without 'session' wrapper."""
        raw = {"name": "flat-plan"}
        plan = parse_plan_dict(raw)
        assert plan.name == "flat-plan"


class TestConnections:
    def test_subprocess_connection(self):
        raw = {
            "session": {
                "name": "test",
                "connections": {
                    "installer": {
                        "command": ["./installer", "--flag"],
                        "cwd": "/opt",
                    }
                },
            }
        }
        plan = parse_plan_dict(raw)
        conn = plan.connections["installer"]
        assert conn.command == ["./installer", "--flag"]
        assert conn.cwd == "/opt"

    def test_tcp_connection(self):
        raw = {
            "session": {
                "name": "test",
                "connections": {
                    "debug_shell": {"host": "192.168.1.100", "port": 1534}
                },
            }
        }
        plan = parse_plan_dict(raw)
        conn = plan.connections["debug_shell"]
        assert conn.host == "192.168.1.100"
        assert conn.port == 1534


class TestSetup:
    def test_setup_commands(self):
        raw = {
            "session": {
                "name": "test",
                "setup": [
                    {"run": "reset", "args": ["--hard"], "timeout": 15},
                    {"run": "load", "expect_exit_code": 0},
                ],
            }
        }
        plan = parse_plan_dict(raw)
        assert len(plan.setup) == 2
        assert plan.setup[0].run == "reset"
        assert plan.setup[0].args == ["--hard"]
        assert plan.setup[0].timeout == 15.0
        assert plan.setup[1].expect_exit_code == 0

    def test_missing_run_raises(self):
        raw = {"session": {"name": "test", "setup": [{"args": ["x"]}]}}
        with pytest.raises(ConfigError, match="run"):
            parse_plan_dict(raw)


class TestRules:
    def test_basic_rule(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "r1",
                            "watch": {"stream": "installer", "pattern": "Step 1"},
                            "then": [
                                {
                                    "send_command": {
                                        "stream": "debug_shell",
                                        "command": "bp 0x80004000",
                                    }
                                }
                            ],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert len(plan.rules) == 1
        rule = plan.rules[0]
        assert rule.name == "r1"
        assert rule.watch.stream == "installer"
        assert rule.watch.pattern == "Step 1"
        assert rule.once is True
        assert len(rule.then) == 1
        assert rule.then[0].action_type == "send_command"
        assert rule.then[0].command == "bp 0x80004000"

    def test_breakpoint_watch(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "bp",
                            "watch": {
                                "stream": "debug_shell",
                                "pattern": "Break at",
                                "is_breakpoint": True,
                            },
                            "then": [],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].watch.is_breakpoint is True

    def test_once_false(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "repeat",
                            "watch": {"stream": "installer", "pattern": "x"},
                            "then": [],
                            "once": False,
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].once is False

    def test_invalid_regex_raises(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "bad",
                            "watch": {"stream": "x", "pattern": "[unclosed"},
                            "then": [],
                        }
                    ]
                },
            }
        }
        with pytest.raises(ConfigError, match="invalid regex"):
            parse_plan_dict(raw)


class TestActions:
    def test_abort_action(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "err",
                            "watch": {"stream": "installer", "pattern": "ERROR"},
                            "then": [{"abort": {"reason": "failure"}}],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        action = plan.rules[0].then[0]
        assert action.action_type == "abort"
        assert action.reason == "failure"

    def test_steady_state_action(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "done",
                            "watch": {"stream": "installer", "pattern": "Complete"},
                            "then": [{"steady_state": True}],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].then[0].action_type == "steady_state"

    def test_capture_as(self):
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "cap",
                            "watch": {"stream": "installer", "pattern": "x"},
                            "then": [
                                {
                                    "send_command": {
                                        "stream": "debug_shell",
                                        "command": "md 0x80000000 256",
                                        "capture_as": "mem_dump",
                                    }
                                }
                            ],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].then[0].capture_as == "mem_dump"

    def test_debug_shell_shorthand(self):
        """Support the spec's shorthand: {debug_shell: "command"}."""
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "sh",
                            "watch": {"stream": "installer", "pattern": "x"},
                            "then": [
                                {"debug_shell": "bp 0x80004000"},
                                {
                                    "debug_shell": "md 0x80004000 256",
                                    "capture_as": "mem",
                                },
                            ],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].then[0].command == "bp 0x80004000"
        assert plan.rules[0].then[0].stream == "debug_shell"
        assert plan.rules[0].then[1].capture_as == "mem"

    def test_action_key_format(self):
        """Support spec format: {action: abort}."""
        raw = {
            "session": {
                "name": "test",
                "reactive": {
                    "rules": [
                        {
                            "name": "a",
                            "watch": {"stream": "installer", "pattern": "x"},
                            "then": [{"action": "abort"}],
                        }
                    ]
                },
            }
        }
        plan = parse_plan_dict(raw)
        assert plan.rules[0].then[0].action_type == "abort"


class TestLoadFromFile:
    def test_load_example_basic(self, tmp_path):
        yaml_content = """
session:
  name: "test-load"
  connections:
    installer:
      command: ["./installer"]
  reactive:
    rules:
      - name: "done"
        watch:
          stream: installer
          pattern: "Complete"
        then:
          - steady_state: true
"""
        config_file = tmp_path / "plan.yaml"
        config_file.write_text(yaml_content)
        plan = load_plan(config_file)
        assert plan.name == "test-load"

    def test_load_nonexistent_raises(self):
        with pytest.raises(ConfigError, match="not found"):
            load_plan("/nonexistent/path.yaml")
