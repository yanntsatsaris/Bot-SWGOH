---
trigger: always_on
description: Failure modes specific to this repository that an agent cannot infer from the code
---

**Répondre en français si la question est posée en français.** This file is an instruction to you, not text to reproduce.

# Repository traps

Facts that are not visible from reading a single file, and that cost real debugging time.

## `database/db.py` once had eight functions defined twice

Python keeps the **last** definition. Every earlier one was unreachable. The file
contained two copies of `record_counter_feedback`, `get_counter_feedback_stats`,
`add_used_units`, `set_sector_status`, `cycle_sector_counter_offset`,
`get_active_sector_statuses`, `save_user_defense_slot` and `save_user_defense_zones`.
Seven pairs were byte-identical; `save_user_defense_slot` diverged, and only the live
copy took a `used_type` argument.

The failure mode is silent and specific to how agents work: you grep for a name, land on
the first match, edit it, run nothing, and report success. Behaviour is unchanged because
you edited dead code.

The duplicates are gone. `tests/test_module_integrity.py::test_no_shadowed_top_level_definitions`
blocks their return across the whole repo. Before adding a function to `db.py`:

```bash
grep -n "^async def <name>\|^def <name>" database/db.py
```

## `_archive/` is dead

Thirty-five files, roughly 2,600 lines of one-off debug scripts. Nothing imports them.
They contain stale patterns, obsolete APIs and abandoned approaches. Never read them as
reference, never edit them, never cite them as precedent. A test asserts live code does
not reference the directory.

## Raw SQL sits in seven of nine cogs

`admin.py` (9), `gac.py` (9), `review_portraits.py` (9), `gac_scout.py` (8),
`meta_scanner.py` (2), `gac_counter.py` (1), `gac_global_meta.py` (1).

This is existing debt, budgeted in `tests/test_layering.py`. The budget only ratchets
down. New data access goes into `services/`. If you refactor SQL out of a cog, lower its
budget in the same change or the test tells you it is stale.

## `requirements.txt` was unresolvable until recently

`seleniumbase==4.30.5` hard-pins `requests==2.31.0`, which contradicted the file's
`requests==2.32.3`. `pip install -r requirements.txt` failed outright. The pin is now
aligned. If you bump `requests`, you must bump `seleniumbase` with it.

SeleniumBase also drags in an old `pytest-html` that imports `pkg_resources`, gone since
Python 3.12. Both plugins are disabled in `pytest.ini`. Do not remove those `-p no:` flags.

## SeleniumBase is load-bearing

`services/gac_history_scraper.py` imports it at module level, and `main.py` constructs
`GACHistoryScraper` in `setup_hook`. The bot cannot boot without it. It is not an
optional scraping extra.

## The Postgres compatibility layer is hand-rolled

`_translate_sql_to_pg()` rewrites SQL strings with a regex, and `PGRowWrapper`,
`PGCursorWrapper`, `PGExecuteContext` and `PGConnectionWrapper` make asyncpg impersonate
aiosqlite. Every query in the system passes through it, and none of it is tested.
Changes here need a real review, not a confident patch.
