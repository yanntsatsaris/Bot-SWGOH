import asyncio
import json
from database.db import get_db, init_db

async def dump_zetas():
    await init_db()
    zetas = {}
    omis = {}
    async with get_db() as db:
        async with db.execute("SELECT skill_id, zeta_tier FROM game_zetas") as cursor:
            async for row in cursor:
                zetas[row["skill_id"]] = row["zeta_tier"]
        async with db.execute("SELECT skill_id, omicron_tier FROM game_omicrons") as cursor:
            async for row in cursor:
                omis[row["skill_id"]] = row["omicron_tier"]
                
    with open("debug_zetas.json", "w") as f:
        json.dump(zetas, f, indent=2)
    with open("debug_omicrons.json", "w") as f:
        json.dump(omis, f, indent=2)

asyncio.run(dump_zetas())
