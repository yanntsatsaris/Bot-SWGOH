import asyncio
import json
import os
import sys

# Ajouter le chemin du projet au sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import get_db

async def test():
    async with get_db() as db:
        # Get thiogre ally code
        cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = '123'") # Just a dummy, let's search by name
        
        # Let's just search gac_rounds directly
        cursor = await db.execute("SELECT id, format, round_number FROM gac_rounds WHERE opponent_name = 'thiogre' OR player_code = 'thiogre' LIMIT 10")
        rounds = await cursor.fetchall()
        print(f"Rounds for thiogre:")
        for r in rounds:
            print(dict(r))
            
        # Get matches for the first 3v3 round
        for r in rounds:
            if r["format"] == "3v3":
                cursor = await db.execute("SELECT defender_team, attacker_team FROM gac_matches WHERE round_id = ? LIMIT 5", (r["id"],))
                matches = await cursor.fetchall()
                print(f"Matches for round {r['id']} (3v3):")
                for m in matches:
                    print(dict(m))
                break

if __name__ == "__main__":
    asyncio.run(test())
