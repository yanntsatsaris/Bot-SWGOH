# Ajouter une commande slash

## 1. Choisir le cog

Les cogs existants sont regroupés par domaine : `gac.py` (inscription), `gac_scout.py`
(scouting), `gac_counter.py` (counters), `gac_fleet.py` (flottes), `admin.py`
(administration), `forum_manager.py` (fils forum par joueur).

Un nouveau cog doit être ajouté à `INITIAL_EXTENSIONS` dans `main.py` et exposer
`async def setup(bot)`. Un test vérifie les deux.

## 2. Écrire la commande

```python
@app_commands.command(name="ma-commande", description="Ce que ça fait.")
async def ma_commande(self, interaction: discord.Interaction, code_allie: str):
    await interaction.response.defer()
    resultat = await mon_service.calculer(code_allie)
    await interaction.followup.send(embed=construire_embed(resultat))
```

`defer()` en premier pour tout ce qui dépasse trois secondes — le scraping et la
génération d'images dépassent toujours. Sinon Discord invalide l'interaction.

## 3. Garder le cog mince

**Pas de SQL dans un cog.** Sept cogs sur neuf en contiennent déjà et
`tests/test_layering.py` fait redescendre cette dette par cliquet : une nouvelle
instruction fait échouer la suite.

Le cog lit l'entrée, vérifie les permissions, formate la réponse. Tout ce qui décide
*quelle* est la réponse appartient à un service, qui appelle `database/db.py`.

## 4. Synchronisation des commandes

`setup_hook` synchronise sur `DISCORD_GUILD_ID` quand il est défini (instantané, pour le
développement) ou globalement sinon (environ une heure de propagation). Une nouvelle
commande qui n'apparaît pas dans Discord vient presque toujours de là, pas du code.

## 5. Vérifier

```bash
.venv/bin/python -m pytest
```

La suite prouve que le cog s'importe et expose `setup()`. Elle ne peut pas prouver que la
commande se comporte correctement — l'essayer dans Discord, et dire clairement si on l'a
fait ou non.
