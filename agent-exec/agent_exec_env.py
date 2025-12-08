"""
Agent Execution Environment

A reference implementation for giving an AI agent the ability to execute
Python code with access to shared resources (databases, indices, etc.)
while maintaining appropriate boundaries.

Key patterns demonstrated:
- Curated namespace with explicit resource exposure
- Stateful vs. stateless execution modes
- Structured output capture
- Error handling with traceback feedback
- Session management

This is designed for a "researcher/advisor" agent that explores codebases
and data sources, not for autonomous code generation.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Callable
from contextlib import redirect_stdout, redirect_stderr


@dataclass
class ExecutionResult:
    """Structured result from code execution."""
    success: bool
    result: Any = None           # Value of 'result' variable if set
    stdout: str = ""
    stderr: str = ""
    error: str | None = None     # Formatted traceback if execution failed
    namespace_keys: list[str] = field(default_factory=list)  # What's now in scope


class AgentExecutionEnvironment:
    """
    Provides a controlled Python execution environment for an AI agent.
    
    The agent can execute code that has access to pre-configured resources
    (databases, indices, query functions) while results and errors are
    captured in a structured way suitable for feeding back to the model.
    
    Example usage:
        env = AgentExecutionEnvironment()
        env.expose("db", sqlite_connection)
        env.expose("query_symbols", my_query_function)
        
        result = env.execute('''
            symbols = query_symbols("main")
            result = [(s.name, s.location) for s in symbols]
        ''')
        
        if result.success:
            print(result.result)  # The list of (name, location) tuples
        else:
            print(result.error)   # Traceback for the agent to see
    """
    
    def __init__(self, stateful: bool = True, restrict_builtins: bool = False):
        """
        Initialize the execution environment.
        
        Args:
            stateful: If True, variable assignments persist across execute() calls.
                     If False, each execution starts fresh (but exposed resources
                     are always available).
            restrict_builtins: If True, use a restricted subset of builtins (safer
                             but limits imports). If False (default), allow full
                             builtins including __import__. For internal dev tools
                             where you trust the agent, False is usually appropriate.
        """
        self.stateful = stateful
        self._base_namespace: dict[str, Any] = {}
        self._session_namespace: dict[str, Any] = {}
        self._setup_builtins(restrict_builtins)
    
    def _setup_builtins(self, restrict_builtins: bool = False) -> None:
        """
        Configure which builtins are available to agent code.
        
        Args:
            restrict_builtins: If True, use a restricted subset. If False (default),
                             allow all builtins including __import__. For internal
                             tooling where you trust the agent, False is usually fine.
        """
        import builtins
        
        if not restrict_builtins:
            # Full builtins - appropriate for internal dev tools
            # where you trust the agent and want maximum flexibility
            self._base_namespace['__builtins__'] = builtins
            return
        
        # Restricted subset for less trusted environments
        safe_builtins = {
            # Types and constructors
            'bool', 'int', 'float', 'str', 'bytes', 'bytearray',
            'list', 'dict', 'set', 'frozenset', 'tuple',
            'type', 'object',
            
            # Iteration and sequences
            'range', 'enumerate', 'zip', 'map', 'filter', 'reversed', 'sorted',
            'len', 'min', 'max', 'sum', 'any', 'all',
            'iter', 'next',
            
            # String and repr
            'repr', 'str', 'format', 'chr', 'ord',
            
            # Math
            'abs', 'round', 'pow', 'divmod',
            
            # Attribute access
            'getattr', 'setattr', 'hasattr', 'delattr',
            'isinstance', 'issubclass',
            
            # Other utilities
            'callable', 'hash', 'id', 'dir', 'vars',
            'print',  # Captured via redirect_stdout
            
            # Exceptions (for isinstance checks, raising)
            'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
            'AttributeError', 'RuntimeError', 'StopIteration',
        }
        
        self._base_namespace['__builtins__'] = {
            name: getattr(builtins, name)
            for name in safe_builtins
            if hasattr(builtins, name)
        }
    
    def expose(self, name: str, obj: Any) -> None:
        """
        Expose a resource to agent code under the given name.
        
        This is how you give the agent access to databases, indices,
        query functions, etc.
        
        Args:
            name: The variable name the agent will use to access this
            obj: The object to expose (connection, function, class, etc.)
        """
        self._base_namespace[name] = obj
    
    def expose_module(self, module: Any, name: str | None = None) -> None:
        """
        Expose a module to agent code.
        
        Args:
            module: The module object (already imported)
            name: Name to expose it as (defaults to module.__name__)
        """
        exposed_name = name or module.__name__
        self._base_namespace[exposed_name] = module
    
    def expose_function(self, func: Callable, name: str | None = None) -> None:
        """
        Expose a function to agent code.
        
        Args:
            func: The function to expose
            name: Name to expose it as (defaults to func.__name__)
        """
        exposed_name = name or func.__name__
        self._base_namespace[exposed_name] = func
    
    def reset(self) -> None:
        """
        Clear all session state, returning to a fresh environment.
        
        Exposed resources remain available; only agent-created variables
        are cleared.
        """
        self._session_namespace.clear()
    
    def get_namespace_summary(self) -> dict[str, str]:
        """
        Return a summary of what's available in the namespace.
        
        Useful for showing the agent what resources it has access to.
        """
        combined = {**self._base_namespace, **self._session_namespace}
        summary = {}
        
        for name, obj in combined.items():
            if name.startswith('_'):
                continue
            
            if callable(obj):
                # Try to get signature
                try:
                    import inspect
                    sig = str(inspect.signature(obj))
                    summary[name] = f"function{sig}"
                except (ValueError, TypeError):
                    summary[name] = f"callable: {type(obj).__name__}"
            else:
                summary[name] = f"{type(obj).__name__}"
        
        return summary
    
    def execute(self, code: str) -> ExecutionResult:
        """
        Execute agent-provided code and return structured results.
        
        Behaves like a Python REPL:
        - If the code is a single expression, its value is captured and returned
        - If the code ends with an expression, that expression's value is returned
        - If 'result' is explicitly assigned, that value is returned
        - Print statements are captured in stdout
        
        In stateful mode, variable assignments persist to the next call.
        
        Args:
            code: Python code to execute
            
        Returns:
            ExecutionResult with success status, captured output, and any errors
        """
        import ast
        
        # Build the execution namespace
        if self.stateful:
            namespace = {**self._base_namespace, **self._session_namespace}
        else:
            namespace = {**self._base_namespace}
        
        # Capture stdout/stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        result_value = None
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Parse the code to check if we can capture a final expression
                result_value = self._execute_with_expression_capture(code, namespace)
            
            # If 'result' was explicitly set, prefer that
            if 'result' in namespace and namespace['result'] is not result_value:
                # Check if 'result' was set by the user code (not from a previous run)
                if 'result' not in self._session_namespace or \
                   namespace['result'] is not self._session_namespace.get('result'):
                    result_value = namespace['result']
            
            # In stateful mode, save new variables (excluding base namespace keys)
            if self.stateful:
                for key, value in namespace.items():
                    if key not in self._base_namespace and not key.startswith('_'):
                        self._session_namespace[key] = value
            
            # Report what's now in scope
            user_keys = [
                k for k in namespace.keys()
                if k not in self._base_namespace and not k.startswith('_')
            ]
            
            return ExecutionResult(
                success=True,
                result=result_value,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                namespace_keys=user_keys,
            )
            
        except Exception as e:
            # Format the traceback in a way that's useful for the agent
            tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
            
            # Filter out internal frames to reduce noise
            filtered_lines = []
            skip_until_user_code = False
            for line in tb_lines:
                # Skip frames from our execution machinery
                if '_execute_with_expression_capture' in line or \
                   'in execute' in line and 'agent_exec_env' in line:
                    skip_until_user_code = True
                    continue
                if skip_until_user_code and '<string>' in line:
                    skip_until_user_code = False
                if not skip_until_user_code:
                    filtered_lines.append(line)
            
            return ExecutionResult(
                success=False,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                error=''.join(filtered_lines),
                namespace_keys=list(self._session_namespace.keys()),
            )
    
    def _execute_with_expression_capture(self, code: str, namespace: dict) -> Any:
        """
        Execute code and capture the value of the final expression if present.
        
        This mimics REPL behavior where typing an expression prints its value.
        """
        import ast
        
        code = code.strip()
        if not code:
            return None
        
        try:
            # Try to parse as a single expression first
            tree = ast.parse(code, mode='eval')
            # It's a single expression - evaluate and return its value
            return eval(compile(tree, '<string>', 'eval'), namespace)
        except SyntaxError:
            pass
        
        # Parse as statements
        try:
            tree = ast.parse(code, mode='exec')
        except SyntaxError:
            # Let the normal exec handle the syntax error
            exec(code, namespace)
            return None
        
        if not tree.body:
            return None
        
        # Check if the last statement is an expression
        last_stmt = tree.body[-1]
        
        if isinstance(last_stmt, ast.Expr):
            # Execute all statements except the last
            if len(tree.body) > 1:
                mod = ast.Module(body=tree.body[:-1], type_ignores=[])
                exec(compile(mod, '<string>', 'exec'), namespace)
            
            # Evaluate the last expression and return its value
            expr_code = compile(ast.Expression(body=last_stmt.value), '<string>', 'eval')
            return eval(expr_code, namespace)
        else:
            # No trailing expression, just execute everything
            exec(compile(tree, '<string>', 'exec'), namespace)
            return None


# =============================================================================
# Convenience functions for common patterns
# =============================================================================

def create_c_analysis_environment(
    clang_index=None,
    db_connections: dict[str, Any] | None = None,
    project_root: str | None = None,
) -> AgentExecutionEnvironment:
    """
    Factory function to create an environment pre-configured for C code analysis.
    
    This is an example of how you might set up the environment for your
    specific use case. Customize based on what resources you have.
    
    Args:
        clang_index: A libclang Index object (if available)
        db_connections: Dict mapping names to SQLite connections
        project_root: Path to the project being analyzed
    """
    import pathlib
    import re
    import json
    import collections
    
    env = AgentExecutionEnvironment(stateful=True)
    
    # Expose useful stdlib modules
    env.expose_module(re)
    env.expose_module(json)
    env.expose_module(pathlib)
    env.expose('Path', pathlib.Path)
    env.expose('Counter', collections.Counter)
    env.expose('defaultdict', collections.defaultdict)
    
    # Expose project context
    if project_root:
        env.expose('PROJECT_ROOT', pathlib.Path(project_root))
    
    # Expose clang index if available
    if clang_index:
        env.expose('index', clang_index)
    
    # Expose database connections
    if db_connections:
        for name, conn in db_connections.items():
            env.expose(name, conn)
        
        # Add a convenience function for quick SQL queries
        def sql(query: str, db_name: str = 'db') -> list:
            """Execute a SQL query and return all results."""
            if db_name not in db_connections:
                raise ValueError(f"Unknown database: {db_name}")
            return db_connections[db_name].execute(query).fetchall()
        
        env.expose_function(sql)
    
    # Add a report() function for accumulating outputs
    _reports: list[Any] = []
    
    def report(item: Any, label: str | None = None) -> None:
        """Add an item to the report output."""
        if label:
            _reports.append({label: item})
        else:
            _reports.append(item)
    
    def get_reports() -> list[Any]:
        """Get all reported items."""
        return _reports.copy()
    
    def clear_reports() -> None:
        """Clear all reported items."""
        _reports.clear()
    
    env.expose_function(report)
    env.expose_function(get_reports)
    env.expose_function(clear_reports)
    
    return env


# =============================================================================
# Example / Demo
# =============================================================================

def demo():
    """Demonstrate the execution environment with a mock setup."""
    import sqlite3
    
    # Create an in-memory SQLite database with some mock data
    conn = sqlite3.connect(':memory:')
    conn.execute('''
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY,
            name TEXT,
            kind TEXT,
            file TEXT,
            line INTEGER
        )
    ''')
    conn.executemany(
        'INSERT INTO symbols (name, kind, file, line) VALUES (?, ?, ?, ?)',
        [
            ('main', 'function', 'src/main.c', 10),
            ('parse_args', 'function', 'src/main.c', 45),
            ('config_t', 'struct', 'include/config.h', 15),
            ('init_config', 'function', 'src/config.c', 20),
            ('MAX_BUFFER', 'macro', 'include/config.h', 5),
        ]
    )
    conn.commit()
    
    # Create the environment
    env = create_c_analysis_environment(
        db_connections={'db': conn},
        project_root='/path/to/project'
    )
    
    print("=" * 60)
    print("Available in namespace:")
    print("=" * 60)
    for name, desc in env.get_namespace_summary().items():
        print(f"  {name}: {desc}")
    print()
    
    # Example 1: Simple query
    print("=" * 60)
    print("Example 1: Simple SQL query")
    print("=" * 60)
    
    code1 = '''
# Find all functions in the codebase
functions = sql("SELECT name, file, line FROM symbols WHERE kind = 'function'")
result = functions
'''
    
    result1 = env.execute(code1)
    print(f"Success: {result1.success}")
    print(f"Result: {result1.result}")
    print(f"Variables in scope: {result1.namespace_keys}")
    print()
    
    # Example 2: Build on previous results (stateful)
    print("=" * 60)
    print("Example 2: Build on previous results (stateful execution)")
    print("=" * 60)
    
    code2 = '''
# 'functions' is still available from the previous execution
files_with_functions = set(f[1] for f in functions)
result = sorted(files_with_functions)
'''
    
    result2 = env.execute(code2)
    print(f"Success: {result2.success}")
    print(f"Result: {result2.result}")
    print(f"Variables in scope: {result2.namespace_keys}")
    print()
    
    # Example 3: Error handling
    print("=" * 60)
    print("Example 3: Error handling (agent sees the traceback)")
    print("=" * 60)
    
    code3 = '''
# This will fail - 'nonexistent' is not defined
x = nonexistent + 1
'''
    
    result3 = env.execute(code3)
    print(f"Success: {result3.success}")
    print(f"Error:\n{result3.error}")
    print()
    
    # Example 4: Using the report() pattern
    print("=" * 60)
    print("Example 4: Using report() for structured output")
    print("=" * 60)
    
    code4 = '''
# Analyze the codebase and report findings
all_symbols = sql("SELECT * FROM symbols")

for sym in all_symbols:
    name, kind, file, line = sym[1], sym[2], sym[3], sym[4]
    report({
        'name': name,
        'kind': kind,
        'location': f"{file}:{line}"
    })

result = f"Analyzed {len(all_symbols)} symbols"
'''
    
    result4 = env.execute(code4)
    print(f"Success: {result4.success}")
    print(f"Result: {result4.result}")
    print(f"Stdout: {result4.stdout}")
    
    # Get the accumulated reports
    reports_code = 'result = get_reports()'
    reports_result = env.execute(reports_code)
    print(f"Reports: {reports_result.result}")
    print()
    
    # Example 5: Reset and start fresh
    print("=" * 60)
    print("Example 5: Reset session state")
    print("=" * 60)
    
    print(f"Before reset - variables in scope: {list(env._session_namespace.keys())}")
    env.reset()
    print(f"After reset - variables in scope: {list(env._session_namespace.keys())}")
    
    # Verify that base namespace (sql, report, etc.) still works
    verify_code = 'result = sql("SELECT COUNT(*) FROM symbols")[0][0]'
    verify_result = env.execute(verify_code)
    print(f"Base functions still work: {verify_result.result} symbols in database")
    
    conn.close()


if __name__ == '__main__':
    demo()
