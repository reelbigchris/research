# extractor.py
"""
Extract C codebase information into SQLite using libclang.

Usage:
    extractor = ClangExtractor("codebase.db", "/path/to/workspace")
    extractor.extract_all("compile_commands.json")
    # or for incremental:
    extractor.extract_files(["src/modified.c", "src/new.c"])
"""

import json
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Iterator
import sqlite3

from clang.cindex import (
    Index,
    TranslationUnit,
    Cursor,
    CursorKind,
    TypeKind,
    LinkageKind,
    StorageClass,
    TokenKind,
    Config,
)

# Uncomment and adjust if libclang isn't found automatically
# Config.set_library_file("/usr/lib/llvm-14/lib/libclang.so")


@dataclass
class ExtractedFunction:
    name: str
    file: str
    line: int
    end_line: int
    column: int
    return_type: str
    signature: str
    is_definition: bool
    is_static: bool
    is_inline: bool
    is_variadic: bool
    storage_class: str
    linkage: str
    parameters: list[tuple[str, str]]  # (name, type)
    locals: list[tuple[str, str, int]]  # (name, type, line)
    calls: list[tuple[str, int, int, bool]]  # (callee_name, line, col, is_indirect)
    raw_comment: Optional[str] = None


@dataclass
class ExtractedType:
    name: str
    kind: str  # struct, union, enum, typedef
    file: str
    line: int
    column: int
    is_definition: bool
    is_anonymous: bool
    size_bytes: Optional[int]
    alignment: Optional[int]
    underlying_type: Optional[str]  # for typedefs
    fields: list[dict] = field(default_factory=list)  # for struct/union
    enum_constants: list[tuple[str, int]] = field(default_factory=list)  # for enum
    raw_comment: Optional[str] = None


@dataclass
class ExtractedVariable:
    name: str
    file: str
    line: int
    column: int
    type: str
    is_definition: bool
    is_static: bool
    is_const: bool
    is_volatile: bool
    storage_class: str
    linkage: str
    raw_comment: Optional[str] = None


@dataclass
class ExtractedMacro:
    name: str
    file: str
    line: int
    definition: str
    is_function_like: bool
    param_names: Optional[list[str]]


@dataclass
class ExtractedRef:
    symbol_name: str
    symbol_kind: str
    file: str
    line: int
    column: int
    ref_kind: str  # read, write, addr, call, type_ref
    context_function: Optional[str]


@dataclass
class ExtractedInclude:
    including_file: str
    included_path: str
    resolved_path: Optional[str]
    line: int
    is_system: bool


class ClangExtractor:
    def __init__(self, db_path: str, workspace_root: str):
        self.db_path = db_path
        self.workspace_root = Path(workspace_root).resolve()
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self.index = Index.create()

        # Cache for file_id lookups
        self._file_id_cache: dict[str, int] = {}

        # Track current function context for refs
        self._current_function: Optional[str] = None

    def _init_schema(self):
        """Create tables if they don't exist."""
        schema = '''
        -- Extraction metadata
        CREATE TABLE IF NOT EXISTS extraction_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        -- Track file state for incremental updates
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            hash TEXT,
            last_extracted REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

        -- Core symbol table
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            line INTEGER NOT NULL,
            column INTEGER,
            end_line INTEGER,
            end_column INTEGER,
            is_definition INTEGER NOT NULL DEFAULT 0,
            is_static INTEGER NOT NULL DEFAULT 0,
            storage_class TEXT,
            linkage TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
        CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
        CREATE INDEX IF NOT EXISTS idx_symbols_name_kind ON symbols(name, kind);

        -- Function-specific details
        CREATE TABLE IF NOT EXISTS functions (
            symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            return_type TEXT NOT NULL,
            signature TEXT NOT NULL,
            is_variadic INTEGER NOT NULL DEFAULT 0,
            is_inline INTEGER NOT NULL DEFAULT 0,
            cyclomatic_complexity INTEGER
        );

        -- Function parameters
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY,
            function_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            name TEXT,
            type TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_params_function ON parameters(function_id);

        -- Function local variables
        CREATE TABLE IF NOT EXISTS locals (
            id INTEGER PRIMARY KEY,
            function_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            line INTEGER,
            scope_depth INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_locals_function ON locals(function_id);

        -- Type details
        CREATE TABLE IF NOT EXISTS types (
            symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            underlying_type TEXT,
            size_bytes INTEGER,
            alignment INTEGER,
            is_anonymous INTEGER NOT NULL DEFAULT 0
        );

        -- Struct/union fields
        CREATE TABLE IF NOT EXISTS fields (
            id INTEGER PRIMARY KEY,
            type_id INTEGER NOT NULL REFERENCES types(symbol_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            offset_bits INTEGER,
            size_bits INTEGER,
            is_bitfield INTEGER NOT NULL DEFAULT 0,
            bitfield_width INTEGER,
            position INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fields_type ON fields(type_id);

        -- Enum constants
        CREATE TABLE IF NOT EXISTS enum_constants (
            id INTEGER PRIMARY KEY,
            type_id INTEGER NOT NULL REFERENCES types(symbol_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            value INTEGER,
            position INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enum_constants_type ON enum_constants(type_id);
        CREATE INDEX IF NOT EXISTS idx_enum_constants_name ON enum_constants(name);

        -- Variable-specific details
        CREATE TABLE IF NOT EXISTS variables (
            symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            is_const INTEGER NOT NULL DEFAULT 0,
            is_volatile INTEGER NOT NULL DEFAULT 0,
            initial_value TEXT
        );

        -- Macros
        CREATE TABLE IF NOT EXISTS macros (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
            line INTEGER,
            definition TEXT,
            is_function_like INTEGER NOT NULL DEFAULT 0,
            param_names TEXT,
            is_builtin INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_macros_name ON macros(name);
        CREATE INDEX IF NOT EXISTS idx_macros_file ON macros(file_id);

        -- Call graph
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY,
            caller_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
            callee_id INTEGER REFERENCES functions(symbol_id) ON DELETE SET NULL,
            callee_name TEXT NOT NULL,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            line INTEGER NOT NULL,
            column INTEGER,
            is_indirect INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_id);
        CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_id);
        CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON calls(callee_name);

        -- Cross-references
        CREATE TABLE IF NOT EXISTS refs (
            id INTEGER PRIMARY KEY,
            symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            line INTEGER NOT NULL,
            column INTEGER,
            kind TEXT NOT NULL,
            context_function_id INTEGER REFERENCES functions(symbol_id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_refs_symbol ON refs(symbol_id);
        CREATE INDEX IF NOT EXISTS idx_refs_file ON refs(file_id);
        CREATE INDEX IF NOT EXISTS idx_refs_context ON refs(context_function_id);

        -- Include graph
        CREATE TABLE IF NOT EXISTS includes (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            included_path TEXT NOT NULL,
            resolved_path TEXT,
            line INTEGER NOT NULL,
            is_system INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_includes_file ON includes(file_id);
        CREATE INDEX IF NOT EXISTS idx_includes_resolved ON includes(resolved_path);

        -- Documentation
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
            raw_comment TEXT,
            brief TEXT,
            detailed TEXT,
            return_doc TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_docs_symbol ON docs(symbol_id);

        -- Parameter documentation
        CREATE TABLE IF NOT EXISTS param_docs (
            id INTEGER PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
            param_name TEXT NOT NULL,
            description TEXT,
            direction TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_param_docs_doc ON param_docs(doc_id);

        -- Source cache
        CREATE TABLE IF NOT EXISTS source_cache (
            file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
            content TEXT NOT NULL
        );
        '''
        self.conn.executescript(schema)
        self.conn.commit()

    # =========================================================================
    # FILE MANAGEMENT
    # =========================================================================

    def _get_relative_path(self, absolute_path: str) -> str:
        """Convert absolute path to workspace-relative path."""
        try:
            return str(Path(absolute_path).resolve().relative_to(self.workspace_root))
        except ValueError:
            # Outside workspace, use absolute
            return absolute_path

    def _get_or_create_file(self, file_path: str) -> int:
        """Get file_id, creating the file record if needed."""
        rel_path = self._get_relative_path(file_path)

        if rel_path in self._file_id_cache:
            return self._file_id_cache[rel_path]

        cur = self.conn.execute(
            "SELECT id FROM files WHERE path = ?", (rel_path,)
        )
        row = cur.fetchone()
        if row:
            self._file_id_cache[rel_path] = row["id"]
            return row["id"]

        # Create new file record
        abs_path = self.workspace_root / rel_path
        try:
            stat = abs_path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            content_hash = self._hash_file(abs_path)
        except OSError:
            mtime = 0
            size = 0
            content_hash = None

        import time
        cur = self.conn.execute(
            """INSERT INTO files (path, mtime, size, hash, last_extracted)
               VALUES (?, ?, ?, ?, ?)""",
            (rel_path, mtime, size, content_hash, time.time())
        )
        file_id = cur.lastrowid
        self._file_id_cache[rel_path] = file_id
        return file_id

    def _hash_file(self, path: Path) -> Optional[str]:
        """Compute SHA256 hash of file contents."""
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None

    def _delete_file_data(self, file_path: str):
        """Remove all data for a file before re-extraction."""
        rel_path = self._get_relative_path(file_path)
        self.conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        if rel_path in self._file_id_cache:
            del self._file_id_cache[rel_path]

    def _cache_source(self, file_id: int, file_path: str):
        """Cache source content for later retrieval."""
        try:
            with open(file_path, "r", errors="replace") as f:
                content = f.read()
            self.conn.execute(
                """INSERT OR REPLACE INTO source_cache (file_id, content)
                   VALUES (?, ?)""",
                (file_id, content)
            )
        except OSError:
            pass

    # =========================================================================
    # MAIN EXTRACTION ENTRY POINTS
    # =========================================================================

    def extract_all(self, compile_commands_path: str, cache_source: bool = True):
        """
        Extract entire codebase from compile_commands.json.
        This is the full extraction, typically run overnight or on first setup.
        """
        with open(compile_commands_path, "r") as f:
            compile_commands = json.load(f)

        # Clear existing data
        self.conn.execute("DELETE FROM files")
        self.conn.commit()
        self._file_id_cache.clear()

        total = len(compile_commands)
        for i, entry in enumerate(compile_commands):
            file_path = entry["file"]
            directory = entry.get("directory", ".")

            # Build args from command or arguments
            if "arguments" in entry:
                args = entry["arguments"][1:]  # skip compiler name
            else:
                # Parse command string
                import shlex
                args = shlex.split(entry["command"])[1:]

            print(f"[{i+1}/{total}] Extracting {file_path}")

            try:
                self._extract_file(file_path, args, directory, cache_source)
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

        self.conn.commit()
        self._resolve_call_graph()
        self._update_meta()
        print("Extraction complete.")

    def extract_files(
        self,
        file_paths: list[str],
        compile_commands_path: str,
        cache_source: bool = True
    ):
        """
        Incrementally extract specific files.
        Use this for updating after workspace changes.
        """
        # Load compile commands to get args for each file
        with open(compile_commands_path, "r") as f:
            compile_commands = json.load(f)

        # Index by file
        commands_by_file = {}
        for entry in compile_commands:
            commands_by_file[entry["file"]] = entry

        for file_path in file_paths:
            # Find matching compile command
            entry = commands_by_file.get(file_path)
            if not entry:
                # Try resolving path
                abs_path = str((self.workspace_root / file_path).resolve())
                entry = commands_by_file.get(abs_path)

            if not entry:
                print(f"No compile command for {file_path}, skipping")
                continue

            directory = entry.get("directory", ".")
            if "arguments" in entry:
                args = entry["arguments"][1:]
            else:
                import shlex
                args = shlex.split(entry["command"])[1:]

            # Delete old data for this file
            self._delete_file_data(file_path)

            print(f"Re-extracting {file_path}")
            try:
                self._extract_file(file_path, args, directory, cache_source)
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

        self.conn.commit()
        self._resolve_call_graph()
        self._update_meta()

    def get_stale_files(self, compile_commands_path: str) -> list[str]:
        """
        Find files that have changed since last extraction.
        Returns list of file paths that need re-extraction.
        """
        with open(compile_commands_path, "r") as f:
            compile_commands = json.load(f)

        stale = []
        for entry in compile_commands:
            file_path = entry["file"]
            rel_path = self._get_relative_path(file_path)

            cur = self.conn.execute(
                "SELECT mtime, hash FROM files WHERE path = ?",
                (rel_path,)
            )
            row = cur.fetchone()

            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                abs_path = Path(entry.get("directory", ".")) / file_path

            try:
                current_mtime = abs_path.stat().st_mtime
            except OSError:
                # File doesn't exist
                if row:
                    stale.append(file_path)
                continue

            if not row:
                # New file
                stale.append(file_path)
            elif current_mtime > row["mtime"]:
                # Modified
                stale.append(file_path)

        return stale

    def _update_meta(self):
        """Update extraction metadata."""
        import time
        self.conn.execute(
            "INSERT OR REPLACE INTO extraction_meta (key, value) VALUES (?, ?)",
            ("extracted_at", str(time.time()))
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO extraction_meta (key, value) VALUES (?, ?)",
            ("workspace_root", str(self.workspace_root))
        )
        self.conn.commit()

    # =========================================================================
    # CORE EXTRACTION LOGIC
    # =========================================================================

    def _extract_file(
        self,
        file_path: str,
        args: list[str],
        directory: str,
        cache_source: bool
    ):
        """Extract all information from a single translation unit."""
        import os
        old_cwd = os.getcwd()
        os.chdir(directory)

        try:
            tu = self.index.parse(
                file_path,
                args=args,
                options=(
                    TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD |
                    TranslationUnit.PARSE_SKIP_FUNCTION_BODIES * 0  # We want bodies
                )
            )
        finally:
            os.chdir(old_cwd)

        if not tu:
            raise RuntimeError(f"Failed to parse {file_path}")

        # Report diagnostics
        errors = [d for d in tu.diagnostics if d.severity >= 3]
        if errors:
            print(f"  {len(errors)} errors during parsing")

        # Get file_id for the main file
        main_file = str(Path(directory) / file_path)
        file_id = self._get_or_create_file(main_file)

        if cache_source:
            self._cache_source(file_id, main_file)

        # Extract macros from preprocessing
        self._extract_macros(tu, main_file)

        # Extract includes
        self._extract_includes(tu, main_file)

        # Walk AST
        self._walk_cursor(tu.cursor, main_file)

        self.conn.commit()

    def _is_from_main_file(self, cursor: Cursor, main_file: str) -> bool:
        """Check if cursor is from the main file (not an include)."""
        loc = cursor.location
        if not loc.file:
            return False
        cursor_file = str(Path(loc.file.name).resolve())
        main_resolved = str(Path(main_file).resolve())
        return cursor_file == main_resolved

    def _walk_cursor(self, cursor: Cursor, main_file: str, depth: int = 0):
        """Recursively walk AST and extract information."""
        # Only process items from the main file
        if cursor.location.file and not self._is_from_main_file(cursor, main_file):
            return

        kind = cursor.kind

        if kind == CursorKind.FUNCTION_DECL:
            self._extract_function(cursor, main_file)
        elif kind == CursorKind.VAR_DECL and depth == 1:  # Top-level only
            self._extract_global_variable(cursor, main_file)
        elif kind == CursorKind.STRUCT_DECL:
            self._extract_struct_or_union(cursor, main_file, "struct")
        elif kind == CursorKind.UNION_DECL:
            self._extract_struct_or_union(cursor, main_file, "union")
        elif kind == CursorKind.ENUM_DECL:
            self._extract_enum(cursor, main_file)
        elif kind == CursorKind.TYPEDEF_DECL:
            self._extract_typedef(cursor, main_file)

        # Recurse into children
        for child in cursor.get_children():
            self._walk_cursor(child, main_file, depth + 1)

    # =========================================================================
    # FUNCTION EXTRACTION
    # =========================================================================

    def _extract_function(self, cursor: Cursor, main_file: str):
        """Extract function declaration/definition."""
        name = cursor.spelling
        if not name:
            return

        file_id = self._get_or_create_file(main_file)
        loc = cursor.location
        extent = cursor.extent

        is_def = cursor.is_definition()
        is_static = cursor.storage_class == StorageClass.STATIC
        is_inline = cursor.get_usr() and "inline" in cursor.get_usr()  # Approximation

        # Get return type
        result_type = cursor.result_type
        return_type = result_type.spelling if result_type else "void"

        # Build signature
        params = []
        for child in cursor.get_children():
            if child.kind == CursorKind.PARM_DECL:
                param_name = child.spelling or f"param{len(params)}"
                param_type = child.type.spelling
                params.append((param_name, param_type))

        param_str = ", ".join(f"{t} {n}" for n, t in params)
        signature = f"{return_type} {name}({param_str})"

        # Check for variadic
        is_variadic = cursor.type.is_function_variadic() if cursor.type else False

        # Get raw comment
        raw_comment = cursor.raw_comment

        # Determine linkage and storage class
        linkage = self._get_linkage(cursor)
        storage = self._get_storage_class(cursor)

        # Insert symbol
        cur = self.conn.execute(
            """INSERT INTO symbols
               (name, kind, file_id, line, column, end_line, end_column,
                is_definition, is_static, storage_class, linkage)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, "function", file_id, loc.line, loc.column,
             extent.end.line if extent else None,
             extent.end.column if extent else None,
             int(is_def), int(is_static), storage, linkage)
        )
        symbol_id = cur.lastrowid

        # Insert function details
        self.conn.execute(
            """INSERT INTO functions
               (symbol_id, return_type, signature, is_variadic, is_inline)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol_id, return_type, signature, int(is_variadic), int(is_inline))
        )

        # Insert parameters
        for pos, (param_name, param_type) in enumerate(params):
            self.conn.execute(
                """INSERT INTO parameters (function_id, position, name, type)
                   VALUES (?, ?, ?, ?)""",
                (symbol_id, pos, param_name, param_type)
            )

        # Extract documentation
        if raw_comment:
            self._extract_documentation(symbol_id, raw_comment)

        # If this is a definition, extract locals and calls
        if is_def:
            self._extract_function_body(cursor, symbol_id, file_id, main_file)

    def _extract_function_body(
        self,
        cursor: Cursor,
        function_id: int,
        file_id: int,
        main_file: str
    ):
        """Extract local variables and calls from function body."""
        # Track which function we're in for ref context
        old_context = self._current_function
        self._current_function = cursor.spelling

        locals_seen = set()

        def walk_body(c: Cursor, scope_depth: int = 0):
            if c.kind == CursorKind.VAR_DECL:
                var_name = c.spelling
                if var_name and var_name not in locals_seen:
                    locals_seen.add(var_name)
                    var_type = c.type.spelling if c.type else "unknown"
                    self.conn.execute(
                        """INSERT INTO locals
                           (function_id, name, type, line, scope_depth)
                           VALUES (?, ?, ?, ?, ?)""",
                        (function_id, var_name, var_type,
                         c.location.line, scope_depth)
                    )

            elif c.kind == CursorKind.CALL_EXPR:
                callee_name = c.spelling
                if callee_name:
                    # Check if it's an indirect call (function pointer)
                    is_indirect = False
                    ref = c.referenced
                    if ref and ref.kind != CursorKind.FUNCTION_DECL:
                        is_indirect = True

                    self.conn.execute(
                        """INSERT INTO calls
                           (caller_id, callee_name, file_id, line, column, is_indirect)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (function_id, callee_name, file_id,
                         c.location.line, c.location.column, int(is_indirect))
                    )

            elif c.kind == CursorKind.DECL_REF_EXPR:
                # Cross-reference to a symbol
                ref = c.referenced
                if ref:
                    self._record_reference(c, ref, file_id, function_id)

            # Increase scope depth for compound statements
            new_depth = scope_depth
            if c.kind == CursorKind.COMPOUND_STMT:
                new_depth += 1

            for child in c.get_children():
                walk_body(child, new_depth)

        # Find function body (compound statement)
        for child in cursor.get_children():
            if child.kind == CursorKind.COMPOUND_STMT:
                walk_body(child)
                break

        self._current_function = old_context

    def _record_reference(
        self,
        cursor: Cursor,
        referenced: Cursor,
        file_id: int,
        context_function_id: Optional[int]
    ):
        """Record a cross-reference to a symbol."""
        symbol_name = referenced.spelling
        if not symbol_name:
            return

        # Determine reference kind based on context
        ref_kind = "read"  # Default
        parent = cursor.semantic_parent
        if parent:
            if parent.kind == CursorKind.UNARY_OPERATOR:
                # Could be address-of or dereference
                tokens = list(parent.get_tokens())
                if tokens and tokens[0].spelling == "&":
                    ref_kind = "addr"
            elif parent.kind in (CursorKind.BINARY_OPERATOR,
                                  CursorKind.COMPOUND_ASSIGNMENT_OPERATOR):
                # Check if we're on LHS of assignment
                children = list(parent.get_children())
                if children and children[0] == cursor:
                    tokens = list(parent.get_tokens())
                    if any(t.spelling in ("=", "+=", "-=", "*=", "/=",
                                          "|=", "&=", "^=", "<<=", ">>=")
                           for t in tokens):
                        ref_kind = "write"

        # Look up or create the symbol
        cur = self.conn.execute(
            "SELECT id FROM symbols WHERE name = ? LIMIT 1",
            (symbol_name,)
        )
        row = cur.fetchone()
        if not row:
            return  # Symbol not in our database

        symbol_id = row["id"]

        self.conn.execute(
            """INSERT INTO refs
               (symbol_id, file_id, line, column, kind, context_function_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (symbol_id, file_id, cursor.location.line,
             cursor.location.column, ref_kind, context_function_id)
        )

    # =========================================================================
    # TYPE EXTRACTION
    # =========================================================================

    def _extract_struct_or_union(
        self,
        cursor: Cursor,
        main_file: str,
        kind: str
    ):
        """Extract struct or union definition."""
        name = cursor.spelling
        is_anonymous = not name
        if is_anonymous:
            name = f"<anonymous_{kind}_{cursor.hash}>"

        if not cursor.is_definition():
            return  # Skip forward declarations

        file_id = self._get_or_create_file(main_file)
        loc = cursor.location

        # Get size and alignment
        try:
            size = cursor.type.get_size()
            alignment = cursor.type.get_align()
        except:
            size = None
            alignment = None

        # Insert symbol
        cur = self.conn.execute(
            """INSERT INTO symbols
               (name, kind, file_id, line, column, is_definition, is_static)
               VALUES (?, ?, ?, ?, ?, 1, 0)""",
            (name, kind, file_id, loc.line, loc.column)
        )
        symbol_id = cur.lastrowid

        # Insert type details
        self.conn.execute(
            """INSERT INTO types
               (symbol_id, kind, size_bytes, alignment, is_anonymous)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol_id, kind, size, alignment, int(is_anonymous))
        )

        # Extract fields
        position = 0
        for child in cursor.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                field_name = child.spelling or f"field{position}"
                field_type = child.type.spelling if child.type else "unknown"

                # Get offset
                try:
                    offset_bits = cursor.type.get_offset(field_name)
                except:
                    offset_bits = None

                # Get size
                try:
                    size_bits = child.type.get_size() * 8 if child.type else None
                except:
                    size_bits = None

                # Check for bitfield
                is_bitfield = child.is_bitfield()
                bitfield_width = child.get_bitfield_width() if is_bitfield else None

                self.conn.execute(
                    """INSERT INTO fields
                       (type_id, name, type, offset_bits, size_bits,
                        is_bitfield, bitfield_width, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol_id, field_name, field_type, offset_bits, size_bits,
                     int(is_bitfield), bitfield_width, position)
                )
                position += 1

        # Extract documentation
        if cursor.raw_comment:
            self._extract_documentation(symbol_id, cursor.raw_comment)

    def _extract_enum(self, cursor: Cursor, main_file: str):
        """Extract enum definition."""
        name = cursor.spelling
        is_anonymous = not name
        if is_anonymous:
            name = f"<anonymous_enum_{cursor.hash}>"

        if not cursor.is_definition():
            return

        file_id = self._get_or_create_file(main_file)
        loc = cursor.location

        # Insert symbol
        cur = self.conn.execute(
            """INSERT INTO symbols
               (name, kind, file_id, line, column, is_definition, is_static)
               VALUES (?, ?, ?, ?, ?, 1, 0)""",
            (name, "enum", file_id, loc.line, loc.column)
        )
        symbol_id = cur.lastrowid

        # Insert type details
        self.conn.execute(
            """INSERT INTO types
               (symbol_id, kind, is_anonymous)
               VALUES (?, 'enum', ?)""",
            (symbol_id, int(is_anonymous))
        )

        # Extract enum constants
        position = 0
        for child in cursor.get_children():
            if child.kind == CursorKind.ENUM_CONSTANT_DECL:
                const_name = child.spelling
                const_value = child.enum_value

                self.conn.execute(
                    """INSERT INTO enum_constants
                       (type_id, name, value, position)
                       VALUES (?, ?, ?, ?)""",
                    (symbol_id, const_name, const_value, position)
                )

                # Also add as a symbol for cross-referencing
                self.conn.execute(
                    """INSERT INTO symbols
                       (name, kind, file_id, line, column, is_definition, is_static)
                       VALUES (?, 'enum_constant', ?, ?, ?, 1, 0)""",
                    (const_name, file_id, child.location.line, child.location.column)
                )

                position += 1

    def _extract_typedef(self, cursor: Cursor, main_file: str):
        """Extract typedef."""
        name = cursor.spelling
        if not name:
            return

        file_id = self._get_or_create_file(main_file)
        loc = cursor.location

        # Get underlying type
        underlying = cursor.underlying_typedef_type
        underlying_spelling = underlying.spelling if underlying else "unknown"

        # Resolve through typedef chain
        resolved = underlying
        while resolved and resolved.kind == TypeKind.TYPEDEF:
            decl = resolved.get_declaration()
            if decl:
                resolved = decl.underlying_typedef_type
            else:
                break
        resolved_spelling = resolved.spelling if resolved else underlying_spelling

        # Insert symbol
        cur = self.conn.execute(
            """INSERT INTO symbols
               (name, kind, file_id, line, column, is_definition, is_static)
               VALUES (?, 'typedef', ?, ?, ?, 1, 0)""",
            (name, file_id, loc.line, loc.column)
        )
        symbol_id = cur.lastrowid

        # Insert type details with resolved underlying type
        self.conn.execute(
            """INSERT INTO types
               (symbol_id, kind, underlying_type, is_anonymous)
               VALUES (?, 'typedef', ?, 0)""",
            (symbol_id, resolved_spelling)
        )

    # =========================================================================
    # VARIABLE EXTRACTION
    # =========================================================================

    def _extract_global_variable(self, cursor: Cursor, main_file: str):
        """Extract global variable declaration."""
        name = cursor.spelling
        if not name:
            return

        file_id = self._get_or_create_file(main_file)
        loc = cursor.location

        var_type = cursor.type.spelling if cursor.type else "unknown"
        is_static = cursor.storage_class == StorageClass.STATIC
        is_def = cursor.is_definition()

        # Check for const/volatile
        is_const = cursor.type.is_const_qualified() if cursor.type else False
        is_volatile = cursor.type.is_volatile_qualified() if cursor.type else False

        linkage = self._get_linkage(cursor)
        storage = self._get_storage_class(cursor)

        # Insert symbol
        cur = self.conn.execute(
            """INSERT INTO symbols
               (name, kind, file_id, line, column, is_definition, is_static,
                storage_class, linkage)
               VALUES (?, 'variable', ?, ?, ?, ?, ?, ?, ?)""",
            (name, file_id, loc.line, loc.column, int(is_def),
             int(is_static), storage, linkage)
        )
        symbol_id = cur.lastrowid

        # Insert variable details
        self.conn.execute(
            """INSERT INTO variables
               (symbol_id, type, is_const, is_volatile)
               VALUES (?, ?, ?, ?)""",
            (symbol_id, var_type, int(is_const), int(is_volatile))
        )

    # =========================================================================
    # MACRO EXTRACTION
    # =========================================================================

    def _extract_macros(self, tu: TranslationUnit, main_file: str):
        """Extract macro definitions from preprocessing."""
        file_id = self._get_or_create_file(main_file)
        main_resolved = str(Path(main_file).resolve())

        # Walk through all cursors looking for macro definitions
        for cursor in tu.cursor.walk_preorder():
            if cursor.kind == CursorKind.MACRO_DEFINITION:
                loc = cursor.location
                if not loc.file:
                    continue

                cursor_file = str(Path(loc.file.name).resolve())
                if cursor_file != main_resolved:
                    continue

                name = cursor.spelling
                if not name:
                    continue

                # Get the definition by looking at tokens
                tokens = list(cursor.get_tokens())
                if not tokens:
                    continue

                # First token is the macro name
                # For function-like macros, parameters follow
                is_function_like = False
                param_names = None
                definition = ""

                if len(tokens) > 1:
                    # Check if it's function-like (has parentheses right after name)
                    token_texts = [t.spelling for t in tokens]
                    name_idx = 0

                    if len(token_texts) > 1 and token_texts[1] == "(":
                        is_function_like = True
                        # Find the closing paren
                        paren_depth = 0
                        param_end = 1
                        for i, t in enumerate(token_texts[1:], 1):
                            if t == "(":
                                paren_depth += 1
                            elif t == ")":
                                paren_depth -= 1
                                if paren_depth == 0:
                                    param_end = i
                                    break

                        # Extract parameter names
                        param_tokens = token_texts[2:param_end]
                        param_names = [p for p in param_tokens if p not in (",", "...")]

                        # Definition is everything after the params
                        definition = " ".join(token_texts[param_end + 1:])
                    else:
                        # Object-like macro
                        definition = " ".join(token_texts[1:])

                self.conn.execute(
                    """INSERT INTO macros
                       (name, file_id, line, definition, is_function_like,
                        param_names, is_builtin)
                       VALUES (?, ?, ?, ?, ?, ?, 0)""",
                    (name, file_id, loc.line, definition, int(is_function_like),
                     ",".join(param_names) if param_names else None)
                )

    # =========================================================================
    # INCLUDE EXTRACTION
    # =========================================================================

    def _extract_includes(self, tu: TranslationUnit, main_file: str):
        """Extract #include directives."""
        file_id = self._get_or_create_file(main_file)
        main_resolved = str(Path(main_file).resolve())

        for cursor in tu.cursor.walk_preorder():
            if cursor.kind == CursorKind.INCLUSION_DIRECTIVE:
                loc = cursor.location
                if not loc.file:
                    continue

                cursor_file = str(Path(loc.file.name).resolve())
                if cursor_file != main_resolved:
                    continue

                included_file = cursor.get_included_file()
                included_path = cursor.spelling  # As written in source
                resolved_path = included_file.name if included_file else None

                # Determine if system include
                # Heuristic: check if it's in a system path or uses <>
                is_system = False
                if resolved_path:
                    is_system = "/usr/" in resolved_path or "include" in resolved_path

                self.conn.execute(
                    """INSERT INTO includes
                       (file_id, included_path, resolved_path, line, is_system)
                       VALUES (?, ?, ?, ?, ?)""",
                    (file_id, included_path, resolved_path, loc.line, int(is_system))
                )

    # =========================================================================
    # DOCUMENTATION EXTRACTION
    # =========================================================================

    def _extract_documentation(self, symbol_id: int, raw_comment: str):
        """Parse Doxygen-style comment and extract structured documentation."""
        if not raw_comment:
            return

        brief = None
        detailed = []
        return_doc = None
        params = {}

        # Simple Doxygen parsing
        lines = raw_comment.split("\n")
        current_section = "brief"
        current_param = None

        for line in lines:
            # Strip comment markers
            line = re.sub(r"^[\s*/]*", "", line)
            line = line.strip()

            if not line:
                if current_section == "brief" and brief:
                    current_section = "detailed"
                continue

            # Check for Doxygen commands
            if line.startswith("@brief") or line.startswith("\\brief"):
                brief = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
                current_section = "brief"
            elif line.startswith("@param") or line.startswith("\\param"):
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    # Check for [in], [out], [in,out] direction
                    direction = None
                    param_name = parts[1]
                    desc_start = 2

                    if param_name.startswith("["):
                        direction = param_name.strip("[]")
                        if len(parts) >= 3:
                            param_name = parts[2]
                            desc_start = 3

                    desc = " ".join(parts[desc_start:]) if len(parts) > desc_start else ""
                    params[param_name] = {"description": desc, "direction": direction}
                    current_param = param_name
                current_section = "param"
            elif line.startswith("@return") or line.startswith("\\return"):
                return_doc = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
                current_section = "return"
            elif line.startswith("@") or line.startswith("\\"):
                # Other command, switch to detailed
                current_section = "detailed"
                detailed.append(line)
            else:
                # Continuation of current section
                if current_section == "brief":
                    if brief:
                        brief += " " + line
                    else:
                        brief = line
                elif current_section == "detailed":
                    detailed.append(line)
                elif current_section == "param" and current_param:
                    params[current_param]["description"] += " " + line
                elif current_section == "return":
                    return_doc += " " + line

        # Insert documentation
        cur = self.conn.execute(
            """INSERT INTO docs
               (symbol_id, raw_comment, brief, detailed, return_doc)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol_id, raw_comment, brief,
             "\n".join(detailed) if detailed else None, return_doc)
        )
        doc_id = cur.lastrowid

        # Insert parameter docs
        for param_name, param_info in params.items():
            self.conn.execute(
                """INSERT INTO param_docs
                   (doc_id, param_name, description, direction)
                   VALUES (?, ?, ?, ?)""",
                (doc_id, param_name, param_info["description"],
                 param_info["direction"])
            )

    # =========================================================================
    # POST-PROCESSING
    # =========================================================================

    def _resolve_call_graph(self):
        """
        Resolve callee_id in calls table by matching callee_name to functions.
        Run after all files are extracted.
        """
        self.conn.execute("""
            UPDATE calls
            SET callee_id = (
                SELECT f.symbol_id
                FROM functions f
                JOIN symbols s ON s.id = f.symbol_id
                WHERE s.name = calls.callee_name AND s.is_definition = 1
                LIMIT 1
            )
            WHERE callee_id IS NULL
        """)
        self.conn.commit()

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_linkage(self, cursor: Cursor) -> str:
        """Get linkage kind as string."""
        linkage = cursor.linkage
        if linkage == LinkageKind.EXTERNAL:
            return "external"
        elif linkage == LinkageKind.INTERNAL:
            return "internal"
        elif linkage == LinkageKind.NO_LINKAGE:
            return "none"
        return "unknown"

    def _get_storage_class(self, cursor: Cursor) -> str:
        """Get storage class as string."""
        sc = cursor.storage_class
        if sc == StorageClass.STATIC:
            return "static"
        elif sc == StorageClass.EXTERN:
            return "extern"
        elif sc == StorageClass.REGISTER:
            return "register"
        return "none"

    def close(self):
        """Close database connection."""
        self.conn.close()


# =============================================================================
# CONVENIENCE WRAPPER
# =============================================================================

def extract_workspace(
    workspace_root: str,
    db_path: str = "codebase.db",
    compile_commands: str = "compile_commands.json"
):
    """
    One-shot extraction of a workspace.

    Usage:
        extract_workspace("/path/to/workspace")
    """
    extractor = ClangExtractor(db_path, workspace_root)
    cc_path = Path(workspace_root) / compile_commands
    extractor.extract_all(str(cc_path))
    extractor.close()
    print(f"Database written to {db_path}")


def update_workspace(
    workspace_root: str,
    db_path: str = "codebase.db",
    compile_commands: str = "compile_commands.json"
):
    """
    Incremental update of changed files.

    Usage:
        update_workspace("/path/to/workspace")
    """
    extractor = ClangExtractor(db_path, workspace_root)
    cc_path = Path(workspace_root) / compile_commands

    stale = extractor.get_stale_files(str(cc_path))
    if not stale:
        print("No files changed.")
        extractor.close()
        return

    print(f"Updating {len(stale)} changed files...")
    extractor.extract_files(stale, str(cc_path))
    extractor.close()
    print("Update complete.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <workspace_root> [--update]")
        sys.exit(1)

    workspace = sys.argv[1]
    if "--update" in sys.argv:
        update_workspace(workspace)
    else:
        extract_workspace(workspace)
