import aiosqlite
import pytest

from admin_coin_commands import create_admin_coin_commands
from tests.conftest import (
    TEST_ADMIN_ID,
    TEST_CHAT_ID,
    FakeUser,
    get_player_coins,
    set_pet_care,
    set_player_coins,
)


@pytest.mark.asyncio
async def test_adminping_sends_private_message_when_owner_invokes(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await commands["cmd_adminping"](update, context)

    assert context.bot.sent_messages == [
        {
            "chat_id": TEST_ADMIN_ID,
            "text": "Admin-Ping: Ich kann dir PMs schicken und habe den Command empfangen.",
        }
    ]


@pytest.mark.asyncio
async def test_careminus_reduces_today_care_but_not_below_zero(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    target = FakeUser(123, "pet")
    await set_pet_care(db_path, pet_id=123, care_done_today=3, day_ymd="2026-04-05")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)

    await commands["cmd_careminus"](update, context)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT care_done_today FROM pets WHERE chat_id=? AND pet_id=?",
            (TEST_CHAT_ID, 123),
        ) as cur:
            row = await cur.fetchone()
    assert row[0] == 0
    assert "Pflege reduziert" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_increases_target_balance(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["50"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 60
    assert "50 Coins an @alice vergeben" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_supports_amount_before_username_target(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["60000", "@alice"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 60010
    assert "60000 Coins an @alice vergeben" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_supports_case_insensitive_username(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["50", "@ALICE"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 60
    assert "50 Coins an @alice vergeben" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_supports_numeric_target_id_before_amount(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["111", "50"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 60


@pytest.mark.asyncio
async def test_addcoins_rejects_zero_amount(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["0", "@alice"]

    await commands["cmd_addcoins"](update, context)

    assert "Nutzung: als Reply" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_rejects_non_numeric_amount(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["fuenfzig", "@alice"]

    await commands["cmd_addcoins"](update, context)

    assert "Nutzung: als Reply" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_creates_target_entry_when_missing_and_numeric_id_is_used(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["444", "50"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 444) == 50
    assert "ID:444" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_addcoins_prefers_reply_target_over_args(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    await set_player_coins(db_path, 222, "bob", 20)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["50", "@bob"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 60
    assert await get_player_coins(db_path, 222) == 20


@pytest.mark.asyncio
async def test_addcoins_rejects_non_admin(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    target = FakeUser(111, "alice")
    update, context = make_update(222, "notadmin", reply_from_user=target)
    context.args = ["50"]

    await commands["cmd_addcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 0
    assert update.effective_message.replies[-1]["text"] == "Nur der Bot-Admin darf das."


@pytest.mark.asyncio
async def test_takecoins_never_drops_below_zero(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 20)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["50"]

    await commands["cmd_takecoins"](update, context)

    assert await get_player_coins(db_path, 111) == 0
    assert "Neuer Kontostand: 0." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_takecoins_supports_case_insensitive_username(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 70)
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["20", "@ALICE"]

    await commands["cmd_takecoins"](update, context)

    assert await get_player_coins(db_path, 111) == 50


@pytest.mark.asyncio
async def test_takecoins_on_missing_target_creates_entry_and_keeps_zero(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["555", "20"]

    await commands["cmd_takecoins"](update, context)

    assert await get_player_coins(db_path, 555) == 0
    assert "Neuer Kontostand: 0." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_takecoins_rejects_invalid_amount(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["-10", "@alice"]

    await commands["cmd_takecoins"](update, context)

    assert "Nutzung: als Reply" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_setcoins_sets_exact_value(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 20)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["345"]

    await commands["cmd_setcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 345
    assert "auf 345 Coins gesetzt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_setcoins_supports_zero_value(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 20)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["0"]

    await commands["cmd_setcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 0


@pytest.mark.asyncio
async def test_setcoins_rejects_invalid_value(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    update, context = make_update(TEST_ADMIN_ID, "owner")
    context.args = ["wert", "@alice"]

    await commands["cmd_setcoins"](update, context)

    assert "Nutzung: als Reply" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_resetcoins_sets_balance_to_zero(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "alice", 777)
    target = FakeUser(111, "alice")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)

    await commands["cmd_resetcoins"](update, context)

    assert await get_player_coins(db_path, 111) == 0
    assert "auf 0 gesetzt" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_steal_rejects_self_target(admin_deps_factory, make_update):
    commands = create_admin_coin_commands(admin_deps_factory())
    user = FakeUser(111, "alice")
    update, context = make_update(111, "alice", reply_from_user=user)
    context.args = ["10"]

    await commands["cmd_steal"](update, context)

    assert update.effective_message.replies[-1]["text"] == "Nice try. Dich selbst beklauen geht nicht."


@pytest.mark.asyncio
async def test_steal_case_insensitive_username_target(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.10]))
    await set_player_coins(db_path, 111, "thief", 100)
    await set_player_coins(db_path, 222, "target", 60)
    update, context = make_update(111, "thief")
    context.args = ["20", "@TARGET"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 120
    assert await get_player_coins(db_path, 222) == 40


@pytest.mark.asyncio
async def test_steal_blocks_when_cooldown_active(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory())
    await set_player_coins(db_path, 111, "thief", 100)
    await set_player_coins(db_path, 222, "target", 100)
    async with aiosqlite.connect(db_path) as db:
        await admin_deps_factory()["set_cd"](db, TEST_CHAT_ID, 111, "steal", 300)
        await db.commit()
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["10"]

    await commands["cmd_steal"](update, context)

    assert "Cooldown aktiv" in update.effective_message.replies[-1]["text"]
    assert await get_player_coins(db_path, 111) == 100
    assert await get_player_coins(db_path, 222) == 100


@pytest.mark.asyncio
async def test_steal_success_transfers_requested_amount(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.10]))
    await set_player_coins(db_path, 111, "thief", 20)
    await set_player_coins(db_path, 222, "target", 70)
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["50"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 70
    assert await get_player_coins(db_path, 222) == 20
    assert "klaut 50 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_steal_success_only_takes_available_balance(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.10]))
    await set_player_coins(db_path, 111, "thief", 5)
    await set_player_coins(db_path, 222, "target", 12)
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["50"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 17
    assert await get_player_coins(db_path, 222) == 0
    assert "klaut 12 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_steal_failure_applies_20_percent_penalty(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.99]))
    await set_player_coins(db_path, 111, "thief", 80)
    await set_player_coins(db_path, 222, "target", 40)
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["10"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 64
    assert await get_player_coins(db_path, 222) == 40
    assert "(-16 / 20%)" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_steal_success_against_broke_target_reports_no_loot(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.10]))
    await set_player_coins(db_path, 111, "thief", 80)
    await set_player_coins(db_path, 222, "target", 0)
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["10"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 80
    assert await get_player_coins(db_path, 222) == 0
    assert "pleite. Nix zu holen." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_steal_creates_thief_entry_when_missing(admin_deps_factory, make_update, db_path):
    commands = create_admin_coin_commands(admin_deps_factory(random_values=[0.99]))
    await set_player_coins(db_path, 222, "target", 40)
    target = FakeUser(222, "target")
    update, context = make_update(111, "thief", reply_from_user=target)
    context.args = ["10"]

    await commands["cmd_steal"](update, context)

    assert await get_player_coins(db_path, 111) == 0
    assert "(-0 / 20%)" in update.effective_message.replies[-1]["text"]
