The key design decisions:

1. **CASCADE deletes** — When you re-extract a file, delete its `files` row and everything cascades. Clean incremental updates.

2. **Flexible path matching** — Most queries use `LIKE %path%` so you can pass partial paths. Your agent won't always know the full path.

3. **Context tracking on refs** — Knowing which function contains a reference is invaluable for understanding usage patterns.

4. **Callee name always stored** — Even when we can resolve the callee to a symbol ID, we keep the name for external/library calls that aren't in our database.

5. **Documentation as a separate table** — You can populate it from libclang's raw comments initially, then overlay Doxygen XML parsing later without schema changes.
