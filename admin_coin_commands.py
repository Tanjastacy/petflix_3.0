def create_admin_coin_commands(deps: dict):
    aiosqlite = deps["aiosqlite"]
    DB = deps["DB"]
    ADMIN_ID = deps["ADMIN_ID"]
    ParseMode = deps["ParseMode"]
    escape = deps["escape"]
    random = deps["random"]
    STEAL_SUCCESS_CHANCE = deps["STEAL_SUCCESS_CHANCE"]
    STEAL_COOLDOWN_S = deps["STEAL_COOLDOWN_S"]
    STEAL_FAIL_PENALTY = deps["STEAL_FAIL_PENALTY"]
    set_cd = deps["set_cd"]
    get_cd_left = deps["get_cd_left"]
    mention_html = deps["mention_html"]
    today_ymd = deps["today_ymd"]
    is_group = deps["is_group"]
    _is_admin_here = deps["_is_admin_here"]
    _resolve_target = deps["_resolve_target"]
    _ensure_player_entry = deps["_ensure_player_entry"]
    _get_coins = deps["_get_coins"]
    _parse_amount_from_args = deps["_parse_amount_from_args"]

    async def cmd_adminping(update, context):
        if not is_group(update):
            return
        if not _is_admin_here(update):
            return
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="Admin-Ping: Ich kann dir PMs schicken und habe den Command empfangen."
            )
        except Exception:
            pass

    async def cmd_careminus(update, context):
        if not is_group(update):
            return
        if not _is_admin_here(update):
            return

        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text(
                    "Ziel nicht gefunden. Nutze Reply, @username oder user_id."
                )
            chat_id = update.effective_chat.id
            async with db.execute(
                "SELECT care_done_today, day_ymd FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, tid)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return await update.effective_message.reply_text("Kein Pflege-Eintrag fuer den User.")

            done, day = int(row[0] or 0), row[1]
            today = today_ymd()
            if day != today:
                return await update.effective_message.reply_text("Heute wurde noch nicht gepflegt.")

            new_done = max(0, done - 5)
            await db.execute(
                "UPDATE pets SET care_done_today=? WHERE chat_id=? AND pet_id=?",
                (new_done, chat_id, tid)
            )
            await db.commit()

        tag = f"@{uname}" if uname else f"ID:{tid}"
        await update.effective_message.reply_text(
            f"Pflege reduziert: {escape(tag, quote=False)} {done} -> {new_done}."
        )

    async def cmd_addcoins(update, context):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Nur der Bot-Admin darf das.")
            return
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nett versucht. Nur der Owner darf auszahlen.")
        amount = _parse_amount_from_args(context)
        if amount is None or amount <= 0:
            return await update.effective_message.reply_text(
                "Nutzung: als Reply `/addcoins 50` oder `/addcoins @user 50`.",
                parse_mode="Markdown"
            )
        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text(
                    "Ziel nicht gefunden. Antworte auf den User oder nutze @username bzw. user_id."
                )
            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            old = await _get_coins(db, chat_id, tid)
            new = old + amount
            await db.execute("UPDATE players SET coins=? WHERE chat_id=? AND user_id=?", (new, chat_id, tid))
            await db.commit()
        tag = f"@{uname}" if uname else f"ID:{tid}"
        await update.effective_message.reply_text(
            f"{amount} Coins an {escape(tag, quote=False)} vergeben. Neuer Kontostand: {new}."
        )

    async def cmd_takecoins(update, context):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Nur der Bot-Admin darf das.")
            return
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur der Owner darf abkassieren. Kapitalismus bleibt in der Familie.")
        amount = _parse_amount_from_args(context)
        if amount is None or amount <= 0:
            return await update.effective_message.reply_text(
                "Nutzung: als Reply `/takecoins 50` oder `/takecoins @user 50`.",
                parse_mode="Markdown"
            )
        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text("Ziel nicht gefunden.")
            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            old = await _get_coins(db, chat_id, tid)
            new = max(0, old - amount)
            await db.execute("UPDATE players SET coins=? WHERE chat_id=? AND user_id=?", (new, chat_id, tid))
            await db.commit()
        tag = f"@{uname}" if uname else f"ID:{tid}"
        await update.effective_message.reply_text(
            f"{amount} Coins bei {escape(tag, quote=False)} eingezogen. Neuer Kontostand: {new}."
        )

    async def cmd_setcoins(update, context):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Nur der Bot-Admin darf das.")
            return
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur der Owner darf den Kontostand setzen.")
        value = _parse_amount_from_args(context)
        if value is None or value < 0:
            return await update.effective_message.reply_text(
                "Nutzung: als Reply `/setcoins 123` oder `/setcoins @user 123`.",
                parse_mode="Markdown"
            )
        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text("Ziel nicht gefunden.")
            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            await db.execute("UPDATE players SET coins=? WHERE chat_id=? AND user_id=?", (value, chat_id, tid))
            await db.commit()
        tag = f"@{uname}" if uname else f"ID:{tid}"
        await update.effective_message.reply_text(
            f"Kontostand von {escape(tag, quote=False)} auf {value} Coins gesetzt."
        )

    async def cmd_resetcoins(update, context):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("Nur der Bot-Admin darf das.")
            return
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur der Owner darf resetten. Sonst weint die Buchhaltung.")
        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text("Ziel nicht gefunden.")
            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            await db.execute("UPDATE players SET coins=0 WHERE chat_id=? AND user_id=?", (chat_id, tid))
            await db.commit()
        tag = f"@{uname}" if uname else f"ID:{tid}"
        await update.effective_message.reply_text(
            f"Kontostand von {escape(tag, quote=False)} auf 0 gesetzt."
        )

    async def cmd_steal(update, context):
        if not is_group(update):
            return
        if not context.args:
            return await update.effective_message.reply_text(
                "Nutzung: als Reply `/steal 50` oder `/steal @user 50`.",
                parse_mode="Markdown"
            )

        amount = _parse_amount_from_args(context)
        if amount is None or amount <= 0:
            return await update.effective_message.reply_text(
                "Bitte gib eine gueltige Coin-Zahl an. Beispiel: `/steal @user 50`.",
                parse_mode="Markdown"
            )

        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text(
                    "Ziel nicht gefunden. Antworte auf den User oder nutze @username bzw. user_id."
                )
            thief = update.effective_user
            if tid == thief.id:
                return await update.effective_message.reply_text("Nice try. Dich selbst beklauen geht nicht.")

            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            await _ensure_player_entry(db, chat_id, thief.id, thief.username or thief.full_name or "")

            left = await get_cd_left(db, chat_id, thief.id, "steal")
            if left > 0:
                mins = max(1, left // 60)
                return await update.effective_message.reply_text(
                    f"Cooldown aktiv. Warte noch ca. {mins} Min.",
                    parse_mode=ParseMode.HTML
                )

            if random.random() > STEAL_SUCCESS_CHANCE:
                target_tag = mention_html(tid, uname or None)
                thief_old = await _get_coins(db, chat_id, thief.id)
                new_thief = max(0, thief_old - STEAL_FAIL_PENALTY)
                await db.execute(
                    "UPDATE players SET coins=? WHERE chat_id=? AND user_id=?",
                    (new_thief, chat_id, thief.id)
                )
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                return await update.effective_message.reply_text(
                    f"War wohl nix. {mention_html(thief.id, thief.username or None)} hat versucht {target_tag} zu beklauen - erwischt. (-{STEAL_FAIL_PENALTY})",
                    parse_mode=ParseMode.HTML
                )

            victim_coins = await _get_coins(db, chat_id, tid)
            stolen = min(amount, victim_coins)
            if stolen <= 0:
                target_tag = mention_html(tid, uname or None)
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                return await update.effective_message.reply_text(
                    f"{target_tag} ist sowieso pleite. Nix zu holen.",
                    parse_mode=ParseMode.HTML
                )

            thief_old = await _get_coins(db, chat_id, thief.id)
            await db.execute(
                "UPDATE players SET coins=? WHERE chat_id=? AND user_id=?",
                (victim_coins - stolen, chat_id, tid)
            )
            await db.execute(
                "UPDATE players SET coins=? WHERE chat_id=? AND user_id=?",
                (thief_old + stolen, chat_id, thief.id)
            )
            await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
            await db.commit()

        target_tag = mention_html(tid, uname or None)
        thief_tag = mention_html(thief.id, thief.username or None)
        await update.effective_message.reply_text(
            f"{thief_tag} klaut {stolen} Coins von {target_tag}.",
            parse_mode=ParseMode.HTML
        )

    return {
        "cmd_adminping": cmd_adminping,
        "cmd_careminus": cmd_careminus,
        "cmd_addcoins": cmd_addcoins,
        "cmd_takecoins": cmd_takecoins,
        "cmd_setcoins": cmd_setcoins,
        "cmd_resetcoins": cmd_resetcoins,
        "cmd_steal": cmd_steal,
    }
