import asyncio
from services.comlink import ComlinkService
from database.db import get_db, init_db

async def check():
    await init_db()
    try:
        player = await ComlinkService.get_player(allycode='954848523')
    except Exception as e:
        print("Failed to get player:", e)
        return
    roster = player.get('rosterUnit', [])
    rey = next((u for u in roster if u['definitionId'].split(':')[0] == 'GLREY'), None)
    if rey:
        print('Rey Skills in Roster:')
        for sk in rey.get('skill', []):
            print(f"  {sk.get('id')}: tier {sk.get('tier')}")
            
    print('\nZetas in DB for Rey:')
    async with get_db() as db:
        async with db.execute("SELECT skill_id, zeta_tier FROM game_zetas WHERE skill_id LIKE '%rey%'") as c:
            rows = await c.fetchall()
            for r in rows:
                print(f"  {r['skill_id']}: tier {r['zeta_tier']}")

asyncio.run(check())
