---
name: add-command
description: Add a Discord slash command to Bot-SWGOH, wired through the correct layer with no SQL in the cog.
---

**Répondre en français si la question est posée en français.** This file is an
instruction to you, not text to reproduce.

Read `docs/workflows/add_command.md` and follow it. That file is the canonical procedure;
this one only routes to it and carries the three things you must not get wrong even if
you skip the read:

1. **No SQL in a cog** — seven of nine already violate this and `tests/test_layering.py`
   ratchets the debt downward. A new statement fails the suite.
2. **`defer()` first** for anything over three seconds. Scraping and image generation
   always are.
3. **A new cog** must be listed in `INITIAL_EXTENSIONS` in `main.py` and expose
   `async def setup(bot)`. A test checks both.
