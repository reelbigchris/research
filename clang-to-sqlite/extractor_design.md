Key design points:

**Incremental by default** — The `files` table tracks mtime, and `get_stale_files()` compares against current filesystem state. Re-extraction deletes the old file record (CASCADE handles cleanup) and re-extracts fresh.

**CASCADE everywhere** — When you delete a file record, all symbols, refs, calls, etc. from that file disappear automatically. No orphaned data.

**Call graph resolution is deferred** — During extraction, we store `callee_name` but leave `callee_id` NULL. After all files are processed, `_resolve_call_graph()` links them up. This handles the case where function A calls function B, but B's file hasn't been extracted yet.

**Macro extraction is best-effort** — libclang's macro support is limited. We get the definition from tokens, but expansion tracking would need more work. This captures the basics.

**Documentation parsing is simple** — The Doxygen parser handles `@brief`, `@param`, `@return` and basic continuation. You could swap in a proper Doxygen XML parser later without changing the schema.

**Reference tracking includes context** — Every ref records which function it's in, so you can answer "where is X read within function Y?"

For your environment, this is all standard library plus the `clang` bindings. The extraction runs standalone, produces a single `.db` file, and the query functions from the previous message consume it.
