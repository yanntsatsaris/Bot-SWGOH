---
trigger: always_on
description: Layering rules and where each kind of change belongs
---

**Répondre en français si la question est posée en français.** This file is an instruction to you, not text to reproduce.

# Architecture

```
cogs/  →  services/  →  database/
```

One direction. A layer never imports from the one above it.

## `cogs/` — controllers

Slash commands, buttons, modals, embeds. Discord objects in, Discord objects out.

Allowed: parsing interaction input, permission checks, formatting a reply, calling a
service, dispatching to `image_generator`.

Not allowed: SQL, business rules, scraping, roster maths. If a cog is deciding *what*
the answer is rather than *how to display it*, the logic belongs in `services/`.

## `services/` — business logic

Scouting, planning, meta analysis, scraping orchestration, image generation. Services
may call `database/db.py` and may call other services. They must not import from `cogs/`
and must not touch `discord.` types beyond what they are handed.

## `database/` — repository

`db.py` owns connections and queries. `models.py` owns schema DDL, split into
`CREATE_TABLES_SQL` (SQLite) and `CREATE_TABLES_PG_SQL` (Postgres). A new table needs
both.

Query functions return plain dicts, sets and lists — never row objects, never cursors.
The connection must not escape `async with get_db()`.

## `scripts/` — out-of-process workers

SeleniumBase workers run as separate processes because Chrome cannot be driven safely
from inside the bot's event loop. They talk to the bot through the database or stdout,
never by import.

## Adding a feature

1. Decide the layer. Data shape first, in `models.py` if the schema moves.
2. Query functions in `db.py`, one concern each.
3. Logic in a service, returning plain data.
4. A thin cog that formats it.
5. A round-trip test in `tests/` if anything is stored and read back.

## Size

A function past ~80 lines is doing several jobs. `services/scouting.py` is the warning:
2,026 lines with a 450-line function. Do not add to it — extract a new module.
