import time

import aiosqlite
import pytest

from tests.conftest import TEST_ADMIN_ID, FakeUser, TEST_CHAT_ID, fetch_scalar, get_player_coins, upsert_pet, upsert_player


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


@pytest.mark.asyncio
async def test_liebes_starts_challenge_and_sends_text(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "caller", coins=10)
    await upsert_player(main_db_path, 222, "target", coins=0)
    target = FakeUser(222, "target")
    update, context = make_update(111, "caller", reply_from_user=target)

    await main_module.cmd_liebes(update, context)

    assert "Liebes-Bombe detoniert" in update.effective_message.replies[-1]["text"]
    assert await fetch_scalar(
        main_db_path,
        "SELECT active FROM love_challenges WHERE chat_id=? AND user_id=?",
        (TEST_CHAT_ID, 222),
    ) == 1


@pytest.mark.asyncio
async def test_liebes_for_master_grants_direct_reward_without_challenge(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "caller", coins=10)
    await upsert_player(main_db_path, TEST_ADMIN_ID, "owner", coins=100)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    target = FakeUser(TEST_ADMIN_ID, "owner")
    update, context = make_update(111, "caller", reply_from_user=target)

    await main_module.cmd_liebes(update, context)

    assert update.effective_message.replies[-1]["text"] == main_module.LOVE_MASTER_LINES[0]
    assert await get_player_coins(main_db_path, TEST_ADMIN_ID) == 5100
    assert await fetch_scalar(
        main_db_path,
        "SELECT COUNT(*) FROM love_challenges WHERE chat_id=? AND user_id=? AND active=1",
        (TEST_CHAT_ID, TEST_ADMIN_ID),
    ) == 0


@pytest.mark.asyncio
async def test_care_command_without_reply_or_pet_reports_missing_target(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    update, context = make_update(111, "owner", with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert "kaufe dir eines mit /buy" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_care_command_rejects_self_target(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_pet(main_db_path, 111, 111, care_done_today=0, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    target = FakeUser(111, "owner")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert "Selbstpflege ist wichtig" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_care_command_rejects_foreign_pet(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 333, "other", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(main_db_path, 222, 333, care_done_today=0, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert "nicht dein Haustier" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_care_command_respects_cooldown(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(main_db_path, 222, 111, care_done_today=0, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)
    async with aiosqlite.connect(main_db_path) as db:
        await main_module.set_cd(db, TEST_CHAT_ID, 111, "care:pet:111:222", main_module.CARE_COOLDOWN_S)
        await db.commit()

    await main_module.cmd_pet(update, context)

    assert "Langsam, Casanova" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_care_command_stops_at_daily_limit(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(main_db_path, 222, 111, care_done_today=main_module.CARES_PER_DAY, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert "Heute ist das Haustier bereits bestens versorgt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_care_command_ignored_outside_group(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(main_db_path, 222, 111, care_done_today=0, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, chat_type="private", with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert update.effective_message.replies == []


@pytest.mark.asyncio
async def test_full_care_grants_masterofpuppets_title(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(
        main_db_path,
        222,
        111,
        care_done_today=main_module.CARES_PER_DAY - 1,
        day_ymd=main_module.today_ymd(),
        fullcare_days=0,
        fullcare_streak=0,
    )
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert await fetch_scalar(
        main_db_path,
        "SELECT title FROM user_titles WHERE chat_id=? AND user_id=?",
        (TEST_CHAT_ID, 111),
    ) == "MasterofPuppets"


@pytest.mark.asyncio
async def test_second_full_care_promotes_owner_to_unantastbar(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet1", coins=0)
    await upsert_player(main_db_path, 333, "pet2", coins=0)
    await upsert_pet(main_db_path, 222, 111, care_done_today=main_module.CARES_PER_DAY, day_ymd=main_module.today_ymd())
    await upsert_pet(main_db_path, 333, 111, care_done_today=main_module.CARES_PER_DAY - 1, day_ymd=main_module.today_ymd())
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    target = FakeUser(333, "pet2")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert await fetch_scalar(
        main_db_path,
        "SELECT title FROM user_titles WHERE chat_id=? AND user_id=?",
        (TEST_CHAT_ID, 111),
    ) == "Unantastbar"


@pytest.mark.asyncio
async def test_neglected_pet_turns_widerspenstig_before_running_away(main_module, main_db_path, make_update, monkeypatch):
    now = int(time.time())
    old_ts = now - (main_module.RUNAWAY_HOURS * 3600) - 3600
    await upsert_player(main_db_path, 111, "owner", coins=100)
    await upsert_player(main_db_path, 222, "pet", coins=0)
    await upsert_pet(
        main_db_path,
        222,
        111,
        acquired_ts=old_ts,
        last_care_ts=old_ts,
        care_done_today=0,
        day_ymd=main_module.today_ymd(),
    )
    monkeypatch.setattr(main_module, "get_cached_json", lambda context, key, path: {})
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    async with aiosqlite.connect(main_db_path) as db:
        for message_id in range(1, 9):
            await db.execute(
                "INSERT OR REPLACE INTO care_events(chat_id, message_id, pet_id, owner_id, action, ts) VALUES(?,?,?,?,?,?)",
                (TEST_CHAT_ID, 9000 + message_id, 222, 111, "pet", now - 3600),
            )
        await db.commit()
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target, with_job_queue=True)

    await main_module.cmd_pet(update, context)

    assert await fetch_scalar(
        main_db_path,
        "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?",
        (TEST_CHAT_ID, 222),
    ) == 111
    assert (await fetch_scalar(
        main_db_path,
        "SELECT rebellious_until FROM pets WHERE chat_id=? AND pet_id=?",
        (TEST_CHAT_ID, 222),
    )) > now
    assert any("widerspenstig" in reply["text"].lower() for reply in update.effective_message.replies)
