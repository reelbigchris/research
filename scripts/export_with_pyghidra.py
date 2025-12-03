#!/usr/bin/env python3
"""
Export Ghidra projects to SQLite databases using PyGhidra.

This script can export from:
1. Local Ghidra project files (.gpr)
2. Individual binary files (will create temporary project)

Requirements:
    pip install pyghidra
    GHIDRA_INSTALL_DIR environment variable set

Usage:
    # Export from a local Ghidra project
    python export_with_pyghidra.py --project /path/to/project.gpr --output ./databases/

    # Export a single binary (creates temp project, runs analysis)
    python export_with_pyghidra.py --binary /path/to/firmware.bin --output ./databases/firmware.db

    # Export specific program from project
    python export_with_pyghidra.py --project /path/to/project.gpr --program "firmware_v2" --output ./db/
"""

import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from binascii import hexlify

# Script version
SCRIPT_VERSION = "1.0.0"


def create_schema(conn):
    """Create all database tables."""
    cursor = conn.cursor()
    
    schema_sql = """
    -- Metadata table
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    
    -- Segments table
    CREATE TABLE IF NOT EXISTS segments (
        id INTEGER PRIMARY KEY,
        name TEXT,
        start_address INTEGER,
        end_address INTEGER,
        size INTEGER,
        permissions TEXT,
        is_initialized INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_segments_addr ON segments(start_address, end_address);
    
    -- Functions table
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
    );
    CREATE INDEX IF NOT EXISTS idx_functions_name ON functions(name);
    CREATE INDEX IF NOT EXISTS idx_functions_addr ON functions(entry_address);
    
    -- Symbols table
    CREATE TABLE IF NOT EXISTS symbols (
        id INTEGER PRIMARY KEY,
        name TEXT,
        address INTEGER,
        type TEXT,
        namespace TEXT,
        source TEXT,
        is_primary INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
    CREATE INDEX IF NOT EXISTS idx_symbols_addr ON symbols(address);
    CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(type);
    
    -- Cross-references table
    CREATE TABLE IF NOT EXISTS xrefs (
        id INTEGER PRIMARY KEY,
        from_address INTEGER,
        to_address INTEGER,
        ref_type TEXT,
        is_call INTEGER,
        operand_index INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_xrefs_to ON xrefs(to_address);
    CREATE INDEX IF NOT EXISTS idx_xrefs_from ON xrefs(from_address);
    CREATE INDEX IF NOT EXISTS idx_xrefs_type ON xrefs(ref_type);
    
    -- Strings table
    CREATE TABLE IF NOT EXISTS strings (
        id INTEGER PRIMARY KEY,
        address INTEGER UNIQUE,
        value TEXT,
        length INTEGER,
        encoding TEXT,
        is_terminated INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_strings_value ON strings(value);
    CREATE INDEX IF NOT EXISTS idx_strings_addr ON strings(address);
    
    -- Comments table
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY,
        address INTEGER,
        comment_type TEXT,
        text TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_comments_addr ON comments(address);
    
    -- Data types table
    CREATE TABLE IF NOT EXISTS data_types (
        id INTEGER PRIMARY KEY,
        name TEXT,
        category TEXT,
        kind TEXT,
        size INTEGER,
        alignment INTEGER,
        definition TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_data_types_name ON data_types(name);
    CREATE INDEX IF NOT EXISTS idx_data_types_kind ON data_types(kind);
    
    -- Function bytes table
    CREATE TABLE IF NOT EXISTS function_bytes (
        function_id INTEGER PRIMARY KEY,
        bytes BLOB,
        start_address INTEGER,
        size INTEGER
    );
    
    -- Function disassembly table
    CREATE TABLE IF NOT EXISTS function_disassembly (
        function_id INTEGER PRIMARY KEY,
        disassembly TEXT,
        instruction_count INTEGER
    );
    
    -- Call graph table
    CREATE TABLE IF NOT EXISTS call_graph (
        caller_id INTEGER,
        callee_id INTEGER,
        call_count INTEGER,
        PRIMARY KEY (caller_id, callee_id)
    );
    CREATE INDEX IF NOT EXISTS idx_call_graph_callee ON call_graph(callee_id);
    
    -- Imports table
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY,
        name TEXT,
        library TEXT,
        address INTEGER,
        ordinal INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_imports_name ON imports(name);
    
    -- Exports table
    CREATE TABLE IF NOT EXISTS exports (
        id INTEGER PRIMARY KEY,
        name TEXT,
        address INTEGER,
        ordinal INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_exports_name ON exports(name);
    """
    
    cursor.executescript(schema_sql)
    conn.commit()


def export_program(program, flat_api, output_path: str, project_name: str = "unknown"):
    """Export a Ghidra program to SQLite database."""
    from ghidra.program.model.listing import CodeUnit
    from ghidra.util.task import ConsoleTaskMonitor
    
    # Remove existing database
    if os.path.exists(output_path):
        os.remove(output_path)
    
    conn = sqlite3.connect(output_path)
    create_schema(conn)
    cursor = conn.cursor()
    
    print(f"Exporting {program.getName()} to {output_path}")
    
    # Export metadata
    lang = program.getLanguage()
    metadata = {
        'project_name': project_name,
        'program_name': program.getName(),
        'architecture': str(lang.getLanguageID()),
        'compiler': str(program.getCompilerSpec().getCompilerSpecID()),
        'endianness': 'big' if lang.isBigEndian() else 'little',
        'pointer_size': str(lang.getDefaultSpace().getPointerSize()),
        'base_address': hex(program.getImageBase().getOffset()),
        'min_address': hex(program.getMinAddress().getOffset()) if program.getMinAddress() else '0x0',
        'max_address': hex(program.getMaxAddress().getOffset()) if program.getMaxAddress() else '0x0',
        'export_date': datetime.now().isoformat(),
        'ghidra_version': 'pyghidra',
        'export_script_version': SCRIPT_VERSION
    }
    for key, value in metadata.items():
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value))
    print(f"  Exported metadata")
    
    # Export segments
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
    print(f"  Exported {len(list(memory.getBlocks()))} segments")
    
    # Export functions
    fm = program.getFunctionManager()
    listing = program.getListing()
    func_count = 0
    
    for func in fm.getFunctions(True):
        ns = func.getParentNamespace()
        namespace = ns.getName(True) if ns and not ns.isGlobal() else None
        
        # Get plate comment
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
        func_count += 1
    conn.commit()
    print(f"  Exported {func_count} functions")
    
    # Export symbols
    st = program.getSymbolTable()
    sym_count = 0
    for sym in st.getAllSymbols(True):
        sym_type = str(sym.getSymbolType())
        if sym_type == 'Function':
            type_str = 'function'
        elif sym_type == 'Label':
            type_str = 'label'
        elif sym_type in ('Class', 'Namespace'):
            continue
        else:
            type_str = 'data'
        
        source = str(sym.getSource())
        source_map = {
            'USER_DEFINED': 'user',
            'ANALYSIS': 'analysis',
            'IMPORTED': 'imported'
        }
        source_str = source_map.get(source, 'default')
        
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
        sym_count += 1
    conn.commit()
    print(f"  Exported {sym_count} symbols")
    
    # Export cross-references
    rm = program.getReferenceManager()
    xref_count = 0
    
    addr_iter = program.getMemory().getAddresses(True)
    while addr_iter.hasNext():
        addr = addr_iter.next()
        refs = rm.getReferencesFrom(addr)
        for ref in refs:
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
            xref_count += 1
            
            if xref_count % 10000 == 0:
                conn.commit()
                print(f"    ... {xref_count} xrefs")
    
    conn.commit()
    print(f"  Exported {xref_count} cross-references")
    
    # Export strings
    str_count = 0
    for data in listing.getDefinedData(True):
        dt = data.getDataType()
        if dt is None:
            continue
        
        dt_name = dt.getName().lower()
        if 'string' not in dt_name and 'char' not in dt_name:
            continue
        
        try:
            value = data.getValue()
            if value is None:
                continue
            value_str = str(value)
            
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
                1
            ))
            str_count += 1
        except Exception:
            pass
    conn.commit()
    print(f"  Exported {str_count} strings")
    
    # Export comments
    comment_types = [
        (CodeUnit.EOL_COMMENT, 'eol'),
        (CodeUnit.PRE_COMMENT, 'pre'),
        (CodeUnit.POST_COMMENT, 'post'),
        (CodeUnit.PLATE_COMMENT, 'plate'),
        (CodeUnit.REPEATABLE_COMMENT, 'repeatable')
    ]
    
    comment_count = 0
    for cu in listing.getCodeUnits(True):
        for ghidra_type, type_str in comment_types:
            comment = cu.getComment(ghidra_type)
            if comment:
                cursor.execute("""
                    INSERT INTO comments (address, comment_type, text)
                    VALUES (?, ?, ?)
                """, (cu.getAddress().getOffset(), type_str, comment))
                comment_count += 1
    conn.commit()
    print(f"  Exported {comment_count} comments")
    
    # Export function bytes and disassembly
    cursor.execute("SELECT id, entry_address, size FROM functions")
    func_map = {row[1]: (row[0], row[2]) for row in cursor.fetchall()}
    
    bytes_count = 0
    disasm_count = 0
    
    for func in fm.getFunctions(True):
        entry_offset = func.getEntryPoint().getOffset()
        if entry_offset not in func_map:
            continue
        
        func_id, size = func_map[entry_offset]
        
        # Export bytes
        try:
            body = func.getBody()
            byte_list = []
            for addr_range in body:
                start = addr_range.getMinAddress()
                length = int(addr_range.getLength())
                if length > 0:
                    bytes_arr = flat_api.getBytes(start, length)
                    byte_list.extend(bytes_arr)
            
            if byte_list:
                # Convert signed bytes to unsigned
                unsigned_bytes = bytes([b & 0xff for b in byte_list])
                cursor.execute("""
                    INSERT INTO function_bytes (function_id, bytes, start_address, size)
                    VALUES (?, ?, ?, ?)
                """, (func_id, unsigned_bytes, entry_offset, len(unsigned_bytes)))
                bytes_count += 1
        except Exception as e:
            pass
        
        # Export disassembly
        try:
            body = func.getBody()
            lines = []
            instr_count = 0
            
            for cu in listing.getCodeUnits(body, True):
                addr = cu.getAddress()
                try:
                    raw_bytes = cu.getBytes()
                    bytes_hex = ''.join(f'{b & 0xff:02x}' for b in raw_bytes)
                except Exception:
                    bytes_hex = '??'
                
                line = f"0x{addr.getOffset():08X}: {bytes_hex:<16} {cu.toString()}"
                lines.append(line)
                instr_count += 1
            
            if lines:
                cursor.execute("""
                    INSERT INTO function_disassembly (function_id, disassembly, instruction_count)
                    VALUES (?, ?, ?)
                """, (func_id, '\n'.join(lines), instr_count))
                disasm_count += 1
        except Exception:
            pass
    
    conn.commit()
    print(f"  Exported bytes for {bytes_count} functions")
    print(f"  Exported disassembly for {disasm_count} functions")
    
    # Export call graph
    cursor.execute("SELECT id, entry_address FROM functions")
    func_addr_map = {row[1]: row[0] for row in cursor.fetchall()}
    
    call_counts = {}
    monitor = ConsoleTaskMonitor()
    
    for func in fm.getFunctions(True):
        caller_addr = func.getEntryPoint().getOffset()
        if caller_addr not in func_addr_map:
            continue
        caller_id = func_addr_map[caller_addr]
        
        try:
            called_funcs = func.getCalledFunctions(monitor)
            for called_func in called_funcs:
                callee_addr = called_func.getEntryPoint().getOffset()
                if callee_addr not in func_addr_map:
                    continue
                callee_id = func_addr_map[callee_addr]
                
                key = (caller_id, callee_id)
                call_counts[key] = call_counts.get(key, 0) + 1
        except Exception:
            pass
    
    for (caller_id, callee_id), count in call_counts.items():
        cursor.execute("""
            INSERT INTO call_graph (caller_id, callee_id, call_count)
            VALUES (?, ?, ?)
        """, (caller_id, callee_id, count))
    
    conn.commit()
    print(f"  Exported call graph with {len(call_counts)} edges")
    
    conn.close()
    print(f"Export complete: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Export Ghidra projects to SQLite databases using PyGhidra',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--project', '-p', help='Path to Ghidra project (.gpr file)')
    parser.add_argument('--binary', '-b', help='Path to binary file (creates temp project)')
    parser.add_argument('--program', help='Specific program name within project')
    parser.add_argument('--output', '-o', required=True, 
                        help='Output path (directory for project, file for binary)')
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='Run analysis before export (for binary imports)')
    
    args = parser.parse_args()
    
    if not args.project and not args.binary:
        parser.error("Either --project or --binary must be specified")
    
    # Check for GHIDRA_INSTALL_DIR
    if 'GHIDRA_INSTALL_DIR' not in os.environ:
        print("Error: GHIDRA_INSTALL_DIR environment variable not set")
        sys.exit(1)
    
    try:
        import pyghidra
    except ImportError:
        print("Error: pyghidra not installed")
        print("Install with: pip install pyghidra")
        sys.exit(1)
    
    # Start PyGhidra
    pyghidra.start()
    
    if args.binary:
        # Import and optionally analyze a binary
        output_path = args.output
        if os.path.isdir(output_path):
            binary_name = Path(args.binary).stem
            output_path = os.path.join(output_path, f"{binary_name}.db")
        
        print(f"Importing binary: {args.binary}")
        with pyghidra.open_program(args.binary, analyze=args.analyze) as flat_api:
            program = flat_api.getCurrentProgram()
            export_program(program, flat_api, output_path, "imported")
    
    else:
        # Open existing project
        project_path = Path(args.project)
        if not project_path.exists():
            print(f"Error: Project not found: {project_path}")
            sys.exit(1)
        
        # Ensure output is a directory
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        project_location = str(project_path.parent)
        project_name = project_path.stem
        
        print(f"Opening project: {project_path}")
        
        with pyghidra.open_program(
            None,  # No binary to import
            project_location=project_location,
            project_name=project_name,
            analyze=False
        ) as flat_api:
            # Get project data to iterate programs
            # Note: This simplified version exports the "current" program
            # For full project iteration, you'd need more complex logic
            program = flat_api.getCurrentProgram()
            if program:
                safe_name = "".join(
                    c if c.isalnum() or c in '-_.' else '_' 
                    for c in program.getName()
                )
                output_path = output_dir / f"{safe_name}.db"
                export_program(program, flat_api, str(output_path), project_name)


if __name__ == '__main__':
    main()
