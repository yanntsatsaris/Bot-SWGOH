# `/comlink-test` — Diagnostic Endpoint for Deployed Bot

A slash command to verify Comlink connectivity and display a player's GAC data in a rich embed, serving as a health-check and demo of the Comlink integration.

## User Review Required

> [!WARNING]
> **Existing bug discovered**: [gac_analysis.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/services/gac_analysis.py#L6) imports `get_player_arena` from `comlink.py`, but **this function does not exist** in [comlink.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/services/comlink.py). This means `/gac-stats` currently crashes on every call. The plan includes fixing this.

> [!IMPORTANT]
> **Division mapping is inverted** in [gac_analysis.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/services/gac_analysis.py#L24-L30). The wiki says `5 = Division 5` and `25 = Division 1`, but the code maps `5 → "I"` and `25 → "V"` (reversed). Should I fix this while I'm in there? The correct mapping is:
> - `5` → Division 5 (`V`)
> - `10` → Division 4 (`IV`)
> - `15` → Division 3 (`III`)
> - `20` → Division 2 (`II`)
> - `25` → Division 1 (`I`)

## Open Questions

1. **Access control**: Should `/comlink-test` be restricted to admins only, or available to all users? (I'll default to admin-only since it's a diagnostic tool.)
2. **Ally code parameter**: Should the command accept an ally code to test with, or should it use the registered player's code (from `/register`)? (I'll do both — optional param with fallback to registered code.)

---

## Proposed Changes

### Comlink Service — Fix Missing Functions

#### [MODIFY] [comlink.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/services/comlink.py)

Add the missing `get_player_arena` function (calls the `/playerArena` endpoint) and a new `check_health` function for connectivity testing:

```python
async def check_health() -> dict:
    """Ping Comlink by calling /metadata. Returns version info or raises."""
    return await _post_raw("metadata", {})

async def get_player_arena(ally_code: str) -> dict:
    """Fetch player arena data (squad/fleet arena ranks + teams)."""
    clean = str(ally_code).replace("-", "")
    return await _post_raw("playerArena", {"allyCode": clean})
```

---

### GAC Analysis — Fix Division Mapping

#### [MODIFY] [gac_analysis.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/services/gac_analysis.py)

Fix the `_DIVISION_LABELS` dict to match the actual Comlink enum values per the wiki documentation:

```diff
 _DIVISION_LABELS = {
-    5:  "I",
-    10: "II",
-    15: "III",
-    20: "IV",
-    25: "V",
+    5:  "V",
+    10: "IV",
+    15: "III",
+    20: "II",
+    25: "I",
 }
```

---

### New Cog — Comlink Test Command

#### [NEW] [comlink_test.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/cogs/comlink_test.py)

A new cog with the `/comlink-test` slash command that:

1. **Phase 1 — Health Check**: Calls `check_health()` → verifies Comlink is reachable, displays game data version + localization version
2. **Phase 2 — Player Fetch** (if ally code given): Calls `get_player()` → extracts and displays:
   - Player name, level, guild
   - `playerRating` → Skill Rating, current League & Division
   - `seasonStatus` → last 3 seasons with points, rank, league, division
3. Outputs everything in a structured Discord embed with clear ✅/❌ status indicators per check

**Command signature:**
```
/comlink-test [ally_code: optional]
```

If `ally_code` is omitted, falls back to the caller's registered code (from `players` table). If neither exists, runs only the health check.

**Embed structure:**
```
🔧 Comlink Diagnostic
├── ✅ Connectivity: OK (v0.28.6)
├── ✅ Game Version: 0.28.6:benKkO...
├── ✅ Localization: FRE_FR ready
│
├── 👤 Player: Kidori (596-966-614)
├── 🏆 Skill Rating: 2150
├── 🎖️ League: Kyber I
│
└── 📜 Season History
    ├── S40: Kyber I — #15 — 1850 pts
    ├── S39: Kyber II — #32 — 1620 pts
    └── S38: Aurodium I — #8 — 1440 pts
```

---

### Main — Register the New Cog

#### [MODIFY] [main.py](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/main.py)

Add `"cogs.comlink_test"` to the `INITIAL_EXTENSIONS` list.

---

## Verification Plan

### Automated Tests
- No automated test suite exists in the project currently.

### Manual Verification
1. Run the bot locally with Comlink Docker container running
2. Execute `/comlink-test` with no arguments → verify health check embed appears
3. Execute `/comlink-test ally_code:596966614` → verify full GAC data embed
4. Execute `/gac-stats ally_code:596966614` → verify it no longer crashes (the `get_player_arena` fix)
5. Verify division labels display correctly (Kyber **I** for division `25`, not Kyber **V**)
