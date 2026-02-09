# Embedded Debug Harness

A reactive orchestration harness for embedded firmware debugging sessions, designed to work with AI assistants like Claude Code.

## Overview

The embedded-debug-harness automates the complex, timing-sensitive process of setting up embedded devices (PowerPC/VxWorks) for firmware reverse engineering. It orchestrates multiple concurrent processes (command interface utilities, installer binaries, debug shells) using a reactive, event-driven approach.

## Key Features

- **Reactive Session Plans**: Define setup sequences with pattern-based rules that trigger actions across multiple streams
- **Multi-Stream Orchestration**: Coordinate command-line utilities, installer processes, and TCP debug shells
- **MCP Integration**: Full Model Context Protocol server for Claude Code integration
- **Session Artifacts**: Automatic capture and logging of all session activity
- **Mock Support**: Test session plans without real hardware

## Quick Start

### Installation

```bash
pip install -e .
```

This installs two CLI tools:
- `debug-harness` - The orchestration harness
- `debug-harness-mcp` - MCP server for Claude Code integration

### Run a Session

```bash
# Using real hardware
debug-harness start --config examples/basic_session.yaml

# Using mock streams (no hardware)
debug-harness start --config examples/basic_session.yaml --mock

# With MCP control server
debug-harness start --config examples/basic_session.yaml --control-socket /tmp/debug-harness.sock
```

### Use with Claude Code

1. Start the harness with a control endpoint:
   ```bash
   debug-harness start --config session.yaml --control-socket /tmp/debug-harness.sock
   ```

2. Configure the MCP server in Claude Code:
   ```json
   {
     "mcpServers": {
       "embedded-debug-harness": {
         "command": "debug-harness-mcp",
         "args": ["--control-socket", "/tmp/debug-harness.sock"]
       }
     }
   }
   ```

3. Claude Code can now use tools like `send_command()`, `set_breakpoint()`, `read_memory()`, etc.

See [MCP_INTEGRATION.md](MCP_INTEGRATION.md) for complete MCP integration details.

## Architecture

The harness orchestrates three components:

1. **Command Interface Utility** - Device prep commands (subprocess)
2. **Installer** - Firmware loading binary (subprocess)
3. **Debug Shell** - Interactive TCP connection to device

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code                                                  │
│  Reads source code → generates session config                 │
│  After steady state: issues ad-hoc debug commands via MCP     │
├──────────────────────────────────────────────────────────────┤
│  MCP Server (thin layer)                                      │
│  Connects to the harness process, exposes tools to Claude     │
├──────────────────────────────────────────────────────────────┤
│  Harness Process                                              │
│  - Runs command interface utility (subprocess)                │
│  - Runs installer (subprocess)                                │
│  - Holds debug shell TCP socket                               │
│  - Executes the reactive session config                       │
│  - Exposes a local interface (socket/pipe) for MCP server     │
└──────────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete architectural specification.

## Session Plans

Session plans are YAML files that define:

- **Connections**: Which processes and streams to create
- **Setup**: Sequential initialization commands
- **Reactive Rules**: Pattern-based triggers across output streams
- **Steady State**: Transition to interactive mode

Example:

```yaml
session:
  name: "basic-debug"

  connections:
    installer:
      command: ["./installer", "--target", "192.168.1.100"]
    debug_shell:
      host: "192.168.1.100"
      port: 1534

  reactive:
    rules:
      - name: "set_breakpoint_after_load"
        watch:
          stream: installer
          pattern: "Step 3: code loaded at 0x80004000"
        then:
          - send_command:
              stream: debug_shell
              command: "bp 0x80004000"

      - name: "installation_complete"
        watch:
          stream: installer
          pattern: "Installation complete"
        then:
          - steady_state: true
```

See `examples/` for more session plan examples.

## MCP Tools

When integrated with Claude Code via MCP, the following tools are available:

| Tool | Description |
|------|-------------|
| `prepare_session(config)` | Start a debug session with a reactive plan |
| `get_device_status()` | Query current session state and progress |
| `send_command(cmd)` | Send arbitrary command to debug shell |
| `set_breakpoint(address)` | Set breakpoint at memory address |
| `read_memory(address, length)` | Read device memory |
| `read_register(register)` | Read CPU register value |
| `get_captured_data(name?)` | Retrieve captured session data |
| `teardown()` | Abort session and cleanup |

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Project Structure

```
embedded-debug-harness/
├── debug_harness/
│   ├── api/              # ControlServer for external integration
│   ├── artifacts/        # Session logging and capture collection
│   ├── config/           # YAML plan loading and validation
│   ├── engine/           # Session orchestrator and reactive engine
│   ├── mcp/              # MCP server for Claude Code integration
│   ├── streams/          # Subprocess, TCP, and debug shell adapters
│   └── cli.py            # Command-line interface
├── examples/             # Example session plans
├── tests/                # Test suite
├── mocks/                # Mock streams for testing
├── ARCHITECTURE.md       # Detailed architecture specification
├── MCP_INTEGRATION.md    # MCP integration guide
└── README.md            # This file
```

## Use Cases

### Full AI-Assisted Debugging

1. Claude reads installer source code and firmware analysis
2. Claude generates a reactive session plan
3. Operator starts the harness with the plan
4. Harness executes setup and reaches steady state
5. Claude uses MCP tools for interactive debugging
6. Session artifacts are saved for iterative refinement

### Offline Analysis

When the harness isn't running, Claude can:
- Analyze saved session logs and captures
- Work with Ghidra projects and static analysis
- Review and improve session plans
- Generate new reactive configs based on source code

## Contributing

This is an internal research tool. For issues or questions, contact the development team.

## License

Internal use only.
