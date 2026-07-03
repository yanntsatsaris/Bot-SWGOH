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

### Approach 2: Scraping swgoh.gg avec SeleniumBase UC (✅ VIABLE — Full Data)

swgoh.gg est la **seule** source qui affiche l'historique détaillé des matchs GAC round par round.
L'URL est :
```
https://swgoh.gg/p/{ally_code}/gac-history/
```

Cette page contient :
- Les équipes posées en défense
- Les équipes utilisées en attaque
- Les bannières marquées par round
- Le résultat final (win/loss)

**Le problème initial (Résolu le 03/07/2026) :**
swgoh.gg utilise la protection redoutable **Cloudflare Turnstile**. Les bibliothèques standards (`curl_cffi`, `playwright`, `cloudscraper`) échouent toutes face au mode "Headless".

**La Solution Architecturale (SeleniumBase UC + Xvfb) :**
Grâce à un test grandeur nature, nous avons prouvé qu'il est possible de vaincre Cloudflare Turnstile sur un serveur Linux en ligne de commande en utilisant :
1. **Xvfb (X Virtual Framebuffer)** : Pour créer un faux écran système.
2. **Google Chrome installé nativement**.
3. **SeleniumBase en mode UC (Undetected Chromedriver)** : Qui recompile le driver pour cacher l'automatisation.
4. **La méthode `sb.uc_gui_click_captcha()`** : Une IA intégrée qui vise et clique le widget Turnstile physiquement.

**Conséquences pour le bot :**
Cette victoire change totalement la donne. Le bot n'a plus à dépendre uniquement des logs manuels (`/gac-log-round`). Il peut **extraire automatiquement** le vrai historique des adversaires.

**Points d'attention (Downsides gérables) :**
- L'extraction prend environ 15-20 secondes par profil (à cause du défi Turnstile).
- Il faut concevoir ce scraper comme une tâche de fond asynchrone (Background Task) pour ne pas bloquer les commandes Discord.
- La structure HTML de swgoh.gg (`div` et `classes`) devra être parsée avec BeautifulSoup.

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
