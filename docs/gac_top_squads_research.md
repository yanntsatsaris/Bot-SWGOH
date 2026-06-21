# Building Your Own GAC Top Squads Meta — Research & Strategy

## How swgoh.gg Gets Their Data

> **They have a privileged partnership with Capital Games.**

swgoh.gg does **not** use the same public API that Comlink wraps. Here's what they actually do:

1. **Capital Games cooperation** — CG provides swgoh.gg with access to **internal battle data** that is not exposed through any public API. This includes detailed per-battle logs: which squads attacked which, banners earned, win/loss outcome.

2. **Account sync** — When players "sync" their account on swgoh.gg, the site gets permission to read their profile data through the game's systems. This contributes to the dataset.

3. **Scale** — They process **15+ million battles per season** from synced accounts. Their "Top Squads" page aggregates:
   - Squad composition (leader + members)
   - Frequency ("Seen" count)
   - Win rate (offense) / Hold rate (defense)
   - Average banners
   - First-attempt-only data (to keep stats clean)

> [!CAUTION]
> **You cannot replicate their exact methodology.** The battle log data (who attacked whom with what teams, what banners resulted) is **private to CG** and only shared with swgoh.gg through their partnership. No API — not Comlink, not anything else — exposes this data.

---

## What YOU Can Do: Comlink Bracket Scanning

While you can't get battle logs, you **can** scan Kyber brackets during active GAC and pull every player's full roster. By analyzing top players' rosters, you can **infer** what the meta teams are.

### The Pipeline

```
┌────────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│  1. Get Events │ ──► │ 2. Enumerate │ ──► │ 3. Pull Player │ ──► │ 4. Run Your  │
│  (find active  │     │    Brackets   │     │    Rosters     │     │   Predictive │
│   GAC season)  │     │  (Kyber D1)  │     │  (/player)     │     │   Analysis   │
└────────────────┘     └──────────────┘     └────────────────┘     └──────────────┘
                                                    │
                                                    ▼
                                            ┌──────────────┐
                                            │ 5. Aggregate │
                                            │    into Meta  │
                                            │   Statistics  │
                                            └──────────────┘
```

### Step-by-Step Implementation

#### Step 1: Find the Active GAC Event

```python
async def get_active_gac_event() -> dict | None:
    """Find the currently active GAC event via /getEvents."""
    data = await _post_raw("getEvents", {}, top_level_params={"enums": True})
    
    for event in data.get("gameEvent", []):
        event_id = event.get("id", "")
        if "CHAMPIONSHIPS" not in event_id or "GRAND_ARENA" not in event_id:
            continue
        
        # Find the active instance (status == ACTIVE)
        for instance in event.get("instance", []):
            # The instance with the latest start time that hasn't ended
            return {
                "event_id": event_id,
                "instance_id": instance.get("id"),
                "event_instance_id": f"{event_id}:{instance.get('id')}",
            }
    return None
```

#### Step 2: Enumerate All Brackets in a League

```python
async def enumerate_brackets(event_instance_id: str, league: str = "KYBER") -> list[dict]:
    """
    Scan all brackets for a given league.
    Brackets start at 0 and go up. We iterate until we get an error.
    """
    all_players = []
    bracket_num = 0
    
    while True:
        group_id = f"{event_instance_id}:{league}:{bracket_num}"
        try:
            data = await _post_raw("getLeaderboard", {
                "leaderboardType": 4,
                "eventInstanceId": event_instance_id,
                "groupId": group_id,
            })
            
            players = data.get("player", data.get("leaderboardEntry", []))
            if not players:
                break
                
            for p in players:
                all_players.append({
                    "name": p.get("name"),
                    "ally_code": p.get("allyCode"),
                    "player_id": p.get("playerId"),
                    "score": p.get("score"),
                    "rank": p.get("rank"),
                    "bracket": bracket_num,
                })
            
            bracket_num += 1
            await asyncio.sleep(0.1)  # Rate limiting: ~20 req/sec max
            
        except Exception as e:
            log.info(f"Bracket scan ended at #{bracket_num}: {e}")
            break
    
    return all_players
```

#### Step 3: Pull Rosters & Predict Defenses

```python
async def analyze_player_meta(ally_code: str, fmt: str = "5v5") -> list[dict]:
    """
    Pull a player's roster and predict their likely GAC teams
    using the existing scouting engine.
    """
    profile = await get_player(ally_code)
    roster = profile.get("rosterUnit", [])
    
    omicron_dict = await get_omicron_dict()
    index = _build_roster_index(roster, omicron_dict)
    
    # Get their league for quotas
    league = "KYBER"  # We're scanning Kyber
    quotas = get_gac_quotas(league, fmt)
    
    # Use your existing prediction engine!
    zones = _predict_zones(index, quotas, fmt)
    
    # Extract the predicted teams
    predicted_teams = []
    for zone_name, teams in zones.items():
        for team in teams:
            if team.get("leader_id") and team["source"] != "empty":
                predicted_teams.append({
                    "leader_id": team["leader_id"],
                    "members_ids": team["members_ids"],
                    "zone": zone_name,
                    "source": team["source"],
                })
    
    return predicted_teams
```

#### Step 4: Aggregate into Meta Statistics

```python
from collections import Counter

async def build_meta_report(players: list[dict], fmt: str = "5v5") -> list[dict]:
    """
    For each player, predict their teams, then aggregate 
    to find the most commonly predicted squads.
    """
    team_counter = Counter()    # (leader, frozenset(members)) → count
    leader_counter = Counter()  # leader_id → count
    total_players = 0
    
    for player in players:
        try:
            teams = await analyze_player_meta(player["ally_code"], fmt)
            total_players += 1
            
            for team in teams:
                leader = team["leader_id"]
                members = tuple(sorted(team["members_ids"]))
                
                leader_counter[leader] += 1
                team_counter[(leader, members)] += 1
                
            # CRITICAL: Rate limit! /player allows ~100 req/sec
            # but be conservative
            await asyncio.sleep(0.15)
            
        except Exception as e:
            log.warning(f"Failed to analyze {player['ally_code']}: {e}")
            continue
    
    # Build the meta report
    meta_teams = []
    for (leader, members), count in team_counter.most_common(50):
        meta_teams.append({
            "leader_id": leader,
            "members_ids": list(members),
            "seen_count": count,
            "usage_rate": count / total_players if total_players else 0,
        })
    
    return meta_teams
```

---

## Feasibility Math

### How many players can you scan?

| Metric | Value |
|---|---|
| Kyber D1 brackets | ~200-500 brackets |
| Players per bracket | 8 players |
| Total Kyber D1 players | ~1,600 - 4,000 |
| `/player` rate limit | ~100 req/sec (but be conservative: 10/sec) |
| Time to scan 2,000 rosters at 10/sec | **~3-4 minutes** |
| Time to scan all 5 Kyber divisions | **~15-20 minutes** |

> [!TIP]
> This is **very feasible** as a daily cron job. You can scan all Kyber brackets in under 20 minutes and build meaningful meta statistics from 2,000-4,000 top players.

### Limitations vs swgoh.gg

| Feature | swgoh.gg | Your Comlink Scanner |
|---|---|---|
| Data source | Actual battle logs | Roster-based prediction |
| Win/Hold rates | ✅ Real data | ❌ Can't compute (no battle data) |
| Banners | ✅ Real data | ❌ Not available |
| Squad frequency | ✅ From battles | ⚠️ Predicted from rosters |
| Sample size | 15M+ battles | 2,000-4,000 rosters |
| Accuracy for "top teams" | Perfect | Good (prediction is based on roster+meta knowledge) |
| Works outside GAC | ✅ Historical | ⚠️ Brackets only during active GAC, but rosters always available |

---

## Recommended Architecture for Your Bot

### Daily Cron Job (via `discord.ext.tasks`)

```python
from discord.ext import tasks

class MetaScannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_meta_scan.start()
    
    @tasks.loop(hours=24)
    async def daily_meta_scan(self):
        """Scan Kyber brackets and rebuild meta statistics."""
        log.info("Starting daily meta scan...")
        
        # 1. Get top 50 from Kyber D1 (always available, no active GAC needed)
        top_players = await get_top50_players(league=100, division=25)
        
        # 2. Pull each player's roster
        # 3. Run predictive analysis
        # 4. Aggregate into meta stats
        meta = await build_meta_report(top_players, fmt="5v5")
        
        # 5. Save to database
        async with get_db() as db:
            await db.execute("DELETE FROM meta_teams WHERE source_url = 'comlink_scan'")
            for team in meta[:20]:  # Top 20 teams
                await db.execute("""
                    INSERT INTO meta_teams (leader_name, members, counters, format, 
                                           win_rate, usage_rate, source_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    team["leader_id"],
                    json.dumps(team["members_ids"]),
                    "[]",
                    "5v5",
                    None,  # We can't compute real win rates
                    team["usage_rate"],
                    "comlink_scan",
                ))
        
        log.info(f"Meta scan complete: {len(meta)} teams catalogued.")
```

### Key Insight: Top 50 Leaderboard Is Always Available

> [!IMPORTANT]
> You don't need to wait for active GAC to get player data! The `/getLeaderboard` type `6` (Top 50 per league/division) is **always available**. This gives you 50 player IDs from Kyber D1, and you can then call `/player` for each to get their full roster.
>
> **50 players × all 5 Kyber divisions = 250 top players** you can scan at any time, every day, without needing active GAC brackets.

### Even Better: Top 50 × 5 Leagues × 5 Divisions = 1,250 Players

```python
LEAGUES = [20, 40, 60, 80, 100]       # Carbonite → Kyber
DIVISIONS = [5, 10, 15, 20, 25]       # D5 → D1

async def scan_all_leaderboards():
    """Pull top 50 from every league/division combo. Always works."""
    all_players = []
    for league in LEAGUES:
        for division in DIVISIONS:
            try:
                data = await _post_raw("getLeaderboard", {
                    "leaderboardType": 6,
                    "league": league,
                    "division": division,
                })
                # Extract player IDs/ally codes from response
                for entry in data.get("leaderboardEntry", []):
                    all_players.append(entry)
                await asyncio.sleep(0.1)
            except Exception:
                continue
    return all_players  # Up to 1,250 players
```

This approach works **every day**, regardless of whether GAC is active. It's the most practical way to build your own meta database.
