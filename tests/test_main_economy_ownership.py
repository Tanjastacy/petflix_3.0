import time

import pytest

from tests.conftest import TEST_ADMIN_ID, TEST_CHAT_ID, FakeUser, fetch_scalar, get_player_coins, upsert_pet, upsert_player


@pytest.mark.asyncio
async def test_treasure_awards_daily_amount_and_blocks_second_claim(main_module, main_db_path, make_update, monkeypatch):
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    update, context = make_update(111, "alice")

    await main_module.cmd_treasure(update, context)

    gained = await get_player_coins(main_db_path, 111)
    assert gained == main_module._daily_treasure_amount(111, TEST_CHAT_ID, main_module.today_ymd())
    assert str(gained) in update.effective_message.replies[-1]["text"]

    await main_module.cmd_treasure(update, context)
    assert "heute schon gegraben" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_boxen_shows_box_overview(main_module, make_update):
    update, context = make_update(111, "alice")

    await main_module.cmd_boxen(update, context)

    assert "Kellerkiste" in update.effective_message.replies[-1]["text"]
    assert "Abyss-Kiste" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_requires_choice(main_module, make_update):
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox(update, context)

    assert update.effective_message.replies[-1]["text"] == "Nutzung: /buybox <keller|abyss>"


@pytest.mark.asyncio
async def test_buybox_keller_opens_and_updates_balance(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST + 5000)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.10)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    expected = 5000 + main_module._min_box_coin_payout(main_module.BOX_STANDARD_COST)
    assert await get_player_coins(main_db_path, 111) == expected
    assert "Kellerkiste" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_abyss_opens_and_updates_balance(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_ABYSS_COST + 30000)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.10)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_abyss(update, context)

    expected = 30000 + main_module._min_box_coin_payout(main_module.BOX_ABYSS_COST)
    assert await get_player_coins(main_db_path, 111) == expected
    assert "Abyss-Kiste" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_keller_allows_exact_balance(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.10)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    assert await get_player_coins(main_db_path, 111) == main_module._min_box_coin_payout(main_module.BOX_STANDARD_COST)


@pytest.mark.asyncio
async def test_buybox_keller_rejects_when_one_coin_short(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST - 1)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    assert "Zu teuer." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_keller_fallback_without_pet_uses_coin_reward(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST + 1000)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.90)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    assert await get_player_coins(main_db_path, 111) == 1000 + main_module._min_box_coin_payout(main_module.BOX_STANDARD_COST)
    assert "Trostpflaster" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_keller_xp_reward_with_pet_does_not_change_coin_balance(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST + 1000)
    await upsert_pet(main_db_path, 222, 111, pet_xp=0, pet_level=0)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.90)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    assert await get_player_coins(main_db_path, 111) == 1000
    assert await fetch_scalar(main_db_path, "SELECT pet_xp FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 18


@pytest.mark.asyncio
async def test_buybox_keller_shield_sets_cooldown(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_STANDARD_COST + 1000)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.80)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_keller(update, context)

    shield_until = await fetch_scalar(
        main_db_path,
        "SELECT ts FROM cooldowns WHERE chat_id=? AND user_id=? AND key=?",
        (TEST_CHAT_ID, 111, main_module.CURSE_SHIELD_KEY),
    )
    assert shield_until is not None
    assert "Fluchschild" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buybox_abyss_jackpot_gives_title_and_large_coin_reward(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "alice", coins=main_module.BOX_ABYSS_COST + 10000)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.97)
    monkeypatch.setattr(main_module.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(main_module.random, "randint", lambda a, b: a)
    update, context = make_update(111, "alice")

    await main_module.cmd_buybox_abyss(update, context)

    assert await get_player_coins(main_db_path, 111) == 10000 + max(main_module._min_box_coin_payout(main_module.BOX_ABYSS_COST), 28000)
    assert await fetch_scalar(main_db_path, "SELECT title FROM user_titles WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 111)) is not None
    assert "+28000 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buy_purchases_unowned_pet_and_raises_price(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    monkeypatch.setattr(main_module, "resolve_next_skill", lambda prev, has_prev: ("schildwall", False))
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)

    await main_module.cmd_buy(update, context)

    assert await get_player_coins(main_db_path, 111) == 400
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 111
    assert await fetch_scalar(main_db_path, "SELECT price FROM players WHERE chat_id=? AND user_id=?", (TEST_CHAT_ID, 222)) == 300
    assert "fuer 100 Coins gekauft" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buy_allows_exact_balance(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "buyer", coins=100)
    await upsert_player(main_db_path, 222, "target", price=100)
    monkeypatch.setattr(main_module, "resolve_next_skill", lambda prev, has_prev: ("schildwall", False))
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)

    await main_module.cmd_buy(update, context)

    assert await get_player_coins(main_db_path, 111) == 0


@pytest.mark.asyncio
async def test_buy_rejects_when_pet_is_locked(main_module, main_db_path, make_update):
    now = int(time.time())
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_pet(main_db_path, 222, 333, purchase_lock_until=now + 3600)
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)

    await main_module.cmd_buy(update, context)

    assert "geschuetzt" in update.effective_message.replies[-1]["text"]
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 333


@pytest.mark.asyncio
async def test_buy_rejects_unknown_username(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    update, context = make_update(111, "buyer")
    context.args = ["@missing"]

    await main_module.cmd_buy(update, context)

    assert "User nicht gefunden" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buy_rejects_self_target(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500, price=100)
    update, context = make_update(111, "buyer")
    context.args = ["@buyer"]

    await main_module.cmd_buy(update, context)

    assert "Dich selbst kaufen?" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buy_rejects_bot_target(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    target = FakeUser(222, "target", is_bot=True)
    update, context = make_update(111, "buyer", reply_from_user=target)

    await main_module.cmd_buy(update, context)

    assert "Mich kaufst du nicht" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_buy_rejects_when_pet_already_owned_by_buyer(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_pet(main_db_path, 222, 111)
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)

    await main_module.cmd_buy(update, context)

    assert "bereits" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_success_steals_pet_and_charges_price_plus_risk(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_player(main_db_path, 333, "owner", coins=0)
    await upsert_pet(main_db_path, 222, 333, care_done_today=0, day_ymd=main_module.today_ymd(), purchase_lock_until=0)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.10)
    monkeypatch.setattr(main_module, "resolve_next_skill", lambda prev, has_prev: ("schildwall", False))
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert await get_player_coins(main_db_path, 111) == 350
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 111
    assert "Risk: 50 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_admin_risk_uses_hidden_90_percent_success(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, TEST_ADMIN_ID, "owner", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_player(main_db_path, 333, "otherowner", coins=0)
    await upsert_pet(main_db_path, 222, 333, care_done_today=0, day_ymd=main_module.today_ymd(), purchase_lock_until=0)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.89)
    monkeypatch.setattr(main_module, "resolve_next_skill", lambda prev, has_prev: ("schildwall", False))
    target = FakeUser(222, "target")
    update, context = make_update(TEST_ADMIN_ID, "owner", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert await get_player_coins(main_db_path, TEST_ADMIN_ID) == 350
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == TEST_ADMIN_ID
    assert "Risk: 50 Coins" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_rejects_missing_target(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    update, context = make_update(111, "buyer")
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert "Nutzung: als Reply" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_rejects_unowned_target(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert "Risk geht nur" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_rejects_when_funds_are_too_low(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "buyer", coins=120)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_player(main_db_path, 333, "owner", coins=0)
    await upsert_pet(main_db_path, 222, 333, care_done_today=0, day_ymd=main_module.today_ymd(), purchase_lock_until=0)
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert "Zu wenig Coins. Preis: 100 + Risiko: 50 = 150." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_failure_applies_penalty_and_leaves_owner(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, 222, "target", price=100)
    await upsert_player(main_db_path, 333, "owner", coins=0)
    await upsert_pet(main_db_path, 222, 333, care_done_today=0, day_ymd=main_module.today_ymd(), purchase_lock_until=0)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.99)
    target = FakeUser(222, "target")
    update, context = make_update(111, "buyer", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert await get_player_coins(main_db_path, 111) == 350
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 333
    assert "Blutgeld: -100 Coins (20%) + Riskeinsatz -50" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_risk_against_admin_owned_pet_always_fails_with_normal_failure_text(main_module, main_db_path, make_update, monkeypatch):
    await upsert_player(main_db_path, 111, "buyer", coins=500)
    await upsert_player(main_db_path, TEST_ADMIN_ID, "owner", price=100)
    await upsert_player(main_db_path, 222, "holder", coins=0)
    await upsert_pet(main_db_path, TEST_ADMIN_ID, 222, care_done_today=0, day_ymd=main_module.today_ymd(), purchase_lock_until=0)
    monkeypatch.setattr(main_module.random, "random", lambda: 0.10)
    target = FakeUser(TEST_ADMIN_ID, "owner")
    update, context = make_update(111, "buyer", reply_from_user=target)
    context.args = ["50"]

    await main_module.cmd_risk(update, context)

    assert await get_player_coins(main_db_path, 111) == 350
    assert await fetch_scalar(main_db_path, "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, TEST_ADMIN_ID)) == 222
    assert "Fehlschlag" in update.effective_message.replies[-1]["text"]
    assert "Blutgeld: -100 Coins (20%) + Riskeinsatz -50" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_owner_without_owner_shows_no_owner(ownership_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 222, "pet", price=250)
    target = FakeUser(222, "pet")
    update, context = make_update(9999, "viewer", reply_from_user=target)

    await ownership_commands["cmd_owner"](update, context)

    assert "Kein Besitzer." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_owner_reports_current_owner_and_price(ownership_commands, main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "owner")
    await upsert_player(main_db_path, 222, "pet", price=250)
    await upsert_pet(main_db_path, 222, 111, pet_skill="schildwall", pet_level=1, pet_xp=10, fullcare_days=2, fullcare_streak=1)
    target = FakeUser(222, "pet")
    update, context = make_update(9999, "viewer", reply_from_user=target)

    await ownership_commands["cmd_owner"](update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "Besitzer:" in text
    assert "250" in text


@pytest.mark.asyncio
async def test_ownerlist_empty_reports_no_relationships(ownership_commands, make_update):
    update, context = make_update(111, "owner")

    await ownership_commands["cmd_ownerlist"](update, context)

    assert "Noch keine Besitzverhaeltnisse" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_ownerlist_groups_pets_by_owner(ownership_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "owner")
    await upsert_player(main_db_path, 222, "pet1", price=300)
    await upsert_player(main_db_path, 333, "pet2", price=100)
    await upsert_pet(main_db_path, 222, 111, pet_skill="schildwall", pet_level=1, fullcare_days=0)
    await upsert_pet(main_db_path, 333, 111, pet_skill="goldesel", pet_level=2, fullcare_days=1)
    update, context = make_update(111, "owner")

    await ownership_commands["cmd_ownerlist"](update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "Ownerliste" in text
    assert "@pet1" in text
    assert "@pet2" in text


@pytest.mark.asyncio
async def test_release_requires_reply(ownership_commands, make_update):
    update, context = make_update(111, "owner")

    await ownership_commands["cmd_release"](update, context)

    assert "Antworte auf dein Haustier" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_release_rejects_foreign_pet(ownership_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "owner")
    await upsert_player(main_db_path, 333, "other")
    await upsert_player(main_db_path, 222, "pet")
    await upsert_pet(main_db_path, 222, 333)
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target)

    await ownership_commands["cmd_release"](update, context)

    assert "nicht dein Haustier" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_release_removes_pet_relationship(ownership_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "owner")
    await upsert_player(main_db_path, 222, "pet")
    await upsert_pet(main_db_path, 222, 111)
    target = FakeUser(222, "pet")
    update, context = make_update(111, "owner", reply_from_user=target)

    await ownership_commands["cmd_release"](update, context)

    assert await fetch_scalar(main_db_path, "SELECT COUNT(*) FROM pets WHERE chat_id=? AND pet_id=?", (TEST_CHAT_ID, 222)) == 0
    assert "Freigelassen" in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_prices_empty_reports_no_users(main_module, main_db_path, make_update):
    update, context = make_update(111, "alice")

    await main_module.cmd_prices(update, context)

    assert "Keine User gefunden." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_prices_lists_users_by_price(main_module, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", price=300)
    await upsert_player(main_db_path, 222, "bob", price=100)
    update, context = make_update(111, "alice")

    await main_module.cmd_prices(update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "Preisliste aller User" in text
    assert text.index("@alice") < text.index("@bob")


@pytest.mark.asyncio
async def test_top_empty_reports_no_players(ownership_commands, make_update):
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await ownership_commands["cmd_top"](update, context)

    assert "Noch keine Spieler." in update.effective_message.replies[-1]["text"]


@pytest.mark.asyncio
async def test_top_lists_richest_players(ownership_commands, main_db_path, make_update):
    await upsert_player(main_db_path, 111, "alice", coins=500)
    await upsert_player(main_db_path, 222, "bob", coins=100)
    await upsert_player(main_db_path, 333, "charlie", coins=50)
    update, context = make_update(TEST_ADMIN_ID, "owner")

    await ownership_commands["cmd_top"](update, context)

    text = update.effective_message.replies[-1]["text"]
    assert "Rangliste aller Spieler" in text
    assert text.index("@alice") < text.index("@bob")
    assert text.index("@bob") < text.index("@charlie")
