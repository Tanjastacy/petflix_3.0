import pytest

from economy_commands import create_economy_commands
from tests.conftest import FakeUser, TEST_CHAT_ID, get_player_coins, set_player_coins


@pytest.mark.asyncio
async def test_balance_returns_zero_for_new_user(economy_deps_factory, make_update):
    commands = create_economy_commands(economy_deps_factory())
    update, context = make_update(111, "alice")

    await commands["cmd_balance"](update, context)

    assert update.effective_message.replies[-1]["text"] == "Dein Kontostand: 0 Coins."


@pytest.mark.asyncio
async def test_gift_rejects_self_gift(economy_deps_factory, make_update):
    commands = create_economy_commands(economy_deps_factory())
    user = FakeUser(111, "alice")
    update, context = make_update(111, "alice", reply_from_user=user)
    context.args = ["25"]

    await commands["cmd_gift"](update, context)

    assert update.effective_message.replies[-1]["text"] == "Dich selbst beschenken? Nett versucht."


@pytest.mark.asyncio
async def test_gift_rejects_when_sender_has_too_few_coins(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory())
    await set_player_coins(db_path, 111, "alice", 10)
    target = FakeUser(222, "bob")
    update, context = make_update(111, "alice", reply_from_user=target)
    context.args = ["25"]

    await commands["cmd_gift"](update, context)

    assert await get_player_coins(db_path, 111) == 10
    assert await get_player_coins(db_path, 222) == 0
    assert "Zu wenig Coins. Dein Guthaben: 10." == update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_gift_transfers_coins_to_reply_target(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory())
    await set_player_coins(db_path, 111, "alice", 100)
    await set_player_coins(db_path, 222, "bob", 5)
    target = FakeUser(222, "bob")
    update, context = make_update(111, "alice", reply_from_user=target)
    context.args = ["40"]

    await commands["cmd_gift"](update, context)

    assert await get_player_coins(db_path, 111) == 60
    assert await get_player_coins(db_path, 222) == 45
    assert "Geschenk:" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_daily_awards_bonus_and_sets_cooldown(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory())
    update, context = make_update(111, "alice")

    await commands["cmd_daily"](update, context)

    assert await get_player_coins(db_path, 111) == 250
    assert update.effective_message.replies[-1]["text"] == "+250 Coins Tagesbonus."


@pytest.mark.asyncio
async def test_daily_respects_existing_cooldown(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory())
    update, context = make_update(111, "alice")

    await commands["cmd_daily"](update, context)
    await commands["cmd_daily"](update, context)

    assert await get_player_coins(db_path, 111) == 250
    assert "Daily wieder in" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_rejects_bet_outside_limits(economy_deps_factory, make_update):
    commands = create_economy_commands(economy_deps_factory())
    update, context = make_update(111, "alice")
    context.args = ["5"]

    await commands["cmd_blackjack"](update, context)

    assert "Einsatz muss zwischen 10 und 200 liegen." == update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_rejects_when_balance_is_too_low(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory())
    await set_player_coins(db_path, 111, "alice", 30)
    update, context = make_update(111, "alice")
    context.args = ["50"]

    await commands["cmd_blackjack"](update, context)

    assert await get_player_coins(db_path, 111) == 30
    assert "Zu wenig Coins. Du hast 30, Einsatz waere 50." == update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_bust_loses_bet_and_sets_cooldown(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory(random_values=[0.10]))
    await set_player_coins(db_path, 111, "alice", 100)
    update, context = make_update(111, "alice")
    context.args = ["20"]

    await commands["cmd_blackjack"](update, context)

    assert await get_player_coins(db_path, 111) == 80
    assert "Einsatz -20" in update.effective_message.replies[-1]["text"]

    await commands["cmd_blackjack"](update, context)
    assert "Blackjack-Cooldown aktiv" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_push_returns_stake(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory(random_values=[0.45]))
    await set_player_coins(db_path, 111, "alice", 100)
    update, context = make_update(111, "alice")
    context.args = ["20"]

    await commands["cmd_blackjack"](update, context)

    assert await get_player_coins(db_path, 111) == 100
    assert "Einsatz zurueck (+0)" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_win_pays_double(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory(random_values=[0.70]))
    await set_player_coins(db_path, 111, "alice", 100)
    update, context = make_update(111, "alice")
    context.args = ["20"]

    await commands["cmd_blackjack"](update, context)

    assert await get_player_coins(db_path, 111) == 120
    assert "Gewinn +20" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_blackjack_blackjack_pays_two_point_five_x(economy_deps_factory, make_update, db_path):
    commands = create_economy_commands(economy_deps_factory(random_values=[0.95]))
    await set_player_coins(db_path, 111, "alice", 100)
    update, context = make_update(111, "alice")
    context.args = ["20"]

    await commands["cmd_blackjack"](update, context)

    assert await get_player_coins(db_path, 111) == 130
    assert "Blackjack" in update.effective_message.replies[-1]["text"]
    assert "Gewinn +30" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_id_returns_chat_id(economy_deps_factory, make_update):
    commands = create_economy_commands(economy_deps_factory())
    update, context = make_update(111, "alice", chat_id=TEST_CHAT_ID)

    await commands["cmd_id"](update, context)

    assert update.effective_message.replies[-1]["text"] == f"Chat ID: {TEST_CHAT_ID}"
