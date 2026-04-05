from pathlib import Path

import aiosqlite
import pytest

from tests.conftest import TEST_ADMIN_ID, TEST_CHAT_ID, FakeUser, fetch_scalar, get_player_coins, upsert_pet, upsert_player


@pytest.mark.asyncio
async def test_settings_status_and_toggle(runtime_commands, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await runtime_commands["cmd_settings"](update, context)
    assert "<b>Settings</b>" in update.effective_message.replies[-1]["text"]

    context.args = ["dailycurse", "off"]
    await runtime_commands["cmd_settings"](update, context)
    assert "Daily Curse: off" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_admin_dashboard_reports_counts(runtime_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=100)
    await upsert_player(main_db_path, 222, "bob", coins=50)
    await upsert_pet(main_db_path, 222, 111)
    async with aiosqlite.connect(main_db_path) as db:
        await db.execute(
            "INSERT INTO hass_challenges(chat_id, user_id, username, triggered_by, started_ts, expires_ts, active) VALUES(?,?,?,?,?,?,1)",
            (TEST_CHAT_ID, 111, "alice", TEST_ADMIN_ID, 0, 9999999999),
        )
        await db.execute(
            "INSERT INTO love_challenges(chat_id, user_id, username, triggered_by, started_ts, expires_ts, active) VALUES(?,?,?,?,?,?,1)",
            (TEST_CHAT_ID, 222, "bob", TEST_ADMIN_ID, 0, 9999999999),
        )
        await db.execute(
            "INSERT INTO care_events(chat_id, message_id, pet_id, owner_id, action, ts) VALUES(?,?,?,?,?,?)",
            (TEST_CHAT_ID, 1, 222, 111, "pet", 999999999),
        )
        await db.commit()
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await runtime_commands["cmd_admin"](update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "- Players: 2" in text
    assert "- Pets: 1" in text
    assert "- Active Hass: 1" in text
    assert "- Active Love: 1" in text


@pytest.mark.asyncio
async def test_backup_commands_create_list_and_restore(runtime_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await runtime_commands["cmd_backupnow"](update, context)
    created_text = update.effective_message.replies[-1]["text"]
    assert "Backup erstellt" in created_text

    backup_name = Path(created_text.split("<code>", 1)[1].split("</code>", 1)[0]).name
    await runtime_commands["cmd_backups"](update, context)
    assert backup_name in update.effective_message.replies[-1]["text"]

    await upsert_player(main_db_path, 111, "alice", coins=999)
    context.args = [backup_name]
    await runtime_commands["cmd_restorebackup"](update, context)
    assert "Restore abgeschlossen" in update.effective_message.replies[-1]["text"]
    assert await get_player_coins(main_db_path, 111) == 100


@pytest.mark.asyncio
async def test_moraltax_status_toggle_and_set(main_module, main_db_path, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_moraltax(update, context)
    assert "Moralische Steuer ist" in update.effective_message.replies[-1]["text"]

    context.args = ["off"]
    await main_module.cmd_moraltax(update, context)
    assert "deaktiviert" in update.effective_message.replies[-1]["text"]

    context.args = ["17"]
    await main_module.cmd_moraltaxset(update, context)
    assert "gesetzt auf 17 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_cleanup_zombies_purges_missing_members(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alive", coins=100)
    await upsert_player(main_db_path, 222, "ghost", coins=50)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.bot.chat_member_results[111] = object()
    context.bot.chat_member_errors[222] = Exception("User not found")

    await main_module.cmd_cleanup_zombies(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0
    assert update.effective_message.replies[0]["text"].startswith("🧟") or "Daddy durchsucht" in update.effective_message.replies[0]["text"]


@pytest.mark.asyncio
async def test_listdbusers_lists_all_players(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=100)
    await upsert_player(main_db_path, 222, "bob", coins=50)
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_listdbusers(update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "Alle Seelen in der DB" in text
    assert "@alice" in text
    assert "@bob" in text


@pytest.mark.asyncio
async def test_sendalluser_sends_schema_and_rows_via_dm(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_sendalluser(update, context)

    assert len(context.bot.sent_messages) >= 2
    assert "players schema" in context.bot.sent_messages[0]["text"]
    assert "players daten" in context.bot.sent_messages[1]["text"]
    assert "Privatnachricht" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_purgeuser_removes_target_from_tables(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "owner")
    await upsert_player(main_db_path, 222, "target", coins=100)
    await upsert_pet(main_db_path, 222, 111)
    target = FakeUser(222, "target")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)

    await main_module.cmd_purgeuser(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0
    assert "entfernt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_forcepurge_removes_user_by_username(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 222, "target", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["@target"]

    await main_module.cmd_forcepurge(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0
    assert "entsorgt" in update.effective_message.replies[-1]["text"]
