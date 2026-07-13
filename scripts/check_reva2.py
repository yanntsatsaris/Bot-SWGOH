import sqlite3
import json

db_path = "c:/Users/yann/Documents/Projet/Bot-SWGOH/swgoh.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check all 3v3 teams for thiogre
cur.execute("SELECT m.defender_team, r.id FROM gac_matches m JOIN gac_rounds r ON m.round_id = r.id WHERE r.player_code = '134145313' AND m.is_attack = 0 AND r.format = '3v3'")
rows = cur.fetchall()

print(f"Total rows: {len(rows)}")
for r in rows:
    print(r["id"], r["defender_team"])

cur.close()
conn.close()
