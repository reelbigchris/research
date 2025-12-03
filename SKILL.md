---
name: ghidra-firmware-analysis
description: Query pre-processed Ghidra firmware analysis databases for embedded firmware reverse engineering. Use when the user asks about firmware binaries, function lookups, cross-references, call graphs, symbol resolution, disassembly, or binary patching tasks. Supports queries like "find function at address", "show callers of X", "get disassembly for function Y", "what references this address", or "help me patch this firmware". Each firmware project has a corresponding SQLite database in /mnt/user-data/uploads/firmware-dbs/.
---

# Ghidra Firmware Analysis Skill

Query pre-processed Ghidra analysis databases for firmware reverse engineering tasks.

## Database Location

Firmware databases are stored at: `/mnt/user-data/uploads/firmware-dbs/`

Each database is named `{project_name}.db` corresponding to the original Ghidra project.

**First step**: List available databases to identify which firmware to query:
```bash
ls -la /mnt/user-data/uploads/firmware-dbs/*.db
```

## Database Schema

See `references/schema.md` for complete table definitions and indexes.

### Core Tables
- `metadata` - Project info, architecture, endianness, base address
- `functions` - Function names, addresses, sizes, signatures
- `symbols` - All symbols (functions, labels, data)
- `xrefs` - Cross-references (calls, jumps, data reads/writes)
- `strings` - Defined strings with addresses
- `comments` - User and auto-generated comments
- `segments` - Memory segments with permissions
- `data_types` - Struct/enum/typedef definitions
- `function_bytes` - Raw bytes for each function (binary BLOB)
- `function_disassembly` - Pre-rendered disassembly text

## Common Query Patterns

### Find a function by name
```sql
SELECT entry_address, size, signature FROM functions WHERE name LIKE '%uart%';
```

### Get function at specific address
```sql
SELECT * FROM functions WHERE entry_address = 0x08001234;
-- Or find function containing an address:
SELECT * FROM functions 
WHERE entry_address <= 0x08001234 
  AND entry_address + size > 0x08001234;
```

### Get callers of a function
```sql
SELECT f.name, x.from_address 
FROM xrefs x
JOIN functions f ON x.from_address BETWEEN f.entry_address AND f.entry_address + f.size - 1
WHERE x.to_address = (SELECT entry_address FROM functions WHERE name = 'target_func')
  AND x.ref_type = 'call';
```

### Get callees from a function
```sql
SELECT DISTINCT f2.name, x.to_address
FROM functions f1
JOIN xrefs x ON x.from_address BETWEEN f1.entry_address AND f1.entry_address + f1.size - 1
JOIN functions f2 ON x.to_address = f2.entry_address
WHERE f1.name = 'source_func' AND x.ref_type = 'call';
```

### Get disassembly for a function
```sql
SELECT disassembly FROM function_disassembly 
WHERE function_id = (SELECT id FROM functions WHERE name = 'main');
```

### Get raw bytes for patching
```sql
SELECT hex(bytes) FROM function_bytes 
WHERE function_id = (SELECT id FROM functions WHERE name = 'check_license');
```

### Find strings containing text
```sql
SELECT address, value FROM strings WHERE value LIKE '%password%';
```

### Find data references to an address
```sql
SELECT * FROM xrefs WHERE to_address = 0x20000100 AND ref_type IN ('data_read', 'data_write');
```

## Query Script

For complex analysis, use `scripts/query_firmware.py`:

```bash
python scripts/query_firmware.py <db_path> "<sql_query>"
python scripts/query_firmware.py <db_path> --function <name_or_addr> --disasm
python scripts/query_firmware.py <db_path> --function <name_or_addr> --bytes
python scripts/query_firmware.py <db_path> --callers <function_name>
python scripts/query_firmware.py <db_path> --callees <function_name>
python scripts/query_firmware.py <db_path> --xrefs-to <address>
python scripts/query_firmware.py <db_path> --xrefs-from <address>
```

## Workflow for Patching Tasks

1. **Identify target**: Query functions/strings to find patch location
2. **Get context**: Retrieve disassembly and surrounding xrefs
3. **Get bytes**: Extract raw bytes from `function_bytes`
4. **Plan patch**: Analyze instruction encoding (check `metadata` for architecture)
5. **Validate**: Verify patch doesn't break xrefs or function boundaries

## Multi-Database Queries

When comparing across firmware versions:
```python
import sqlite3

def compare_function(name, db1_path, db2_path):
    """Compare function bytes across two firmware versions."""
    conn1 = sqlite3.connect(db1_path)
    conn2 = sqlite3.connect(db2_path)
    
    q = """SELECT hex(fb.bytes) FROM function_bytes fb
           JOIN functions f ON fb.function_id = f.id
           WHERE f.name = ?"""
    
    bytes1 = conn1.execute(q, (name,)).fetchone()
    bytes2 = conn2.execute(q, (name,)).fetchone()
    
    return bytes1 == bytes2, bytes1, bytes2
```

## Notes

- Addresses are stored as integers; use `hex()` for display
- Function sizes may be 0 for thunks or unanalyzed code
- The `is_thunk` flag identifies wrapper functions
- Cross-reference types: `call`, `jump`, `data_read`, `data_write`, `offset`
- Comments include type: `eol`, `pre`, `post`, `plate`
