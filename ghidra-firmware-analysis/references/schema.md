# Firmware Analysis Database Schema

Complete SQLite schema for Ghidra firmware analysis exports.

## Table: metadata

Project-level information about the analyzed binary.

```sql
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**Standard keys:**
- `project_name` - Original Ghidra project name
- `program_name` - Binary filename
- `architecture` - Processor architecture (e.g., `ARM:LE:32:Cortex`)
- `compiler` - Compiler spec ID
- `endianness` - `little` or `big`
- `pointer_size` - Pointer size in bytes (4 or 8)
- `base_address` - Image base address (hex string)
- `min_address` - Lowest defined address
- `max_address` - Highest defined address
- `export_date` - ISO 8601 timestamp of export
- `ghidra_version` - Ghidra version used for analysis
- `export_script_version` - Version of the export script

## Table: segments

Memory segments/sections with permissions.

```sql
CREATE TABLE segments (
    id INTEGER PRIMARY KEY,
    name TEXT,
    start_address INTEGER,
    end_address INTEGER,
    size INTEGER,
    permissions TEXT,      -- e.g., 'rwx', 'r-x', 'rw-'
    is_initialized INTEGER -- 1 if initialized, 0 if not
);

CREATE INDEX idx_segments_addr ON segments(start_address, end_address);
```

## Table: functions

All defined functions in the binary.

```sql
CREATE TABLE functions (
    id INTEGER PRIMARY KEY,
    name TEXT,
    entry_address INTEGER UNIQUE,
    size INTEGER,              -- Function body size in bytes
    signature TEXT,            -- Full function signature
    calling_convention TEXT,   -- e.g., '__stdcall', '__cdecl'
    return_type TEXT,
    is_thunk INTEGER,          -- 1 if function is a thunk/trampoline
    is_external INTEGER,       -- 1 if external/imported
    namespace TEXT,            -- Namespace path (e.g., 'MyClass')
    comment TEXT               -- Function-level comment
);

CREATE INDEX idx_functions_name ON functions(name);
CREATE INDEX idx_functions_addr ON functions(entry_address);
```

## Table: symbols

All symbols including functions, labels, and data.

```sql
CREATE TABLE symbols (
    id INTEGER PRIMARY KEY,
    name TEXT,
    address INTEGER,
    type TEXT,           -- 'function', 'label', 'data', 'external'
    namespace TEXT,
    source TEXT,         -- 'user', 'analysis', 'imported', 'default'
    is_primary INTEGER   -- 1 if primary symbol at this address
);

CREATE INDEX idx_symbols_name ON symbols(name);
CREATE INDEX idx_symbols_addr ON symbols(address);
CREATE INDEX idx_symbols_type ON symbols(type);
```

## Table: xrefs

Cross-references between addresses.

```sql
CREATE TABLE xrefs (
    id INTEGER PRIMARY KEY,
    from_address INTEGER,
    to_address INTEGER,
    ref_type TEXT,       -- 'call', 'jump', 'data_read', 'data_write', 'offset'
    is_call INTEGER,     -- 1 for call references
    operand_index INTEGER -- Which operand contains the reference (-1 for mnemonic)
);

CREATE INDEX idx_xrefs_to ON xrefs(to_address);
CREATE INDEX idx_xrefs_from ON xrefs(from_address);
CREATE INDEX idx_xrefs_type ON xrefs(ref_type);
```

**Reference types:**
- `call` - Function call (CALL instruction or equivalent)
- `jump` - Control flow jump (conditional or unconditional)
- `data_read` - Memory read reference
- `data_write` - Memory write reference
- `offset` - Offset/pointer reference (address-of)

## Table: strings

Defined string data in the binary.

```sql
CREATE TABLE strings (
    id INTEGER PRIMARY KEY,
    address INTEGER UNIQUE,
    value TEXT,
    length INTEGER,
    encoding TEXT,       -- 'ascii', 'utf-8', 'utf-16-le', 'utf-16-be'
    is_terminated INTEGER -- 1 if null-terminated
);

CREATE INDEX idx_strings_value ON strings(value);
CREATE INDEX idx_strings_addr ON strings(address);
```

## Table: comments

All comments from Ghidra analysis.

```sql
CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    address INTEGER,
    comment_type TEXT,   -- 'eol', 'pre', 'post', 'plate', 'repeatable'
    text TEXT
);

CREATE INDEX idx_comments_addr ON comments(address);
```

**Comment types:**
- `eol` - End-of-line comment
- `pre` - Pre-instruction comment
- `post` - Post-instruction comment
- `plate` - Plate comment (function header)
- `repeatable` - Repeatable comment

## Table: data_types

User-defined and imported data types.

```sql
CREATE TABLE data_types (
    id INTEGER PRIMARY KEY,
    name TEXT,
    category TEXT,       -- Category path, e.g., '/structs'
    kind TEXT,           -- 'struct', 'union', 'enum', 'typedef', 'function_def'
    size INTEGER,
    alignment INTEGER,
    definition TEXT      -- JSON representation of fields/values
);

CREATE INDEX idx_data_types_name ON data_types(name);
CREATE INDEX idx_data_types_kind ON data_types(kind);
```

**Definition JSON format for structs:**
```json
{
  "fields": [
    {"name": "field1", "type": "uint32_t", "offset": 0, "size": 4},
    {"name": "field2", "type": "char[16]", "offset": 4, "size": 16}
  ]
}
```

**Definition JSON format for enums:**
```json
{
  "values": [
    {"name": "VALUE_A", "value": 0},
    {"name": "VALUE_B", "value": 1}
  ]
}
```

## Table: function_bytes

Raw bytes for each function (for patching).

```sql
CREATE TABLE function_bytes (
    function_id INTEGER PRIMARY KEY REFERENCES functions(id),
    bytes BLOB,
    start_address INTEGER,
    size INTEGER
);
```

**Usage:**
```sql
-- Get bytes as hex string
SELECT hex(bytes) FROM function_bytes WHERE function_id = 42;

-- Get specific byte range
SELECT hex(substr(bytes, 5, 10)) FROM function_bytes WHERE function_id = 42;
```

## Table: function_disassembly

Pre-rendered disassembly for each function.

```sql
CREATE TABLE function_disassembly (
    function_id INTEGER PRIMARY KEY REFERENCES functions(id),
    disassembly TEXT,    -- Full disassembly listing
    instruction_count INTEGER
);
```

**Disassembly format:**
```
0x08001000: 80 b5        push    {r7, lr}
0x08001002: 00 af        add     r7, sp, #0
0x08001004: 02 46        mov     r2, r0
...
```

## Table: call_graph

Materialized call graph for efficient traversal.

```sql
CREATE TABLE call_graph (
    caller_id INTEGER REFERENCES functions(id),
    callee_id INTEGER REFERENCES functions(id),
    call_count INTEGER,  -- Number of call sites
    PRIMARY KEY (caller_id, callee_id)
);

CREATE INDEX idx_call_graph_callee ON call_graph(callee_id);
```

## Table: imports

Imported functions from external libraries.

```sql
CREATE TABLE imports (
    id INTEGER PRIMARY KEY,
    name TEXT,
    library TEXT,        -- Library name if known
    address INTEGER,     -- Thunk/stub address
    ordinal INTEGER      -- Import ordinal if applicable
);

CREATE INDEX idx_imports_name ON imports(name);
CREATE INDEX idx_imports_lib ON imports(library);
```

## Table: exports

Exported symbols from the binary.

```sql
CREATE TABLE exports (
    id INTEGER PRIMARY KEY,
    name TEXT,
    address INTEGER,
    ordinal INTEGER
);

CREATE INDEX idx_exports_name ON exports(name);
```

## Common Query Recipes

### Find all callers (N levels deep)
```sql
WITH RECURSIVE callers AS (
    SELECT caller_id, callee_id, 1 as depth
    FROM call_graph
    WHERE callee_id = (SELECT id FROM functions WHERE name = 'target')
    
    UNION ALL
    
    SELECT cg.caller_id, cg.callee_id, c.depth + 1
    FROM call_graph cg
    JOIN callers c ON cg.callee_id = c.caller_id
    WHERE c.depth < 3  -- Limit depth
)
SELECT DISTINCT f.name, f.entry_address, c.depth
FROM callers c
JOIN functions f ON c.caller_id = f.id
ORDER BY c.depth, f.name;
```

### Find functions by size range
```sql
SELECT name, entry_address, size 
FROM functions 
WHERE size BETWEEN 100 AND 500
ORDER BY size DESC;
```

### Find functions with specific string references
```sql
SELECT DISTINCT f.name, f.entry_address, s.value
FROM functions f
JOIN xrefs x ON x.from_address BETWEEN f.entry_address AND f.entry_address + f.size - 1
JOIN strings s ON x.to_address = s.address
WHERE s.value LIKE '%error%'
ORDER BY f.name;
```

### Get function with all its metadata
```sql
SELECT 
    f.*,
    hex(fb.bytes) as hex_bytes,
    fd.disassembly,
    fd.instruction_count
FROM functions f
LEFT JOIN function_bytes fb ON f.id = fb.function_id
LEFT JOIN function_disassembly fd ON f.id = fd.function_id
WHERE f.name = 'main';
```

### Find unreferenced functions
```sql
SELECT f.name, f.entry_address
FROM functions f
WHERE f.id NOT IN (SELECT DISTINCT callee_id FROM call_graph)
  AND f.is_external = 0
  AND f.name NOT LIKE 'entry%';
```

### Compare function signatures across databases
For comparing firmware versions, use a Python script to attach multiple databases and join on function names.
