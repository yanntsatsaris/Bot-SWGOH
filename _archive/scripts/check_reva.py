import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db

async def check():
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT m.defender_team, r.id as round_id, r.format 
            FROM gac_matches m 
            JOIN gac_rounds r ON m.round_id = r.id 
            WHERE r.player_code = '134145313' OR r.player_code = '266539582' OR r.player_code = 'thiogre' 
            AND m.is_attack = 0 AND r.format = '3v3'
        """)
        rows = await cursor.fetchall()
        print(f"Total 3v3 defensive teams found: {len(rows)}")
        for r in rows:
            if 'THIRDSISTER' in r['defender_team']:
                print("FOUND REVA TEAM:", r['defender_team'], "Round ID:", r['round_id'])
            if 'SECONDSISTER' in r['defender_team']:
                print("FOUND SECOND SISTER TEAM:", r['defender_team'], "Round ID:", r['round_id'])

if __name__ == "__main__":
    asyncio.run(check())
