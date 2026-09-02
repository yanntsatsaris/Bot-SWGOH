"""
cogs/forum_manager.py — Gestion du Salon Forum Discord
Crée automatiquement un fil personnel par joueur lors du /register.
Met à jour les tags (ligue, statut GAC) automatiquement.
"""
import logging

import discord
from discord.ext import commands

from config import FORUM_CHANNEL_ID, ADMIN_ROLE_ID
from database.db import get_player_by_thread_id, set_player_forum_thread

log = logging.getLogger(__name__)

# ── Noms des tags attendus dans le salon Forum ────────────────────────────────
TAG_LEAGUES = {
    "kyber":     "🏆 Kyber",
    "aurodium":  "💎 Aurodium",
    "chromium":  "🔵 Chromium",
    "bronzium":  "⭐ Bronzium",
    "carbonite": "⚪ Carbonite",
}
TAG_FORMATS = {
    "5v5": "5️⃣ 5v5",
    "3v3": "3️⃣ 3v3",
}
TAG_STATUS = {
    "scout_ready": "🎯 Scout Prêt",
    "in_attack":   "⚔️ En Attaque",
    "round_won":   "✅ Round Gagné",
    "need_help":   "🆘 Besoin d'Aide",
}

WELCOME_TEMPLATE = """\
👋 **Bienvenue dans ton espace personnel, {username} !**

Ton compte SWGOH a été lié avec succès.
> 🎮 Code Allié : `{ally_code}`

**Toutes tes commandes bot se font directement ici** — tes scouts, plans d'attaque et contres seront archivés dans ce fil.

📋 **Commandes principales :**
• `/gac-scout code_ennemi:<code> format_gac:<5v5/3v3>` — Scouter un adversaire
• `/gac-counter leader:<nom> format_gac:<5v5/3v3>` — Trouver un contre
• `/gac-edit-slot` — Modifier un slot de ta carte
• `/gac-record-battle zone:<zone> slot:<n> resultat:<Victoire/Échec>` — Enregistrer un combat

Bonne GAC ! ⚔️
"""


def _find_tag(forum_channel: discord.ForumChannel, name: str) -> discord.ForumTag | None:
    """Recherche un tag disponible dans le salon Forum par son nom exact."""
    for tag in forum_channel.available_tags:
        if tag.name == name:
            return tag
    return None


async def create_player_forum_thread(
    bot: commands.Bot,
    discord_id: str,
    ally_code: str,
    username: str,
    league: str | None = None,
    format_gac: str | None = None,
) -> discord.Thread | None:
    """Crée un fil Forum personnel pour un joueur."""
    if not FORUM_CHANNEL_ID:
        log.warning("[Forum] FORUM_CHANNEL_ID non configuré — création du fil ignorée.")
        return None

    forum_channel = bot.get_channel(FORUM_CHANNEL_ID)
    if not isinstance(forum_channel, discord.ForumChannel):
        log.error("[Forum] Le canal %s n'est pas un salon Forum.", FORUM_CHANNEL_ID)
        return None

    thread_name = f"🎯 │ {username} ({ally_code})"

    # Collecter les tags à appliquer
    applied_tags: list[discord.ForumTag] = []
    if league:
        league_tag_name = TAG_LEAGUES.get(league.lower())
        if league_tag_name:
            tag = _find_tag(forum_channel, league_tag_name)
            if tag:
                applied_tags.append(tag)
    if format_gac:
        fmt_tag_name = TAG_FORMATS.get(format_gac.lower())
        if fmt_tag_name:
            tag = _find_tag(forum_channel, fmt_tag_name)
            if tag:
                applied_tags.append(tag)

    welcome_msg = WELCOME_TEMPLATE.format(username=username, ally_code=ally_code)

    try:
        thread_with_msg = await forum_channel.create_thread(
            name=thread_name,
            content=welcome_msg,
            applied_tags=applied_tags,
        )
        thread = thread_with_msg.thread
        log.info("[Forum] Fil créé pour %s : %s (ID: %s)", username, thread_name, thread.id)
        await set_player_forum_thread(discord_id, str(thread.id))
        return thread
    except discord.Forbidden:
        log.error("[Forum] Permission refusée pour créer un fil dans %s.", FORUM_CHANNEL_ID)
    except discord.HTTPException as e:
        log.error("[Forum] Erreur HTTP : %s", e)
    return None


async def update_thread_tags(
    bot: commands.Bot,
    thread_id: str,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> None:
    """Met à jour les tags d'un fil Forum (add_tags / remove_tags = clés de TAG_*)."""
    if not FORUM_CHANNEL_ID:
        return

    forum_channel = bot.get_channel(FORUM_CHANNEL_ID)
    if not isinstance(forum_channel, discord.ForumChannel):
        return

    thread = bot.get_channel(int(thread_id))
    if not isinstance(thread, discord.Thread):
        try:
            thread = await bot.fetch_channel(int(thread_id))
        except Exception:
            log.warning("[Forum] Impossible de récupérer le fil %s", thread_id)
            return

    all_known = {**TAG_LEAGUES, **TAG_FORMATS, **TAG_STATUS}
    current_tag_names = {t.name for t in thread.applied_tags}

    names_to_add = {all_known[k] for k in (add_tags or []) if k in all_known}
    names_to_remove = {all_known[k] for k in (remove_tags or []) if k in all_known}
    final_names = (current_tag_names | names_to_add) - names_to_remove
    final_tags = [t for t in forum_channel.available_tags if t.name in final_names]

    try:
        await thread.edit(applied_tags=final_tags)
        log.info("[Forum] Tags du fil %s : %s", thread_id, [t.name for t in final_tags])
    except Exception as e:
        log.warning("[Forum] Impossible de mettre à jour les tags : %s", e)


async def check_forum_access(interaction: discord.Interaction) -> bool:
    """
    Vérifie si l'utilisateur peut interagir avec le bot dans ce fil Forum.
    Retourne True si autorisé, False + réponse ephémère sinon.
    """
    channel = interaction.channel
    if not isinstance(channel, discord.Thread):
        return True
    if not isinstance(channel.parent, discord.ForumChannel):
        return True
    if channel.parent_id != FORUM_CHANNEL_ID:
        return True

    user = interaction.user
    if isinstance(user, discord.Member) and user.guild_permissions.administrator:
        return True
    if ADMIN_ROLE_ID and isinstance(user, discord.Member):
        if any(role.id == ADMIN_ROLE_ID for role in user.roles):
            return True

    player = await get_player_by_thread_id(str(channel.id))
    if player and player.get("discord_id") == str(user.id):
        return True

    await interaction.response.send_message(
        "❌ Ce fil appartient à un autre joueur. Utilise tes commandes dans **ton propre fil**.",
        ephemeral=True,
    )
    return False


class ForumManagerCog(commands.Cog, name="ForumManager"):
    """Gestion du salon Forum — fil personnel par joueur."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Si un membre crée un fil manuellement dans notre Forum, on le supprime."""
        if not FORUM_CHANNEL_ID:
            return
        if thread.parent_id != FORUM_CHANNEL_ID:
            return
        if thread.owner_id == self.bot.user.id:
            return

        log.info("[Forum] Fil manuel créé par %s — suppression.", thread.owner_id)
        try:
            await thread.send(
                "⚠️ Pour créer ton espace personnel, utilise `/register <ton_code_allié>` "
                "dans n'importe quel salon. Le bot créera automatiquement ton fil ici !"
            )
            await thread.delete()
        except Exception as e:
            log.warning("[Forum] Suppression du fil manuel échouée : %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ForumManagerCog(bot))
