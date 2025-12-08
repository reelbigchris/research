
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
        output.write("\nAvailable functions:")
        for name, sig in self.session.get_namespace_summary().items():
            output.write(f"  • {name}: {sig}")
        output.write("\n" + "─" * 40)
    
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
        
        output.write(f"\n[bold cyan]>>> {code}[/bold cyan]")
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
