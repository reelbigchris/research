"""MCP server for embedded debug harness integration with Claude Code.

This server exposes the debug harness functionality as MCP tools that Claude Code
can use to orchestrate firmware debugging sessions.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from debug_harness.mcp.control_client import ControlClient

log = logging.getLogger(__name__)

# Global control client instance
_client: ControlClient | None = None


def get_client() -> ControlClient:
    """Get the global control client instance."""
    if _client is None:
        raise RuntimeError("Control client not initialized")
    return _client


async def check_harness_available() -> bool:
    """Check if the harness control server is available."""
    client = get_client()
    return await client.is_connected()


# Create MCP server instance
server = Server("embedded-debug-harness")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available MCP tools for the debug harness."""
    # Check if harness is available
    available = await check_harness_available()

    if not available:
        # Return limited tools when harness is not running
        return [
            types.Tool(
                name="get_harness_status",
                description="Check if the debug harness is running and available",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    # Full tool set when harness is running
    return [
        types.Tool(
            name="get_harness_status",
            description="Check if the debug harness is running and available",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="prepare_session",
            description=(
                "Start a debug session with a reactive plan. The plan defines "
                "setup steps, reactive rules for pattern matching across streams, "
                "and transitions to steady state for interactive debugging."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config_path": {
                        "type": "string",
                        "description": "Path to YAML session plan file",
                    },
                    "plan": {
                        "type": "object",
                        "description": "Inline session plan as a dictionary (alternative to config_path)",
                    },
                },
                "oneOf": [
                    {"required": ["config_path"]},
                    {"required": ["plan"]},
                ],
            },
        ),
        types.Tool(
            name="get_device_status",
            description=(
                "Query the current debug session state. Returns session status, "
                "whether it's in steady state, rules fired, and available captures."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="send_command",
            description=(
                "Send an arbitrary command to the debug shell. The harness handles "
                "prompt detection and response parsing. Only works in steady state."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command to send to the debug shell",
                    },
                },
                "required": ["command"],
            },
        ),
        types.Tool(
            name="set_breakpoint",
            description="Set a breakpoint at the specified address in the debug shell",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Memory address for breakpoint (e.g., '0x80004000')",
                    },
                },
                "required": ["address"],
            },
        ),
        types.Tool(
            name="read_memory",
            description="Read memory from the device at the specified address",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Memory address to read from (e.g., '0x80004000')",
                    },
                    "length": {
                        "type": "integer",
                        "description": "Number of bytes to read",
                        "default": 256,
                    },
                },
                "required": ["address"],
            },
        ),
        types.Tool(
            name="read_register",
            description="Read the value of a CPU register from the debug shell",
            inputSchema={
                "type": "object",
                "properties": {
                    "register": {
                        "type": "string",
                        "description": "Register name (e.g., 'r3', 'pc', 'lr')",
                    },
                },
                "required": ["register"],
            },
        ),
        types.Tool(
            name="get_captured_data",
            description=(
                "Retrieve data captured during session execution. Captures are created "
                "by reactive rules with 'capture_as' directives."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of specific capture to retrieve (omit for all captures)",
                    },
                },
            },
        ),
        types.Tool(
            name="teardown",
            description="Abort the current debug session and cleanup resources",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    args = arguments or {}
    client = get_client()

    try:
        if name == "get_harness_status":
            available = await check_harness_available()
            if available:
                status = await client.get_status()
                return [
                    types.TextContent(
                        type="text",
                        text=f"Debug harness is running.\nSession state: {status.get('state', 'unknown')}\n"
                        f"Status: {status}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text="Debug harness is NOT running or not reachable.\n"
                        "Start the harness with: debug-harness start --config <plan.yaml> --control-socket <path>",
                    )
                ]

        # All other tools require the harness to be running
        if not await check_harness_available():
            return [
                types.TextContent(
                    type="text",
                    text="Error: Debug harness is not running. Please start it first.",
                )
            ]

        if name == "prepare_session":
            plan = args.get("plan")
            config_path = args.get("config_path")
            result = await client.start_session(plan=plan, config_path=config_path)

            if result.get("status") == "ok":
                session_id = result.get("session_id", "unknown")
                return [
                    types.TextContent(
                        type="text",
                        text=f"Session started successfully.\nSession ID: {session_id}\n"
                        "The harness is executing the session plan. Use get_device_status() to check progress.",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error starting session: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "get_device_status":
            result = await client.get_status()
            if result.get("status") == "ok":
                state = result.get("state", "unknown")
                steady = result.get("steady_state", False)
                rules_fired = result.get("rules_fired", [])
                captures = result.get("captures", [])

                text = f"Session State: {state}\n"
                text += f"Steady State: {steady}\n"
                if rules_fired:
                    text += f"Rules Fired: {', '.join(rules_fired)}\n"
                if captures:
                    text += f"Captures Available: {', '.join(captures)}\n"

                return [types.TextContent(type="text", text=text)]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "send_command":
            command = args.get("command", "")
            result = await client.send_command(command)

            if result.get("status") == "ok":
                response = result.get("response", "")
                return [
                    types.TextContent(
                        type="text",
                        text=f"Command: {command}\nResponse:\n{response}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "set_breakpoint":
            address = args.get("address", "")
            command = f"bp {address}"
            result = await client.send_command(command)

            if result.get("status") == "ok":
                return [
                    types.TextContent(
                        type="text",
                        text=f"Breakpoint set at {address}\nResponse:\n{result.get('response', '')}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error setting breakpoint: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "read_memory":
            address = args.get("address", "")
            length = args.get("length", 256)
            command = f"md {address} {length}"
            result = await client.send_command(command)

            if result.get("status") == "ok":
                return [
                    types.TextContent(
                        type="text",
                        text=f"Memory at {address} ({length} bytes):\n{result.get('response', '')}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error reading memory: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "read_register":
            register = args.get("register", "")
            command = f"r {register}"
            result = await client.send_command(command)

            if result.get("status") == "ok":
                return [
                    types.TextContent(
                        type="text",
                        text=f"Register {register}:\n{result.get('response', '')}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error reading register: {result.get('message', 'Unknown error')}",
                    )
                ]

        elif name == "get_captured_data":
            name_filter = args.get("name")
            if name_filter:
                result = await client.get_capture(name_filter)
                if result.get("status") == "ok":
                    content = result.get("content", "")
                    return [
                        types.TextContent(
                            type="text",
                            text=f"Capture '{name_filter}':\n{content}",
                        )
                    ]
                else:
                    return [
                        types.TextContent(
                            type="text",
                            text=f"Error: {result.get('message', 'Unknown error')}",
                        )
                    ]
            else:
                result = await client.get_captures()
                if result.get("status") == "ok":
                    captures = result.get("captures", {})
                    if not captures:
                        return [types.TextContent(type="text", text="No captures available.")]

                    text = "Available Captures:\n\n"
                    for cap_name, cap_content in captures.items():
                        text += f"=== {cap_name} ===\n{cap_content}\n\n"
                    return [types.TextContent(type="text", text=text)]
                else:
                    return [
                        types.TextContent(
                            type="text",
                            text=f"Error: {result.get('message', 'Unknown error')}",
                        )
                    ]

        elif name == "teardown":
            result = await client.abort()
            if result.get("status") == "ok":
                return [
                    types.TextContent(
                        type="text",
                        text=f"Session teardown: {result.get('message', 'Done')}",
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: {result.get('message', 'Unknown error')}",
                    )
                ]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        log.exception(f"Error executing tool {name}")
        return [
            types.TextContent(
                type="text",
                text=f"Error executing {name}: {str(e)}",
            )
        ]


async def main(socket_path: str | None = None, host: str = "127.0.0.1", port: int = 0):
    """Run the MCP server."""
    global _client

    # Initialize control client
    _client = ControlClient(socket_path=socket_path, host=host, port=port)
    log.info(
        f"MCP server initialized. Control endpoint: "
        f"{socket_path if socket_path else f'{host}:{port}'}"
    )

    # Run the server using stdin/stdout
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="embedded-debug-harness",
            server_version="0.1.0",
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )
        await server.run(
            read_stream,
            write_stream,
            init_options,
        )


def cli():
    """CLI entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        prog="debug-harness-mcp",
        description="MCP server for embedded debug harness",
    )
    parser.add_argument(
        "--control-socket",
        default=os.environ.get("DEBUG_HARNESS_SOCKET"),
        help="Path to debug harness control Unix socket (or set DEBUG_HARNESS_SOCKET env var)",
    )
    parser.add_argument(
        "--control-host",
        default=os.environ.get("DEBUG_HARNESS_HOST", "127.0.0.1"),
        help="Host for debug harness control TCP server",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=int(os.environ.get("DEBUG_HARNESS_PORT", "0")),
        help="Port for debug harness control TCP server",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,  # Log to stderr to keep stdout clean for MCP protocol
    )

    if not args.control_socket and not args.control_port:
        log.error(
            "Must specify either --control-socket or --control-port "
            "(or set DEBUG_HARNESS_SOCKET / DEBUG_HARNESS_PORT environment variables)"
        )
        sys.exit(1)

    # Run the server
    asyncio.run(main(
        socket_path=args.control_socket,
        host=args.control_host,
        port=args.control_port,
    ))


if __name__ == "__main__":
    cli()
