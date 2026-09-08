---
trigger: glob
globs: ["**/*.py"]
description: Python style and error-handling conventions for this repository
---

**Répondre en français si la question est posée en français.** This file is an instruction to you, not text to reproduce.

# Python conventions

## Language

French. Identifiers, docstrings and comments in this codebase are French and stay
French. Do not translate existing code, and do not introduce English names next to
French ones.

## Comments

Default to none. A clearer name or a named constant beats a comment and cannot go stale.
Write one only for something the code cannot say: an external constraint, a non-obvious
*why*, a deliberate omission. Never restate what the line does.

## Errors

`except Exception` is already used 163 times here, 12 of them swallowing into `pass`.
That is why a duplicate-definition bug survived unnoticed.

- Catch the narrowest exception you can name.
- Never write `except ...: pass`. Log it, or let it raise.
- Never swallow an exception around a database write.

## Types

Type hints on new functions. Modern syntax: `str | None`, `list[dict]`, `dict[str, int]`.
Not `Optional[str]`, not `List[Dict]`.

## Async

Everything touching the database or the network is `async`. Never call blocking I/O in a
coroutine — SeleniumBase work is dispatched to a separate process for exactly this reason.
Always `async with get_db() as db`; never open a connection by hand.

## Imports

Standard library, third party, then local, separated by blank lines. Module-level imports
only, except where a heavy or optional dependency is deliberately deferred inside a
function — `pyvirtualdisplay` in the workers is the existing precedent.

## Module-level side effects

None. `config.py` already raises `KeyError` at import time when `DISCORD_TOKEN` is unset,
which makes every module importing it untestable without environment setup. Do not add
more of this.
