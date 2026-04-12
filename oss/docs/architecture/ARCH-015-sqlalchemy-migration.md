# ARCH-015: Migrate from raw sqlite3 to SQLAlchemy

**Priority:** medium
**Complexity:** high
**Status:** planned

## Problem

The codebase uses raw `sqlite3` with hand-written SQL strings throughout:
- `history_compare_store.py` — 10+ queries with repeated WHERE patterns
- `usage_backends.py` — dynamic IN-clause construction
- `history_ingest.py`, `history_normalize.py`, `history_derive.py` — pipeline stage queries
- `cost_audit.py` — usage resolution queries

As query complexity grows (joins, subqueries, optional filters, aggregations), raw SQL becomes harder to maintain, test, and refactor safely. Dynamic SQL construction requires careful `nosec` annotation to satisfy bandit, and optional WHERE clauses use the `(? IS NULL OR col = ?)` workaround pattern.

## Proposed solution

Migrate to **SQLAlchemy Core** (SQL Expression Language) as the query-building layer:
- Replace hand-written SQL strings with composable `select()`, `where()`, `join()` expressions
- Use SQLAlchemy's `Table` / `Column` definitions as the schema source of truth
- Keep using SQLite as the storage engine (no change to warehouse format)

**SQLAlchemy ORM** is not needed — the data model is read-heavy analytics, not entity lifecycle management. Core alone provides:
- Type-safe query composition
- Automatic parameterization (eliminates B608 concerns entirely)
- Optional WHERE clauses via `.where()` chaining instead of SQL string patterns
- Schema introspection and migration support (via Alembic, if needed later)

## Migration strategy

1. Add `sqlalchemy` as a dependency
2. Define `Table` objects for existing warehouse tables (`derived_goals`, `derived_session_usage`, `derived_projects`, etc.)
3. Migrate one module at a time, starting with `history_compare_store.py` (most repetitive queries)
4. Keep raw `sqlite3` in modules that don't benefit from the migration (simple single-query lookups)
5. Validate each module migration with existing tests

## Risks

- Adds a runtime dependency (~1.5 MB) to a currently dependency-light package
- Learning curve for contributors unfamiliar with SQLAlchemy Core
- Migration must be incremental — no big-bang rewrite
