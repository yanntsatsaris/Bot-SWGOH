# Bot-SWGOH — contrat pour les assistants

Bot Discord d'aide à la Grande Arène (GAC) pour Star Wars: Galaxy of Heroes. Il lit les
rosters via un proxy Comlink auto-hébergé, scrape swgoh.gg pour les données méta et les
counters, planifie attaque et défense, et publie le résultat sous forme d'images générées.

Lire ce fichier en premier. C'est le contrat partagé entre tous les assistants qui
travaillent sur ce dépôt, quel que soit l'outil ou le modèle.

## Langue

**Répondre dans la langue de la question.** Une question en français appelle une réponse
entièrement en français, titres de sections compris.

Les fichiers de `.agents/` et `.claude/` sont rédigés en anglais : ce sont des
instructions destinées au modèle, pas du texte à reproduire. Les lire ne change pas la
langue de la réponse. Le contrat complet et le vocabulaire figé sont dans
`.agents/rules/langue.md` — à lire au début de toute session.

Les messages de commit restent en anglais, comme tout l'historique du dépôt.

## Pile technique

Python 3.10–3.12 · discord.py 2.4 · aiosqlite / asyncpg · Pillow · SeleniumBase.

**Pas 3.13+.** `discord.py` 2.4.0 importe `audioop`, retiré en Python 3.13 (PEP 594).
La production tourne sous **Python 3.11.2** (VM Debian) et `.python-version` épingle cette
version. Installation : `docs/setup_python_pyenv.md`.

## Organisation

| Chemin | Rôle |
|---|---|
| `main.py` | Point d'entrée. `INITIAL_EXTENSIONS` liste tous les cogs chargés au démarrage. |
| `cogs/` | **Contrôleurs.** Commandes slash, boutons, embeds. I/O Discord uniquement. |
| `services/` | **Logique métier.** Scouting, planification, scraping, génération d'images. |
| `database/` | **Dépôt de données.** `db.py` (connexions + requêtes), `models.py` (schéma). |
| `scripts/` | Workers SeleniumBase autonomes, lancés comme processus séparés. |
| `utils/` | Petits helpers purs. |
| `docs/` | Recherches, procédures et plans. Versionné — à lire avant de concevoir. |
| `_archive/` | **Code mort.** Importé par rien. Ne jamais s'en inspirer, ne jamais l'éditer. |

Les dépendances vont dans un seul sens : `cogs → services → database`. Jamais l'inverse.

## Installation

```bash
pyenv install 3.11.2      # voir docs/setup_python_pyenv.md
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # puis renseigner DISCORD_TOKEN
```

## Tests

```bash
.venv/bin/python -m pytest
```

Dix-huit tests. C'est un plancher, pas une couverture : ils existent pour empêcher le
retour de pannes connues, et ils sont le seul signal automatique de ce dépôt. Les lancer
avant d'affirmer qu'une modification fonctionne.

- `test_module_integrity.py` — aucune définition masquée, tout parse, `_archive/` reste injoignable.
- `test_layering.py` — cliquet sur le SQL brut dans `cogs/` : la dette existante est budgétée, toute nouvelle échoue.
- `test_extensions_load.py` — chaque cog de `INITIAL_EXTENSIONS` s'importe et expose `setup()`.
- `test_db_round_trip.py` — écriture puis relecture sur une vraie base SQLite temporaire.
- `test_bootstrap.py` — `init_db` accepte un chemin sans dossier, et le logger se replie au lieu de bloquer le démarrage.

## Quel modèle pour quoi

Le quota premium est rare et, sur l'offre AI Pro, peut se bloquer plusieurs jours. Flash
n'est pas concerné. On conçoit pour Flash comme plancher.

| Travail | Modèle |
|---|---|
| Lire, chercher, cartographier — « où est X », « comment marche Y » | **Flash**, via le sous-agent `explorer` |
| Modifications ordinaires, nouvelles commandes, corrections de bugs | **Gemini Pro** (défaut) |
| Restructurer `database/db.py`, toucher `_translate_sql_to_pg`, découper `services/scouting.py` | **Claude Sonnet**, via l'agent `reviewer`, à la demande |

Les sous-agents utilisent Flash par défaut. Ne pas imbriquer les sous-agents sans raison :
les agents d'arrière-plan consomment du quota de façon invisible.

## Non négociable

1. **Jamais de SQL brut dans `cogs/`.** L'accès aux données passe par `services/`, qui
   appelle `database/db.py`. Sept cogs violent déjà cette règle ; le cliquet empêche que
   ça se propage.
2. **Chercher une définition existante avant d'ajouter une fonction à `database/db.py`.**
   Huit fonctions y ont été définies deux fois ; Python gardait la seconde et la première
   était inatteignable. Voir `.agents/rules/repo-traps.md`.
3. **Pas de nouveau `except Exception: pass`.** Il y en a déjà douze, et ce sont eux qui
   ont permis au bug des doublons de passer inaperçu.
4. **Ne pas rallonger les longues fonctions de `services/scouting.py`.** Extraire.
5. **Prouver.** Lancer la suite. « Ça devrait marcher » n'est pas un résultat.
6. **`docs/` est versionné et partagé.** Le mettre à jour quand le comportement change.

## Règles détaillées

Ces fichiers portent le détail. Un assistant qui ne les charge pas automatiquement doit
les lire au début de la session :

| Fichier | Contenu |
|---|---|
| `.agents/rules/langue.md` | Contrat de langue et vocabulaire figé |
| `.agents/rules/repo-traps.md` | Pièges propres à ce dépôt |
| `.agents/rules/architecture.md` | Règles de couches |
| `.agents/rules/python-conventions.md` | Conventions Python |

## Procédures

| Tâche | Procédure |
|---|---|
| Modifier la base de données | `docs/workflows/db_change.md` |
| Ajouter une commande slash | `docs/workflows/add_command.md` |
| Travailler avec une IA sur ce dépôt | `docs/workflows/ai_collaboration.md` |
| Installer Python | `docs/setup_python_pyenv.md` |

## Conventions

- Le code, les identifiants et les commentaires de ce dépôt sont en français. Les garder
  en français.
- Les commentaires expliquent le *pourquoi*, jamais le *quoi*. Un nom plus clair vaut
  mieux qu'un commentaire.
- Annotations de type sur les nouvelles fonctions. `str | None`, pas `Optional[str]`.
- Pas de nouvel effet de bord au niveau module — `config.py` lève déjà une `KeyError` à
  l'import quand `DISCORD_TOKEN` est absent.

## Points ouverts connus

Pas bloquants, mais à ne pas découvrir par surprise :

- `services/scouting.py` fait 2 026 lignes ; `generate_attack_plan` en fait 450 à lui seul.
- `database/db.py` implémente à la main une traduction SQLite→PostgreSQL
  (`_translate_sql_to_pg` plus quatre classes d'enrobage). C'est de la réécriture de
  chaînes non testée. Y toucher avec précaution.
- 163 `except Exception` dans le code, dont douze qui avalent l'erreur.
- `_archive/` : trente-cinq fichiers morts, environ 2 600 lignes, à supprimer un jour.
