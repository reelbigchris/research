# agent_functions.py
"""
Clang analysis functions for C codebase exploration.

These functions query a pre-extracted SQLite database containing
symbol definitions, call graphs, type information, and cross-references.
"""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Optional


@dataclass
class Symbol:
    name: str
    kind: str
    file: str
    line: int
    is_definition: bool


@dataclass
class Function:
    name: str
    signature: str
    return_type: str
    file: str
    line: int
    is_static: bool


@dataclass
class Parameter:
    name: str
    type: str
    position: int


@dataclass
class CallSite:
    caller: str
    callee: str
    file: str
    line: int
    is_indirect: bool


@dataclass
class Reference:
    symbol: str
    file: str
    line: int
    kind: str  # read, write, addr, call, type_ref
    context_function: Optional[str]


@dataclass
class StructField:
    name: str
    type: str
    offset_bytes: Optional[int]
    size_bits: Optional[int]


@dataclass
class Macro:
    name: str
    definition: str
    file: str
    line: int
    is_function_like: bool
    params: Optional[list[str]]


@dataclass
class TypeInfo:
    name: str
    kind: str  # struct, union, enum, typedef
    file: str
    line: int
    size_bytes: Optional[int]
    underlying_type: Optional[str]  # for typedefs


class CodebaseDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def _get_file_path(self, file_id: int) -> str:
        cur = self.conn.execute("SELECT path FROM files WHERE id = ?", (file_id,))
        row = cur.fetchone()
        return row["path"] if row else "<unknown>"

    # =========================================================================
    # FUNCTION QUERIES
    # =========================================================================

    def find_function(self, name: str) -> list[Function]:
        """
        Find function(s) by name. Returns all matching definitions and declarations.
        Use this when you need to locate where a function is defined or declared.
        """
        cur = self.conn.execute("""
            SELECT s.name, f.signature, f.return_type, s.file_id, s.line, s.is_static
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            WHERE s.name = ? AND s.kind = 'function'
            ORDER BY s.is_definition DESC
        """, (name,))
        return [
            Function(
                name=row["name"],
                signature=row["signature"],
                return_type=row["return_type"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_static=bool(row["is_static"])
            )
            for row in cur.fetchall()
        ]

    def get_function_signature(self, name: str) -> Optional[str]:
        """
        Get the full signature of a function.
        Returns the signature string or None if not found.
        """
        cur = self.conn.execute("""
            SELECT f.signature
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            WHERE s.name = ? AND s.kind = 'function' AND s.is_definition = 1
            LIMIT 1
        """, (name,))
        row = cur.fetchone()
        return row["signature"] if row else None

    def get_function_parameters(self, name: str) -> list[Parameter]:
        """
        Get parameters for a function.
        Returns list of parameters with names, types, and positions.
        """
        cur = self.conn.execute("""
            SELECT p.name, p.type, p.position
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            JOIN parameters p ON p.function_id = f.symbol_id
            WHERE s.name = ? AND s.is_definition = 1
            ORDER BY p.position
        """, (name,))
        return [
            Parameter(name=row["name"], type=row["type"], position=row["position"])
            for row in cur.fetchall()
        ]

    def get_function_locals(self, name: str) -> list[tuple[str, str]]:
        """
        Get local variables declared in a function.
        Returns list of (name, type) tuples.
        """
        cur = self.conn.execute("""
            SELECT l.name, l.type
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            JOIN locals l ON l.function_id = f.symbol_id
            WHERE s.name = ? AND s.is_definition = 1
            ORDER BY l.line
        """, (name,))
        return [(row["name"], row["type"]) for row in cur.fetchall()]

    def extract_function_source(self, name: str) -> Optional[str]:
        """
        Extract the source code of a function.
        Returns the function body as a string, or None if not found.
        """
        cur = self.conn.execute("""
            SELECT s.file_id, s.line, s.end_line
            FROM symbols s
            WHERE s.name = ? AND s.kind = 'function' AND s.is_definition = 1
            LIMIT 1
        """, (name,))
        row = cur.fetchone()
        if not row or not row["end_line"]:
            return None

        file_path = self._get_file_path(row["file_id"])
        start, end = row["line"], row["end_line"]

        # Try source cache first
        cache_cur = self.conn.execute("""
            SELECT content FROM source_cache WHERE file_id = ?
        """, (row["file_id"],))
        cache_row = cache_cur.fetchone()

        if cache_row:
            lines = cache_row["content"].splitlines()
            return "\n".join(lines[start-1:end])

        # Fall back to file system
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
                return "".join(lines[start-1:end])
        except (IOError, OSError):
            return None

    def list_functions_in_file(self, file_path: str) -> list[Function]:
        """
        List all functions defined in a file.
        Useful for getting an overview of a source file.
        """
        cur = self.conn.execute("""
            SELECT s.name, f.signature, f.return_type, s.file_id, s.line, s.is_static
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            JOIN files fi ON fi.id = s.file_id
            WHERE fi.path LIKE ? AND s.kind = 'function' AND s.is_definition = 1
            ORDER BY s.line
        """, (f"%{file_path}%",))
        return [
            Function(
                name=row["name"],
                signature=row["signature"],
                return_type=row["return_type"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_static=bool(row["is_static"])
            )
            for row in cur.fetchall()
        ]

    def search_functions(self, pattern: str) -> list[Function]:
        """
        Search for functions by name pattern (SQL LIKE syntax).
        Use % as wildcard. Example: '%init%' finds all functions with 'init' in name.
        """
        cur = self.conn.execute("""
            SELECT s.name, f.signature, f.return_type, s.file_id, s.line, s.is_static
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            WHERE s.name LIKE ? AND s.kind = 'function' AND s.is_definition = 1
            ORDER BY s.name
            LIMIT 100
        """, (pattern,))
        return [
            Function(
                name=row["name"],
                signature=row["signature"],
                return_type=row["return_type"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_static=bool(row["is_static"])
            )
            for row in cur.fetchall()
        ]

    # =========================================================================
    # CALL GRAPH QUERIES
    # =========================================================================

    def get_callees(self, function_name: str) -> list[CallSite]:
        """
        Get all functions called by a given function.
        Shows what this function depends on.
        """
        cur = self.conn.execute("""
            SELECT
                ? as caller,
                c.callee_name as callee,
                c.file_id,
                c.line,
                c.is_indirect
            FROM symbols s
            JOIN functions f ON f.symbol_id = s.id
            JOIN calls c ON c.caller_id = f.symbol_id
            WHERE s.name = ? AND s.is_definition = 1
            ORDER BY c.line
        """, (function_name, function_name))
        return [
            CallSite(
                caller=row["caller"],
                callee=row["callee"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_indirect=bool(row["is_indirect"])
            )
            for row in cur.fetchall()
        ]

    def get_callers(self, function_name: str) -> list[CallSite]:
        """
        Get all functions that call a given function.
        Shows what depends on this function. Essential for impact analysis.
        """
        cur = self.conn.execute("""
            SELECT
                caller_s.name as caller,
                ? as callee,
                c.file_id,
                c.line,
                c.is_indirect
            FROM calls c
            JOIN functions caller_f ON caller_f.symbol_id = c.caller_id
            JOIN symbols caller_s ON caller_s.id = caller_f.symbol_id
            WHERE c.callee_name = ?
            ORDER BY caller_s.name, c.line
        """, (function_name, function_name))
        return [
            CallSite(
                caller=row["caller"],
                callee=row["callee"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_indirect=bool(row["is_indirect"])
            )
            for row in cur.fetchall()
        ]

    def find_call_path(
        self,
        from_func: str,
        to_func: str,
        max_depth: int = 10
    ) -> list[list[str]]:
        """
        Find call paths between two functions.
        Returns list of paths, where each path is a list of function names.
        Limited to max_depth to avoid infinite loops.
        """
        paths = []
        visited = set()

        def dfs(current: str, target: str, path: list[str], depth: int):
            if depth > max_depth:
                return
            if current == target:
                paths.append(path.copy())
                return
            if current in visited:
                return

            visited.add(current)
            for callee in self.get_callees(current):
                path.append(callee.callee)
                dfs(callee.callee, target, path, depth + 1)
                path.pop()
            visited.remove(current)

        dfs(from_func, to_func, [from_func], 0)
        return paths

    def get_call_tree(self, function_name: str, depth: int = 3) -> dict:
        """
        Get a tree of calls rooted at a function.
        Returns nested dict structure showing call hierarchy.
        Useful for understanding function behavior.
        """
        def build_tree(name: str, current_depth: int, visited: set) -> dict:
            if current_depth >= depth or name in visited:
                return {"name": name, "calls": "..."}

            visited.add(name)
            callees = self.get_callees(name)
            children = [
                build_tree(c.callee, current_depth + 1, visited.copy())
                for c in callees
            ]
            return {"name": name, "calls": children}

        return build_tree(function_name, 0, set())

    # =========================================================================
    # TYPE QUERIES
    # =========================================================================

    def get_type_definition(self, type_name: str) -> Optional[TypeInfo]:
        """
        Get information about a type (struct, union, enum, typedef).
        For typedefs, includes the underlying resolved type.
        """
        cur = self.conn.execute("""
            SELECT s.name, t.kind, s.file_id, s.line, t.size_bytes, t.underlying_type
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            WHERE s.name = ? AND s.is_definition = 1
            LIMIT 1
        """, (type_name,))
        row = cur.fetchone()
        if not row:
            return None
        return TypeInfo(
            name=row["name"],
            kind=row["kind"],
            file=self._get_file_path(row["file_id"]),
            line=row["line"],
            size_bytes=row["size_bytes"],
            underlying_type=row["underlying_type"]
        )

    def resolve_typedef(self, type_name: str) -> str:
        """
        Resolve a typedef to its underlying type.
        Follows the typedef chain to the base type.
        Returns the original name if not a typedef.
        """
        cur = self.conn.execute("""
            SELECT t.underlying_type
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            WHERE s.name = ? AND t.kind = 'typedef' AND s.is_definition = 1
        """, (type_name,))
        row = cur.fetchone()
        return row["underlying_type"] if row else type_name

    def get_struct_fields(self, struct_name: str) -> list[StructField]:
        """
        Get all fields of a struct or union.
        Includes offset and size information for layout analysis.
        """
        cur = self.conn.execute("""
            SELECT f.name, f.type, f.offset_bits, f.size_bits
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            JOIN fields f ON f.type_id = t.symbol_id
            WHERE s.name = ? AND s.is_definition = 1
            ORDER BY f.position
        """, (struct_name,))
        return [
            StructField(
                name=row["name"],
                type=row["type"],
                offset_bytes=row["offset_bits"] // 8 if row["offset_bits"] else None,
                size_bits=row["size_bits"]
            )
            for row in cur.fetchall()
        ]

    def get_enum_values(self, enum_name: str) -> list[tuple[str, int]]:
        """
        Get all values of an enum.
        Returns list of (name, value) tuples.
        """
        cur = self.conn.execute("""
            SELECT ec.name, ec.value
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            JOIN enum_constants ec ON ec.type_id = t.symbol_id
            WHERE s.name = ? AND s.is_definition = 1
            ORDER BY ec.position
        """, (enum_name,))
        return [(row["name"], row["value"]) for row in cur.fetchall()]

    def find_type_usage(self, type_name: str) -> list[Reference]:
        """
        Find all places where a type is used.
        Includes variable declarations, function parameters, struct fields, etc.
        """
        cur = self.conn.execute("""
            SELECT s.name, fi.path, r.line, r.kind, ctx_s.name as context_func
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            JOIN refs r ON r.symbol_id = s.id
            JOIN files fi ON fi.id = r.file_id
            LEFT JOIN functions ctx_f ON ctx_f.symbol_id = r.context_function_id
            LEFT JOIN symbols ctx_s ON ctx_s.id = ctx_f.symbol_id
            WHERE s.name = ?
            ORDER BY fi.path, r.line
        """, (type_name,))
        return [
            Reference(
                symbol=type_name,
                file=row["path"],
                line=row["line"],
                kind=row["kind"],
                context_function=row["context_func"]
            )
            for row in cur.fetchall()
        ]

    def get_field_offset(self, struct_name: str, field_name: str) -> Optional[int]:
        """
        Get the byte offset of a field within a struct.
        Useful for correlating source with disassembly.
        """
        cur = self.conn.execute("""
            SELECT f.offset_bits
            FROM symbols s
            JOIN types t ON t.symbol_id = s.id
            JOIN fields f ON f.type_id = t.symbol_id
            WHERE s.name = ? AND f.name = ?
        """, (struct_name, field_name))
        row = cur.fetchone()
        if row and row["offset_bits"] is not None:
            return row["offset_bits"] // 8
        return None

    # =========================================================================
    # MACRO QUERIES
    # =========================================================================

    def get_macro_definition(self, name: str) -> Optional[Macro]:
        """
        Get the definition of a macro.
        Includes whether it's function-like and its parameters.
        """
        cur = self.conn.execute("""
            SELECT m.name, m.definition, m.file_id, m.line,
                   m.is_function_like, m.param_names
            FROM macros m
            WHERE m.name = ?
            ORDER BY m.is_builtin ASC
            LIMIT 1
        """, (name,))
        row = cur.fetchone()
        if not row:
            return None
        return Macro(
            name=row["name"],
            definition=row["definition"] or "",
            file=self._get_file_path(row["file_id"]) if row["file_id"] else "<builtin>",
            line=row["line"] or 0,
            is_function_like=bool(row["is_function_like"]),
            params=row["param_names"].split(",") if row["param_names"] else None
        )

    def search_macros(self, pattern: str) -> list[Macro]:
        """
        Search for macros by name pattern (SQL LIKE syntax).
        Useful for finding related macros (e.g., all ERROR_% macros).
        """
        cur = self.conn.execute("""
            SELECT m.name, m.definition, m.file_id, m.line,
                   m.is_function_like, m.param_names
            FROM macros m
            WHERE m.name LIKE ? AND m.is_builtin = 0
            ORDER BY m.name
            LIMIT 100
        """, (pattern,))
        return [
            Macro(
                name=row["name"],
                definition=row["definition"] or "",
                file=self._get_file_path(row["file_id"]) if row["file_id"] else "<builtin>",
                line=row["line"] or 0,
                is_function_like=bool(row["is_function_like"]),
                params=row["param_names"].split(",") if row["param_names"] else None
            )
            for row in cur.fetchall()
        ]

    def expand_macro(self, name: str, args: Optional[list[str]] = None) -> Optional[str]:
        """
        Get the expansion of a macro.
        For function-like macros, pass arguments to see substituted expansion.
        """
        macro = self.get_macro_definition(name)
        if not macro:
            return None

        expansion = macro.definition
        if macro.is_function_like and macro.params and args:
            for param, arg in zip(macro.params, args):
                expansion = expansion.replace(param.strip(), arg)

        return expansion

    # =========================================================================
    # CROSS-REFERENCE QUERIES
    # =========================================================================

    def find_references(self, symbol_name: str) -> list[Reference]:
        """
        Find all references to a symbol (variable, function, type).
        Includes the kind of reference (read, write, call, etc.).
        """
        cur = self.conn.execute("""
            SELECT s.name, fi.path, r.line, r.kind, ctx_s.name as context_func
            FROM symbols s
            JOIN refs r ON r.symbol_id = s.id
            JOIN files fi ON fi.id = r.file_id
            LEFT JOIN functions ctx_f ON ctx_f.symbol_id = r.context_function_id
            LEFT JOIN symbols ctx_s ON ctx_s.id = ctx_f.symbol_id
            WHERE s.name = ?
            ORDER BY fi.path, r.line
        """, (symbol_name,))
        return [
            Reference(
                symbol=symbol_name,
                file=row["path"],
                line=row["line"],
                kind=row["kind"],
                context_function=row["context_func"]
            )
            for row in cur.fetchall()
        ]

    def find_symbol_definition(self, name: str) -> Optional[Symbol]:
        """
        Find where a symbol is defined.
        Works for functions, variables, types, and macros.
        """
        # Try symbols table first
        cur = self.conn.execute("""
            SELECT s.name, s.kind, s.file_id, s.line, s.is_definition
            FROM symbols s
            WHERE s.name = ? AND s.is_definition = 1
            LIMIT 1
        """, (name,))
        row = cur.fetchone()
        if row:
            return Symbol(
                name=row["name"],
                kind=row["kind"],
                file=self._get_file_path(row["file_id"]),
                line=row["line"],
                is_definition=True
            )

        # Try macros
        macro = self.get_macro_definition(name)
        if macro:
            return Symbol(
                name=macro.name,
                kind="macro",
                file=macro.file,
                line=macro.line,
                is_definition=True
            )

        return None

    def get_globals_in_file(self, file_path: str) -> list[tuple[str, str, bool]]:
        """
        Get all global variables in a file.
        Returns list of (name, type, is_static) tuples.
        """
        cur = self.conn.execute("""
            SELECT s.name, v.type, s.is_static
            FROM symbols s
            JOIN variables v ON v.symbol_id = s.id
            JOIN files fi ON fi.id = s.file_id
            WHERE fi.path LIKE ? AND s.kind = 'variable' AND s.is_definition = 1
            ORDER BY s.line
        """, (f"%{file_path}%",))
        return [
            (row["name"], row["type"], bool(row["is_static"]))
            for row in cur.fetchall()
        ]

    # =========================================================================
    # DOCUMENTATION QUERIES
    # =========================================================================

    def get_function_doc(self, name: str) -> Optional[dict]:
        """
        Get Doxygen documentation for a function.
        Returns dict with brief, detailed, return_doc, and param_docs.
        """
        cur = self.conn.execute("""
            SELECT d.brief, d.detailed, d.return_doc, d.raw_comment, d.id
            FROM symbols s
            JOIN docs d ON d.symbol_id = s.id
            WHERE s.name = ? AND s.kind = 'function'
            LIMIT 1
        """, (name,))
        row = cur.fetchone()
        if not row:
            return None

        # Get parameter docs
        param_cur = self.conn.execute("""
            SELECT param_name, description, direction
            FROM param_docs
            WHERE doc_id = ?
        """, (row["id"],))

        params = {
            p["param_name"]: {
                "description": p["description"],
                "direction": p["direction"]
            }
            for p in param_cur.fetchall()
        }

        return {
            "brief": row["brief"],
            "detailed": row["detailed"],
            "return": row["return_doc"],
            "params": params,
            "raw": row["raw_comment"]
        }

    # =========================================================================
    # INCLUDE GRAPH QUERIES
    # =========================================================================

    def get_includes(self, file_path: str, recursive: bool = False) -> list[str]:
        """
        Get files included by a given file.
        If recursive=True, returns transitive closure of includes.
        """
        cur = self.conn.execute("""
            SELECT i.resolved_path
            FROM includes i
            JOIN files f ON f.id = i.file_id
            WHERE f.path LIKE ?
        """, (f"%{file_path}%",))

        direct = [row["resolved_path"] for row in cur.fetchall() if row["resolved_path"]]

        if not recursive:
            return direct

        all_includes = set(direct)
        to_process = list(direct)
        while to_process:
            current = to_process.pop()
            for inc in self.get_includes(current, recursive=False):
                if inc not in all_includes:
                    all_includes.add(inc)
                    to_process.append(inc)

        return sorted(all_includes)

    def get_includers(self, file_path: str) -> list[str]:
        """
        Get files that include a given file.
        Useful for understanding header dependencies.
        """
        cur = self.conn.execute("""
            SELECT DISTINCT f.path
            FROM includes i
            JOIN files f ON f.id = i.file_id
            WHERE i.resolved_path LIKE ?
        """, (f"%{file_path}%",))
        return [row["path"] for row in cur.fetchall()]

    # =========================================================================
    # INCREMENTAL UPDATE SUPPORT
    # =========================================================================

    def get_stale_files(self, workspace_root: str) -> list[str]:
        """
        Find files that have changed since last extraction.
        Compares mtime in database to current file mtime.
        """
        stale = []
        cur = self.conn.execute("SELECT path, mtime FROM files")
        for row in cur.fetchall():
            full_path = Path(workspace_root) / row["path"]
            try:
                current_mtime = full_path.stat().st_mtime
                if current_mtime > row["mtime"]:
                    stale.append(row["path"])
            except OSError:
                # File deleted
                stale.append(row["path"])
        return stale

    def delete_file_data(self, file_path: str):
        """
        Remove all extracted data for a file.
        Called before re-extracting a modified file.
        CASCADE handles removing related symbols, refs, etc.
        """
        self.conn.execute("""
            DELETE FROM files WHERE path LIKE ?
        """, (f"%{file_path}%",))
        self.conn.commit()
