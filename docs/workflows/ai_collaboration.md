# Travailler sur ce dépôt avec une IA

Ce dépôt est partagé entre deux personnes qui utilisent deux outils différents :
Antigravity (Gemini, avec un quota Claude/GPT limité) et Claude Code. Les règles
ci-dessous valent pour les deux.

## Langue

**Les réponses sont dans la langue de la question.** Une question posée en français
appelle une réponse en français, entièrement — titres de sections compris.

Les fichiers d'instruction (`.agents/rules/`, `.agents/skills/`, `.agents/agents/`,
`.claude/`) sont rédigés en anglais. Ce sont des instructions destinées au modèle, pas du
texte à reproduire. Lire une consigne en anglais ne change pas la langue de la réponse.

Ne se traduisent jamais : les identifiants du code, les noms de fichiers et de chemins,
les noms de branches, les préfixes de commit (`feat:`, `fix:`), les noms de bibliothèques,
les options de ligne de commande, et la sortie brute d'un outil (`pytest`, `git`). On cite
la sortie telle quelle et on l'explique en français.

Les messages de commit restent en anglais : c'est la convention de tout l'historique.

Le vocabulaire technique est fixé dans `.agents/rules/langue.md`. S'y tenir — un même
concept doit toujours recevoir le même mot français.

## Quel modèle pour quoi

Le quota premium est rare et, sur l'offre AI Pro, peut se bloquer plusieurs jours. Flash
n'est pas concerné. On conçoit donc pour Flash comme plancher.

| Travail | Modèle |
|---|---|
| Lire, chercher, cartographier — « où est X », « comment marche Y » | **Flash**, via le sous-agent `explorer` |
| Modifications ordinaires, nouvelles commandes, corrections de bugs | **Gemini Pro** (défaut) |
| Restructurer `database/db.py`, toucher `_translate_sql_to_pg`, découper `services/scouting.py` | **Claude Sonnet**, via l'agent `reviewer`, à la demande uniquement |

Les sous-agents utilisent Flash par défaut. Ne pas imbriquer les sous-agents sans raison :
les agents d'arrière-plan consomment du quota de façon invisible.

Ces trois seuls chantiers justifient de dépenser du quota premium. Pour tout le reste,
`reviewer` doit refuser et rendre la main.

## Ce qu'il ne faut jamais laisser passer

1. **Une réponse sans vérification.** « Ça devrait marcher » n'est pas un résultat. La
   suite tourne en moins d'une seconde : `pytest`, 18 tests.
2. **Une modification de `database/db.py` sans avoir cherché le nom d'abord.** Huit
   fonctions y ont été définies deux fois ; Python gardait la seconde et la première était
   inatteignable. C'est le piège dans lequel un agent tombe naturellement : il cherche,
   trouve la première occurrence, la modifie, et annonce que c'est fait.
3. **Du SQL ajouté dans `cogs/`.** L'accès aux données passe par `services/`.
4. **Un `except Exception: pass` de plus.** Il y en a déjà douze, et ce sont eux qui ont
   permis au bug des doublons de passer inaperçu.
5. **Une lecture de `_archive/`.** Trente-cinq fichiers morts, importés par rien, pleins
   de motifs obsolètes. Un agent qui s'en inspire produit du code périmé.

## Vérifier avant de conclure

```bash
.venv/bin/python -m pytest
```

Ces 18 tests sont un plancher, pas une couverture : ils existent pour empêcher le retour
de pannes connues. Ils prouvent que les modules s'importent, qu'aucune définition n'est
masquée, que le SQL ne se propage pas dans les cogs, et que les écritures en base se
relisent correctement. Ils ne prouvent rien sur le comportement d'une commande dans
Discord — cela se teste à la main, et se dit explicitement.

## Où trouver quoi

| Question | Fichier |
|---|---|
| Contrat général, architecture, pièges | `AGENTS.md` (lien `CLAUDE.md`) |
| Pièges détaillés du dépôt | `.agents/rules/repo-traps.md` |
| Règles de couches | `.agents/rules/architecture.md` |
| Conventions Python | `.agents/rules/python-conventions.md` |
| Langue et vocabulaire | `.agents/rules/langue.md` |
| Modifier la base | `docs/workflows/db_change.md` |
| Ajouter une commande | `docs/workflows/add_command.md` |
| Installer Python | `docs/setup_python_pyenv.md` |
| Recherches sur les données GAC | `docs/` (les six documents d'origine) |
