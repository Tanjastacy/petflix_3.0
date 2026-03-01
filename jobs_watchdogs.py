def create_jobs_watchdogs(deps: dict):
    aiosqlite = deps["aiosqlite"]
    time = deps["time"]
    ParseMode = deps["ParseMode"]
    random = deps["random"]
    ALLOWED_CHAT_ID = deps["ALLOWED_CHAT_ID"]
    today_ymd = deps["today_ymd"]
    get_cd_left = deps["get_cd_left"]
    set_cd = deps["set_cd"]
    _secs_until_tomorrow = deps["_secs_until_tomorrow"]
    _pick_random_player = deps["_pick_random_player"]
    _mention_from_uid_username = deps["_mention_from_uid_username"]
    _SAVAGE_LINES = deps["_SAVAGE_LINES"]
    DAILY_GIFT_COINS = deps["DAILY_GIFT_COINS"]
    get_runtime_settings = deps["get_runtime_settings"]
    DAILY_CURSE_PENALTY = deps["DAILY_CURSE_PENALTY"]
    DAILY_PRIMETIME_COINS = deps["DAILY_PRIMETIME_COINS"]
    mention_html = deps["mention_html"]
    FLUCH_LINES = deps["FLUCH_LINES"]
    _apply_hass_penalty = deps["_apply_hass_penalty"]
    _finish_hass = deps["_finish_hass"]
    _finish_love = deps["_finish_love"]
    LOVE_PENALTY = deps["LOVE_PENALTY"]
    LOVE_REMIND_1_S = deps["LOVE_REMIND_1_S"]
    LOVE_REMIND_2_S = deps["LOVE_REMIND_2_S"]
    _care_count_last_24h = deps["_care_count_last_24h"]
    MIN_CARES_PER_24H = deps["MIN_CARES_PER_24H"]
    LEVEL_DECAY_XP = deps["LEVEL_DECAY_XP"]
    pet_level_from_xp = deps["pet_level_from_xp"]
    LEVEL_DECAY_INTERVAL_S = deps["LEVEL_DECAY_INTERVAL_S"]
    _should_runaway = deps["_should_runaway"]
    _apply_runaway_owner_penalty = deps["_apply_runaway_owner_penalty"]
    runaway_text = deps["runaway_text"]
    PRIME_TIME_LINES = [
        "Prime-Time Jackpot! {user} hat heute den Chat gerockt und kassiert +{coins} Coins.",
        "20:00 Uhr, Spotlight an: {user} schnappt sich +{coins} Coins aus dem Nichts.",
        "Abendbonus explodiert: {user} wird gezogen und nimmt +{coins} Coins mit.",
        "Zufall trifft voll: {user} raeumt den Prime-Time Pot mit +{coins} Coins ab.",
        "Jackpot-Alarm! {user} bekommt fuer heute +{coins} Coins auf die Kralle."
    ]

    async def daily_gift_job(context):
        chat_id = ALLOWED_CHAT_ID
        today = today_ymd()
        cd_key = f"dailygift:{today}"

        async with aiosqlite.connect(deps["DB"]) as db:
            left = await get_cd_left(db, chat_id, 0, cd_key)
            if left > 0:
                return

            uid, uname = await _pick_random_player(chat_id)
            if not uid:
                await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
                await db.commit()
                return

            await db.execute("UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?", (DAILY_GIFT_COINS, chat_id, uid))
            await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
            await db.commit()

        user_mention = _mention_from_uid_username(uid, uname)
        line = random.choice(_SAVAGE_LINES).format(user=user_mention, coins=DAILY_GIFT_COINS)
        await context.bot.send_message(chat_id=chat_id, text=f"Taegliche Almosen-Time!\n{line}", parse_mode="Markdown")

    async def daily_curse_job(context):
        chat_id = ALLOWED_CHAT_ID
        today = today_ymd()
        cd_key = f"dailycurse:{today}"

        async with aiosqlite.connect(deps["DB"]) as db:
            runtime = await get_runtime_settings(db, chat_id)
            if not runtime["daily_curse_enabled"]:
                await db.commit()
                return
            left = await get_cd_left(db, chat_id, 0, cd_key)
            if left > 0:
                return

            uid, uname = await _pick_random_player(chat_id)
            if not uid:
                await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
                await db.commit()
                return

            await db.execute(
                "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
                (DAILY_CURSE_PENALTY, chat_id, uid)
            )
            await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
            await db.commit()

        user_mention = mention_html(uid, uname)
        line = random.choice(FLUCH_LINES).format(user=user_mention)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Taeglicher Fluch!\n{line}\n<b>Strafe:</b> -{DAILY_CURSE_PENALTY} Coins",
            parse_mode=ParseMode.HTML
        )

    async def daily_primetime_job(context):
        chat_id = ALLOWED_CHAT_ID
        today = today_ymd()
        cd_key = f"dailyprimetime:{today}"

        async with aiosqlite.connect(deps["DB"]) as db:
            left = await get_cd_left(db, chat_id, 0, cd_key)
            if left > 0:
                return

            async with db.execute(
                """
                SELECT user_id, username
                FROM players
                WHERE chat_id=?
                  AND last_seen IS NOT NULL
                  AND date(last_seen, 'unixepoch', 'localtime') = ?
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (chat_id, today),
            ) as cur:
                row = await cur.fetchone()

            if not row:
                await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
                await db.commit()
                return

            uid = int(row[0])
            uname = row[1] if len(row) > 1 else None
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (DAILY_PRIMETIME_COINS, chat_id, uid),
            )
            await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
            await db.commit()

        user_mention = mention_html(uid, uname or None)
        line = random.choice(PRIME_TIME_LINES).format(user=user_mention, coins=DAILY_PRIMETIME_COINS)
        await context.bot.send_message(chat_id=chat_id, text=line, parse_mode=ParseMode.HTML)

    async def hass_watchdog_job(context):
        chat_id = ALLOWED_CHAT_ID
        now = int(time.time())

        async with aiosqlite.connect(deps["DB"]) as db:
            async with db.execute("""
                SELECT user_id, username, expires_ts, required, done, penalty
                FROM hass_challenges
                WHERE chat_id=? AND active=1 AND expires_ts <= ?
            """, (chat_id, now)) as cur:
                rows = await cur.fetchall()

            if not rows:
                return

            for user_id, username, expires_ts, required, done, penalty in rows:
                user_id = int(user_id)
                required = int(required)
                done = int(done)
                penalty = int(penalty)

                if done < required:
                    await _apply_hass_penalty(db, chat_id, user_id, penalty)
                    msg = f"Hass-Deadline vorbei. {mention_html(user_id, username or None)} hat nur {done}/{required}. -{penalty} Coins."
                else:
                    msg = f"Hass-Check: {mention_html(user_id, username or None)} war rechtzeitig ({done}/{required})."

                await _finish_hass(db, chat_id, user_id)

                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                except Exception:
                    pass

            await db.commit()

    async def love_watchdog_job(context):
        chat_id = ALLOWED_CHAT_ID
        now = int(time.time())

        async with aiosqlite.connect(deps["DB"]) as db:
            async with db.execute("""
                SELECT user_id, username, started_ts, expires_ts, remind_stage
                FROM love_challenges
                WHERE chat_id=? AND active=1
            """, (chat_id,)) as cur:
                rows = await cur.fetchall()

            if not rows:
                return

            for user_id, username, started_ts, expires_ts, remind_stage in rows:
                user_id = int(user_id)
                started_ts = int(started_ts or 0)
                expires_ts = int(expires_ts or 0)
                remind_stage = int(remind_stage or 0)

                if expires_ts <= now:
                    await db.execute(
                        "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
                        (LOVE_PENALTY, chat_id, user_id)
                    )
                    await _finish_love(db, chat_id, user_id)
                    msg = (
                        f"{mention_html(user_id, username or None)} hatte nicht genug Eier fuer ein bisschen Liebe.\n"
                        "Jetzt weiss jeder: Unter der harten Schale steckt nichts. Nur Leere und kalte Finger."
                    )
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
                    continue

                if remind_stage == 0 and now >= started_ts + LOVE_REMIND_2_S:
                    remind_stage = 2
                    left = max(0, expires_ts - now)
                    m = left // 60
                    msg = f"{mention_html(user_id, username or None)} letzte Erinnerung: noch {m}m fuer dein Liebesgestaendniss."
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
                    await db.execute(
                        "UPDATE love_challenges SET remind_stage=? WHERE chat_id=? AND user_id=?",
                        (remind_stage, chat_id, user_id)
                    )
                    continue

                if remind_stage == 0 and now >= started_ts + LOVE_REMIND_1_S:
                    remind_stage = 1
                    left = max(0, expires_ts - now)
                    m = left // 60
                    msg = f"{mention_html(user_id, username or None)} Erinnerung: noch {m}m fuer dein Liebesgestaendniss."
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
                    await db.execute(
                        "UPDATE love_challenges SET remind_stage=? WHERE chat_id=? AND user_id=?",
                        (remind_stage, chat_id, user_id)
                    )
                    continue

                if remind_stage == 1 and now >= started_ts + LOVE_REMIND_2_S:
                    remind_stage = 2
                    left = max(0, expires_ts - now)
                    m = left // 60
                    msg = f"{mention_html(user_id, username or None)} letzte Erinnerung: noch {m}m fuer dein Liebesgestaendniss."
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                    except Exception:
                        pass
                    await db.execute(
                        "UPDATE love_challenges SET remind_stage=? WHERE chat_id=? AND user_id=?",
                        (remind_stage, chat_id, user_id)
                    )

            await db.commit()

    async def runaway_watchdog_job(context):
        chat_id = ALLOWED_CHAT_ID
        now = int(time.time())

        async with aiosqlite.connect(deps["DB"]) as db:
            await db.execute(
                "UPDATE pets SET last_care_ts=? WHERE chat_id=? AND last_care_ts IS NULL",
                (now, chat_id)
            )
            await db.execute(
                "UPDATE pets SET acquired_ts=COALESCE(acquired_ts, last_care_ts, ?) WHERE chat_id=?",
                (now, chat_id)
            )

            async with db.execute("""
                SELECT p.pet_id, p.owner_id, p.acquired_ts, pl.username, ou.username
                FROM pets p
                LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
                LEFT JOIN players ou ON ou.chat_id=p.chat_id AND ou.user_id=p.owner_id
                WHERE p.chat_id=?
            """, (chat_id,)) as cur:
                rows = await cur.fetchall()

            if not rows:
                await db.commit()
                return

            for pet_id, owner_id, acquired_ts, pet_username, owner_username in rows:
                if not owner_id:
                    continue
                pet_id_i = int(pet_id)
                owner_id_i = int(owner_id)
                care_24h = await _care_count_last_24h(db, chat_id, pet_id_i, owner_id_i, now)

                if care_24h < MIN_CARES_PER_24H:
                    decay_key = f"petlvl_decay:{pet_id_i}"
                    decay_left = await get_cd_left(db, chat_id, 0, decay_key)
                    if decay_left <= 0:
                        async with db.execute(
                            "SELECT COALESCE(pet_xp,0) FROM pets WHERE chat_id=? AND pet_id=?",
                            (chat_id, pet_id_i)
                        ) as cur:
                            xp_row = await cur.fetchone()
                        old_xp = int(xp_row[0]) if xp_row and xp_row[0] is not None else 0
                        new_xp = max(0, old_xp - LEVEL_DECAY_XP)
                        if new_xp != old_xp:
                            old_level = pet_level_from_xp(old_xp)
                            new_level = pet_level_from_xp(new_xp)
                            await db.execute(
                                "UPDATE pets SET pet_xp=?, pet_level=? WHERE chat_id=? AND pet_id=?",
                                (new_xp, new_level, chat_id, pet_id_i)
                            )
                            pet_tag = mention_html(pet_id_i, pet_username or None)
                            owner_tag = mention_html(owner_id_i, owner_username or None)
                            try:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=(
                                        f"Pflege-Reminder: {pet_tag} hat zu wenig Pflege (<{MIN_CARES_PER_24H}/24h). "
                                        f"-{LEVEL_DECAY_XP} XP | Level {old_level} -> {new_level} (Owner: {owner_tag})."
                                    ),
                                    parse_mode=ParseMode.HTML
                                )
                            except Exception:
                                pass
                        await set_cd(db, chat_id, 0, decay_key, LEVEL_DECAY_INTERVAL_S)

                if not await _should_runaway(db, chat_id, pet_id_i, owner_id_i, acquired_ts, now):
                    continue
                await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id_i))
                await _apply_runaway_owner_penalty(db, chat_id, owner_id_i)
                pet_tag = mention_html(pet_id_i, pet_username or None)
                owner_tag = mention_html(owner_id_i, owner_username or None)
                msg = runaway_text(pet_tag, owner_tag)
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                except Exception:
                    pass

            await db.commit()

    return {
        "daily_gift_job": daily_gift_job,
        "daily_curse_job": daily_curse_job,
        "daily_primetime_job": daily_primetime_job,
        "hass_watchdog_job": hass_watchdog_job,
        "love_watchdog_job": love_watchdog_job,
        "runaway_watchdog_job": runaway_watchdog_job,
    }
