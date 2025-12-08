# Agent Execution Environment Reference Implementation

A reference implementation for giving an AI agent the ability to execute Python
code with access to shared resources (databases, indices, analysis tools) while
keeping a Textual TUI responsive.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Textual App                               │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │   UI Widgets    │    │         Worker Thread               │ │
│  │                 │    │  ┌───────────────────────────────┐  │ │
│  │  - Input        │    │  │   TextualAgentSession         │  │ │
│  │  - Output Log   │───▶│  │                               │  │ │
│  │  - Status       │    │  │  ┌─────────────────────────┐  │  │ │
│  │                 │    │  │  │ AgentExecutionEnvironment│  │  │ │
│  │                 │◀───│  │  │                         │  │  │ │
│  │                 │    │  │  │  - Curated namespace    │  │  │ │
│  └─────────────────┘    │  │  │  - Stateful sessions    │  │  │ │
│                         │  │  │  - REPL-like execution  │  │  │ │
│                         │  │  └─────────────────────────┘  │  │ │
│                         │  │                               │  │ │
│                         │  │  ┌─────────────────────────┐  │  │ │
│                         │  │  │     AgentTools          │  │  │ │
│                         │  │  │                         │  │  │ │
│                         │  │  │  - search_definition()  │  │  │ │
│                         │  │  │  - search_code()        │  │  │ │
│                         │  │  │  - search_commits()     │  │  │ │
│                         │  │  │  - context memory       │  │  │ │
│                         │  │  └─────────────────────────┘  │  │ │
│                         │  └───────────────────────────────┘  │ │
│                         └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │       Data Sources            │
                    │                               │
                    │  - SQLite databases           │
                    │  - libclang index             │
                    │  - Ghidra project exports     │
                    │  - Git repository             │
                    └───────────────────────────────┘
```

## Files

### `agent_exec_env.py`
Core execution environment. Key features:
- **Curated namespace**: Expose specific resources to agent code via `expose()`
- **Stateful sessions**: Variables persist across executions within a session
- **REPL-like behavior**: Last expression's value is automatically captured
- **Structured output**: `ExecutionResult` with success, result, stdout, stderr, error
- **Clean tracebacks**: Internal frames filtered out for agent-friendly errors

### `agent_tools.py`
Structured search primitives inspired by the Code Researcher paper:
- **search_definition(symbol)**: Find function/struct/macro definitions
- **search_code(pattern)**: Regex search across codebase
- **search_commits(pattern)**: Search git history (stubbed - needs real git integration)
- **Context memory**: Accumulates search results across the session

### `agent_textual.py`
Textual TUI integration:
- **TextualAgentSession**: Combines execution environment + tools
- **Worker-based execution**: Runs in thread to keep UI responsive
- **Async alternatives**: `execute_async()` for non-Textual async contexts

### `example_agent_app.py`
Working Textual app demonstrating the integration. Run with:
```bash
pip install textual
python example_agent_app.py
```

## Key Patterns

### 1. Worker-based execution (keeps UI responsive)
```python
class MyApp(App):
    @work(exclusive=True, thread=True)
    def run_agent_code(self, code: str) -> ExecutionResult:
        return self.session.execute_in_worker(code)
    
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            self.display_result(result)
```

### 2. SQLite threading
When using SQLite with workers, create connections with:
```python
conn = sqlite3.connect("mydb.sqlite", check_same_thread=False)
```

### 3. Exposing resources to agent code
```python
env = AgentExecutionEnvironment(stateful=True)
env.expose('index', clang_index)
env.expose('db', sqlite_connection)
env.expose_function(my_query_helper)
env.expose_module(pathlib)
```

### 4. REPL-like execution
```python
# Expression values are auto-captured
result = env.execute('1 + 1')
assert result.result == 2

# Variables persist
env.execute('x = 10')
result = env.execute('x * 2')
assert result.result == 20

# Explicit 'result' assignment still works
result = env.execute('result = "hello"')
assert result.result == "hello"
```

### 5. Context memory for research sessions
```python
session.tools.search_definition("main")
session.tools.search_code("malloc.*sizeof")
session.tools.search_commits("fix.*null")

# Review accumulated context
summary = session.get_context_summary()
```

## Adapting to Your Codebase

1. **Replace mock data sources** with your actual:
   - Symbol database (from ctags, libclang, etc.)
   - Ghidra export database
   - Any other analysis outputs

2. **Implement real git search** in `AgentTools.search_commits()`:
   ```python
   # Use subprocess to call git
   result = subprocess.run(
       ['git', 'log', '-G', pattern, '--oneline', '-n', '10'],
       capture_output=True, text=True
   )
   ```

3. **Add domain-specific helpers** to the namespace:
   ```python
   env.expose_function(find_callers)
   env.expose_function(get_xrefs)
   env.expose_function(decompile_function)
   ```

4. **Tune the system prompt** in `get_system_prompt_fragment()` for your
   codebase's idioms and common query patterns.

## Design Decisions

- **Full builtins by default**: `restrict_builtins=False` allows imports.
  For internal tooling where you trust the agent, this is appropriate.
  
- **Stateful by default**: Variables persist across executions, enabling
  iterative exploration. Call `reset()` for a fresh start.

- **Hybrid tools + exec**: Structured primitives for common operations
  (lower token cost, focused), with Python escape hatch for complex analysis.

- **Context memory**: Search results accumulate, matching the Code Researcher
  paper's finding that deep context gathering improves results.
