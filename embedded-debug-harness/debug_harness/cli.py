"""CLI entry point for the debug harness."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from debug_harness.artifacts.collector import SessionArtifacts
from debug_harness.config.loader import load_plan, parse_plan_dict
from debug_harness.config.schema import SessionPlan


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="debug-harness",
        description="Embedded debug harness — reactive session orchestration",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    subparsers = parser.add_subparsers(dest="command")

    # start command
    start_parser = subparsers.add_parser("start", help="Start a debug session")
    start_parser.add_argument(
        "--config", required=True, help="Path to session plan YAML"
    )
    start_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock streams (no real hardware)",
    )
    start_parser.add_argument(
        "--no-tmux",
        action="store_true",
        help="Disable tmux display",
    )
    start_parser.add_argument(
        "--control-socket",
        default=None,
        help="Path for the control Unix socket",
    )
    start_parser.add_argument(
        "--control-port",
        type=int,
        default=0,
        help="TCP port for the control server (0 for auto)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.command == "start":
        asyncio.run(_start_session(args))
    else:
        parser.print_help()
        sys.exit(1)


async def _start_session(args: argparse.Namespace) -> None:
    from debug_harness.engine.session import SessionOrchestrator

    plan = load_plan(args.config)

    # Choose stream factory
    if args.mock:
        from mocks.mock_subprocess import MockStreamFactory
        factory = MockStreamFactory()
        logging.info("Using mock streams (no hardware)")
    else:
        factory = _make_real_factory()

    artifacts = SessionArtifacts(plan.settings.session_dir, plan.name)

    # Save config for reproducibility
    with open(args.config) as f:
        artifacts.save_config(f.read())

    orchestrator = SessionOrchestrator(plan, factory, artifacts)

    # Optionally start control server
    control_server = None
    if args.control_socket or args.control_port:
        from debug_harness.api.control_server import ControlServer
        control_server = ControlServer(
            stream_factory=factory,
            socket_path=args.control_socket,
            port=args.control_port or 0,
        )
        addr = await control_server.start()
        logging.info("Control server at %s", addr)

    # Run session
    result = await orchestrator.run()

    logging.info("Session completed: status=%s", result.status)
    if result.captures:
        logging.info("Captures: %s", list(result.captures.keys()))
    if result.error:
        logging.error("Error: %s", result.error)
    logging.info("Rules fired: %s", result.rules_fired)
    logging.info("Artifacts: %s", artifacts.session_dir)

    if control_server:
        await control_server.stop()

    sys.exit(0 if result.status == "completed" else 1)


def _make_real_factory():
    """Create a factory that produces real subprocess and TCP streams."""
    from debug_harness.streams.subprocess_stream import SubprocessStream
    from debug_harness.streams.tcp_stream import TcpStream

    class RealStreamFactory:
        async def create_subprocess_stream(self, name, cmd, cwd=None):
            return await SubprocessStream.create(name, cmd, cwd)

        async def create_tcp_stream(self, name, host, port):
            return await TcpStream.connect(name, host, port)

    return RealStreamFactory()
