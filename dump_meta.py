import asyncio
import json
from services.comlink import _post_raw

async def main():
    meta = await _post_raw("metadata", {})
    with open("meta_dump.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print("Metadata dumped to meta_dump.json")

asyncio.run(main())
