import sqlite3

conn = sqlite3.connect("c:/Users/yann/Documents/Projet/Bot-SWGOH/swgoh.db")
cur = conn.cursor()

cur.execute("SELECT base_id FROM game_characters WHERE name LIKE '%Executor%'")
rows = cur.fetchall()
print("Executor base_id:", rows)

cur.close()
conn.close()
