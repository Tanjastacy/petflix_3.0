def create_economy_commands(deps: dict):
    aiosqlite = deps["aiosqlite"]
    DB = deps["DB"]
    ParseMode = deps["ParseMode"]
    random = deps["random"]
    is_group = deps["is_group"]
    _parse_amount_from_args = deps["_parse_amount_from_args"]
    _resolve_target = deps["_resolve_target"]
    _ensure_player_entry = deps["_ensure_player_entry"]
    _get_coins = deps["_get_coins"]
    mention_html = deps["mention_html"]
    ensure_player = deps["ensure_player"]
    get_cd_left = deps["get_cd_left"]
    set_cd = deps["set_cd"]
    DAILY_COINS = deps["DAILY_COINS"]
    DAILY_COOLDOWN_S = deps["DAILY_COOLDOWN_S"]
    BLACKJACK_COOLDOWN_S = deps["BLACKJACK_COOLDOWN_S"]
    BLACKJACK_MIN_BET = deps["BLACKJACK_MIN_BET"]
    BLACKJACK_MAX_BET = deps["BLACKJACK_MAX_BET"]
    BLACKJACK_OUTCOMES = deps["BLACKJACK_OUTCOMES"]

    async def cmd_balance(update, context):
        if not is_group(update):
            return
        chat_id = update.effective_chat.id
        uid = update.effective_user.id
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, uid)) as cur:
                row = await cur.fetchone()
        coins = row[0] if row else 0
        await update.effective_message.reply_text(f"Dein Kontostand: {coins} Coins.")

    async def cmd_gift(update, context):
        if not is_group(update):
            return
        msg = update.effective_message
        amount = _parse_amount_from_args(context)
        if amount is None or amount <= 0:
            return await msg.reply_text(
                "Nutzung: als Reply `/treat 50` oder `/treat @user 50`.",
                parse_mode="Markdown"
            )
        async with aiosqlite.connect(DB) as db:
            chat_id = update.effective_chat.id
            sender = update.effective_user

            if msg.reply_to_message and msg.reply_to_message.from_user:
                target = msg.reply_to_message.from_user
                tid = target.id
                tname = target.username or None
            else:
                if not context.args or len(context.args) < 2:
                    return await msg.reply_text(
                        "Nutzung: als Reply `/treat 50` oder `/treat @user 50`.",
                        parse_mode="Markdown"
                    )
                tid, tname = await _resolve_target(db, update, context)

            if not tid:
                return await msg.reply_text("Ziel nicht gefunden. Antworte auf den User oder nutze @username bzw. user_id.")
            if tid == sender.id:
                return await msg.reply_text("Dich selbst beschenken? Nett versucht.")

            await _ensure_player_entry(db, chat_id, sender.id, sender.username or sender.full_name or "")
            await _ensure_player_entry(db, chat_id, tid, tname)
            sender_coins = await _get_coins(db, chat_id, sender.id)
            if sender_coins < amount:
                return await msg.reply_text(f"Zu wenig Coins. Dein Guthaben: {sender_coins}.")

            await db.execute(
                "UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?",
                (amount, chat_id, sender.id)
            )
            await db.execute(
                "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                (amount, chat_id, tid)
            )
            await db.commit()

        sender_tag = mention_html(sender.id, sender.username or None)
        target_tag = mention_html(tid, tname if tname else None)
        await msg.reply_text(f"Geschenk: {sender_tag} schenkt {target_tag} {amount} Coins.", parse_mode=ParseMode.HTML)

    async def cmd_daily(update, context):
        if not is_group(update):
            return
        chat_id = update.effective_chat.id
        uid = update.effective_user.id
        async with aiosqlite.connect(DB) as db:
            await ensure_player(db, chat_id, uid, update.effective_user.username or update.effective_user.full_name or "")
            left = await get_cd_left(db, chat_id, uid, "daily")
            if left > 0:
                await db.commit()
                return await update.effective_message.reply_text(f"Daily wieder in {left // 60} Min.")
            await db.execute("UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?", (DAILY_COINS, chat_id, uid))
            await set_cd(db, chat_id, uid, "daily", DAILY_COOLDOWN_S)
            await db.commit()
        await update.effective_message.reply_text(f"+{DAILY_COINS} Coins Tagesbonus.")

    async def cmd_blackjack(update, context):
        if not is_group(update):
            return
        amount = _parse_amount_from_args(context)
        if amount is None:
            return await update.effective_message.reply_text(
                f"Nutzung: /blackjack <einsatz> (min {BLACKJACK_MIN_BET}, max {BLACKJACK_MAX_BET})"
            )
        if amount < BLACKJACK_MIN_BET or amount > BLACKJACK_MAX_BET:
            return await update.effective_message.reply_text(
                f"Einsatz muss zwischen {BLACKJACK_MIN_BET} und {BLACKJACK_MAX_BET} liegen."
            )

        chat_id = update.effective_chat.id
        user = update.effective_user
        uid = user.id

        async with aiosqlite.connect(DB) as db:
            await ensure_player(db, chat_id, uid, user.username or user.full_name or "")
            left = await get_cd_left(db, chat_id, uid, "blackjack")
            if left > 0:
                return await update.effective_message.reply_text(
                    f"Blackjack-Cooldown aktiv. Versuch es in {left}s nochmal."
                )

            coins = await _get_coins(db, chat_id, uid)
            if coins < amount:
                return await update.effective_message.reply_text(
                    f"Zu wenig Coins. Du hast {coins}, Einsatz waere {amount}."
                )

            await db.execute(
                "UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?",
                (amount, chat_id, uid)
            )

            r = random.random()
            acc = 0.0
            result_key, _, payout_mult, result_name = BLACKJACK_OUTCOMES[-1]
            for key, chance, mult, label in BLACKJACK_OUTCOMES:
                acc += chance
                if r <= acc:
                    result_key, payout_mult, result_name = key, mult, label
                    break

            payout_total = int(amount * payout_mult)
            net = payout_total - amount
            if payout_total > 0:
                await db.execute(
                    "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                    (payout_total, chat_id, uid)
                )

            await set_cd(db, chat_id, uid, "blackjack", BLACKJACK_COOLDOWN_S)
            async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, uid)) as cur:
                row = await cur.fetchone()
            final_coins = int(row[0]) if row else 0
            await db.commit()

        if result_key == "bust":
            line = f"Blackjack: <b>{result_name}</b>. Einsatz -{amount}. Neuer Stand: {final_coins}."
        elif result_key == "push":
            line = f"Blackjack: <b>{result_name}</b>. Einsatz zurueck (+0). Neuer Stand: {final_coins}."
        elif result_key == "blackjack":
            line = f"Blackjack: <b>{result_name}</b>! Gewinn +{net}. Neuer Stand: {final_coins}."
        else:
            line = f"Blackjack: <b>{result_name}</b>. Gewinn +{net}. Neuer Stand: {final_coins}."

        await update.effective_message.reply_text(line, parse_mode=ParseMode.HTML)

    async def cmd_id(update, context):
        await update.effective_message.reply_text(f"Chat ID: {update.effective_chat.id}")

    return {
        "cmd_balance": cmd_balance,
        "cmd_gift": cmd_gift,
        "cmd_daily": cmd_daily,
        "cmd_blackjack": cmd_blackjack,
        "cmd_id": cmd_id,
    }
