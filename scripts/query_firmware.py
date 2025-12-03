#!/usr/bin/env python3
"""
Query firmware analysis SQLite databases exported from Ghidra.

Usage:
    python query_firmware.py <db_path> "<sql_query>"
    python query_firmware.py <db_path> --function <name_or_addr> [--disasm] [--bytes]
    python query_firmware.py <db_path> --callers <function_name>
    python query_firmware.py <db_path> --callees <function_name>
    python query_firmware.py <db_path> --xrefs-to <address>
    python query_firmware.py <db_path> --xrefs-from <address>
    python query_firmware.py <db_path> --strings [<pattern>]
    python query_firmware.py <db_path> --info
"""

import sqlite3
import argparse
import sys
import json
from pathlib import Path


def parse_address(addr_str: str) -> int:
    """Parse address from string (supports hex with 0x prefix or decimal)."""
    addr_str = addr_str.strip()
    if addr_str.startswith('0x') or addr_str.startswith('0X'):
        return int(addr_str, 16)
    # Try hex first if it looks like hex
    if all(c in '0123456789abcdefABCDEF' for c in addr_str) and len(addr_str) >= 6:
        try:
            return int(addr_str, 16)
        except ValueError:
            pass
    return int(addr_str)


def format_address(addr: int, width: int = 8) -> str:
    """Format address as hex string."""
    return f"0x{addr:0{width}X}"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list:
    """Execute query and return results as list of dicts."""
    cursor = conn.execute(query, params)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def print_results(results: list, format_addresses: bool = True):
    """Print results in a readable format."""
    if not results:
        print("No results found.")
        return
    
    # Get column widths
    columns = list(results[0].keys())
    widths = {col: len(col) for col in columns}
    
    for row in results:
        for col in columns:
            val = row[col]
            if val is not None:
                # Format addresses
                if format_addresses and isinstance(val, int) and ('address' in col.lower() or col == 'size'):
                    if 'size' in col.lower():
                        val_str = str(val)
                    else:
                        val_str = format_address(val)
                elif isinstance(val, bytes):
                    val_str = val.hex()[:40] + ('...' if len(val) > 20 else '')
                else:
                    val_str = str(val)[:60]
                widths[col] = max(widths[col], len(val_str))
    
    # Print header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))
    
    # Print rows
    for row in results:
        row_strs = []
        for col in columns:
            val = row[col]
            if val is None:
                val_str = ""
            elif format_addresses and isinstance(val, int) and 'address' in col.lower():
                val_str = format_address(val)
            elif isinstance(val, bytes):
                val_str = val.hex()[:40] + ('...' if len(val) > 20 else '')
            else:
                val_str = str(val)[:60]
            row_strs.append(val_str.ljust(widths[col]))
        print(" | ".join(row_strs))


def cmd_raw_query(conn: sqlite3.Connection, query: str):
    """Execute a raw SQL query."""
    results = execute_query(conn, query)
    print_results(results)
    print(f"\n({len(results)} rows)")


def cmd_info(conn: sqlite3.Connection):
    """Show database metadata."""
    print("=== Firmware Database Info ===\n")
    
    # Metadata
    results = execute_query(conn, "SELECT key, value FROM metadata ORDER BY key")
    print("Metadata:")
    for row in results:
        print(f"  {row['key']}: {row['value']}")
    
    # Counts
    print("\nTable counts:")
    tables = ['functions', 'symbols', 'xrefs', 'strings', 'comments', 'segments', 'data_types']
    for table in tables:
        try:
            count = execute_query(conn, f"SELECT COUNT(*) as cnt FROM {table}")[0]['cnt']
            print(f"  {table}: {count}")
        except sqlite3.OperationalError:
            print(f"  {table}: (table not found)")


def cmd_function(conn: sqlite3.Connection, name_or_addr: str, show_disasm: bool, show_bytes: bool):
    """Look up a function by name or address."""
    # Determine if it's an address or name
    try:
        addr = parse_address(name_or_addr)
        # Look up by address (exact or containing)
        results = execute_query(conn, """
            SELECT * FROM functions 
            WHERE entry_address = ? 
               OR (entry_address <= ? AND entry_address + size > ?)
        """, (addr, addr, addr))
    except ValueError:
        # Look up by name
        results = execute_query(conn, """
            SELECT * FROM functions WHERE name LIKE ?
        """, (f"%{name_or_addr}%",))
    
    if not results:
        print(f"No function found matching '{name_or_addr}'")
        return
    
    for func in results:
        print(f"\n=== Function: {func['name']} ===")
        print(f"Address:    {format_address(func['entry_address'])}")
        print(f"Size:       {func['size']} bytes")
        print(f"Signature:  {func['signature'] or '(unknown)'}")
        print(f"Convention: {func['calling_convention'] or '(default)'}")
        print(f"Thunk:      {'Yes' if func['is_thunk'] else 'No'}")
        print(f"External:   {'Yes' if func['is_external'] else 'No'}")
        if func['namespace']:
            print(f"Namespace:  {func['namespace']}")
        if func['comment']:
            print(f"Comment:    {func['comment']}")
        
        if show_disasm:
            disasm = execute_query(conn, """
                SELECT disassembly, instruction_count 
                FROM function_disassembly 
                WHERE function_id = ?
            """, (func['id'],))
            if disasm:
                print(f"\n--- Disassembly ({disasm[0]['instruction_count']} instructions) ---")
                print(disasm[0]['disassembly'])
        
        if show_bytes:
            bytes_data = execute_query(conn, """
                SELECT hex(bytes) as hex_bytes FROM function_bytes WHERE function_id = ?
            """, (func['id'],))
            if bytes_data:
                hex_str = bytes_data[0]['hex_bytes']
                print(f"\n--- Raw bytes ({len(hex_str)//2} bytes) ---")
                # Format in rows of 32 bytes
                for i in range(0, len(hex_str), 64):
                    chunk = hex_str[i:i+64]
                    # Add spaces between bytes
                    spaced = ' '.join(chunk[j:j+2] for j in range(0, len(chunk), 2))
                    print(f"{format_address(func['entry_address'] + i//2)}: {spaced}")


def cmd_callers(conn: sqlite3.Connection, func_name: str):
    """Find all callers of a function."""
    # Get target function
    target = execute_query(conn, "SELECT id, entry_address FROM functions WHERE name = ?", (func_name,))
    if not target:
        # Try partial match
        target = execute_query(conn, "SELECT id, entry_address, name FROM functions WHERE name LIKE ?", (f"%{func_name}%",))
        if not target:
            print(f"Function '{func_name}' not found")
            return
        if len(target) > 1:
            print(f"Multiple matches for '{func_name}':")
            for t in target:
                print(f"  {t['name']} @ {format_address(t['entry_address'])}")
            return
    
    target_id = target[0]['id']
    target_addr = target[0]['entry_address']
    
    # Find callers via call_graph if available
    callers = execute_query(conn, """
        SELECT f.name, f.entry_address, cg.call_count
        FROM call_graph cg
        JOIN functions f ON cg.caller_id = f.id
        WHERE cg.callee_id = ?
        ORDER BY f.name
    """, (target_id,))
    
    if not callers:
        # Fall back to xrefs
        callers = execute_query(conn, """
            SELECT DISTINCT f.name, f.entry_address, x.from_address as call_site
            FROM xrefs x
            JOIN functions f ON x.from_address BETWEEN f.entry_address AND f.entry_address + f.size - 1
            WHERE x.to_address = ? AND x.ref_type = 'call'
            ORDER BY f.name
        """, (target_addr,))
    
    if callers:
        print(f"Callers of {func_name}:")
        print_results(callers)
    else:
        print(f"No callers found for {func_name}")


def cmd_callees(conn: sqlite3.Connection, func_name: str):
    """Find all functions called by a function."""
    # Get source function
    source = execute_query(conn, "SELECT id, entry_address, size FROM functions WHERE name = ?", (func_name,))
    if not source:
        source = execute_query(conn, "SELECT id, entry_address, size, name FROM functions WHERE name LIKE ?", (f"%{func_name}%",))
        if not source:
            print(f"Function '{func_name}' not found")
            return
        if len(source) > 1:
            print(f"Multiple matches for '{func_name}':")
            for s in source:
                print(f"  {s['name']} @ {format_address(s['entry_address'])}")
            return
    
    source_id = source[0]['id']
    
    # Find callees via call_graph if available
    callees = execute_query(conn, """
        SELECT f.name, f.entry_address, cg.call_count
        FROM call_graph cg
        JOIN functions f ON cg.callee_id = f.id
        WHERE cg.caller_id = ?
        ORDER BY f.name
    """, (source_id,))
    
    if not callees:
        # Fall back to xrefs
        src = source[0]
        callees = execute_query(conn, """
            SELECT DISTINCT f.name, f.entry_address, x.from_address as call_site
            FROM xrefs x
            JOIN functions f ON x.to_address = f.entry_address
            WHERE x.from_address BETWEEN ? AND ?
              AND x.ref_type = 'call'
            ORDER BY x.from_address
        """, (src['entry_address'], src['entry_address'] + src['size'] - 1))
    
    if callees:
        print(f"Functions called by {func_name}:")
        print_results(callees)
    else:
        print(f"No callees found for {func_name}")


def cmd_xrefs_to(conn: sqlite3.Connection, addr_str: str):
    """Find all references to an address."""
    addr = parse_address(addr_str)
    
    results = execute_query(conn, """
        SELECT x.from_address, x.ref_type, f.name as from_function
        FROM xrefs x
        LEFT JOIN functions f ON x.from_address BETWEEN f.entry_address AND f.entry_address + f.size - 1
        WHERE x.to_address = ?
        ORDER BY x.from_address
    """, (addr,))
    
    print(f"References to {format_address(addr)}:")
    print_results(results)


def cmd_xrefs_from(conn: sqlite3.Connection, addr_str: str):
    """Find all references from an address."""
    addr = parse_address(addr_str)
    
    results = execute_query(conn, """
        SELECT x.to_address, x.ref_type, 
               COALESCE(f.name, s.value, '') as target
        FROM xrefs x
        LEFT JOIN functions f ON x.to_address = f.entry_address
        LEFT JOIN strings s ON x.to_address = s.address
        WHERE x.from_address = ?
        ORDER BY x.to_address
    """, (addr,))
    
    print(f"References from {format_address(addr)}:")
    print_results(results)


def cmd_strings(conn: sqlite3.Connection, pattern: str = None):
    """Search for strings."""
    if pattern:
        results = execute_query(conn, """
            SELECT address, value, length, encoding 
            FROM strings 
            WHERE value LIKE ?
            ORDER BY address
            LIMIT 100
        """, (f"%{pattern}%",))
    else:
        results = execute_query(conn, """
            SELECT address, value, length, encoding 
            FROM strings 
            ORDER BY address
            LIMIT 100
        """)
    
    print_results(results)
    if len(results) == 100:
        print("\n(Limited to 100 results)")


def main():
    parser = argparse.ArgumentParser(
        description='Query firmware analysis SQLite databases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('db_path', help='Path to the SQLite database')
    parser.add_argument('query', nargs='?', help='SQL query to execute')
    parser.add_argument('--function', '-f', metavar='NAME_OR_ADDR',
                        help='Look up function by name or address')
    parser.add_argument('--disasm', '-d', action='store_true',
                        help='Show disassembly (with --function)')
    parser.add_argument('--bytes', '-b', action='store_true',
                        help='Show raw bytes (with --function)')
    parser.add_argument('--callers', '-c', metavar='FUNC',
                        help='Find callers of a function')
    parser.add_argument('--callees', '-e', metavar='FUNC',
                        help='Find functions called by a function')
    parser.add_argument('--xrefs-to', '-t', metavar='ADDR',
                        help='Find references to an address')
    parser.add_argument('--xrefs-from', '-r', metavar='ADDR',
                        help='Find references from an address')
    parser.add_argument('--strings', '-s', nargs='?', const='', metavar='PATTERN',
                        help='Search for strings (optional pattern)')
    parser.add_argument('--info', '-i', action='store_true',
                        help='Show database info')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output results as JSON')
    
    args = parser.parse_args()
    
    if not Path(args.db_path).exists():
        print(f"Error: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    conn = get_connection(args.db_path)
    
    try:
        if args.info:
            cmd_info(conn)
        elif args.function:
            cmd_function(conn, args.function, args.disasm, args.bytes)
        elif args.callers:
            cmd_callers(conn, args.callers)
        elif args.callees:
            cmd_callees(conn, args.callees)
        elif args.xrefs_to:
            cmd_xrefs_to(conn, args.xrefs_to)
        elif args.xrefs_from:
            cmd_xrefs_from(conn, args.xrefs_from)
        elif args.strings is not None:
            cmd_strings(conn, args.strings if args.strings else None)
        elif args.query:
            cmd_raw_query(conn, args.query)
        else:
            parser.print_help()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
