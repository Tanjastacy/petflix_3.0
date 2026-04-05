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
async def test_settings_rejects_invalid_key(runtime_commands, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["invalid", "on"]

    await runtime_commands["cmd_settings"](update, context)

    assert "Nutzung: /settings" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_settings_rejects_invalid_value(runtime_commands, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["moraltax", "maybe"]

    await runtime_commands["cmd_settings"](update, context)

    assert "Nutzung: /settings" in update.effective_message.replies[-1]["text"]


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
async def test_restorebackup_rejects_missing_file(runtime_commands, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["missing.db"]

    await runtime_commands["cmd_restorebackup"](update, context)

    assert "Backup-Datei nicht gefunden." in update.effective_message.replies[-1]["text"]


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
async def test_moraltax_rejects_non_admin(main_module, make_update):
    update, context = make_update(111, "user")

    await main_module.cmd_moraltax(update, context)

    assert "Nur der Bot-Admin" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_moraltaxset_rejects_invalid_value(main_module, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["abc"]

    await main_module.cmd_moraltaxset(update, context)

    assert "Nutzung: /moraltaxset" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_superwords_have_more_than_600_unique_keys(main_module):
    assert len(main_module.SUPERWORD_KEYS) > 600


@pytest.mark.asyncio
async def test_superword_claim_has_four_day_cooldown(main_module, main_db_path):
    async with aiosqlite.connect(main_db_path) as db:
        claimed = await main_module.claim_superword_once(db, TEST_CHAT_ID, "kriegdersterne", 111)
        await db.commit()
        assert claimed is True

        claimed_again = await main_module.claim_superword_once(db, TEST_CHAT_ID, "kriegdersterne", 111)
        await db.commit()
        assert claimed_again is False

        old_ts = int(main_module.time.time()) - main_module.SUPERWORD_COOLDOWN_S - 10
        await db.execute(
            "UPDATE superwords_found SET found_ts=? WHERE chat_id=? AND word=?",
            (old_ts, TEST_CHAT_ID, "kriegdersterne"),
        )
        await db.commit()

        claimed_after_cooldown = await main_module.claim_superword_once(db, TEST_CHAT_ID, "kriegdersterne", 111)
        await db.commit()
        assert claimed_after_cooldown is True


@pytest.mark.asyncio
async def test_superwordsstatus_uses_unique_total_and_active_cooldown(main_module, main_db_path, make_update):
    now = int(main_module.time.time())
    async with aiosqlite.connect(main_db_path) as db:
        await db.execute(
            "INSERT INTO superwords_found(chat_id, word, found_by, found_ts) VALUES(?,?,?,?)",
            (TEST_CHAT_ID, "kriegdersterne", 111, now),
        )
        await db.execute(
            "INSERT INTO superwords_found(chat_id, word, found_by, found_ts) VALUES(?,?,?,?)",
            (TEST_CHAT_ID, "standbyme", 222, now - main_module.SUPERWORD_COOLDOWN_S - 100),
        )
        await db.commit()
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_superwordsstatus(update, context)

    text = update.effective_message.replies[-1]["text"]
    assert f"Geladene Eintraege: <b>{len(main_module.SUPERWORDS)}</b>" in text
    assert f"Gesamt (eindeutige Superworte): <b>{len(main_module.SUPERWORD_KEYS)}</b>" in text
    assert "Aktuell gefundene Worte: <b>1</b>" in text


@pytest.mark.asyncio
async def test_resetsuperwords_clears_all_active_cooldowns(main_module, main_db_path, make_update):
    now = int(main_module.time.time())
    async with aiosqlite.connect(main_db_path) as db:
        await db.execute(
            "INSERT INTO superwords_found(chat_id, word, found_by, found_ts) VALUES(?,?,?,?)",
            (TEST_CHAT_ID, "kriegdersterne", 111, now),
        )
        await db.execute(
            "INSERT INTO superwords_found(chat_id, word, found_by, found_ts) VALUES(?,?,?,?)",
            (TEST_CHAT_ID, "standbyme", 222, now),
        )
        await db.commit()
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_resetsuperwords(update, context)

    remaining = await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM superwords_found WHERE chat_id=?", (TEST_CHAT_ID,))
    assert remaining == 0
    assert "Superwort-Cooldowns wurden zurueckgesetzt" in update.effective_message.replies[-1]["text"]


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
async def test_cleanup_zombies_skips_unknown_errors(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alive", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.bot.chat_member_errors[111] = Exception("telegram timeout")

    await main_module.cmd_cleanup_zombies(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 111)) == 1


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
async def test_sendalluser_reports_when_dm_fails(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")

    async def fail_send_message(chat_id, text, **kwargs):
        raise Exception("forbidden")

    context.bot.send_message = fail_send_message

    await main_module.cmd_sendalluser(update, context)

    assert "keine Privatnachricht" in update.effective_message.replies[-1]["text"]


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
async def test_purgeuser_requires_target(main_module, main_db_path, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await main_module.cmd_purgeuser(update, context)

    assert "Ziel nicht gefunden" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_forcepurge_removes_user_by_username(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 222, "target", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["@target"]

    await main_module.cmd_forcepurge(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0
    assert "entsorgt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_forcepurge_removes_user_by_reply_without_username(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 222, "", coins=100)
    target = FakeUser(222, None)
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)

    await main_module.cmd_forcepurge(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0
    assert "entsorgt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_forcepurge_removes_user_by_numeric_id(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 222, "", coins=100)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["222"]

    await main_module.cmd_forcepurge(update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 0


@pytest.mark.asyncio
async def test_forcepurge_reports_unknown_username(main_module, main_db_path, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["@missing"]

    await main_module.cmd_forcepurge(update, context)

    assert "Kenn ich nicht" in update.effective_message.replies[-1]["text"]
