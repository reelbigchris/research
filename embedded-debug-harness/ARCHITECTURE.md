# Embedded Debug Harness — Architecture Spec

## Problem

Firmware reverse engineering on embedded targets (PowerPC/VxWorks) requires a multi-step, timing-sensitive setup process to get a device into a debuggable state. This involves running a command interface utility to prep the device, launching an installer binary on the PC, and interacting with the device's debug shell over TCP — sometimes concurrently, with ordering constraints between them. An AI assistant (Claude Code) is good at reasoning about *what* to analyze but bad at real-time orchestration and concurrent process management.

Claude Code has full access to the installer source code and can build the binary. It can also read the firmware and Ghidra analysis to understand what the installer does and when it's safe to set breakpoints. The goal is for Claude to express a plan and have a harness execute it reliably.

## The Three Things

The harness orchestrates three concrete components. Two are run-and-done Linux processes, one is a persistent socket.

### 1. Command Interface Utility

A Linux utility developed by the team. It connects to the device, runs a given set of commands, and disconnects. It's a normal CLI tool — takes arguments or a command list, produces stdout, exits with a return code. The harness simply invokes it as a subprocess.

### 2. The Installer

A Linux binary. Claude has the source code and can build it. It runs on the PC, communicates with the device, and prints progress to stdout (including step numbers that indicate what it's done). The harness runs it as a subprocess.

### 3. The Debug Shell (TCP Socket)

Accessed via TCP (currently the operator connects with netcat). The harness replaces netcat by holding a persistent TCP socket connection.

**Prompt behavior:**

- The prompt is `->`.
- After initial connection, the prompt **does not appear automatically** — you must send a bare `\n` (press enter) after a short delay to elicit it.
- After hitting a breakpoint, the shell prints the break notification but **does not return to the prompt** until you send another `\n`.
- The harness must account for both of these: send `\n` after connecting and after detecting breakpoint-related output, then wait for `->`.

**Response boundary detection:**

- Watch for `->` to know a response is complete.
- Include a configurable timeout for cases where the prompt never appears (device crash, unexpected state).
- After timeout, the harness should report what it received rather than silently hanging.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Claude Code                                                  │
│  Reads skill + source code → generates session config         │
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
│  - Creates tmux session for operator observation              │
│  - Exposes a local interface (socket/pipe) for MCP server     │
├──────────────────────────────────────────────────────────────┤
│  tmux session (operator's view)                               │
│  Left pane: command interface + installer stdout (sequential) │
│  Right pane: debug shell session (read-only mirror)           │
└──────────────────────────────────────────────────────────────┘
```

### Startup Flow

1. Operator starts the harness: `./debug_harness start --config session_plan.yaml`
1. Harness creates a tmux session with two panes.
1. Harness starts executing the session config (prep, install, debug).
1. Harness also starts a local server (Unix socket or localhost TCP) that the MCP server connects to.
1. Operator attaches to the tmux session to watch: `tmux attach -t debug-harness`
1. Once the config reaches steady state, Claude can issue ad-hoc commands through MCP.
1. Operator kills the harness when done.

When the harness isn't running, the MCP server has nothing to connect to and its tools fail gracefully (or don't appear). Claude falls back to offline analysis.

### Separation: Harness vs. MCP Server

The harness is the real workhorse — it manages subprocesses, holds the socket, runs the reactive plan, and owns the tmux session. The MCP server is a thin adapter that connects to the harness and translates MCP tool calls into harness commands. This keeps the harness testable and usable independently of Claude Code.

## The Reactive Session Config

Claude reads the installer source code and the firmware (via Ghidra or static analysis) to understand what happens during setup. It then generates a config that tells the harness: "run these things in this order, and when you see X in one stream, do Y in another."

The config is event-driven because the installer and debug shell are concurrent and interdependent. You can't set a breakpoint at an address before the installer has loaded code there. Claude knows this from reading the source — it sees that the installer prints "Step 3" after loading code to a region, so it writes a rule: "when you see 'Step 3', set the breakpoint."

```yaml
# Session config — generated by Claude based on source code analysis

# Phase 1: Device prep via command interface utility
# The harness runs the command interface utility with these arguments/commands.
command_interface:
  commands:
    - "reset"
    - "load firmware /path/to/image.bin"
  # Harness runs the utility, waits for exit, checks return code.
  # Output appears in the left tmux pane.

# Phase 2: Installer + debug shell (concurrent, reactive)
# The harness starts the installer as a subprocess and connects to the
# debug shell. It monitors both output streams and triggers actions
# based on pattern matches.

installer:
  binary: "./installer"
  args: ["--target", "192.168.1.100", "--image", "firmware.bin"]

reactive_plan:
  # Rules are evaluated continuously against all output streams.
  # "watch" specifies the stream, "then" specifies actions.

  - watch: installer
    pattern: "Step 3: code loaded at 0x80004000"
    then:
      - debug_shell: "bp 0x80004000"
      - debug_shell: "bp 0x80008000"

  - watch: installer
    pattern: "Step 5: validation complete"
    then:
      - debug_shell: "md 0x80004000 256"
        capture_as: "post_validation_memory"

  - watch: debug_shell
    pattern: "Break at 0x80004000"
    # Harness knows to send \n first to get back to ->, then execute:
    then:
      - debug_shell: "r r3"
        capture_as: "r3_at_entry"
      - debug_shell: "go"

  - watch: installer
    pattern: "ERROR"
    then:
      - action: abort

  - watch: installer
    pattern: "Installation complete"
    then:
      - action: steady_state
      # At this point, Claude gets interactive control via MCP.

# Phase 3: Steady state (Claude takes over via MCP)
on_steady_state:
  # These run automatically when steady_state is reached, before
  # handing interactive control to Claude.
  - debug_shell: "md 0x80000000 4096"
    capture_as: "initial_memory_dump"
```

### Rule Execution Details

- When a rule's `then` block includes debug shell commands, the harness handles the prompt dance: send `\n` if needed, wait for `->`, send the command, read until `->`.
- Commands execute sequentially within a `then` block.
- Multiple rules can be pending simultaneously (watching different patterns).
- `capture_as` writes the command output to a named file in the session directory.
- If a pattern never appears, the rule simply never fires. The harness doesn't block on it.

## Observability — tmux

No custom TUI framework. The operator needs to see raw output from the components. tmux provides this naturally.

### Layout

```
┌─ Left Pane ──────────────────────┬─ Right Pane ─────────────────────────┐
│                                  │                                       │
│  $ command_interface reset       │  -> bp 0x80004000                     │
│  OK                              │  Breakpoint set at 0x80004000         │
│  $ command_interface load ...    │  -> bp 0x80008000                     │
│  OK                              │  Breakpoint set at 0x80008000         │
│                                  │  -> md 0x80004000 256                 │
│  $ ./installer --target ...      │  80004000: 7C 08 02 A6 94 21 FF F0   │
│  Step 1: Initializing...         │  80004008: BF C1 00 08 3C 60 80 00   │
│  Step 2: Connecting...           │  ...                                  │
│  Step 3: code loaded at 0x8...   │  -> r r3                              │
│  Step 4: Running...              │  r3 = 0x00000001                      │
│  Step 5: validation complete     │  -> go                                │
│  Installation complete           │  ->                                   │
│                                  │                                       │
└──────────────────────────────────┴───────────────────────────────────────┘
```

### What appears where

|Pane     |Content                                                                                                                                                          |
|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**Left** |Sequential stdout from the command interface utility, then the installer. These run one after the other. Raw output, exactly as if you ran them in a terminal.   |
|**Right**|The debug shell session — every command sent and every response received, exactly as if you were connected with netcat. Read-only mirror; the harness is driving.|

### Implementation

The harness uses **libtmux** to programmatically create the tmux session and panes at startup. The left pane runs a shell that the harness feeds subprocess output to. The right pane mirrors the debug shell socket I/O to a pty so the operator sees the raw back-and-forth.

The operator attaches from another terminal. They can scroll back, search output, and detach without affecting the harness. If something looks wrong, they kill the harness.

## MCP Tools

Exposed to Claude Code when the harness is running and has reached steady state (or when connected to a device in an existing state).

|Tool                          |Description                                                                                                                                        |
|------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
|`prepare_session(config)`     |Send a session config to the harness. The harness executes phases 1-2, reaching steady state. Returns captured data and a summary of what happened.|
|`get_device_status()`         |Query the debug shell for current state info. Useful when the operator has been working manually and wants Claude to orient itself.                |
|`send_command(cmd)`           |Send an arbitrary command to the debug shell. Handles the prompt dance, returns the output.                                                        |
|`set_breakpoint(address)`     |Convenience wrapper around `send_command`.                                                                                                         |
|`read_memory(address, length)`|Convenience wrapper.                                                                                                                               |
|`read_register(register)`     |Convenience wrapper.                                                                                                                               |
|`get_captured_data(name?)`    |Retrieve data captured during session config execution. If `name` is provided, return a specific capture. Otherwise return all.                    |
|`get_session_log()`           |Return the full session log — everything that happened during config execution.                                                                    |
|`teardown()`                  |Disconnect from the device, terminate the tmux session.                                                                                            |

## The Skill

A `SKILL.md` that teaches Claude how to use this system. Contains:

- Device architecture, debug shell command reference, prompt behavior quirks.
- How to read the installer source and reason about the setup sequence.
- The reactive config schema — what fields are available, how pattern matching works, what actions are supported.
- Examples of good configs for common analysis tasks.
- Common gotchas: "you can't set a breakpoint before step 3", "the debug shell needs a `\n` after breakpoint hits", etc.
- Guidance for both modes: harness running (use MCP tools) vs. offline (work with saved dumps and Ghidra).
- How to read a session log from a failed run and improve the config.

## Workflow

### Full AI-Assisted Session

1. Claude reads the skill, the installer source code, and any Ghidra analysis.
1. Claude generates a reactive session config based on what it learns.
1. Claude tells the operator: "Ready — start the harness with this config."
1. Operator runs `./debug_harness start --config session_plan.yaml`.
1. Operator attaches to the tmux session to watch.
1. Harness executes: command interface → installer + debug shell with reactive rules → steady state.
1. Operator sees everything happening in real time across both tmux panes.
1. Claude receives the captured data and enters interactive mode via MCP tools.
1. Claude inspects memory, sets additional breakpoints, reasons about what it finds, iterates.
1. Operator shuts down the harness when done.

### Iterative Refinement After Failure

1. A session fails (installer errors out, pattern never appears, device crashes).
1. Operator sees the failure in tmux and kills the harness.
1. Claude reads the session log (`get_session_log()` or the saved file).
1. Claude analyzes what went wrong, adjusts the config (different pattern, different ordering, additional prep commands).
1. Operator runs the harness again with the new config.
1. Repeat until the setup succeeds.

### Manual-First, AI-Assist Later

1. Operator preps the device manually (or the device is already in some state).
1. Operator starts the harness without a config: `./debug_harness start` (just connects to debug shell, no choreography).
1. Claude uses `get_device_status()` to orient itself, then issues commands interactively.

### Offline Analysis

1. Harness is not running. MCP tools unavailable.
1. Claude works with static artifacts: saved memory dumps, session logs, Ghidra projects, source code.

## Debug Shell Prompt Handling

This is a critical implementation detail. The VxWorks debug shell prompt (`->`) has quirks that the harness must handle explicitly.

### The Problem

|Situation                 |What happens                          |What the harness must do                             |
|--------------------------|--------------------------------------|-----------------------------------------------------|
|Initial connection        |No prompt appears                     |Wait ~1 second, send `\n`, wait for `->`             |
|After sending a command   |Shell prints output, then `->`        |Read until `->`                                      |
|After hitting a breakpoint|Shell prints break info, **no prompt**|Detect break-related output, send `\n`, wait for `->`|
|Device crash/hang         |Nothing comes back                    |Timeout, report what was received                    |

### Implementation

The harness's socket reader should:

1. Maintain a buffer of all received data.
1. After sending a command or `\n`, read in a loop until `->` appears at the end of the buffer (after stripping whitespace) or timeout expires.
1. Recognize breakpoint patterns (e.g., `"Break at"`) and automatically send `\n` to re-elicit the prompt before executing the next queued command.
1. Make the raw byte stream available to the tmux pane so the operator sees exactly what the harness sees.

## Session Artifacts

Every session produces files in a session directory:

|Artifact                      |Contents                                                                                                         |
|------------------------------|-----------------------------------------------------------------------------------------------------------------|
|`session_log.json`            |Timestamped event stream: commands sent, responses received, patterns matched, rules triggered, state transitions|
|`command_interface_output.txt`|Raw stdout from the command interface utility                                                                    |
|`installer_output.txt`        |Raw stdout from the installer                                                                                    |
|`debug_shell_transcript.txt`  |Raw debug shell I/O (commands and responses)                                                                     |
|`captured/`                   |Named captures from `capture_as` directives (memory dumps, register values, etc.)                                |
|`session_config.yaml`         |The config that was used (for reproducibility)                                                                   |

These serve triple duty: Claude reads them for iterative refinement, they form a historical record for institutional knowledge, and they aid debugging when things go wrong.

## Key Design Decisions

**Why separate the harness from the MCP server?**
The harness does the real work — subprocesses, socket management, tmux, reactive plan execution. The MCP server is a thin adapter. This keeps the harness testable and usable independently (e.g., an operator could use it without Claude).

**Why a reactive config instead of step-by-step commands?**
The installer and debug shell are concurrent and interdependent. You can't set a breakpoint at an address before the installer has loaded code there. Claude reads the source to understand this choreography and expresses it as event-driven rules. The harness handles the real-time pattern matching and cross-stream coordination that Claude can't do interactively.

**Why reset on startup?**
Eliminates the "what state is the device in" problem. Claude can always assume a clean starting point.

**Why tmux and not a custom TUI?**
The operator needs to see raw output from three things (command interface, installer, debug shell). tmux panes showing actual terminal output are the most natural and lowest-overhead way to do this. Works over SSH, no extra dependencies, and the operator already knows how to use tmux.

**Why `get_device_status` for manual-first workflows?**
Sometimes the operator has been manually working with the device and wants Claude to assist without a full reset. `get_device_status` lets Claude orient itself from whatever state the device is in.

## Current Implementation Status

As of this documentation, the harness includes:

- ✅ Core reactive session orchestration
- ✅ YAML config parsing and validation
- ✅ Stream adapters (subprocess, TCP, debug shell)
- ✅ ControlServer with JSON protocol
- ✅ Session artifacts and logging
- ⏳ **Missing: MCP server implementation** - The ControlServer provides a foundation but needs an MCP wrapper
- ⏳ **Missing: Claude Code skill** - SKILL.md needs to be created
- ⏳ **Missing: tmux integration** - libtmux orchestration not yet implemented
- ⏳ **Missing: Convenience MCP tools** - Higher-level wrappers around send_command

The current ControlServer API provides these methods:
- `start_session(plan)` - Execute a session plan
- `get_status()` - Query current state
- `send_command(cmd)` - Send debug shell command
- `get_capture(name)` / `get_captures()` - Retrieve captured data
- `abort()` - Abort session

These map closely to the intended MCP tools but need an MCP protocol wrapper to be usable by Claude Code.
