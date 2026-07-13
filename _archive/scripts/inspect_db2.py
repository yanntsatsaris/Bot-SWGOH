import asyncio
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import get_db

async def test():
    async with get_db() as db:
        cursor = await db.execute("SELECT id, format, round_number FROM gac_rounds WHERE opponent_name = 'thiogre' OR player_code = 'thiogre' LIMIT 10")
        rounds = await cursor.fetchall()
        print(f"Rounds for thiogre:")
        for r in rounds:
            print(dict(r))
            
        r_3v3 = [r for r in rounds if r["format"] == "3v3"]
        if r_3v3:
            cursor = await db.execute("SELECT defender_team, attacker_team FROM gac_matches WHERE round_id = ? LIMIT 5", (r_3v3[0]["id"],))
            matches = await cursor.fetchall()
            print(f"Matches for round {r_3v3[0]['id']} (3v3):")
            for m in matches:
                print(dict(m))

if __name__ == "__main__":
    asyncio.run(test())
