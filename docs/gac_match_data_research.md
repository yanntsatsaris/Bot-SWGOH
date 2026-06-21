# Getting GAC Match Data for a Player — Complete Research

## TL;DR — The Hard Truth

**Detailed GAC match data (teams used per round, banners, attack/defense logs) is NOT available from any public API.** Capital Games does not expose this data. Here's what actually exists:

---

## What Data Is Available (and Where)

| Data | Source | How |
|---|---|---|
| Skill Rating, League, Division | **Comlink** `/player` | `playerRating` + `seasonStatus` fields |
| Last 3 season summaries (points, rank) | **Comlink** `/player` | `seasonStatus` array |
| Players in same bracket (during active GAC) | **Comlink** `/getLeaderboard` type `4` | Requires `eventInstanceId` + `groupId` |
| Global top 50 per league/division | **Comlink** `/getLeaderboard` type `6` | League + division IDs |
| Player's full roster (all units + gear/relics) | **Comlink** `/player` | `rosterUnit` array |
| **Teams used, banners, round results** | **swgoh.gg website only** | 🔒 Web scraping required |
| GAC Meta Report (aggregated counters) | **swgoh.gg website only** | 🔒 Web scraping required |

---

## The 3 Possible Approaches

### Approach 1: Comlink Bracket Scouting (✅ Viable — Partial Data)

During an **active GAC**, you can enumerate all players in a bracket. For each player, you can pull their full roster. This is exactly what your bot's scouting engine already does.

**What you get:**
- Who's in the player's bracket
- Each opponent's full roster (units, gear, relics, mods)
- Each opponent's league/division/skill rating

**What you DON'T get:**
- What teams they actually placed on defense
- What teams they attacked with
- Banners scored per match
- Win/loss per round

**How it works:**

```python
# 1. Get the current GAC event
events = await comlink._post_raw("getEvents", {})
gac_event = next(e for e in events.get("gameEvent", []) if "CHAMPIONSHIPS" in e.get("id", ""))

# 2. Build eventInstanceId from the event
event_id = gac_event["id"]
instance_id = gac_event["instance"][0]["id"]  # e.g., "O1718000000000"
event_instance_id = f"{event_id}:{instance_id}"

# 3. Iterate brackets for a given league
for bracket_num in range(200):  # brackets start at 0
    group_id = f"{event_instance_id}:KYBER:{bracket_num}"
    try:
        data = await comlink._post_raw("getLeaderboard", {
            "leaderboardType": 4,
            "eventInstanceId": event_instance_id,
            "groupId": group_id,
        })
        # data contains a list of players in this bracket
        # Check if your target player is here
        for player in data.get("player", []):
            if player.get("allyCode") == target_ally_code:
                # Found them! All bracket members are in data["player"]
                pass
    except:
        break  # No more brackets
```

> ⚠️ **Only works during active GAC.** Brackets are transient — they disappear between seasons.

---

### Approach 2: Scraping swgoh.gg with Playwright (⚠️ Complex — Full Data)

swgoh.gg is the **only** source that shows detailed per-round GAC history. The URL pattern is:
```
https://swgoh.gg/p/{ally_code}/gac-history/
```

This page shows:
- Every GAC round with opponent name
- Teams placed on defense (both players)
- Teams used on offense (both players)  
- Banners scored per attack
- Final result (win/loss)

**The problem (as noted in your dev_notes.md):**
> Scraping web direct est écarté — swgoh.gg uses **Cloudflare Turnstile** protection. `curl_cffi` and `cloudscraper` both fail with 403. You need a **real browser** (Playwright/Selenium) to pass the invisible CAPTCHA.

**If you want to pursue this:**

```python
# Requires: pip install playwright
# Then: playwright install chromium

from playwright.async_api import async_playwright

async def scrape_gac_history(ally_code: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = f"https://swgoh.gg/p/{ally_code}/gac-history/"
        await page.goto(url, wait_until="networkidle")
        
        # Wait for Cloudflare challenge to complete
        await page.wait_for_timeout(5000)
        
        # The GAC history page loads data via XHR — intercept it
        # or parse the rendered DOM
        content = await page.content()
        
        await browser.close()
        return parse_gac_html(content)
```

**Downsides:**
- Heavy dependency (Chromium binary ~400MB)
- Fragile (Cloudflare may block headless browsers)
- Slow (~5-10s per page load)
- Can break if swgoh.gg changes HTML structure
- Rate limiting risk (IP ban)

---

### Approach 3: Self-Reported Data via Discord Bot (✅ Recommended Practical Path)

This is what your bot is already building toward (per dev_notes.md). Instead of trying to extract data from external sources, **let users report their matches** and let the bot learn over time.

**Already implemented:**
- `/gac-report-match` — manual defense reporting (in `cogs/gac_scout.py`)
- `gac_history` table — stores enemy defenses
- `counter_performance` table — tracks wins/losses per counter

**What to add for "full match info":**

```sql
-- New table: complete round tracking
CREATE TABLE IF NOT EXISTS gac_rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id       TEXT    NOT NULL,
    round_number    INTEGER NOT NULL,
    player_code     TEXT    NOT NULL,
    opponent_code   TEXT    NOT NULL,
    opponent_name   TEXT,
    result          TEXT    CHECK(result IN ('win', 'loss')),
    player_banners  INTEGER,
    opponent_banners INTEGER,
    format          TEXT    NOT NULL CHECK(format IN ('3v3', '5v5')),
    recorded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- New table: teams used per round
CREATE TABLE IF NOT EXISTS gac_round_teams (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
    side            TEXT    NOT NULL CHECK(side IN ('offense', 'defense')),
    owner           TEXT    NOT NULL CHECK(owner IN ('player', 'opponent')),
    zone            TEXT,
    leader_id       TEXT    NOT NULL,
    members_ids     TEXT    NOT NULL,
    banners         INTEGER
);
```

**New slash command concept:**
```
/gac-log-round 
    opponent_code: 123-456-789
    result: win
    player_banners: 1750
    opponent_banners: 1200
```

This approach:
- ✅ Works always (not just during active GAC)
- ✅ No external dependencies
- ✅ Builds a private dataset unique to your guild
- ✅ Feeds the counter_performance learning system
- ❌ Requires manual input from users

---

## Recommendation

Given the constraints documented in your [dev_notes.md](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/dev_notes.md):

1. **Short term**: Use **Comlink bracket scouting** (Approach 1) to identify opponents and pull their rosters during active GAC. Your scouting engine already does the prediction.

2. **Medium term**: Build the **self-reported match system** (Approach 3) with `/gac-log-round`. This feeds your `counter_performance` learning loop.

3. **Long term (optional)**: If the data need becomes critical, set up a **Playwright scraper** (Approach 2) running on a schedule to pull GAC history from swgoh.gg for registered players. This is the most brittle but most data-rich option.
