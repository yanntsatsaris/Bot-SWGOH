DISCORD_ID = "424242424242"


async def test_init_db_creates_the_active_round_schema(db):
    async with db.get_db() as connection:
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        tables = {row["name"] for row in await cursor.fetchall()}
    assert {"players", "active_round_units", "active_sector_status"} <= tables


async def test_defense_slot_survives_a_save_and_load(db):
    await db.save_user_defense_slot(
        DISCORD_ID, "North", 0, "REY", ["FINN", "ROSETICO"]
    )

    zones = await db.load_user_defense_zones(DISCORD_ID)

    assert zones["North"] == [
        {"leader_id": "REY", "members_ids": ["FINN", "ROSETICO"], "slot_index": 0}
    ]
    assert zones["South"] == []


async def test_defense_and_enemy_defense_are_stored_separately(db):
    await db.save_user_defense_slot(DISCORD_ID, "North", 0, "REY", ["FINN"])
    await db.save_user_defense_slot(
        DISCORD_ID, "South", 1, "VADER", ["MAUL"], used_type="enemy_defense"
    )

    mine = await db.load_user_defense_zones(DISCORD_ID)
    theirs = await db.load_user_defense_zones(DISCORD_ID, used_type="enemy_defense")

    assert [slot["leader_id"] for slot in mine["North"]] == ["REY"]
    assert mine["South"] == []
    assert [slot["leader_id"] for slot in theirs["South"]] == ["VADER"]
    assert theirs["North"] == []


async def test_saving_a_slot_replaces_the_team_already_there(db):
    await db.save_user_defense_slot(DISCORD_ID, "North", 0, "REY", ["FINN"])
    await db.save_user_defense_slot(DISCORD_ID, "North", 0, "LUKE", ["HAN"])

    zones = await db.load_user_defense_zones(DISCORD_ID)

    assert zones["North"] == [
        {"leader_id": "LUKE", "members_ids": ["HAN"], "slot_index": 0}
    ]


async def test_placeholder_units_are_not_persisted(db):
    await db.save_user_defense_slot(
        DISCORD_ID, "North", 0, "REY", ["USED", "None", "EMPTY", "FINN"]
    )

    zones = await db.load_user_defense_zones(DISCORD_ID)

    assert zones["North"][0]["members_ids"] == ["FINN"]


async def test_used_units_round_trip_and_clear(db):
    await db.add_used_units(DISCORD_ID, ["rey", "finn"], used_type="attack")

    assert await db.get_used_units(DISCORD_ID) == {"REY", "FINN"}

    await db.clear_used_units(DISCORD_ID)

    assert await db.get_used_units(DISCORD_ID) == set()


async def test_sector_status_round_trip(db):
    await db.set_sector_status(DISCORD_ID, "North", 0, "CLEARED", counter_offset=2)

    statuses = await db.get_active_sector_statuses(DISCORD_ID)

    assert statuses[("North", 0)] == {"status": "CLEARED", "counter_offset": 2}


async def test_cycling_the_counter_offset_advances_it(db):
    await db.set_sector_status(DISCORD_ID, "North", 0, "OPEN", counter_offset=0)

    first = await db.cycle_sector_counter_offset(DISCORD_ID, "North", 0)
    second = await db.cycle_sector_counter_offset(DISCORD_ID, "North", 0)

    assert (first, second) == (1, 2)
