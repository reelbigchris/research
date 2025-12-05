# Export Ghidra analysis to SQLite database
# Run with: analyzeHeadless <project_location> <project_name> -process -postScript export_to_sqlite.py <output_db_path>
# Or for server: analyzeHeadless ghidra://<server>/<repo> -process -postScript export_to_sqlite.py <output_db_path>
#
# @category Export
# @author Firmware Analysis Skill

from ghidra.program.model.listing import CodeUnit
from ghidra.program.model.symbol import SourceType, SymbolType
from ghidra.program.model.mem import MemoryAccessException
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from binascii import hexlify
import sqlite3
import json
import os
import sys
from datetime import datetime

# Get output path from script arguments
args = getScriptArgs()
if len(args) < 1:
    print("ERROR: No output database path specified")
    print("Usage: -postScript export_to_sqlite.py <output_db_path>")
    sys.exit(1)

OUTPUT_DB = args[0]

# Script version for tracking
SCRIPT_VERSION = "1.0.0"


def create_schema(conn):
    """Create all database tables."""
    cursor = conn.cursor()
    
    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Segments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY,
            name TEXT,
            start_address INTEGER,
            end_address INTEGER,
            size INTEGER,
            permissions TEXT,
            is_initialized INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_segments_addr ON segments(start_address, end_address)")
    
    # Functions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY,
            name TEXT,
            entry_address INTEGER UNIQUE,
            size INTEGER,
            signature TEXT,
            calling_convention TEXT,
            return_type TEXT,
            is_thunk INTEGER,
            is_external INTEGER,
            namespace TEXT,
            comment TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_functions_addr ON functions(entry_address)")
    
    # Symbols table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            name TEXT,
            address INTEGER,
            type TEXT,
            namespace TEXT,
            source TEXT,
            is_primary INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_addr ON symbols(address)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(type)")
    
    # Cross-references table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS xrefs (
            id INTEGER PRIMARY KEY,
            from_address INTEGER,
            to_address INTEGER,
            ref_type TEXT,
            is_call INTEGER,
            operand_index INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_xrefs_to ON xrefs(to_address)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_xrefs_from ON xrefs(from_address)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_xrefs_type ON xrefs(ref_type)")
    
    # Strings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strings (
            id INTEGER PRIMARY KEY,
            address INTEGER UNIQUE,
            value TEXT,
            length INTEGER,
            encoding TEXT,
            is_terminated INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_strings_value ON strings(value)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_strings_addr ON strings(address)")
    
    # Comments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY,
            address INTEGER,
            comment_type TEXT,
            text TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_addr ON comments(address)")
    
    # Data types table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_types (
            id INTEGER PRIMARY KEY,
            name TEXT,
            category TEXT,
            kind TEXT,
            size INTEGER,
            alignment INTEGER,
            definition TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_types_name ON data_types(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_types_kind ON data_types(kind)")
    
    # Function bytes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS function_bytes (
            function_id INTEGER PRIMARY KEY,
            bytes BLOB,
            start_address INTEGER,
            size INTEGER
        )
    """)
    
    # Function disassembly table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS function_disassembly (
            function_id INTEGER PRIMARY KEY,
            disassembly TEXT,
            instruction_count INTEGER
        )
    """)
    
    # Call graph table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_graph (
            caller_id INTEGER,
            callee_id INTEGER,
            call_count INTEGER,
            PRIMARY KEY (caller_id, callee_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_graph_callee ON call_graph(callee_id)")
    
    # Imports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY,
            name TEXT,
            library TEXT,
            address INTEGER,
            ordinal INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(name)")
    
    # Exports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exports (
            id INTEGER PRIMARY KEY,
            name TEXT,
            address INTEGER,
            ordinal INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exports_name ON exports(name)")
    
    conn.commit()


def export_metadata(conn, program):
    """Export program metadata."""
    cursor = conn.cursor()
    
    lang = program.getLanguage()
    
    metadata = {
        'project_name': str(currentProgram.getDomainFile().getProjectLocator().getName()) if currentProgram.getDomainFile() else 'unknown',
        'program_name': program.getName(),
        'architecture': str(lang.getLanguageID()),
        'compiler': str(program.getCompilerSpec().getCompilerSpecID()),
        'endianness': 'big' if lang.isBigEndian() else 'little',
        'pointer_size': str(lang.getDefaultSpace().getPointerSize()),
        'base_address': hex(program.getImageBase().getOffset()),
        'min_address': hex(program.getMinAddress().getOffset()) if program.getMinAddress() else '0x0',
        'max_address': hex(program.getMaxAddress().getOffset()) if program.getMaxAddress() else '0x0',
        'export_date': datetime.now().isoformat(),
        'ghidra_version': getGhidraVersion(),
        'export_script_version': SCRIPT_VERSION
    }
    
    for key, value in metadata.items():
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    print("Exported metadata")


def export_segments(conn, program):
    """Export memory segments."""
    cursor = conn.cursor()
    memory = program.getMemory()
    
    for block in memory.getBlocks():
        perms = ''
        perms += 'r' if block.isRead() else '-'
        perms += 'w' if block.isWrite() else '-'
        perms += 'x' if block.isExecute() else '-'
        
        cursor.execute("""
            INSERT INTO segments (name, start_address, end_address, size, permissions, is_initialized)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            block.getName(),
            block.getStart().getOffset(),
            block.getEnd().getOffset(),
            block.getSize(),
            perms,
            1 if block.isInitialized() else 0
        ))
    
    conn.commit()
    print("Exported %d segments" % len(list(memory.getBlocks())))


def export_functions(conn, program):
    """Export all functions with their signatures."""
    cursor = conn.cursor()
    fm = program.getFunctionManager()
    
    count = 0
    for func in fm.getFunctions(True):
        ns = func.getParentNamespace()
        namespace = ns.getName(True) if ns and not ns.isGlobal() else None
        
        # Get plate comment as function comment
        listing = program.getListing()
        plate_comment = None
        cu = listing.getCodeUnitAt(func.getEntryPoint())
        if cu:
            plate_comment = cu.getComment(CodeUnit.PLATE_COMMENT)
        
        cursor.execute("""
            INSERT INTO functions (name, entry_address, size, signature, calling_convention,
                                   return_type, is_thunk, is_external, namespace, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            func.getName(),
            func.getEntryPoint().getOffset(),
            func.getBody().getNumAddresses(),
            func.getPrototypeString(False, False),
            func.getCallingConventionName(),
            str(func.getReturnType()),
            1 if func.isThunk() else 0,
            1 if func.isExternal() else 0,
            namespace,
            plate_comment
        ))
        count += 1
    
    conn.commit()
    print("Exported %d functions" % count)


def export_symbols(conn, program):
    """Export all symbols."""
    cursor = conn.cursor()
    st = program.getSymbolTable()
    
    count = 0
    for sym in st.getAllSymbols(True):
        sym_type = str(sym.getSymbolType())
        if sym_type == 'Function':
            type_str = 'function'
        elif sym_type == 'Label':
            type_str = 'label'
        elif sym_type == 'Class' or sym_type == 'Namespace':
            continue  # Skip namespace symbols
        else:
            type_str = 'data'
        
        source = str(sym.getSource())
        if source == 'USER_DEFINED':
            source_str = 'user'
        elif source == 'ANALYSIS':
            source_str = 'analysis'
        elif source == 'IMPORTED':
            source_str = 'imported'
        else:
            source_str = 'default'
        
        ns = sym.getParentNamespace()
        namespace = ns.getName(True) if ns and not ns.isGlobal() else None
        
        cursor.execute("""
            INSERT INTO symbols (name, address, type, namespace, source, is_primary)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            sym.getName(),
            sym.getAddress().getOffset(),
            type_str,
            namespace,
            source_str,
            1 if sym.isPrimary() else 0
        ))
        count += 1
    
    conn.commit()
    print("Exported %d symbols" % count)


def export_xrefs(conn, program):
    """Export all cross-references."""
    cursor = conn.cursor()
    rm = program.getReferenceManager()
    
    count = 0
    for ref_iter in rm.getReferenceIterator(program.getMinAddress()):
        ref = ref_iter
        
        ref_type_obj = ref.getReferenceType()
        if ref_type_obj.isCall():
            ref_type = 'call'
        elif ref_type_obj.isJump():
            ref_type = 'jump'
        elif ref_type_obj.isRead():
            ref_type = 'data_read'
        elif ref_type_obj.isWrite():
            ref_type = 'data_write'
        elif ref_type_obj.isData():
            ref_type = 'offset'
        else:
            ref_type = 'other'
        
        cursor.execute("""
            INSERT INTO xrefs (from_address, to_address, ref_type, is_call, operand_index)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ref.getFromAddress().getOffset(),
            ref.getToAddress().getOffset(),
            ref_type,
            1 if ref_type_obj.isCall() else 0,
            ref.getOperandIndex()
        ))
        count += 1
        
        # Commit in batches
        if count % 10000 == 0:
            conn.commit()
            print("  ... %d xrefs" % count)
    
    conn.commit()
    print("Exported %d cross-references" % count)


def export_strings(conn, program):
    """Export all defined strings."""
    cursor = conn.cursor()
    listing = program.getListing()
    dtm = program.getDataTypeManager()
    
    count = 0
    for data in listing.getDefinedData(True):
        dt = data.getDataType()
        if dt is None:
            continue
        
        # Check if it's a string type
        dt_name = dt.getName().lower()
        if 'string' not in dt_name and 'char' not in dt_name:
            continue
        
        try:
            value = data.getValue()
            if value is None:
                continue
            value_str = str(value)
            
            # Determine encoding
            if 'unicode' in dt_name or 'utf16' in dt_name or 'wchar' in dt_name:
                encoding = 'utf-16-le'
            elif 'utf8' in dt_name:
                encoding = 'utf-8'
            else:
                encoding = 'ascii'
            
            cursor.execute("""
                INSERT OR IGNORE INTO strings (address, value, length, encoding, is_terminated)
                VALUES (?, ?, ?, ?, ?)
            """, (
                data.getAddress().getOffset(),
                value_str,
                len(value_str),
                encoding,
                1  # Assume null-terminated
            ))
            count += 1
        except:
            pass
    
    conn.commit()
    print("Exported %d strings" % count)


def export_comments(conn, program):
    """Export all comments."""
    cursor = conn.cursor()
    listing = program.getListing()
    
    comment_types = [
        (CodeUnit.EOL_COMMENT, 'eol'),
        (CodeUnit.PRE_COMMENT, 'pre'),
        (CodeUnit.POST_COMMENT, 'post'),
        (CodeUnit.PLATE_COMMENT, 'plate'),
        (CodeUnit.REPEATABLE_COMMENT, 'repeatable')
    ]
    
    count = 0
    for cu in listing.getCodeUnits(True):
        for ghidra_type, type_str in comment_types:
            comment = cu.getComment(ghidra_type)
            if comment:
                cursor.execute("""
                    INSERT INTO comments (address, comment_type, text)
                    VALUES (?, ?, ?)
                """, (
                    cu.getAddress().getOffset(),
                    type_str,
                    comment
                ))
                count += 1
    
    conn.commit()
    print("Exported %d comments" % count)


def export_function_bytes(conn, program):
    """Export raw bytes for each function."""
    cursor = conn.cursor()
    fm = program.getFunctionManager()
    memory = program.getMemory()
    
    # Build function ID mapping
    cursor.execute("SELECT id, entry_address, size FROM functions")
    func_map = {row[1]: (row[0], row[2]) for row in cursor.fetchall()}
    
    count = 0
    for func in fm.getFunctions(True):
        entry_offset = func.getEntryPoint().getOffset()
        if entry_offset not in func_map:
            continue
        
        func_id, size = func_map[entry_offset]
        if size == 0:
            continue
        
        try:
            body = func.getBody()
            # Get bytes from function body
            byte_list = []
            for addr_range in body:
                start = addr_range.getMinAddress()
                length = addr_range.getLength()
                if length > 0:
                    bytes_arr = bytearray(length)
                    memory.getBytes(start, bytes_arr)
                    byte_list.extend(bytes_arr)
            
            if byte_list:
                cursor.execute("""
                    INSERT INTO function_bytes (function_id, bytes, start_address, size)
                    VALUES (?, ?, ?, ?)
                """, (
                    func_id,
                    sqlite3.Binary(bytes(byte_list)),
                    entry_offset,
                    len(byte_list)
                ))
                count += 1
        except MemoryAccessException:
            pass
        except Exception as e:
            print("Warning: Failed to export bytes for %s: %s" % (func.getName(), str(e)))
    
    conn.commit()
    print("Exported bytes for %d functions" % count)


def export_function_disassembly(conn, program):
    """Export disassembly listing for each function."""
    cursor = conn.cursor()
    fm = program.getFunctionManager()
    listing = program.getListing()
    
    # Build function ID mapping
    cursor.execute("SELECT id, entry_address FROM functions")
    func_map = {row[1]: row[0] for row in cursor.fetchall()}
    
    count = 0
    for func in fm.getFunctions(True):
        entry_offset = func.getEntryPoint().getOffset()
        if entry_offset not in func_map:
            continue
        
        func_id = func_map[entry_offset]
        
        try:
            body = func.getBody()
            lines = []
            instr_count = 0
            
            for cu in listing.getCodeUnits(body, True):
                addr = cu.getAddress()
                try:
                    bytes_hex = hexlify(bytearray(cu.getBytes())).decode('ascii')
                except:
                    bytes_hex = '??'
                
                # Format: address: bytes mnemonic operands
                line = "0x%08X: %-16s %s" % (
                    addr.getOffset(),
                    bytes_hex[:16],
                    cu.toString()
                )
                lines.append(line)
                instr_count += 1
            
            if lines:
                cursor.execute("""
                    INSERT INTO function_disassembly (function_id, disassembly, instruction_count)
                    VALUES (?, ?, ?)
                """, (
                    func_id,
                    '\n'.join(lines),
                    instr_count
                ))
                count += 1
        except Exception as e:
            print("Warning: Failed to export disassembly for %s: %s" % (func.getName(), str(e)))
    
    conn.commit()
    print("Exported disassembly for %d functions" % count)


def export_call_graph(conn, program):
    """Export materialized call graph."""
    cursor = conn.cursor()
    fm = program.getFunctionManager()
    
    # Build function address to ID mapping
    cursor.execute("SELECT id, entry_address FROM functions")
    func_map = {row[1]: row[0] for row in cursor.fetchall()}
    
    # Count calls between functions
    call_counts = {}  # (caller_id, callee_id) -> count
    
    for func in fm.getFunctions(True):
        caller_addr = func.getEntryPoint().getOffset()
        if caller_addr not in func_map:
            continue
        caller_id = func_map[caller_addr]
        
        called_funcs = func.getCalledFunctions(ConsoleTaskMonitor())
        for called_func in called_funcs:
            callee_addr = called_func.getEntryPoint().getOffset()
            if callee_addr not in func_map:
                continue
            callee_id = func_map[callee_addr]
            
            key = (caller_id, callee_id)
            call_counts[key] = call_counts.get(key, 0) + 1
    
    for (caller_id, callee_id), count in call_counts.items():
        cursor.execute("""
            INSERT INTO call_graph (caller_id, callee_id, call_count)
            VALUES (?, ?, ?)
        """, (caller_id, callee_id, count))
    
    conn.commit()
    print("Exported call graph with %d edges" % len(call_counts))


def main():
    print("=" * 60)
    print("Exporting Ghidra analysis to SQLite")
    print("Output: %s" % OUTPUT_DB)
    print("=" * 60)
    
    # Remove existing database
    if os.path.exists(OUTPUT_DB):
        os.remove(OUTPUT_DB)
    
    # Create database and schema
    conn = sqlite3.connect(OUTPUT_DB)
    create_schema(conn)
    
    program = currentProgram
    
    # Export all data
    export_metadata(conn, program)
    export_segments(conn, program)
    export_functions(conn, program)
    export_symbols(conn, program)
    export_xrefs(conn, program)
    export_strings(conn, program)
    export_comments(conn, program)
    export_function_bytes(conn, program)
    export_function_disassembly(conn, program)
    export_call_graph(conn, program)
    
    # Final stats
    cursor = conn.cursor()
    print("\n" + "=" * 60)
    print("Export complete!")
    for table in ['functions', 'symbols', 'xrefs', 'strings', 'comments']:
        cursor.execute("SELECT COUNT(*) FROM %s" % table)
        print("  %s: %d" % (table, cursor.fetchone()[0]))
    print("=" * 60)
    
    conn.close()


# Run the export
main()
