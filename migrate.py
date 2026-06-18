import asyncio
import sqlite3
from database.db import init_db
from config import DATABASE_PATH

async def run_migration():
    print("Début de la migration...")
    
    # On se connecte en synchrone pour faire les modifs DDL qui bloquent
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 1. GAC History
    print("Suppression de l'ancienne table gac_history...")
    cursor.execute("DROP TABLE IF EXISTS gac_history")
    
    # 2. Units Directory -> Game Characters
    print("Modification de units_directory...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='units_directory'")
    if cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE units_directory ADD COLUMN type TEXT NOT NULL DEFAULT 'character'")
            cursor.execute("ALTER TABLE units_directory RENAME TO game_characters")
            print("Table units_directory renommée en game_characters avec la colonne type.")
        except sqlite3.OperationalError as e:
            print(f"Erreur d'alteration (peut-être déjà fait) : {e}")
    else:
        print("La table units_directory n'existe pas ou est déjà renommée.")
        
    conn.commit()
    conn.close()

    # 3. On relance l'init_db pour créer les nouvelles tables (counter_performance, gac_history propre)
    print("Re-création des tables manquantes avec init_db()...")
    await init_db()
    
    print("Migration terminée !")

if __name__ == "__main__":
    asyncio.run(run_migration())
