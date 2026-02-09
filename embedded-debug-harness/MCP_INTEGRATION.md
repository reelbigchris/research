# MCP Server Integration for Embedded Debug Harness

This document describes how to use the MCP (Model Context Protocol) server to enable Claude Code to interact with the embedded debug harness.

## Architecture

```
┌──────────────────────┐
│   Claude Code        │
│   (MCP Client)       │
└──────────┬───────────┘
           │ MCP Protocol (stdio)
           │
┌──────────▼───────────┐
│   MCP Server         │
│   debug-harness-mcp  │
└──────────┬───────────┘
           │ JSON/Unix Socket or TCP
           │
┌──────────▼───────────┐
│   Debug Harness      │
│   ControlServer      │
└──────────────────────┘
```

The MCP server acts as a thin adapter between Claude Code and the debug harness:

1. **Claude Code** uses the MCP protocol to discover and invoke tools
2. **MCP Server** (`debug-harness-mcp`) translates MCP tool calls to ControlServer JSON requests
3. **ControlServer** executes the requests and returns results
4. **MCP Server** formats the results back to Claude Code

## Installation

Install the embedded-debug-harness package with MCP support:

```bash
cd embedded-debug-harness
pip install -e .
```

This installs two CLI tools:
- `debug-harness` - The main harness orchestrator
- `debug-harness-mcp` - The MCP server for Claude Code integration

## Usage

### 1. Start the Debug Harness with Control Server

First, start the debug harness with a control endpoint:

```bash
# Using Unix socket (recommended)
debug-harness start --config examples/basic_session.yaml --control-socket /tmp/debug-harness.sock

# Or using TCP port
debug-harness start --config examples/basic_session.yaml --control-port 9999
```

The harness will:
- Execute the session plan (setup, reactive rules, etc.)
- Start a ControlServer listening on the specified socket/port
- Reach steady state and wait for MCP commands

### 2. Start the MCP Server

In a separate terminal, start the MCP server:

```bash
# Connect to Unix socket
debug-harness-mcp --control-socket /tmp/debug-harness.sock

# Or connect to TCP port
debug-harness-mcp --control-port 9999

# Enable verbose logging
debug-harness-mcp --control-socket /tmp/debug-harness.sock --verbose
```

The MCP server will:
- Connect to the harness ControlServer
- Listen on stdin/stdout for MCP protocol messages
- Expose tools to Claude Code

### 3. Configure Claude Code to Use the MCP Server

Add the MCP server to your Claude Code configuration. This is typically done in your MCP settings file or via the Claude Code UI.

**Example MCP configuration:**

```json
{
  "mcpServers": {
    "embedded-debug-harness": {
      "command": "debug-harness-mcp",
      "args": ["--control-socket", "/tmp/debug-harness.sock"],
      "env": {
        "DEBUG_HARNESS_SOCKET": "/tmp/debug-harness.sock"
      }
    }
  }
}
```

**Using environment variables:**

```json
{
  "mcpServers": {
    "embedded-debug-harness": {
      "command": "debug-harness-mcp",
      "env": {
        "DEBUG_HARNESS_SOCKET": "/tmp/debug-harness.sock"
      }
    }
  }
}
```

### 4. Use the Tools in Claude Code

Once configured, Claude Code can discover and use the debug harness tools:

```
You: Check if the debug harness is running

Claude: Let me check the harness status.
[Uses get_harness_status tool]
The debug harness is running in steady state.

You: Set a breakpoint at 0x80004000

Claude: I'll set that breakpoint.
[Uses set_breakpoint tool with address: "0x80004000"]
Breakpoint set successfully at 0x80004000.
```

## Available MCP Tools

When the harness is running, the following tools are exposed:

### `get_harness_status()`
Check if the debug harness is running and get basic status.

**Returns:** Connection status and basic state information.

### `prepare_session(config_path?, plan?)`
Start a new debug session with a reactive plan.

**Parameters:**
- `config_path` (string): Path to a YAML session plan file
- `plan` (object): Inline session plan as a dictionary

**Note:** Provide either `config_path` or `plan`, not both.

### `get_device_status()`
Query the current session state and progress.

**Returns:**
- Session state (running, completed, error, etc.)
- Whether in steady state
- Rules that have fired
- Available captures

### `send_command(command)`
Send an arbitrary command to the debug shell.

**Parameters:**
- `command` (string): Command to send (e.g., "bp 0x80004000", "md 0x80000000 256")

**Returns:** Command response from the debug shell.

**Note:** Only works when the session is in steady state.

### `set_breakpoint(address)`
Convenience wrapper to set a breakpoint.

**Parameters:**
- `address` (string): Memory address (e.g., "0x80004000")

**Returns:** Breakpoint confirmation.

### `read_memory(address, length?)`
Read memory from the device.

**Parameters:**
- `address` (string): Memory address to read from
- `length` (integer, optional): Number of bytes (default: 256)

**Returns:** Memory dump.

### `read_register(register)`
Read a CPU register value.

**Parameters:**
- `register` (string): Register name (e.g., "r3", "pc", "lr")

**Returns:** Register value.

### `get_captured_data(name?)`
Retrieve captured data from session execution.

**Parameters:**
- `name` (string, optional): Specific capture name (omit to get all)

**Returns:** Captured data content.

Captures are created by reactive rules with `capture_as` directives.

### `teardown()`
Abort the current session and cleanup.

**Returns:** Confirmation of teardown.

## Workflows

### Full AI-Assisted Session

1. **Operator starts harness:**
   ```bash
   debug-harness start --config session_plan.yaml --control-socket /tmp/debug-harness.sock
   ```

2. **MCP server connects:**
   ```bash
   debug-harness-mcp --control-socket /tmp/debug-harness.sock
   ```

3. **Claude Code uses tools:**
   - Monitors session progress with `get_device_status()`
   - Waits for steady state
   - Issues debug commands with `send_command()`, `set_breakpoint()`, `read_memory()`
   - Retrieves captured data with `get_captured_data()`

4. **Operator observes in harness logs/output**

5. **Claude or operator calls `teardown()` when done**

### Offline Mode (Harness Not Running)

When the harness is not running, the MCP server still works but only exposes:
- `get_harness_status()` - Returns "not running" status

This allows Claude Code to:
- Detect that live debugging is unavailable
- Fall back to static analysis of source code, Ghidra projects, or saved session artifacts
- Inform the user how to start the harness

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG_HARNESS_SOCKET` | Unix socket path for ControlServer | None |
| `DEBUG_HARNESS_HOST` | TCP host for ControlServer | 127.0.0.1 |
| `DEBUG_HARNESS_PORT` | TCP port for ControlServer | 0 (unset) |

## Troubleshooting

### "Debug harness is not running"

**Cause:** The MCP server cannot connect to the ControlServer.

**Solutions:**
- Verify the harness is running: check for the process
- Verify the control endpoint matches:
  - Unix socket: file exists at the specified path
  - TCP: port is listening (`netstat -an | grep <port>`)
- Check that both harness and MCP server use the same socket path/port

### "No active debug shell"

**Cause:** Trying to send commands before reaching steady state, or the debug shell connection failed.

**Solutions:**
- Check session status with `get_device_status()`
- Wait for `steady_state: true`
- Review harness logs for connection errors

### "No completed session" when getting captures

**Cause:** Session hasn't completed or no data was captured.

**Solutions:**
- Check if session is still running with `get_device_status()`
- Verify reactive rules have `capture_as` directives
- Check if the patterns in rules actually matched (review `rules_fired`)

## Example Session

```python
# In Claude Code conversation:

User: "Start a debug session with examples/basic_session.yaml"

Claude: [Uses prepare_session(config_path="examples/basic_session.yaml")]
        "Session started successfully. Session ID: a3f4d891"

User: "What's the status?"

Claude: [Uses get_device_status()]
        "Session State: running
         Steady State: False
         Rules Fired: set_initial_breakpoint"

# ... wait for completion ...

Claude: [Uses get_device_status()]
        "Session State: completed
         Steady State: True
         Rules Fired: set_initial_breakpoint, installation_complete
         Captures Available: post_validation_memory"

User: "Show me the captured memory"

Claude: [Uses get_captured_data(name="post_validation_memory")]
        "Capture 'post_validation_memory':
         80004000: 7C 08 02 A6 94 21 FF F0
         80004008: BF C1 00 08 3C 60 80 00
         ..."

User: "Read register r3"

Claude: [Uses read_register(register="r3")]
        "Register r3:
         r3 = 0x00000001"
```

## Development

### Testing the MCP Server

You can test the MCP server directly using the MCP inspector or by writing a simple MCP client.

**Start harness in mock mode:**
```bash
debug-harness start --config examples/basic_session.yaml --mock --control-socket /tmp/debug-harness.sock
```

**Start MCP server:**
```bash
debug-harness-mcp --control-socket /tmp/debug-harness.sock --verbose
```

**Send MCP requests via stdin/stdout** (for testing)

### Adding New Tools

To add a new MCP tool:

1. Add the tool definition in `handle_list_tools()` in `debug_harness/mcp/server.py`
2. Add the implementation in `handle_call_tool()`
3. If needed, add a corresponding method to `ControlClient` and `ControlServer`
4. Update this documentation

## See Also

- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system design
- [Model Context Protocol Specification](https://modelcontextprotocol.io/) - MCP protocol details
- [Claude Code Documentation](https://docs.anthropic.com/claude/docs/claude-code) - Using Claude Code with MCP
