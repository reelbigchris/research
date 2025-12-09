-- schema.sql
-- Extraction metadata
CREATE TABLE extraction_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Populate with: 'extracted_at', 'workspace_root', 'clang_version'

-- Track file state for incremental updates
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    hash TEXT,  -- optional, for more reliable change detection
    last_extracted REAL NOT NULL
);
CREATE INDEX idx_files_path ON files(path);

-- Core symbol table
CREATE TABLE symbols (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,  -- function, variable, typedef, struct, union, enum, macro, enum_constant
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    column INTEGER,
    end_line INTEGER,
    end_column INTEGER,
    is_definition INTEGER NOT NULL DEFAULT 0,
    is_static INTEGER NOT NULL DEFAULT 0,
    storage_class TEXT,  -- extern, static, register, none
    linkage TEXT  -- external, internal, none
);
CREATE INDEX idx_symbols_name ON symbols(name);
CREATE INDEX idx_symbols_kind ON symbols(kind);
CREATE INDEX idx_symbols_file ON symbols(file_id);
CREATE INDEX idx_symbols_name_kind ON symbols(name, kind);

-- Function-specific details
CREATE TABLE functions (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    return_type TEXT NOT NULL,
    signature TEXT NOT NULL,  -- full signature for display
    is_variadic INTEGER NOT NULL DEFAULT 0,
    is_inline INTEGER NOT NULL DEFAULT 0,
    cyclomatic_complexity INTEGER  -- if you want to compute it
);

-- Function parameters
CREATE TABLE parameters (
    id INTEGER PRIMARY KEY,
    function_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT,
    type TEXT NOT NULL
);
CREATE INDEX idx_params_function ON parameters(function_id);

-- Function local variables
CREATE TABLE locals (
    id INTEGER PRIMARY KEY,
    function_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    line INTEGER,
    scope_depth INTEGER  -- nesting level
);
CREATE INDEX idx_locals_function ON locals(function_id);

-- Type details (structs, unions, enums, typedefs)
CREATE TABLE types (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,  -- struct, union, enum, typedef
    underlying_type TEXT,  -- for typedefs: fully resolved type
    size_bytes INTEGER,
    alignment INTEGER,
    is_anonymous INTEGER NOT NULL DEFAULT 0
);

-- Struct/union fields
CREATE TABLE fields (
    id INTEGER PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES types(symbol_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    offset_bits INTEGER,
    size_bits INTEGER,
    is_bitfield INTEGER NOT NULL DEFAULT 0,
    bitfield_width INTEGER,
    position INTEGER NOT NULL  -- field order
);
CREATE INDEX idx_fields_type ON fields(type_id);

-- Enum constants
CREATE TABLE enum_constants (
    id INTEGER PRIMARY KEY,
    type_id INTEGER NOT NULL REFERENCES types(symbol_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value INTEGER,
    position INTEGER NOT NULL
);
CREATE INDEX idx_enum_constants_type ON enum_constants(type_id);
CREATE INDEX idx_enum_constants_name ON enum_constants(name);

-- Variable-specific details (globals)
CREATE TABLE variables (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    is_const INTEGER NOT NULL DEFAULT 0,
    is_volatile INTEGER NOT NULL DEFAULT 0,
    initial_value TEXT  -- if determinable
);

-- Macros (captured during preprocessing)
CREATE TABLE macros (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
    line INTEGER,
    definition TEXT,  -- the replacement text
    is_function_like INTEGER NOT NULL DEFAULT 0,
    param_names TEXT,  -- comma-separated
    is_builtin INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_macros_name ON macros(name);
CREATE INDEX idx_macros_file ON macros(file_id);

-- Call graph
CREATE TABLE calls (
    id INTEGER PRIMARY KEY,
    caller_id INTEGER NOT NULL REFERENCES functions(symbol_id) ON DELETE CASCADE,
    callee_id INTEGER REFERENCES functions(symbol_id) ON DELETE SET NULL,  -- null for unresolved/external
    callee_name TEXT NOT NULL,  -- always store name for external/unresolved calls
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    column INTEGER,
    is_indirect INTEGER NOT NULL DEFAULT 0  -- function pointer
);
CREATE INDEX idx_calls_caller ON calls(caller_id);
CREATE INDEX idx_calls_callee ON calls(callee_id);
CREATE INDEX idx_calls_callee_name ON calls(callee_name);

-- Cross-references
CREATE TABLE refs (
    id INTEGER PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    column INTEGER,
    kind TEXT NOT NULL,  -- read, write, addr, call, type_ref
    context_function_id INTEGER REFERENCES functions(symbol_id) ON DELETE SET NULL  -- what function contains this ref
);
CREATE INDEX idx_refs_symbol ON refs(symbol_id);
CREATE INDEX idx_refs_file ON refs(file_id);
CREATE INDEX idx_refs_context ON refs(context_function_id);

-- Include graph
CREATE TABLE includes (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    included_path TEXT NOT NULL,  -- as written in #include
    resolved_path TEXT,  -- actual file path
    line INTEGER NOT NULL,
    is_system INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_includes_file ON includes(file_id);
CREATE INDEX idx_includes_resolved ON includes(resolved_path);

-- Documentation (Doxygen comments)
CREATE TABLE docs (
    id INTEGER PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    raw_comment TEXT,
    brief TEXT,
    detailed TEXT,
    return_doc TEXT
);
CREATE INDEX idx_docs_symbol ON docs(symbol_id);

-- Documentation for parameters
CREATE TABLE param_docs (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
    param_name TEXT NOT NULL,
    description TEXT,
    direction TEXT  -- in, out, inout
);
CREATE INDEX idx_param_docs_doc ON param_docs(doc_id);

-- Source text cache (optional, for showing code without file access)
CREATE TABLE source_cache (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    content TEXT NOT NULL
);
