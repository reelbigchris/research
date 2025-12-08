"""
Textual Integration for Agent Execution Environment

Provides async-compatible wrappers that keep the Textual UI responsive
while agent code executes. Uses Textual's worker system to run execution
off the main thread.

Usage:
    class MyAgentApp(App):
        def compose(self) -> ComposeResult:
            yield AgentOutputView()
            yield AgentInputArea()
        
        def on_mount(self) -> None:
            self.agent = TextualAgentSession(
                symbols_db=my_db,
                project_root=Path("/project")
            )
        
        async def run_code(self, code: str) -> None:
            output_view = self.query_one(AgentOutputView)
            output_view.set_status("Running...")
            
            result = await self.agent.execute_async(self, code)
            
            output_view.display_result(result)
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING
from enum import Enum, auto

from agent_exec_env import AgentExecutionEnvironment, ExecutionResult
from agent_tools import AgentTools, AgentSession, AgentAction, ActionType, ToolResult

if TYPE_CHECKING:
    from textual.app import App
    from textual.widget import Widget


# =============================================================================
# Async Execution Wrapper
# =============================================================================

class AsyncExecutionEnvironment:
    """
    Async wrapper around AgentExecutionEnvironment.
    
    Can be used standalone with asyncio.to_thread(), or with Textual workers.
    """
    
    def __init__(self, stateful: bool = True, restrict_builtins: bool = False):
        self._env = AgentExecutionEnvironment(
            stateful=stateful, 
            restrict_builtins=restrict_builtins
        )
        self._lock = asyncio.Lock()
    
    def expose(self, name: str, obj: Any) -> None:
        """Expose a resource to agent code."""
        self._env.expose(name, obj)
    
    def expose_module(self, module: Any, name: str | None = None) -> None:
        """Expose a module to agent code."""
        self._env.expose_module(module, name)
    
    def expose_function(self, func: Callable, name: str | None = None) -> None:
        """Expose a function to agent code."""
        self._env.expose_function(func, name)
    
    def reset(self) -> None:
        """Clear session state."""
        self._env.reset()
    
    def get_namespace_summary(self) -> dict[str, str]:
        """Get summary of available namespace."""
        return self._env.get_namespace_summary()
    
    async def execute(self, code: str) -> ExecutionResult:
        """
        Execute code asynchronously using asyncio.to_thread().
        
        Use this when you're in an async context but not using Textual,
        or when you want simple async execution without worker management.
        """
        async with self._lock:  # Serialize access to the environment
            return await asyncio.to_thread(self._env.execute, code)
    
    def execute_sync(self, code: str) -> ExecutionResult:
        """
        Execute code synchronously.
        
        Use this inside a Textual worker (which already runs in a thread).
        """
        return self._env.execute(code)


# =============================================================================
# Textual Worker Integration
# =============================================================================

@dataclass
class WorkerExecutionRequest:
    """Request to execute code in a worker."""
    code: str
    request_id: str | None = None


@dataclass 
class WorkerExecutionResponse:
    """Response from worker execution."""
    result: ExecutionResult
    request_id: str | None = None


class TextualAgentSession:
    """
    Agent session designed for Textual applications.
    
    Provides both worker-based and async execution methods. The worker
    approach is preferred for Textual apps as it integrates with Textual's
    worker lifecycle management.
    
    IMPORTANT: SQLite threading
        If passing a SQLite connection, create it with check_same_thread=False:
        
            conn = sqlite3.connect("mydb.sqlite", check_same_thread=False)
        
        Otherwise you'll get "SQLite objects created in a thread can only be 
        used in that same thread" errors when using workers.
    
    Example with workers:
        class MyApp(App):
            @work(exclusive=True, thread=True)
            def execute_agent_code(self, code: str) -> ExecutionResult:
                return self.agent_session.execute_in_worker(code)
            
            def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
                if event.worker.name == "execute_agent_code":
                    if event.state == WorkerState.SUCCESS:
                        self.handle_result(event.worker.result)
    
    Example with async (simpler but less integrated):
        async def run_code(self, code: str) -> None:
            result = await self.agent_session.execute_async(code)
            self.handle_result(result)
    """
    
    def __init__(
        self,
        symbols_db: sqlite3.Connection,
        project_root: Path,
        additional_resources: dict[str, Any] | None = None,
        restrict_builtins: bool = False,
    ):
        # Core components
        self.tools = AgentTools(symbols_db, project_root)
        self.exec_env = AgentExecutionEnvironment(
            stateful=True,
            restrict_builtins=restrict_builtins
        )
        
        # Expose tools to the execution environment
        self.exec_env.expose_function(self.tools.search_definition)
        self.exec_env.expose_function(self.tools.search_code)
        self.exec_env.expose_function(self.tools.search_commits)
        self.exec_env.expose_function(self.tools.get_context_memory)
        self.exec_env.expose('db', symbols_db)
        
        if additional_resources:
            for name, resource in additional_resources.items():
                self.exec_env.expose(name, resource)
        
        # Async coordination
        self._lock = asyncio.Lock()
        self._execution_count = 0
    
    def execute_in_worker(self, code: str) -> ExecutionResult:
        """
        Execute code synchronously. Call this from within a Textual worker.
        
        This is the method you call inside a @work(thread=True) decorated method.
        The worker runs in a thread, so this won't block the UI.
        
        Example:
            @work(exclusive=True, thread=True) 
            def run_agent_code(self, code: str) -> ExecutionResult:
                return self.session.execute_in_worker(code)
        """
        self._execution_count += 1
        return self.exec_env.execute(code)
    
    def execute_action_in_worker(self, action: AgentAction) -> str:
        """
        Execute a structured action synchronously. Call from a Textual worker.
        
        Returns formatted string output suitable for display.
        """
        self._execution_count += 1
        
        if action.action_type == ActionType.SEARCH_DEFINITION:
            result = self.tools.search_definition(
                symbol=action.parameters.get('symbol', ''),
                file_path=action.parameters.get('file_path'),
                limit=action.parameters.get('limit', 5)
            )
            return self._format_tool_result(result)
            
        elif action.action_type == ActionType.SEARCH_CODE:
            result = self.tools.search_code(
                pattern=action.parameters.get('pattern', ''),
                limit=action.parameters.get('limit', 10)
            )
            return self._format_tool_result(result)
            
        elif action.action_type == ActionType.SEARCH_COMMITS:
            result = self.tools.search_commits(
                pattern=action.parameters.get('pattern', ''),
                limit=action.parameters.get('limit', 5)
            )
            return self._format_tool_result(result)
            
        elif action.action_type == ActionType.EXECUTE_PYTHON:
            if not action.code:
                return "Error: No code provided for execution"
            exec_result = self.exec_env.execute(action.code)
            return self._format_exec_result(exec_result)
            
        elif action.action_type == ActionType.RESET:
            self.exec_env.reset()
            self.tools.clear_context_memory()
            return "Session state cleared."
            
        elif action.action_type == ActionType.DONE:
            return f"Session complete after {self._execution_count} executions."
            
        else:
            return f"Unknown action: {action.action_type}"
    
    async def execute_async(self, code: str) -> ExecutionResult:
        """
        Execute code asynchronously without Textual worker integration.
        
        Simpler to use but doesn't integrate with Textual's worker lifecycle.
        Good for quick prototyping or non-Textual async contexts.
        """
        async with self._lock:
            return await asyncio.to_thread(self.exec_env.execute, code)
    
    async def execute_action_async(self, action: AgentAction) -> str:
        """Execute a structured action asynchronously."""
        async with self._lock:
            return await asyncio.to_thread(self.execute_action_in_worker, action)
    
    def reset(self) -> None:
        """Reset session state."""
        self.exec_env.reset()
        self.tools.clear_context_memory()
        self._execution_count = 0
    
    def get_context_summary(self) -> str:
        """Get summary of accumulated context."""
        return self.tools.summarize_context()
    
    def get_namespace_summary(self) -> dict[str, str]:
        """Get summary of available namespace."""
        return self.exec_env.get_namespace_summary()
    
    def _format_tool_result(self, result: ToolResult) -> str:
        """Format tool result for display."""
        lines = [f"## {result.tool_name}({result.query})"]
        
        if result.error:
            lines.append(f"\n**Error:** {result.error}")
        elif not result.results:
            lines.append("\nNo results found.")
        else:
            lines.append("")
            for r in result.results:
                loc = f" `{r.location}`" if r.location else ""
                lines.append(f"### {r.metadata.get('name', r.kind)}{loc}")
                lines.append(f"```\n{r.content}\n```")
            
            if result.truncated:
                lines.append("\n*Results truncated.*")
        
        return "\n".join(lines)
    
    def _format_exec_result(self, result: ExecutionResult) -> str:
        """Format execution result for display."""
        lines = ["## Python Execution"]
        
        if result.success:
            lines.append("\n**Status:** Success")
            
            if result.stdout:
                lines.append(f"\n**Output:**\n```\n{result.stdout}\n```")
            
            if result.result is not None:
                result_str = repr(result.result)
                if len(result_str) > 500:
                    result_str = result_str[:500] + "..."
                lines.append(f"\n**Result:** `{result_str}`")
            
            lines.append(f"\n**Variables in scope:** {', '.join(result.namespace_keys)}")
        else:
            lines.append("\n**Status:** Failed")
            lines.append(f"\n**Error:**\n```\n{result.error}\n```")
        
        return "\n".join(lines)


# =============================================================================
# Example Textual App
# =============================================================================

# This is a minimal example showing the integration pattern.
# In a real app, you'd have more sophisticated UI components.

EXAMPLE_APP_CODE = '''
"""
Example Textual app demonstrating agent integration.

Run with: python -m agent_textual
(Requires textual to be installed)
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Static, Input, Button, RichLog
from textual.worker import Worker, WorkerState
from textual import work
import sqlite3
from pathlib import Path

from agent_textual import TextualAgentSession
from agent_exec_env import ExecutionResult


class AgentApp(App):
    """A simple agent interface."""
    
    CSS = """
    #output {
        height: 1fr;
        border: solid green;
        padding: 1;
    }
    
    #input-area {
        height: auto;
        max-height: 30%;
        border: solid blue;
        padding: 1;
    }
    
    #status {
        height: 1;
        background: $surface;
    }
    
    Input {
        margin-bottom: 1;
    }
    """
    
    BINDINGS = [
        ("ctrl+r", "reset", "Reset Session"),
        ("ctrl+q", "quit", "Quit"),
    ]
    
    def __init__(self):
        super().__init__()
        
        # Create a mock database for demo
        # check_same_thread=False allows the connection to be used from worker threads
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("""
            CREATE TABLE symbols (
                id INTEGER PRIMARY KEY, name TEXT, kind TEXT,
                file TEXT, line INTEGER, definition TEXT
            )
        """)
        self.db.executemany(
            "INSERT INTO symbols (name, kind, file, line, definition) VALUES (?, ?, ?, ?, ?)",
            [
                ("main", "function", "src/main.c", 10, "int main(int argc, char **argv) {...}"),
                ("parse_args", "function", "src/main.c", 45, "config_t *parse_args(int argc, char **argv) {...}"),
                ("config_t", "struct", "include/config.h", 12, "typedef struct { int verbose; } config_t;"),
            ]
        )
        self.db.commit()
        
        self.session = TextualAgentSession(
            symbols_db=self.db,
            project_root=Path("/project")
        )
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            RichLog(id="output", highlight=True, markup=True),
            Vertical(
                Static("Enter Python code to execute:", id="status"),
                Input(placeholder="e.g., result = search_definition('main')", id="code-input"),
                Button("Execute", id="execute-btn", variant="primary"),
                id="input-area"
            )
        )
        yield Footer()
    
    def on_mount(self) -> None:
        output = self.query_one("#output", RichLog)
        output.write("[bold]Agent Session Started[/bold]")
        output.write("\\nAvailable functions:")
        for name, sig in self.session.get_namespace_summary().items():
            output.write(f"  • {name}: {sig}")
        output.write("\\n" + "─" * 40)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "execute-btn":
            self.execute_code()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "code-input":
            self.execute_code()
    
    def execute_code(self) -> None:
        code_input = self.query_one("#code-input", Input)
        code = code_input.value.strip()
        
        if not code:
            return
        
        output = self.query_one("#output", RichLog)
        status = self.query_one("#status", Static)
        
        output.write(f"\\n[bold cyan]>>> {code}[/bold cyan]")
        status.update("Running...")
        
        # Run in worker thread to keep UI responsive
        self.run_agent_code(code)
        
        code_input.value = ""
    
    @work(exclusive=True, thread=True)
    def run_agent_code(self, code: str) -> ExecutionResult:
        """Execute code in a worker thread."""
        return self.session.execute_in_worker(code)
    
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion."""
        if event.worker.name != "run_agent_code":
            return
            
        status = self.query_one("#status", Static)
        output = self.query_one("#output", RichLog)
        
        if event.state == WorkerState.SUCCESS:
            result: ExecutionResult = event.worker.result
            status.update("Ready")
            
            if result.success:
                if result.stdout:
                    output.write(f"[dim]{result.stdout}[/dim]")
                if result.result is not None:
                    output.write(f"[green]{repr(result.result)}[/green]")
                output.write(f"[dim]Variables: {', '.join(result.namespace_keys)}[/dim]")
            else:
                output.write(f"[red]{result.error}[/red]")
                
        elif event.state == WorkerState.ERROR:
            status.update("Error")
            output.write(f"[red]Worker error: {event.worker.error}[/red]")
        
        elif event.state == WorkerState.CANCELLED:
            status.update("Cancelled")
    
    def action_reset(self) -> None:
        """Reset the session."""
        self.session.reset()
        output = self.query_one("#output", RichLog)
        output.clear()
        output.write("[bold]Session Reset[/bold]")
        self.query_one("#status", Static).update("Ready")


if __name__ == "__main__":
    app = AgentApp()
    app.run()
'''


def create_example_app_file(path: Path | str = "example_agent_app.py") -> None:
    """Write the example app to a file."""
    Path(path).write_text(EXAMPLE_APP_CODE)
    print(f"Example app written to {path}")
    print("Run with: python example_agent_app.py")


# =============================================================================
# Demo / Self-test
# =============================================================================

async def demo():
    """Demonstrate async execution without Textual."""
    import sqlite3
    
    # Setup mock database
    conn = sqlite3.connect(':memory:')
    conn.execute('''
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY, name TEXT, kind TEXT,
            file TEXT, line INTEGER, definition TEXT
        )
    ''')
    conn.executemany(
        'INSERT INTO symbols (name, kind, file, line, definition) VALUES (?, ?, ?, ?, ?)',
        [
            ('main', 'function', 'src/main.c', 10, 'int main() {...}'),
            ('helper', 'function', 'src/util.c', 20, 'void helper() {...}'),
        ]
    )
    conn.commit()
    
    # Create session
    session = TextualAgentSession(
        symbols_db=conn,
        project_root=Path('/project')
    )
    
    print("Testing async execution...")
    
    # Test async code execution
    result = await session.execute_async('''
functions = search_definition("main")
result = f"Found {len(functions.results)} results"
''')
    
    print(f"Success: {result.success}")
    print(f"Result: {result.result}")
    print(f"Variables: {result.namespace_keys}")
    
    # Test that state persists
    result2 = await session.execute_async('result = functions.results[0].location')
    print(f"Persisted state - location: {result2.result}")
    
    conn.close()
    print("\nAsync demo complete!")
    print("\nTo run the Textual example app:")
    print("  1. pip install textual")
    print("  2. python -c \"from agent_textual import create_example_app_file; create_example_app_file()\"")
    print("  3. python example_agent_app.py")


if __name__ == '__main__':
    asyncio.run(demo())
