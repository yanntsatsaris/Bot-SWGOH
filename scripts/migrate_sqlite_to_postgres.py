#!/usr/bin/env python3
"""
scripts/migrate_sqlite_to_postgres.py — Script de migration complet SQLite vers PostgreSQL

Usage :
    python scripts/migrate_sqlite_to_postgres.py [chemin_vers_sqlite.db] [postgresql_url]

Exemple :
    python scripts/migrate_sqlite_to_postgres.py database/swgoh.db postgresql://user:password@localhost:5432/swgoh
"""
import asyncio
import os
import sys
import sqlite3
from datetime import datetime

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DATABASE_PATH, DATABASE_URL
from database.models import CREATE_TABLES_PG_SQL

# Liste ordonnée des tables (respectant les clés étrangères)
TABLES_ORDER = [
    "players",
    "meta_teams",
    "game_characters",
    "game_omicrons",
    "gac_valid_omicrons",
    "game_zetas",
    "gac_meta_squads",
    "gac_rounds",
    "gac_matches",
    "gac_round_teams",
    "gac_global_meta",
    "gac_counters",
    "counter_feedback",
    "active_round_units",
    "active_sector_status",
    "active_gac_session",
]

# Tables avec clé primaire 'id' auto-incrémentée (SERIAL)
SERIAL_TABLES = [
    "players",
    "meta_teams",
    "gac_meta_squads",
    "gac_rounds",
    "gac_matches",
    "gac_round_teams",
    "gac_global_meta",
    "gac_counters",
    "counter_feedback",
    "active_round_units",
    "active_sector_status",
]


async def migrate(sqlite_path: str, pg_url: str):
    import asyncpg
    if not os.path.exists(sqlite_path):
        print(f"❌ Fichier SQLite introuvable : {sqlite_path}")
        sys.exit(1)

    print("=" * 65)
    print("🚀 MIGRATION DE LA BASE DE DONNÉES SWGOH : SQLITE ➔ POSTGRESQL")
    print("=" * 65)
    print(f"📁 Source SQLite      : {sqlite_path}")
    print(f"🐘 Cible PostgreSQL   : {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")
    print("=" * 65)

    # 1. Connexion PostgreSQL
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    try:
        pg_conn = await asyncpg.connect(pg_url)
    except Exception as e:
        print(f"❌ Erreur de connexion à PostgreSQL : {e}")
        sys.exit(1)

    # 2. Initialisation des tables PostgreSQL
    print("\n⚙️  1. Initialisation des tables PostgreSQL...")
    async with pg_conn.transaction():
        for sql in CREATE_TABLES_PG_SQL:
            await pg_conn.execute(sql)
    print("✅ Tables et index PostgreSQL créés avec succès.")

    # 3. Connexion SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # 4. Migration table par table
    print("\n📦 2. Transfert des données...")
    total_migrated = 0

    for table in TABLES_ORDER:
        # Vérifier si la table existe dans SQLite
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not sqlite_cursor.fetchone():
            print(f"  ⏭️  Table '{table}' absente de SQLite, ignorée.")
            continue

        if table == "gac_matches":
            sqlite_cursor.execute("SELECT * FROM gac_matches WHERE round_id IN (SELECT id FROM gac_rounds)")
        elif table == "gac_round_teams":
            sqlite_cursor.execute("SELECT * FROM gac_round_teams WHERE round_id IN (SELECT id FROM gac_rounds)")
        else:
            sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        if not rows:
            print(f"  ⚪ Table '{table}' : 0 ligne.")
            continue

        columns = [d[0] for d in sqlite_cursor.description]
        col_names = ", ".join(columns)
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))

        insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

        TIMESTAMP_COLS = ["created_at", "updated_at", "recorded_at", "last_updated"]

        migrated_count = 0
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            batch_data = []
            for r in batch:
                row_vals = []
                for idx, val in enumerate(r):
                    col_name = columns[idx]
                    # Conversion booléenne
                    if isinstance(val, int) and col_name in ["is_attack", "is_image_valid", "success"]:
                        row_vals.append(bool(val))
                    # Conversion timestamp / date
                    elif isinstance(val, str) and (col_name in TIMESTAMP_COLS or ("_at" in col_name or "_updated" in col_name)):
                        try:
                            # Parse '2026-06-15 12:22:13' ou '2026-06-15T12:22:13'
                            dt_val = datetime.fromisoformat(val.replace("T", " "))
                            row_vals.append(dt_val)
                        except Exception:
                            row_vals.append(val)
                    else:
                        row_vals.append(val)
                batch_data.append(row_vals)

            try:
                await pg_conn.executemany(insert_sql, batch_data)
                migrated_count += len(batch_data)
            except Exception as e:
                print(f"  ⚠️  Erreur lors de l'insertion dans {table} : {e}")

        print(f"  ✅ Table '{table}' : {migrated_count}/{len(rows)} lignes transférées.")
        total_migrated += migrated_count

    # 5. Synchronisation des séquences SERIAL
    print("\n🔄 3. Réalignement des séquences SERIAL...")
    for table in SERIAL_TABLES:
        try:
            await pg_conn.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1)
                );
            """)
        except Exception:
            pass
    print("✅ Séquences d'identifiants synchronisées.")

    # 6. Fermeture
    sqlite_conn.close()
    await pg_conn.close()

    print("\n" + "=" * 65)
    print(f"🎉 MIGRATION TERMINÉE AVEC SUCCÈS ! Total : {total_migrated} enregistrements.")
    print("=" * 65)


def main():
    sqlite_p = sys.argv[1] if len(sys.argv) > 1 else DATABASE_PATH
    pg_u = sys.argv[2] if len(sys.argv) > 2 else DATABASE_URL

    if not pg_u:
        print("❌ Aucune URL PostgreSQL fournie.")
        print("Usage: python scripts/migrate_sqlite_to_postgres.py [sqlite.db] [postgresql://user:pass@host:5432/db]")
        print("Ou définis la variable DATABASE_URL dans ton fichier .env.")
        sys.exit(1)

    asyncio.run(migrate(sqlite_p, pg_u))


if __name__ == "__main__":
    main()
