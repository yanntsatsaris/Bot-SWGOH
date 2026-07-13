"""
cogs/gac_counter.py — Commande /gac-counter
Trouve les meilleurs counters pour une équipe ennemie en GAC.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db, get_counters_from_db, record_counter_feedback
from services.gac_attack_planner import get_best_counter_with_memory
from services.gac_counters_scraper import GacCountersScraper
from services.unit_names import get_name
from services.comlink import get_player
from services.image_generator import generate_gac_report

log = logging.getLogger(__name__)

_scraper = GacCountersScraper()


# ─── HELPERS ────────────────────────────────────────────────────────────────

async def _build_roster(ally_code: str) -> dict | None:
    """Récupère le roster Comlink pour un ally_code donné et le transforme en index."""
    try:
        profile = await get_player(ally_code.replace("-", ""))
    except Exception as e:
        log.warning(f"[gac-counter] Impossible de récupérer le roster pour {ally_code}: {e}")
        return None

    if not profile:
        return None

    roster = {}
    for unit in profile.get("rosterUnit", []):
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        if not base_id:
            continue
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        roster[base_id] = {
            "base_id": base_id,
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": relic_tier,
            "rarity": unit.get("currentRarity", 0),
        }
    return roster or None


async def _get_my_roster(interaction: discord.Interaction) -> tuple[dict | None, str | None, str | None]:
    """
    Récupère le roster du joueur uniquement via la BDD (lié à son compte Discord).
    Retourne (roster, ally_code, username)
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT ally_code, username FROM players WHERE discord_id = ?",
            (str(interaction.user.id),)
        )
        row = await cursor.fetchone()

    if not row:
        return None, None, None

    clean = row["ally_code"].replace("-", "")
    roster = await _build_roster(clean)
    return roster, clean, row["username"]


# ─── AUTOCOMPLETE ────────────────────────────────────────────────────────────

async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not current:
        return []
    current_lower = current.lower()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT base_id, name FROM game_characters WHERE LOWER(name) LIKE ? OR LOWER(base_id) LIKE ? LIMIT 25",
            (f"%{current_lower}%", f"%{current_lower}%")
        )
        rows = await cursor.fetchall()
    return [
        app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"])
        for row in rows
    ]


# ─── VUE INTERACTIVE ────────────────────────────────────────────────────────

class CounterSuggestionView(discord.ui.View):
    def __init__(
        self, interaction: discord.Interaction, suggestions: list, def_leader: str,
        def_members: list, format_type: str, adv_roster: dict | None,
        adv_name: str, my_roster: dict, my_name: str, current_index: int = 0
    ):
        super().__init__(timeout=600)
        self.original_interaction = interaction
        self.suggestions = suggestions
        self.def_leader = def_leader
        self.def_members = def_members
        self.format_type = format_type
        self.adv_roster = adv_roster
        self.adv_name = adv_name
        self.my_roster = my_roster
        self.my_name = my_name
        self.current_index = current_index

    async def _build_message_and_file(self) -> tuple[str, discord.File | None]:
        if self.current_index >= len(self.suggestions):
            return "❌ **Plus de contres disponibles**\nAucun autre contre n'a été trouvé pour cette équipe avec ton roster.", None

        sugg = self.suggestions[self.current_index]
        atk_leader = sugg["atk_leader_id"]
        
        # Limiter aux vrais membres selon le format
        max_atk_members = 2 if self.format_type == "3v3" else 4
        atk_members = sugg.get("atk_members_ids", [])[:max_atk_members]
        all_chars = [atk_leader] + atk_members

        win_pct = sugg.get("win_pct", 0)
        composite = sugg.get("composite_score", 0)
        total_suggestions = len(self.suggestions)

        # ── Construction de la défense (pour l'image) ──
        all_def_chars = [self.def_leader] + self.def_members
        team_dict = {
            "leader_name": get_name(self.def_leader),
            "members": [get_name(m) for m in all_def_chars],
            "members_base_ids": all_def_chars,
            "units_data": self.adv_roster or {}
        }
        
        counter_units = []
        for cid in all_chars:
            u = self.my_roster.get(cid)
            relic = u["relic_tier"] if u else None
            gear = u["gear_tier"] if u else None
            is_ready = True if u and (relic >= 5 or gear >= 13) else False
            
            counter_units.append({
                "base_id": cid,
                "name": get_name(cid),
                "relic_tier": relic,
                "gear_tier": gear,
                "ready": is_ready,
                "owned": True if u else False
            })
            
        mock_suggestions = [{"enemy_team": team_dict, "counters": counter_units}]
        
        img_file = generate_gac_report(self.my_name, self.adv_name, mock_suggestions, self.format_type)

        missing_str = ""
        if sugg.get("missing"):
            m_names = ", ".join(get_name(m) for m in sugg["missing"])
            missing_str = f"\n⚠️ **Manquants / faibles :** {m_names}"

        content = (
            f"🎯 **Contre #{self.current_index + 1}/{total_suggestions}** — {get_name(self.def_leader)}\n"
            f"📊 **Win Rate global :** {win_pct}% (Score roster: {composite:.2f}){missing_str}\n"
            f"⚠️ *Ce ne sont que des propositions automatiques du bot, des erreurs sont possibles.*"
        )

        return content, img_file

    @discord.ui.button(label="✅ Victoire", style=discord.ButtonStyle.success)
    async def btn_victoire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_feedback(interaction, True)

    @discord.ui.button(label="❌ Défaite", style=discord.ButtonStyle.danger)
    async def btn_defaite(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_feedback(interaction, False)

    @discord.ui.button(label="🔄 Autre option", style=discord.ButtonStyle.secondary)
    async def btn_autre(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        if self.current_index >= len(self.suggestions):
            for child in self.children:
                child.disabled = True
        content, img_file = await self._build_message_and_file()
        
        if img_file:
            await interaction.response.edit_message(content=content, embed=None, view=self, attachments=[img_file])
        else:
            await interaction.response.edit_message(content=content, embed=None, view=self)

    async def _handle_feedback(self, interaction: discord.Interaction, won: bool):
        if self.current_index >= len(self.suggestions):
            return
        sugg = self.suggestions[self.current_index]
        atk_leader = sugg["atk_leader_id"]
        atk_members = sugg.get("atk_members_ids", [])

        await record_counter_feedback(
            self.def_leader, [], atk_leader, atk_members,
            self.format_type, "win" if won else "loss",
            str(interaction.user.id)
        )

        for child in self.children:
            child.disabled = True

        content, img_file = await self._build_message_and_file()
        feedback_text = f"\n✅ **Victoire enregistrée — merci !**" if won else f"\n❌ **Défaite enregistrée — merci !**"
        content += feedback_text
        
        if img_file:
            await interaction.response.edit_message(content=content, embed=None, view=self, attachments=[img_file])
        else:
            await interaction.response.edit_message(content=content, embed=None, view=self)


# ─── COG ─────────────────────────────────────────────────────────────────────

class GACCounterCog(commands.Cog, name="GACCounter"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-counter",
        description="Trouve le meilleur contre pour une équipe ennemie en GAC."
    )
    @app_commands.describe(
        leader="Leader de l'équipe ennemie (autocomplétion disponible)",
        format_gac="Format du combat",
        ally_code_adversaire="Ally code de l'adversaire (pour afficher les reliques de sa défense)",
        membre_2="2ème personnage de l'équipe ennemie",
        membre_3="3ème personnage (optionnel)",
        membre_4="4ème personnage (5v5 uniquement)",
        membre_5="5ème personnage (5v5 uniquement)",
    )
    @app_commands.choices(format_gac=[
        app_commands.Choice(name="3v3", value="3v3"),
        app_commands.Choice(name="5v5", value="5v5"),
    ])
    @app_commands.autocomplete(
        leader=unit_autocomplete,
        membre_2=unit_autocomplete,
        membre_3=unit_autocomplete,
        membre_4=unit_autocomplete,
        membre_5=unit_autocomplete,
    )
    async def gac_counter(
        self,
        interaction: discord.Interaction,
        leader: str,
        format_gac: app_commands.Choice[str],
        ally_code_adversaire: str | None = None,
        membre_2: str | None = None,
        membre_3: str | None = None,
        membre_4: str | None = None,
        membre_5: str | None = None,
    ) -> None:
        await interaction.response.defer()

        fmt = format_gac.value
        leader_id = leader.strip().upper()

        # ── 1. Roster du joueur (via BDD /register uniquement) ───────────────
        my_roster, used_code, my_name = await _get_my_roster(interaction)
        if not my_roster:
            await interaction.followup.send(
                "❌ Impossible de trouver ton roster. "
                "Tu dois d'abord lier ton compte avec `/register`.",
                ephemeral=True
            )
            return
        
        my_name = my_name or interaction.user.display_name

        # ── 2. Membres ennemis selon le format ───────────────────────────────
        max_members = 2 if fmt == "3v3" else 4
        raw_members = [m for m in [membre_2, membre_3, membre_4, membre_5] if m]
        members_list = [m.strip().upper() for m in raw_members[:max_members]]

        # ── 3. Roster adversaire (Optionnel) ─────────────────────────────────
        adv_roster = None
        adv_name = "Adversaire Inconnu"
        if ally_code_adversaire:
            adv_clean = ally_code_adversaire.replace("-", "").strip()
            try:
                profile = await get_player(adv_clean)
                if profile:
                    adv_name = profile.get("name", "Adversaire")
                adv_roster = await _build_roster(adv_clean)
            except Exception as e:
                log.warning(f"Impossible de récupérer l'adversaire {adv_clean}: {e}")

        # ── 4. Vérifier les données en BDD ───────────────────────────────────
        existing = await get_counters_from_db(leader_id, fmt)

        if not existing:
            # Scraping à la demande
            await interaction.followup.send(
                f"⏳ Aucune donnée pour **{get_name(leader_id)}** en {fmt}. "
                f"Scraping en cours sur swgoh.gg (~20s)...",
                ephemeral=True
            )
            members_str = ",".join(members_list)
            await _scraper.ensure_counters_available({leader_id: members_str}, fmt)
            existing = await get_counters_from_db(leader_id, fmt)

        if not existing:
            await interaction.followup.send(
                f"❌ Aucun counter trouvé pour **{get_name(leader_id)}** en {fmt}. "
                "swgoh.gg ne répertorie peut-être pas encore ce leader."
            )
            return

        # ── 5. Filtrer par roster et trier ───────────────────────────────────
        counters = await get_best_counter_with_memory(leader_id, members_list, fmt, my_roster)

        if not counters:
            await interaction.followup.send(
                f"❌ Aucun contre disponible avec ton roster actuel pour **{get_name(leader_id)}** en {fmt}.\n"
                "Tu n'as peut-être pas les personnages requis à un niveau suffisant."
            )
            return

        # ── 6. Afficher ───────────────────────────────────────────────────────
        view = CounterSuggestionView(
            interaction, counters, leader_id, members_list, fmt,
            adv_roster, adv_name, my_roster, my_name
        )
        content, img_file = await view._build_message_and_file()

        roster_info = f"Ton Roster : `{used_code}` • {len(counters)} option(s) trouvée(s)"
        if adv_roster and ally_code_adversaire:
            roster_info += f" | Adversaire : `{ally_code_adversaire}`"
            
        content = f"**{roster_info}**\n\n{content}"

        if img_file:
            await interaction.followup.send(content=content, file=img_file, view=view)
        else:
            await interaction.followup.send(content=content, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GACCounterCog(bot))
