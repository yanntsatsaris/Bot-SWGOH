# Plan d'Implémentation : Scan GAC Complet & Historique

> Dossier : `docs/` | Juillet 2026  
> Objectif : Construire un historique GAC complet via scan de tous les brackets Comlink + auto-report des joueurs

---

## Vue d'ensemble

Ce plan implémente un système en **3 piliers** qui fonctionnent ensemble :

```
┌─────────────────────────────────────────────────────────────────┐
│                    SYSTÈME HISTORIQUE GAC                        │
│                                                                  │
│  PILIER 1            PILIER 2              PILIER 3              │
│  Scan Brackets       Top 50 Quotidien      Auto-Report           │
│  (pendant GAC)       (toujours)            (continu)             │
│       │                   │                    │                  │
│       └──────────────────┼────────────────────┘                  │
│                          ▼                                        │
│                 gac_roster_snapshots                              │
│                 gac_roster_units                                  │
│                 gac_rounds (auto-report)                          │
│                 gac_round_teams (auto-report)                     │
│                          │                                        │
│                          ▼                                        │
│              Moteur de Recommandation                             │
│         (roster + méta + win rates réels)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Base de Données

### 1.1 Nouvelles tables à créer

**Fichier à modifier :** [`database/models.py`](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/database/models.py)

```sql
-- Snapshot roster d'un joueur à un instant T (par saison)
CREATE TABLE IF NOT EXISTS gac_roster_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    TEXT    NOT NULL,
    ally_code    TEXT,
    player_name  TEXT,
    guild_id     TEXT,
    league       INTEGER,          -- 20=Carbonite, 40=Bronzium, 60=Chromium, 80=Aurodium, 100=Kyber
    division     INTEGER,          -- 5=D5, 10=D4, 15=D3, 20=D2, 25=D1
    skill_rating INTEGER,
    season_id    TEXT    NOT NULL, -- ex: "CHAMPIONSHIPS_GA2_EVENT_SEASON_42"
    scanned_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, season_id)   -- Un seul snapshot par joueur par saison
);

-- Unités de chaque snapshot (données réduites)
CREATE TABLE IF NOT EXISTS gac_roster_units (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES gac_roster_snapshots(id) ON DELETE CASCADE,
    unit_id     TEXT    NOT NULL,
    relic_tier  INTEGER DEFAULT 0,
    gear_tier   INTEGER DEFAULT 0,
    stars       INTEGER DEFAULT 7,
    has_omicron INTEGER DEFAULT 0,  -- 0 ou 1
    combat_type INTEGER DEFAULT 1   -- 1=perso, 2=vaisseau
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_snapshots_season ON gac_roster_snapshots(season_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_league  ON gac_roster_snapshots(league, division);
CREATE INDEX IF NOT EXISTS idx_units_snapshot    ON gac_roster_units(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_units_unit        ON gac_roster_units(unit_id);

-- Rounds GAC auto-reportés par les joueurs
CREATE TABLE IF NOT EXISTS gac_rounds (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id        TEXT    NOT NULL,
    round_number     INTEGER NOT NULL,  -- 1, 2 ou 3
    player_code      TEXT    NOT NULL,
    opponent_code    TEXT,
    opponent_name    TEXT,
    result           TEXT    CHECK(result IN ('win','loss','draw')),
    player_banners   INTEGER,
    opponent_banners INTEGER,
    format           TEXT    NOT NULL CHECK(format IN ('3v3','5v5')),
    recorded_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Équipes utilisées dans chaque round auto-reporté
CREATE TABLE IF NOT EXISTS gac_round_teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id    INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
    side        TEXT    NOT NULL CHECK(side IN ('offense','defense')),
    owner       TEXT    NOT NULL CHECK(owner IN ('player','opponent')),
    zone        TEXT,                -- 'North', 'South', 'Back', 'Fleet'
    leader_id   TEXT    NOT NULL,
    members_ids TEXT    NOT NULL,    -- JSON array ["SLKR", "HUXTA", ...]
    banners     INTEGER,
    success     INTEGER              -- 1=tenu/gagné, 0=cassé/perdu
);
```

### 1.2 Migrations à effectuer

**Fichier :** [`migrate.py`](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/migrate.py) — Ajouter les nouvelles tables via le script de migration existant.

---

## Phase 2 — Service de Scan

### 2.1 Nouveau fichier : `services/gac_scanner.py`

Ce service contient toute la logique de scan. Il est **autonome** et peut être appelé depuis un cog Discord ou manuellement.

```python
"""
services/gac_scanner.py
Scan complet des brackets GAC (toutes ligues, toutes divisions).
"""
import asyncio
import logging
import json
from database.db import get_db
from services.comlink import _post_raw  # ou la fonction brute déjà disponible

log = logging.getLogger(__name__)

LEAGUES = {
    "CARBONITE": 20,
    "BRONZIUM":  40,
    "CHROMIUM":  60,
    "AURODIUM":  80,
    "KYBER":     100,
}
DIVISIONS = {25: 1, 20: 2, 15: 3, 10: 4, 5: 5}

# ─── PHASE 1 : Trouver le GAC actif ────────────────────────────────────────

async def get_active_gac_event() -> dict | None:
    """Retourne l'eventInstanceId du GAC en cours, ou None si aucun."""
    data = await _post_raw("getEvents", {})
    for event in data.get("gameEvent", []):
        eid = event.get("id", "")
        if "CHAMPIONSHIPS" in eid and "GRAND_ARENA" in eid:
            for instance in event.get("instance", []):
                iid = instance.get("id", "")
                if iid:
                    return {
                        "event_id":          eid,
                        "instance_id":       iid,
                        "event_instance_id": f"{eid}:{iid}",
                        "season_id":         eid,
                    }
    return None

# ─── PHASE 2 : Scanner tous les brackets d'une ligue ───────────────────────

async def scan_brackets_for_league(
    event_instance_id: str,
    league_name: str,
) -> list[dict]:
    """
    Énumère tous les brackets d'une ligue.
    Retourne une liste de dicts {player_id, ally_code, name, league, division, skill_rating}.
    """
    players = []
    bracket_num = 0

    while True:
        group_id = f"{event_instance_id}:{league_name}:{bracket_num}"
        try:
            data = await _post_raw("getLeaderboard", {
                "leaderboardType": 4,
                "eventInstanceId": event_instance_id,
                "groupId":         group_id,
            })
            entries = data.get("player", data.get("leaderboardEntry", []))
            if not entries:
                break

            for p in entries:
                players.append({
                    "player_id":    p.get("playerId") or p.get("id"),
                    "ally_code":    p.get("allyCode"),
                    "name":         p.get("name"),
                    "league":       LEAGUES.get(league_name, 0),
                    "division":     p.get("divisionId", 25),
                    "skill_rating": p.get("score") or p.get("skillRating", 0),
                })

            bracket_num += 1
            await asyncio.sleep(0.1)  # ~10 req/sec

        except Exception as e:
            log.debug(f"Fin brackets {league_name} à #{bracket_num}: {e}")
            break

    log.info(f"[{league_name}] {len(players)} joueurs dans {bracket_num} brackets")
    return players

# ─── PHASE 3 : Récupérer et stocker les rosters ────────────────────────────

async def fetch_and_store_roster(
    player_info: dict,
    season_id: str,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Récupère le roster d'un joueur et le stocke en BDD."""
    async with semaphore:
        try:
            from services.comlink import get_player
            profile = await get_player(
                player_info.get("ally_code") or player_info["player_id"]
            )
            if not profile:
                return False

            roster = profile.get("rosterUnit", [])

            async with get_db() as db:
                # Insérer ou ignorer (UNIQUE constraint sur player_id+season_id)
                cursor = await db.execute("""
                    INSERT OR IGNORE INTO gac_roster_snapshots
                        (player_id, ally_code, player_name, guild_id,
                         league, division, skill_rating, season_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_info["player_id"],
                    player_info.get("ally_code"),
                    profile.get("name"),
                    profile.get("guildId"),
                    player_info.get("league", 0),
                    player_info.get("division", 25),
                    player_info.get("skill_rating", 0),
                    season_id,
                ))
                snapshot_id = cursor.lastrowid

                if snapshot_id:  # Nouveau snapshot (pas de doublon)
                    for unit in roster:
                        def_id  = unit.get("definitionId", "")
                        unit_id = def_id.split(":")[0] if ":" in def_id else def_id
                        raw_rel = (unit.get("relic") or {}).get("currentTier", 0)
                        relic   = max(0, raw_rel - 2) if raw_rel >= 2 else 0

                        await db.execute("""
                            INSERT INTO gac_roster_units
                                (snapshot_id, unit_id, relic_tier, gear_tier,
                                 stars, combat_type)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            snapshot_id,
                            unit_id,
                            relic,
                            unit.get("currentTier", 0),
                            unit.get("currentRarity", 7),
                            unit.get("combatType", 1),
                        ))

                await db.commit()
            return True

        except Exception as e:
            log.warning(f"Erreur roster {player_info.get('player_id')}: {e}")
            return False
        finally:
            await asyncio.sleep(0.033)  # throttle entre requêtes

# ─── SCAN PRINCIPAL ─────────────────────────────────────────────────────────

async def run_full_gac_scan(
    concurrency: int = 30,
    leagues: list[str] | None = None,
) -> dict:
    """
    Lance le scan complet de tous les brackets GAC.
    Durée estimée : 3-4 heures pour toutes les ligues.

    Args:
        concurrency: Nombre de requêtes /player simultanées (défaut: 30)
        leagues: Liste des ligues à scanner (défaut: toutes)

    Returns:
        Rapport du scan {total_players, success, errors, duration_sec}
    """
    import time
    start = time.time()

    # 1. Trouver le GAC actif
    gac = await get_active_gac_event()
    if not gac:
        log.error("Aucun GAC actif ! Le scan bracket ne peut pas démarrer.")
        return {"error": "Aucun GAC actif"}

    event_instance_id = gac["event_instance_id"]
    season_id         = gac["season_id"]
    log.info(f"GAC actif : {season_id}")

    # 2. Scanner tous les brackets (Phase 1)
    target_leagues = leagues or list(LEAGUES.keys())
    all_players: list[dict] = []
    seen_ids: set[str] = set()

    for league in target_leagues:
        players = await scan_brackets_for_league(event_instance_id, league)
        for p in players:
            pid = p.get("player_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_players.append(p)

    log.info(f"Phase 1 terminée : {len(all_players)} joueurs uniques")

    # 3. Récupérer les rosters (Phase 2)
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        fetch_and_store_roster(p, season_id, semaphore)
        for p in all_players
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if r is True)
    errors  = len(results) - success
    duration = round(time.time() - start)

    log.info(f"Scan terminé : {success}/{len(all_players)} OK en {duration}s")
    return {
        "season_id":     season_id,
        "total_players": len(all_players),
        "success":       success,
        "errors":        errors,
        "duration_sec":  duration,
    }

# ─── SCAN TOP 50 (toujours disponible) ─────────────────────────────────────

async def run_top50_scan() -> dict:
    """
    Scan le Top 50 de chaque ligue/division.
    Fonctionne même hors GAC. Durée : ~5-10 minutes.
    """
    import time
    start = time.time()

    all_players = []
    seen_ids: set[str] = set()

    for league_val in LEAGUES.values():        # 20, 40, 60, 80, 100
        for div_val in DIVISIONS.keys():        # 25, 20, 15, 10, 5
            try:
                data = await _post_raw("getLeaderboard", {
                    "leaderboardType": 6,
                    "league":          league_val,
                    "division":        div_val,
                })
                for entry in data.get("leaderboardEntry", []):
                    pid = entry.get("playerId") or entry.get("id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        all_players.append({
                            "player_id":    pid,
                            "ally_code":    entry.get("allyCode"),
                            "name":         entry.get("name"),
                            "league":       league_val,
                            "division":     div_val,
                            "skill_rating": entry.get("score", 0),
                        })
                await asyncio.sleep(0.1)
            except Exception as e:
                log.warning(f"Erreur Top50 {league_val}/{div_val}: {e}")

    log.info(f"Top50 scan : {len(all_players)} joueurs uniques")

    # Récupérer les rosters
    # Note: pas de season_id pendant hors-GAC, on utilise "TOP50_SCAN"
    semaphore = asyncio.Semaphore(20)
    results = await asyncio.gather(
        *[fetch_and_store_roster(p, "TOP50_DAILY", semaphore) for p in all_players],
        return_exceptions=True
    )

    return {
        "total_players": len(all_players),
        "success":       sum(1 for r in results if r is True),
        "duration_sec":  round(time.time() - start),
    }
```

---

## Phase 3 — Cog Discord : Scanner & Auto-Report

### 3.1 Nouveau fichier : `cogs/gac_scanner.py`

```python
"""
cogs/gac_scanner.py
Commandes Discord pour lancer le scan GAC et l'auto-report des combats.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import json

from services.gac_scanner import run_full_gac_scan, run_top50_scan
from database.db import get_db

log = logging.getLogger(__name__)

class GacScannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_top50.start()   # Cron quotidien Top 50

    def cog_unload(self):
        self.daily_top50.cancel()

    # ─── CRON QUOTIDIEN ────────────────────────────────────────────────────

    @tasks.loop(hours=24)
    async def daily_top50(self):
        """Scan automatique du Top 50 chaque jour à minuit."""
        log.info("[CRON] Démarrage du scan Top 50 quotidien...")
        result = await run_top50_scan()
        log.info(f"[CRON] Top 50 terminé : {result}")

    @daily_top50.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    # ─── COMMANDE ADMIN : Lancer le scan complet ───────────────────────────

    @app_commands.command(
        name="gac-scan-start",
        description="[ADMIN] Lance le scan complet de tous les brackets GAC."
    )
    @app_commands.default_permissions(administrator=True)
    async def gac_scan_start(
        self,
        interaction: discord.Interaction,
        leagues: str = "ALL",  # "ALL" ou "KYBER,AURODIUM"
    ):
        await interaction.response.defer(ephemeral=True)

        target_leagues = None
        if leagues.upper() != "ALL":
            target_leagues = [l.strip().upper() for l in leagues.split(",")]

        embed = discord.Embed(
            title="🚀 Scan GAC démarré",
            description=(
                f"Ligues : `{leagues}`\n"
                "Durée estimée : **3-4 heures** pour un scan complet.\n"
                "Le bot continue à fonctionner normalement pendant le scan."
            ),
            color=0x00D4FF
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Lancer en background (ne bloque pas Discord)
        result = await run_full_gac_scan(
            concurrency=30,
            leagues=target_leagues,
        )

        # Notifier le résultat dans le channel (si disponible)
        log.info(f"Scan terminé : {result}")

    # ─── COMMANDE ADMIN : Scan Top 50 manuel ───────────────────────────────

    @app_commands.command(
        name="gac-scan-top50",
        description="[ADMIN] Scan manuel du Top 50 toutes ligues/divisions."
    )
    @app_commands.default_permissions(administrator=True)
    async def gac_scan_top50(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await run_top50_scan()
        embed = discord.Embed(
            title="✅ Scan Top 50 terminé",
            description=(
                f"**{result['success']}** / **{result['total_players']}** rosters stockés\n"
                f"Durée : {result['duration_sec']}s"
            ),
            color=0x00FF99
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /gac-log-round : Auto-report d'un round ───────────────────────────

    @app_commands.command(
        name="gac-log-round",
        description="Enregistre le résultat d'un round de GAC."
    )
    @app_commands.describe(
        season   = "Numéro de la saison (ex: 42)",
        round_nb = "Numéro du round (1, 2 ou 3)",
        result   = "Résultat du round",
        my_banners  = "Tes banners",
        opp_banners = "Banners de l'adversaire",
        opp_code    = "Ally code de l'adversaire (optionnel)",
        format      = "Format du GAC",
    )
    @app_commands.choices(result=[
        app_commands.Choice(name="✅ Victoire", value="win"),
        app_commands.Choice(name="❌ Défaite",  value="loss"),
        app_commands.Choice(name="🤝 Égalité",  value="draw"),
    ])
    @app_commands.choices(format=[
        app_commands.Choice(name="5v5", value="5v5"),
        app_commands.Choice(name="3v3", value="3v3"),
    ])
    async def gac_log_round(
        self,
        interaction: discord.Interaction,
        season:      int,
        round_nb:    app_commands.Range[int, 1, 3],
        result:      str,
        my_banners:  int,
        opp_banners: int,
        format:      str = "5v5",
        opp_code:    str = "",
    ):
        await interaction.response.defer(ephemeral=True)

        season_id = f"CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_{season}"

        async with get_db() as db:
            cursor = await db.execute("""
                INSERT INTO gac_rounds
                    (season_id, round_number, player_code, opponent_code,
                     result, player_banners, opponent_banners, format)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                season_id,
                round_nb,
                str(interaction.user.id),
                opp_code or None,
                result,
                my_banners,
                opp_banners,
                format,
            ))
            round_id = cursor.lastrowid
            await db.commit()

        emoji = {"win": "✅", "loss": "❌", "draw": "🤝"}[result]
        embed = discord.Embed(
            title=f"{emoji} Round {round_nb} enregistré — Saison {season}",
            description=(
                f"**Résultat :** {result.upper()}\n"
                f"**Banners :** {my_banners} vs {opp_banners}\n"
                f"**Round ID :** `{round_id}`\n\n"
                "Utilise `/gac-log-team` pour ajouter les équipes de ce round."
            ),
            color=0x00FF99 if result == "win" else 0xFF4444
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /gac-log-team : Ajouter une équipe à un round ─────────────────────

    @app_commands.command(
        name="gac-log-team",
        description="Ajoute une équipe à un round GAC déjà enregistré."
    )
    @app_commands.describe(
        round_id  = "ID du round (fourni par /gac-log-round)",
        side      = "Attaque ou Défense",
        owner     = "Ton équipe ou celle de l'adversaire",
        leader    = "ID du leader (ex: LORDVADER)",
        members   = "Membres séparés par virgule (ex: MOFF_GIDEON,RANGE_TROOPER)",
        zone      = "Zone (North/South/Back/Fleet)",
        banners   = "Banners obtenus avec cette équipe",
        success   = "L'équipe a-t-elle tenu/gagné ?",
    )
    @app_commands.choices(side=[
        app_commands.Choice(name="⚔️ Attaque",  value="offense"),
        app_commands.Choice(name="🛡️ Défense", value="defense"),
    ])
    @app_commands.choices(owner=[
        app_commands.Choice(name="Moi",          value="player"),
        app_commands.Choice(name="Adversaire",   value="opponent"),
    ])
    async def gac_log_team(
        self,
        interaction: discord.Interaction,
        round_id:   int,
        side:       str,
        owner:      str,
        leader:     str,
        members:    str,
        zone:       str = "",
        banners:    int = 0,
        success:    bool = True,
    ):
        await interaction.response.defer(ephemeral=True)

        members_list = [m.strip().upper() for m in members.split(",") if m.strip()]
        members_json = json.dumps(members_list)

        async with get_db() as db:
            await db.execute("""
                INSERT INTO gac_round_teams
                    (round_id, side, owner, zone, leader_id, members_ids, banners, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                round_id,
                side,
                owner,
                zone or None,
                leader.upper(),
                members_json,
                banners,
                1 if success else 0,
            ))
            await db.commit()

        embed = discord.Embed(
            title="✅ Équipe enregistrée",
            description=(
                f"**Round :** `{round_id}` | **Zone :** {zone or 'N/A'}\n"
                f"**Leader :** `{leader.upper()}`\n"
                f"**Membres :** {', '.join(f'`{m}`' for m in members_list)}\n"
                f"**Banners :** {banners} | **Succès :** {'✅' if success else '❌'}"
            ),
            color=0x00FF99
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(GacScannerCog(bot))
```

---

## Phase 4 — Requêtes d'Analyse (Méta)

### 4.1 Nouveau fichier : `services/gac_meta_analyzer.py`

```python
"""
services/gac_meta_analyzer.py
Analyse les snapshots stockés pour générer des statistiques méta.
"""
import json
from database.db import get_db

async def get_unit_usage_rate(
    unit_id: str,
    season_id: str | None = None,
    league: int | None = None,
    min_relic: int = 5,
) -> dict:
    """
    Calcule le taux d'utilisation d'un personnage parmi les joueurs scannés.
    
    Returns: {"unit_id", "total_players", "players_with_unit", "usage_rate"}
    """
    async with get_db() as db:
        # Filtres dynamiques
        where = []
        params = []
        if season_id:
            where.append("s.season_id = ?")
            params.append(season_id)
        if league:
            where.append("s.league = ?")
            params.append(league)
        where_clause = "WHERE " + " AND ".join(where) if where else ""

        # Total joueurs
        async with db.execute(
            f"SELECT COUNT(DISTINCT s.id) FROM gac_roster_snapshots s {where_clause}",
            params
        ) as cur:
            total = (await cur.fetchone())[0]

        # Joueurs ayant ce perso au niveau requis
        query = f"""
            SELECT COUNT(DISTINCT s.id)
            FROM gac_roster_snapshots s
            JOIN gac_roster_units u ON u.snapshot_id = s.id
            {where_clause}
            {'AND' if where_clause else 'WHERE'} u.unit_id = ? AND u.relic_tier >= ?
        """
        async with db.execute(query, params + [unit_id, min_relic]) as cur:
            with_unit = (await cur.fetchone())[0]

    return {
        "unit_id":         unit_id,
        "total_players":   total,
        "players_with_unit": with_unit,
        "usage_rate":      round(with_unit / total * 100, 1) if total else 0,
    }


async def get_top_units_by_league(
    season_id: str,
    league: int,
    limit: int = 20,
    min_relic: int = 5,
) -> list[dict]:
    """
    Retourne les personnages les plus répandus dans une ligue.
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT u.unit_id,
                   COUNT(DISTINCT s.id) as player_count
            FROM gac_roster_snapshots s
            JOIN gac_roster_units u ON u.snapshot_id = s.id
            WHERE s.season_id = ?
              AND s.league    = ?
              AND u.relic_tier >= ?
              AND u.combat_type = 1
            GROUP BY u.unit_id
            ORDER BY player_count DESC
            LIMIT ?
        """, (season_id, league, min_relic, limit)) as cur:
            rows = await cur.fetchall()

        # Total joueurs dans cette ligue
        async with db.execute(
            "SELECT COUNT(*) FROM gac_roster_snapshots WHERE season_id=? AND league=?",
            (season_id, league)
        ) as cur:
            total = (await cur.fetchone())[0]

    return [
        {
            "unit_id":     row["unit_id"],
            "player_count": row["player_count"],
            "usage_rate":  round(row["player_count"] / total * 100, 1) if total else 0,
        }
        for row in rows
    ]


async def get_counter_win_rate(
    attacker_leader: str,
    defender_leader: str,
) -> dict:
    """
    Calcule le win rate d'une équipe d'attaque contre une défense spécifique.
    Basé sur les données auto-reportées (gac_round_teams).
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN off_team.success = 1 THEN 1 ELSE 0 END) as wins
            FROM gac_round_teams off_team
            JOIN gac_rounds r ON r.id = off_team.round_id
            WHERE off_team.side = 'offense'
              AND off_team.leader_id = ?
              AND EXISTS (
                SELECT 1 FROM gac_round_teams def_team
                WHERE def_team.round_id = off_team.round_id
                  AND def_team.side = 'defense'
                  AND def_team.leader_id = ?
              )
        """, (attacker_leader, defender_leader)) as cur:
            row = await cur.fetchone()

    total = row["total"] if row else 0
    wins  = row["wins"]  if row else 0
    return {
        "attacker":   attacker_leader,
        "defender":   defender_leader,
        "total_games": total,
        "wins":        wins,
        "win_rate":    round(wins / total * 100, 1) if total else None,
        "confidence":  "haute" if total >= 10 else "moyenne" if total >= 5 else "faible",
    }
```

---

## Phase 5 — Intégration dans main.py

**Fichier :** [`main.py`](file:///c:/Users/yann/Documents/Projet/Bot-SWGOH/main.py)

Ajouter `"cogs.gac_scanner"` à la liste `INITIAL_EXTENSIONS` :

```python
INITIAL_EXTENSIONS = [
    "cogs.gac_counter",
    "cogs.gac_scout",
    "cogs.review_portraits",
    "cogs.comlink_test",
    "cogs.gac_scanner",     # ← NOUVEAU
]
```

---

## Ordre d'Implémentation Recommandé

```
[ ] 1. Ajouter les 4 nouvelles tables dans models.py
[ ] 2. Créer services/gac_scanner.py (Phase 2)
[ ] 3. Tester le scan Top 50 en isolation (pas besoin de GAC actif)
[ ] 4. Créer cogs/gac_scanner.py avec les commandes Discord
[ ] 5. Enregistrer le cog dans main.py
[ ] 6. Tester /gac-log-round et /gac-log-team
[ ] 7. Créer services/gac_meta_analyzer.py
[ ] 8. Intégrer get_counter_win_rate() dans le moteur /gac-counter existant
[ ] 9. Pendant le prochain GAC : lancer /gac-scan-start et valider
[ ] 10. Mettre à jour /gac-counter pour afficher le win rate si dispo
```

---

## Vérification & Tests

### Tests sans GAC actif
```bash
# Tester le scan Top 50 (toujours dispo)
# Via Discord : /gac-scan-top50
# Vérifier dans la BDD : SELECT COUNT(*) FROM gac_roster_snapshots;
```

### Tests pendant GAC actif
```bash
# Via Discord : /gac-scan-start leagues:KYBER
# Vérifier les logs du bot pour le progress
# Estimation : ~1,125 brackets × 8 joueurs = ~9,000 joueurs en ~20 min
```

### Test auto-report
```bash
# /gac-log-round season:42 round_nb:1 result:win my_banners:1800 opp_banners:1200
# /gac-log-team round_id:1 side:offense owner:player leader:SLKR members:HUXTA,FOMODI zone:North banners:68 success:True
# SELECT * FROM gac_round_teams;
```

---

## Notes Importantes

> [!CAUTION]
> **Ne jamais dépasser 30 req/sec** sur `/player` sans monitoring. Commencer à 10 req/sec et augmenter progressivement si tout va bien.

> [!WARNING]
> **Les brackets disparaissent à la fin du GAC.** Lancer le scan dès le début de la période de matchmaking (jour 1 du GAC), pas à la fin.

> [!TIP]
> **Le scan complet en background :** Python asyncio permet de lancer le scan sans bloquer le bot Discord. La commande `/gac-scan-start` répond immédiatement et le scan continue en arrière-plan.
