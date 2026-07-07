import sqlite3

def find_gungans():
    conn = sqlite3.connect("game_characters.db")
    cursor = conn.cursor()
    cursor.execute("SELECT base_id, name FROM game_characters WHERE name LIKE '%Gungan%' OR name LIKE '%Jar%' OR name LIKE '%Tarpals%' OR name LIKE '%Nass%'")
    rows = cursor.fetchall()
    
    with open("gungans.txt", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(f"{row[0]} | {row[1]}\n")

if __name__ == "__main__":
    find_gungans()
