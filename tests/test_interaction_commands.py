import time

import pytest

from tests.conftest import FakeUser, TEST_CHAT_ID, fetch_scalar, get_player_coins, upsert_pet, upsert_player


CARE_COMMANDS = [
    "cmd_pet",
    "cmd_walk",
    "cmd_kiss",
    "cmd_dine",
    "cmd_massage",
    "cmd_lapdance",
    "cmd_knien",
    "cmd_kriechen",
    "cmd_klaps",
    "cmd_knabbern",
    "cmd_leine",
    "cmd_halsband",
    "cmd_lecken",
    "cmd_verweigern",
    "cmd_kaefig",
    "cmd_schande",
    "cmd_erregen",
    "cmd_betteln",
    "cmd_stumm",
    "cmd_bestrafen",
    "cmd_loben",
    "cmd_dienen",
    "cmd_demuetigen",
    "cmd_melken",
    "cmd_ohrfeige",
    "cmd_belohnen",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("command_name", CARE_COMMANDS)
async def test_each_care_command_updates_pet_progress(main_module, main_db_path, make_update, monkeypatch, command_name):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(
        main_db_path,
        222,
        111,
        acquired_ts=int(time.time()),
        last_care_ts=int(time.time()),
        care_done_today=0,
        day_ymd=main_module.today_ymd(),
        pet_xp=0,
        pet_level=0,
    )
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await getattr(main_module, command_name)(update, context)

    assert await fetch_scalar(main_db_path, "SELECT care_done_today FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 1
    assert len(update.effective_message.replies) >= 1


@pytest.mark.asyncio
async def test_dom_awards_bonus_for_male_sender_against_female_target(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "dom", coins=10, gender="m")
    await upsert_player(main_db_path, 222, "pet", coins=0, gender="f")
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {"dom": ["{owner} -> {pet} +{coins}"]})
    target = FakeUser(222, "pet")
    update, context = make_update(111, "dom", reply_from_user=target)

    await main_module.cmd_dom(update, context)

    assert await get_player_coins(main_db_path, 111) == 12
    assert "+2" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_dom_rejects_non_female_target(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "dom", coins=10, gender="m")
    await upsert_player(main_db_path, 222, "target", coins=0, gender="m")
    target = FakeUser(222, "target")
    update, context = make_update(111, "dom", reply_from_user=target)

    await main_module.cmd_dom(update, context)

    assert update.effective_message.replies[-1]["text"] == "Nur bei Frauen."
