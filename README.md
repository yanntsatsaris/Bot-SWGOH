# Bot-SWGOH

Bot Discord d'aide à la Grande Arène (GAC) pour Star Wars: Galaxy of Heroes. Il lit les
rosters via un proxy Comlink auto-hébergé, scrape swgoh.gg pour les données méta et les
counters, planifie attaque et défense, et publie le résultat sous forme d'images générées.

## Prérequis

- **Python 3.11.2** — la version de la VM de production, épinglée dans `.python-version`.
  La plage supportée est 3.10 à 3.12 : pas 3.13+, car `discord.py` 2.4.0 importe
  `audioop`, retiré en Python 3.13 (PEP 594). Installation pas à pas :
  [`docs/setup_python_pyenv.md`](docs/setup_python_pyenv.md).
- Une instance Comlink accessible (Docker, port 3200 par défaut).
- Chrome, pour les workers SeleniumBase.

## Installation

```bash
pyenv install 3.11.2
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Puis renseigner `DISCORD_TOKEN` dans `.env`. `config.py` lève une `KeyError` à l'import
si la variable est absente.

## Lancement

```bash
.venv/bin/python main.py
```

Sur Linux, les logs vont dans `/var/log/bot-swgoh/bot.log` ; le dossier est créé au
démarrage, et si ce n'est pas possible le bot se replie sur un `bot.log` local plutôt que
de refuser de démarrer.

## Tests

```bash
.venv/bin/python -m pytest
```

Dix-huit tests. C'est un plancher, pas une couverture : ils existent pour empêcher le
retour de pannes connues.

| Fichier | Ce qu'il garantit |
|---|---|
| `test_module_integrity.py` | Aucune définition masquée par une seconde, tout parse, `_archive/` reste injoignable |
| `test_layering.py` | Cliquet sur le SQL brut dans `cogs/` : la dette existante est budgétée, toute nouvelle échoue |
| `test_extensions_load.py` | Chaque cog de `INITIAL_EXTENSIONS` s'importe et expose `setup()` |
| `test_db_round_trip.py` | Écriture puis relecture sur une vraie base SQLite temporaire |
| `test_bootstrap.py` | `init_db` accepte un chemin sans dossier, et le logger se replie au lieu de bloquer le démarrage |

## Architecture

```
cogs/  →  services/  →  database/
```

Sens unique. `cogs/` ne fait que de l'I/O Discord, `services/` porte la logique métier,
`database/db.py` porte les requêtes. `scripts/` contient les workers SeleniumBase, lancés
comme processus séparés. `_archive/` est du code mort, importé par rien.

## Assistants IA

[`AGENTS.md`](AGENTS.md) est le contrat partagé, lu nativement par Antigravity et par
Claude Code (via le lien `CLAUDE.md`). Les règles, agents et procédures vivent dans
`.agents/` et `.claude/`, et sont versionnés : c'est le canal de connaissance commun au
projet.

Pour travailler efficacement avec une IA sur ce dépôt — quel modèle pour quelle tâche,
quoi ne jamais laisser passer — lire
[`docs/workflows/ai_collaboration.md`](docs/workflows/ai_collaboration.md).

## Documentation

| Sujet | Fichier |
|---|---|
| Installer Python avec pyenv | `docs/setup_python_pyenv.md` |
| Modifier la base de données | `docs/workflows/db_change.md` |
| Ajouter une commande slash | `docs/workflows/add_command.md` |
| Travailler avec une IA | `docs/workflows/ai_collaboration.md` |
| Recherches sur les données GAC | `docs/gac_*.md` |
