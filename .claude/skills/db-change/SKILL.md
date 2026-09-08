---
name: db-change
description: Add or modify a database query, table or column in Bot-SWGOH, covering both SQLite and Postgres and leaving a round-trip test behind.
---

**Répondre en français si la question est posée en français.** This file is an
instruction to you, not text to reproduce.

Read `docs/workflows/db_change.md` and follow it. That file is the canonical procedure;
this one only routes to it and carries the three things you must not get wrong even if
you skip the read:

1. **Check the name is free first** — `grep -n "^async def <name>\|^def <name>" database/db.py`.
   Eight functions in that file were once defined twice and Python kept the second one.
2. **Both dialects** — a new table needs an entry in `CREATE_TABLES_SQL` *and*
   `CREATE_TABLES_PG_SQL`. Production runs Postgres.
3. **Prove the round trip** — store then read back through the real query path in
   `tests/test_db_round_trip.py`, then run `.venv/bin/python -m pytest`.
