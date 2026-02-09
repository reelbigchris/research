"""MCP server integration for embedded debug harness."""

from debug_harness.mcp.control_client import ControlClient
from debug_harness.mcp.server import main, server

__all__ = ["ControlClient", "server", "main"]
