# CLAUDE.md — Project Guidelines & Instructions

## Always interact with the user in french: answer and expect answers in french. All your skills are in English to facilate the thinking section.

---

## 📋 Development Rules & Code Style

1. **Async-first**: Ensure all I/O, database access, and HTTP requests are non-blocking (`aiohttp`, `aiosqlite`).
2. **Error Handling**: Discord interaction responses must fail gracefully with user-friendly ephemeral messages where appropriate.
3. **Configuration**: Never hardcode credentials or tokens. Always load settings through `config.py` using `.env`.
4. **Preserve Documentation**: Maintain existing comments, docstrings, and architectural conventions when modifying modules.

## Approach
- Read existing files before writing. Don't re-read unless changed.
- Thorough in reasoning, concise in output.
- Skip files over 100KB unless required.
- No sycophantic openers or closing fluff.
- No emojis or em-dashes.
- Do not guess APIs, versions, flags, commit SHAs, or package names. Verify by reading code or docs before asserting.

# Core Rules
Short sentences only (8-10 words max).
No filler, no preamble, no pleasantries.
Tool first. Result first. No explain unless asked.
Code stays normal. English gets compressed.


## Formatting
Output sounds human. Never AI-generated.
Never use em-dashes or replacement hyphens.
Avoid parenthetical clauses entirely.
Hyphens map to standard grammar only.

---

## 🚀 Project Overview
**Bot-SWGOH** is a modular asynchronous Discord bot designed for **Star Wars: Galaxy of Heroes (SWGOH)** guild and player intelligence. It provides tools for Grand Arena Championship (GAC) scouting, counter lookups, fleet counters, forum thread management for guild members, and asset/data synchronization.

---

## 🛠️ Tech Stack & Architecture

- **Language & Runtime**: Python 3.10+
- **Discord Framework**: `discord.py` (v2.4.0) with slash commands (`app_commands`) and dynamic views (`discord.ui`).
- **Data & Storage**:
  - `aiosqlite` (local SQLite database at `database/swgoh.db`)
  - `asyncpg` (PostgreSQL support for production)
- **External APIs & Scraping**:
  - `swgoh-comlink` (official SWGOH game client communication via local/remote Comlink)
  - `aiohttp` / `requests` / `beautifulsoup4` / `seleniumbase` (SWGOH.gg scraping and meta data syncing)
- **Image Generation**: `Pillow` (PIL) for rendering visual GAC scout cards and squad counters.

---

## 📁 Repository Structure

```
├── assets/          # SWGOH icons, character portraits, ship portraits, banners
├── cogs/            # Discord Cogs / Command extensions
│   ├── forum_manager.py   # Forum threads & auto-management per player
│   ├── gac.py             # General GAC slash commands
│   ├── gac_counter.py     # Squad counter search & display
│   ├── gac_fleet.py       # Fleet counter lookups & scouting
│   └── gac_scout.py       # Full opponent scouting & stat analysis
├── config.py        # Centralized environment & setting loader
├── data/            # Static game definitions, localization, abbreviations
├── database/        # Async SQLite/PostgreSQL connection & schema handlers
├── docs/            # Technical research, architecture & implementation plans
├── main.py          # Bot entry point, cog loading, client lifecycle
├── requirements.txt # Python package dependencies
├── services/        # Business logic, SWGOH API clients, GAC lock service
├── sync_all_units.py# Data sync script for unit stats and definitions
├── sync_assets.py   # Asset downloader for character & ship icons
├── sync_meta.py     # SWGOH.gg meta scraper for GAC counters
└── utils/           # Formatting, image renderers, embed builders
```

---

## ⚙️ Common Commands

### Running the Bot
```bash
python main.py
```

### Data Synchronization Scripts
```bash
# Sync all unit definitions, gear, abilities:
python sync_all_units.py

# Sync visual assets (portraits, icons):
python sync_assets.py

# Scrape and update 5v5 / 3v3 meta counters from SWGOH.gg:
python sync_meta.py
```

---

## graphify
- **graphify** (`.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else. The graph already exists in the mentionned folder. 

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Database Access & Querying
The database is running outside of the local project so direct access (through CDM) is not possible. Promptthe  user with postgreSQL queries when data access is absolutely necessary, they will provide the responses. 