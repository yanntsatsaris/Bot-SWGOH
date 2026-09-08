# Modifier la base de données

Deux dialectes font tourner ce bot : SQLite en local, PostgreSQL en production. Une
modification qui ne marche que d'un côté est un bug de production.

## 1. Vérifier que le nom est libre

`database/db.py` a contenu huit fonctions définies deux fois, et Python gardait
silencieusement la seconde. Toujours regarder avant d'ajouter :

```bash
grep -n "^async def <nom>\|^def <nom>" database/db.py
```

Si la fonction existe déjà, l'étendre — ne jamais ajouter une seconde définition.

## 2. Le schéma d'abord, dans les deux dialectes

Le schéma vit dans `database/models.py`, séparé en deux listes :

- `CREATE_TABLES_SQL` — SQLite
- `CREATE_TABLES_PG_SQL` — PostgreSQL

Une nouvelle table a besoin d'une entrée dans les deux. Attention aux différences de
types : `INTEGER PRIMARY KEY AUTOINCREMENT` en SQLite devient `SERIAL PRIMARY KEY` en
PostgreSQL, et SQLite n'a pas de vrai `BOOLEAN`.

Une nouvelle colonne sur une table existante a aussi besoin d'une ligne de migration dans
`init_db`, qui exécute `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` par dialecte.

## 3. Écrire la fonction de requête

Dans `database/db.py`, à côté des fonctions liées :

```python
async def get_something(discord_id: str) -> list[dict]:
    """Une ligne, ce que ça retourne."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT ... FROM ... WHERE discord_id = ?",
            (discord_id,)
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]
```

Règles :

- Toujours des placeholders `?`. `_translate_sql_to_pg` les convertit en `$1`, `$2`.
  Ne jamais construire du SQL avec une f-string.
- Retourner des `dict`, `list` et `set` simples. Un curseur ou un objet ligne ne doit
  jamais sortir de `get_db()`.
- Une seule responsabilité par fonction.
- Pas de `except Exception` autour d'une écriture.

## 4. Prouver l'aller-retour

Écrire puis relire par le vrai chemin de requête, dans `tests/test_db_round_trip.py`.
Tester la transformation seule ne prouve rien sur les bornes de la requête.

```python
async def test_something_survives_a_save_and_load(db):
    await db.save_something(DISCORD_ID, ...)
    assert await db.get_something(DISCORD_ID) == [...]
```

La fixture `db` fournit un vrai fichier SQLite temporaire avec le schéma complet appliqué.

## 5. Lancer les tests

```bash
.venv/bin/python -m pytest
```
