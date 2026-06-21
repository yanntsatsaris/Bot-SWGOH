# Fetching GAC Data via swgoh-comlink

> [!IMPORTANT]
> **Prerequisite**: You need a running instance of swgoh-comlink (Docker or binary). It acts as a proxy to the game's API and exposes a local HTTP server (default port `3000`).

---

## Overview — 3 Ways to Get GAC Data

| Approach | Endpoint | What you get |
|---|---|---|
| **Player GAC profile** | `POST /player` | Current Skill Rating, League, Division, last 3 season summaries |
| **GAC Bracket leaderboard** | `POST /getLeaderboard` (type `4`) | All players in a specific bracket during an active GAC |
| **GAC Top 50 leaderboard** | `POST /getLeaderboard` (type `6`) | Global top 50 per league + division |

---

## 1. Player GAC Profile (`/player`)

This is the **primary way** to get a specific player's GAC data. The response contains two key fields:

### Request

```http
POST http://localhost:3000/player
Content-Type: application/json

{
  "payload": {
    "allyCode": "123456789"
  },
  "enums": false
}
```

You can use `allyCode` OR `playerId` (the player's GUID).

### GAC-relevant fields in the response

#### `playerRating`
The player's **current** Grand Arena Skill Rating, League, and Division.

```json
"playerRating": [
  {
    "ratingType": "...",
    "playerSkillRating": {
      "skillRating": 2150
    },
    "playerRankStatus": {
      "leagueId": "KYBER",
      "divisionId": 25
    }
  }
]
```

#### `seasonStatus`
A list of the **last 3 GAC seasons** with detailed info:

```json
"seasonStatus": [
  {
    "seasonId": "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_40",
    "eventInstanceId": "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_40:O1718000000000",
    "league": "KYBER",       // or integer if enums: false
    "seasonPoints": "1850",
    "division": 25,          // see division mapping below
    "joinTime": "1718000000000",
    "endTime": "1720000000000",
    "rank": 15
  }
]
```

| Field | Description |
|---|---|
| `seasonId` | Identifier for the GAC season |
| `eventInstanceId` | Season + instance (includes Unix epoch start time) |
| `league` | Current league (enum or integer) |
| `seasonPoints` | Points earned this season (recalculated each round) |
| `division` | Current division (recalculated each round) |
| `joinTime` | Unix epoch ms when the player joined |
| `endTime` | Unix epoch ms when the season ends |
| `rank` | Current rank within league/division |
| `wins` / `losses` | ⚠️ **INACTIVE** — not populated |

#### `lifetimeSeasonScore`
Top-level field on the player profile — the legacy lifetime GAC score (no longer actively used).

---

## 2. GAC Bracket Leaderboard (`/getLeaderboard` type `4`)

> [!WARNING]
> **Only available while a GAC event is actively running.** Brackets load progressively and not always in order.

This lets you see all players in a **specific bracket** during an active GAC season.

### Request

```http
POST http://localhost:3000/getLeaderboard
Content-Type: application/json

{
  "payload": {
    "leaderboardType": 4,
    "eventInstanceId": "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_40:O1718000000000",
    "groupId": "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_40:O1718000000000:KYBER:100"
  },
  "enums": false
}
```

### How to build `eventInstanceId` and `groupId`

1. Call `POST /getEvents` → find the GAC event (look for `type = 10`)
2. `eventInstanceId` = `{eventId}:{instanceId}`
   - Example: `CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_40:O1718000000000`
3. `groupId` = `{eventInstanceId}:{LEAGUE_NAME}:{bracketNumber}`
   - Example: `...SEASON_40:O1718000000000:KYBER:100`
   - Brackets start at `0` and increment. Iterate until you find all brackets.

---

## 3. GAC Top 50 Leaderboard (`/getLeaderboard` type `6`)

Returns the **global top 50 players** for a given league + division.

### Request

```http
POST http://localhost:3000/getLeaderboard
Content-Type: application/json

{
  "payload": {
    "leaderboardType": 6,
    "league": 100,
    "division": 25
  },
  "enums": false
}
```

---

## Enum Reference Tables

### Leagues

| Integer | Name |
|---|---|
| `20` | Carbonite |
| `40` | Bronzium |
| `60` | Chromium |
| `80` | Aurodium |
| `100` | Kyber |

### Divisions

| Integer | Division |
|---|---|
| `5` | Division 5 |
| `10` | Division 4 |
| `15` | Division 3 |
| `20` | Division 2 |
| `25` | Division 1 |

---

## Python Example for Your Bot

Here's a ready-to-use helper module that integrates with your existing project:

```python
import aiohttp

COMLINK_URL = "http://localhost:3000"  # adjust to your setup


async def get_player_gac_data(ally_code: str) -> dict:
    """
    Fetch a player's GAC data (skill rating, league, division, season history).
    Returns a dict with keys: playerRating, seasonStatus, lifetimeSeasonScore
    """
    async with aiohttp.ClientSession() as session:
        payload = {
            "payload": {"allyCode": ally_code},
            "enums": True  # use True for human-readable league names
        }
        async with session.post(f"{COMLINK_URL}/player", json=payload) as resp:
            data = await resp.json()
    
    return {
        "playerRating": data.get("playerRating", []),
        "seasonStatus": data.get("seasonStatus", []),
        "lifetimeSeasonScore": data.get("lifetimeSeasonScore", "0"),
    }


async def get_gac_bracket(event_instance_id: str, group_id: str) -> dict:
    """
    Fetch a GAC bracket leaderboard (only works during active GAC).
    """
    async with aiohttp.ClientSession() as session:
        payload = {
            "payload": {
                "leaderboardType": 4,
                "eventInstanceId": event_instance_id,
                "groupId": group_id,
            },
            "enums": False,
        }
        async with session.post(f"{COMLINK_URL}/getLeaderboard", json=payload) as resp:
            return await resp.json()


async def get_gac_top50(league: int = 100, division: int = 25) -> dict:
    """
    Fetch the global top 50 for a league/division.
    Defaults to Kyber Division 1.
    """
    async with aiohttp.ClientSession() as session:
        payload = {
            "payload": {
                "leaderboardType": 6,
                "league": league,
                "division": division,
            },
            "enums": False,
        }
        async with session.post(f"{COMLINK_URL}/getLeaderboard", json=payload) as resp:
            return await resp.json()


# --- Constants ---
LEAGUES = {20: "Carbonite", 40: "Bronzium", 60: "Chromium", 80: "Aurodium", 100: "Kyber"}
DIVISIONS = {5: "Division 5", 10: "Division 4", 15: "Division 3", 20: "Division 2", 25: "Division 1"}
```

---

## What You **Cannot** Get from Comlink

> [!CAUTION]
> Comlink **cannot** retrieve:
> - Detailed GAC battle logs (attack/defense replays, teams used per round)
> - Historical match results (who fought whom, banners scored)
> - The `wins`/`losses` fields in `seasonStatus` are **INACTIVE** and not populated
> 
> Comlink only exposes read-only data equivalent to what you can see when clicking on another player's profile in-game.

---

## Next Steps for Your Bot

Given your [dev_notes.md](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/dev_notes.md) context:

1. **Set up Comlink** — Run via Docker: `docker run --name swgoh-comlink -d -p 3200:3000 -e APP_NAME=bot-swgoh ghcr.io/swgoh-utils/swgoh-comlink:latest`
2. **Use `/player` endpoint** — To get a player's current league, division, skill rating, and last 3 season summaries
3. **Use `/getLeaderboard` type 4** — During active GAC, to scout who's in a player's bracket
4. **Store in SQLite** — Feed the `seasonStatus` data into your existing `gac_history` table for tracking over time
