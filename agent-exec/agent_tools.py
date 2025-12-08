"""
Agent Tools and Conversation Loop

Companion to agent_exec_env.py showing:
- Structured search primitives (inspired by Code Researcher paper)
- Context memory for accumulating findings
- Conversation loop pattern for multi-turn agent interaction
- Integration between constrained tools and freeform execution

This demonstrates the hybrid approach: structured primitives for common
operations, with the ability to drop into Python when needed.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path
from enum import Enum, auto

from agent_exec_env import AgentExecutionEnvironment, ExecutionResult


# =============================================================================
# Structured Search Primitives (Code Researcher-style)
# =============================================================================

@dataclass
class SearchResult:
    """A single result from a search operation."""
    kind: str                    # 'definition', 'code_match', 'commit', etc.
    content: str                 # The actual content found
    location: str | None = None  # File:line or commit hash
    metadata: dict = field(default_factory=dict)


@dataclass  
class ToolResult:
    """Result from invoking a structured tool."""
    tool_name: str
    query: str
    results: list[SearchResult]
    truncated: bool = False      # True if results were limited
    error: str | None = None


class AgentTools:
    """
    Provides structured search primitives for code exploration.
    
    These are higher-level operations that abstract common patterns,
    reducing token cost and keeping the agent focused on reasoning
    rather than implementation details.
    """
    
    def __init__(self, symbols_db: sqlite3.Connection, project_root: Path):
        self.symbols_db = symbols_db
        self.project_root = project_root
        self._context_memory: list[ToolResult] = []
    
    def search_definition(
        self, 
        symbol: str, 
        file_path: str | None = None,
        limit: int = 5
    ) -> ToolResult:
        """
        Search for the definition of a symbol (function, struct, macro, etc.).
        
        Args:
            symbol: Name of the symbol to find
            file_path: Optional file to limit search to
            limit: Maximum results to return
        """
        query = f"SELECT name, kind, file, line, definition FROM symbols WHERE name LIKE ?"
        params: list[Any] = [f"%{symbol}%"]
        
        if file_path:
            query += " AND file LIKE ?"
            params.append(f"%{file_path}%")
        
        query += f" LIMIT {limit + 1}"  # +1 to detect truncation
        
        try:
            cursor = self.symbols_db.execute(query, params)
            rows = cursor.fetchall()
            
            truncated = len(rows) > limit
            rows = rows[:limit]
            
            results = [
                SearchResult(
                    kind='definition',
                    content=row[4] if row[4] else f"{row[1]} {row[0]}",  # definition or kind+name
                    location=f"{row[2]}:{row[3]}",
                    metadata={'name': row[0], 'kind': row[1]}
                )
                for row in rows
            ]
            
            tool_result = ToolResult(
                tool_name='search_definition',
                query=f"symbol={symbol}" + (f", file={file_path}" if file_path else ""),
                results=results,
                truncated=truncated
            )
            
        except Exception as e:
            tool_result = ToolResult(
                tool_name='search_definition',
                query=f"symbol={symbol}",
                results=[],
                error=str(e)
            )
        
        self._context_memory.append(tool_result)
        return tool_result
    
    def search_code(self, pattern: str, limit: int = 10) -> ToolResult:
        """
        Search for code matching a regex pattern.
        
        In a real implementation, this would use `git grep` or similar.
        Here we simulate with a database query.
        
        Args:
            pattern: Regex pattern to search for
            limit: Maximum results to return
        """
        # In reality, you'd shell out to git grep or use a code search index
        # This is a simplified simulation using the symbols database
        query = """
            SELECT name, kind, file, line, definition 
            FROM symbols 
            WHERE definition LIKE ? OR name LIKE ?
            LIMIT ?
        """
        
        try:
            # Convert regex-ish pattern to SQL LIKE
            like_pattern = f"%{pattern.replace('.*', '%').replace('.+', '%')}%"
            cursor = self.symbols_db.execute(query, [like_pattern, like_pattern, limit + 1])
            rows = cursor.fetchall()
            
            truncated = len(rows) > limit
            rows = rows[:limit]
            
            results = [
                SearchResult(
                    kind='code_match',
                    content=row[4] if row[4] else row[0],
                    location=f"{row[2]}:{row[3]}",
                    metadata={'symbol': row[0], 'kind': row[1]}
                )
                for row in rows
            ]
            
            tool_result = ToolResult(
                tool_name='search_code',
                query=pattern,
                results=results,
                truncated=truncated
            )
            
        except Exception as e:
            tool_result = ToolResult(
                tool_name='search_code',
                query=pattern,
                results=[],
                error=str(e)
            )
        
        self._context_memory.append(tool_result)
        return tool_result
    
    def search_commits(self, pattern: str, limit: int = 5) -> ToolResult:
        """
        Search commit history for messages or diffs matching a pattern.
        
        In a real implementation, this would use `git log -G` and `git log --grep`.
        
        Args:
            pattern: Regex pattern to search commit messages and diffs
            limit: Maximum results to return
        """
        # Simulated - in reality you'd call git
        # For demo purposes, return empty results
        tool_result = ToolResult(
            tool_name='search_commits',
            query=pattern,
            results=[
                SearchResult(
                    kind='commit',
                    content=f"[Simulated] No git repository connected. "
                           f"In production, this would search for: {pattern}",
                    location=None,
                    metadata={}
                )
            ],
            truncated=False
        )
        
        self._context_memory.append(tool_result)
        return tool_result
    
    def get_context_memory(self) -> list[ToolResult]:
        """Return all accumulated search results."""
        return self._context_memory.copy()
    
    def clear_context_memory(self) -> None:
        """Clear accumulated search results."""
        self._context_memory.clear()
    
    def summarize_context(self) -> str:
        """Generate a text summary of accumulated context for the agent."""
        if not self._context_memory:
            return "No context gathered yet."
        
        lines = [f"Context Memory ({len(self._context_memory)} searches):"]
        
        for i, result in enumerate(self._context_memory, 1):
            lines.append(f"\n[{i}] {result.tool_name}({result.query})")
            if result.error:
                lines.append(f"    Error: {result.error}")
            elif not result.results:
                lines.append("    No results")
            else:
                for r in result.results[:3]:  # Show first 3 per search
                    loc = f" @ {r.location}" if r.location else ""
                    preview = r.content[:80] + "..." if len(r.content) > 80 else r.content
                    lines.append(f"    - {preview}{loc}")
                if len(result.results) > 3:
                    lines.append(f"    ... and {len(result.results) - 3} more")
                if result.truncated:
                    lines.append(f"    (results truncated)")
        
        return "\n".join(lines)


# =============================================================================
# Integrated Agent Session
# =============================================================================

class ActionType(Enum):
    """Types of actions the agent can take."""
    SEARCH_DEFINITION = auto()
    SEARCH_CODE = auto()
    SEARCH_COMMITS = auto()
    EXECUTE_PYTHON = auto()
    RESET = auto()
    DONE = auto()


@dataclass
class AgentAction:
    """Represents a parsed action from the agent."""
    action_type: ActionType
    parameters: dict[str, Any] = field(default_factory=dict)
    code: str | None = None  # For EXECUTE_PYTHON


class AgentSession:
    """
    Manages a complete agent session with both structured tools and Python execution.
    
    This is the integration layer that your conversation loop would use.
    It handles:
    - Parsing agent actions
    - Dispatching to appropriate tools
    - Formatting results for the agent
    - Managing session state
    """
    
    def __init__(
        self,
        symbols_db: sqlite3.Connection,
        project_root: Path,
        additional_resources: dict[str, Any] | None = None
    ):
        self.tools = AgentTools(symbols_db, project_root)
        self.exec_env = AgentExecutionEnvironment(stateful=True)
        
        # Expose the structured tools to the Python environment too
        self.exec_env.expose_function(self.tools.search_definition)
        self.exec_env.expose_function(self.tools.search_code)
        self.exec_env.expose_function(self.tools.search_commits)
        self.exec_env.expose_function(self.tools.get_context_memory)
        self.exec_env.expose('db', symbols_db)
        
        # Add any additional resources
        if additional_resources:
            for name, resource in additional_resources.items():
                self.exec_env.expose(name, resource)
        
        self._turn_count = 0
        self._action_history: list[tuple[AgentAction, str]] = []  # (action, result)
    
    def get_system_prompt_fragment(self) -> str:
        """
        Returns text to include in the system prompt describing available tools.
        """
        namespace_summary = self.exec_env.get_namespace_summary()
        
        return f"""
## Available Actions

You can take the following actions to explore the codebase:

### Structured Search Tools
These are efficient, focused operations for common exploration patterns:

1. **search_definition(symbol, file_path=None)**
   Find the definition of a function, struct, macro, or other symbol.
   Example: search_definition("parse_config")
   
2. **search_code(pattern)**
   Search for code matching a pattern (regex-like).
   Example: search_code("malloc.*sizeof")
   
3. **search_commits(pattern)**
   Search commit history for relevant changes.
   Example: search_commits("fix.*null pointer")

### Python Execution
For complex analysis that doesn't fit the structured tools, you can execute
Python code. The following are available in the Python environment:

{json.dumps(namespace_summary, indent=2)}

To execute Python, wrap your code in ```python blocks. Your code can:
- Access all the structured search tools as functions
- Query the database directly with `db.execute(sql)`
- Build up variables across multiple executions (stateful)
- Set `result = ...` to return a value

### Session Management
- **reset**: Clear all accumulated state and start fresh
- **done**: Signal that you have gathered enough context

## Context Memory
Your search results accumulate in context memory. Use this to build up
understanding before drawing conclusions.
"""
    
    def execute_action(self, action: AgentAction) -> str:
        """
        Execute an agent action and return a formatted result string.
        
        This is what your conversation loop calls after parsing the agent's response.
        """
        self._turn_count += 1
        
        if action.action_type == ActionType.SEARCH_DEFINITION:
            result = self.tools.search_definition(
                symbol=action.parameters.get('symbol', ''),
                file_path=action.parameters.get('file_path'),
                limit=action.parameters.get('limit', 5)
            )
            output = self._format_tool_result(result)
            
        elif action.action_type == ActionType.SEARCH_CODE:
            result = self.tools.search_code(
                pattern=action.parameters.get('pattern', ''),
                limit=action.parameters.get('limit', 10)
            )
            output = self._format_tool_result(result)
            
        elif action.action_type == ActionType.SEARCH_COMMITS:
            result = self.tools.search_commits(
                pattern=action.parameters.get('pattern', ''),
                limit=action.parameters.get('limit', 5)
            )
            output = self._format_tool_result(result)
            
        elif action.action_type == ActionType.EXECUTE_PYTHON:
            if not action.code:
                output = "Error: No code provided for execution"
            else:
                exec_result = self.exec_env.execute(action.code)
                output = self._format_exec_result(exec_result)
                
        elif action.action_type == ActionType.RESET:
            self.exec_env.reset()
            self.tools.clear_context_memory()
            output = "Session state cleared. Starting fresh."
            
        elif action.action_type == ActionType.DONE:
            output = f"Session complete after {self._turn_count} turns."
            
        else:
            output = f"Unknown action type: {action.action_type}"
        
        self._action_history.append((action, output))
        return output
    
    def _format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for display to the agent."""
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
                lines.append("\n*Results truncated. Refine your search for more specific results.*")
        
        return "\n".join(lines)
    
    def _format_exec_result(self, result: ExecutionResult) -> str:
        """Format a Python execution result for display to the agent."""
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
    
    def get_context_summary(self) -> str:
        """Get a summary of accumulated context for the agent."""
        return self.tools.summarize_context()


# =============================================================================
# Demo
# =============================================================================

def demo():
    """Demonstrate the integrated agent session."""
    
    # Create a mock symbols database with more realistic data
    conn = sqlite3.connect(':memory:')
    conn.execute('''
        CREATE TABLE symbols (
            id INTEGER PRIMARY KEY,
            name TEXT,
            kind TEXT,
            file TEXT,
            line INTEGER,
            definition TEXT
        )
    ''')
    conn.executemany(
        'INSERT INTO symbols (name, kind, file, line, definition) VALUES (?, ?, ?, ?, ?)',
        [
            ('main', 'function', 'src/main.c', 10, 
             'int main(int argc, char **argv) {\n    config_t *cfg = parse_config(argc, argv);\n    ...'),
            ('parse_config', 'function', 'src/config.c', 25,
             'config_t *parse_config(int argc, char **argv) {\n    config_t *cfg = malloc(sizeof(config_t));\n    if (!cfg) return NULL;\n    ...'),
            ('config_t', 'struct', 'include/config.h', 12,
             'typedef struct {\n    char *input_file;\n    int verbose;\n    size_t buffer_size;\n} config_t;'),
            ('free_config', 'function', 'src/config.c', 80,
             'void free_config(config_t *cfg) {\n    if (cfg) {\n        free(cfg->input_file);\n        free(cfg);\n    }\n}'),
            ('MAX_BUFFER_SIZE', 'macro', 'include/config.h', 5,
             '#define MAX_BUFFER_SIZE 4096'),
            ('init_logging', 'function', 'src/logging.c', 15,
             'int init_logging(const char *logfile, int level) {\n    ...'),
        ]
    )
    conn.commit()
    
    # Create the session
    session = AgentSession(
        symbols_db=conn,
        project_root=Path('/project')
    )
    
    print("=" * 70)
    print("SYSTEM PROMPT FRAGMENT")
    print("=" * 70)
    print(session.get_system_prompt_fragment())
    print()
    
    # Simulate agent actions
    print("=" * 70)
    print("SIMULATED AGENT INTERACTION")
    print("=" * 70)
    
    # Action 1: Search for config-related definitions
    action1 = AgentAction(
        action_type=ActionType.SEARCH_DEFINITION,
        parameters={'symbol': 'config'}
    )
    print("\n[Agent] search_definition('config')")
    print(session.execute_action(action1))
    
    # Action 2: Search for malloc patterns
    action2 = AgentAction(
        action_type=ActionType.SEARCH_CODE,
        parameters={'pattern': 'malloc'}
    )
    print("\n[Agent] search_code('malloc')")
    print(session.execute_action(action2))
    
    # Action 3: Execute Python to analyze findings
    action3 = AgentAction(
        action_type=ActionType.EXECUTE_PYTHON,
        code='''
# Analyze the context we've gathered
context = get_context_memory()

# Count symbols by kind
from collections import Counter
kinds = Counter()
for tool_result in context:
    for r in tool_result.results:
        kinds[r.metadata.get('kind', 'unknown')] += 1

result = {
    'total_searches': len(context),
    'total_results': sum(len(tr.results) for tr in context),
    'by_kind': dict(kinds)
}
'''
    )
    print("\n[Agent] <executes Python analysis>")
    print(session.execute_action(action3))
    
    # Show context summary
    print("\n" + "=" * 70)
    print("CONTEXT SUMMARY")
    print("=" * 70)
    print(session.get_context_summary())
    
    conn.close()


if __name__ == '__main__':
    demo()
