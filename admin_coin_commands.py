def create_admin_coin_commands(deps: dict):
    aiosqlite = deps["aiosqlite"]
    DB = deps["DB"]
    ADMIN_ID = deps["ADMIN_ID"]
    ParseMode = deps["ParseMode"]
    escape = deps["escape"]
    random = deps["random"]
    load_json_dict = deps.get("load_json_dict", lambda _path: {})
    STEAL_TEXTS_PATH = deps.get("STEAL_TEXTS_PATH", "")
    STEAL_SUCCESS_CHANCE = deps["STEAL_SUCCESS_CHANCE"]
    STEAL_COOLDOWN_S = deps["STEAL_COOLDOWN_S"]
    STEAL_FAIL_PENALTY_RATIO = deps["STEAL_FAIL_PENALTY_RATIO"]
    FEUD_REVENGE_WINDOW_S = deps.get("FEUD_REVENGE_WINDOW_S", 0)
    FEUD_REVENGE_CHANCE_BONUS = deps.get("FEUD_REVENGE_CHANCE_BONUS", 0.0)
    FEUD_STAGE_BONUS = deps.get("FEUD_STAGE_BONUS", {0: {"label": "Still", "chance": 0.0, "steal_pct": 0.0}})
    set_cd = deps["set_cd"]
    get_cd_left = deps["get_cd_left"]
    mention_html = deps["mention_html"]
    format_duration = deps.get("format_duration", lambda seconds: f"{int(seconds)}s")
    today_ymd = deps["today_ymd"]
    is_group = deps["is_group"]
    _is_admin_here = deps["_is_admin_here"]
    _resolve_target = deps["_resolve_target"]
    _ensure_player_entry = deps["_ensure_player_entry"]
    _get_coins = deps["_get_coins"]
    _parse_amount_from_args = deps["_parse_amount_from_args"]
    feud_revenge_key = deps.get("feud_revenge_key", lambda target_id: f"steal_revenge:{target_id}")
    feud_stage_label = deps.get("feud_stage_label", lambda _stage: "Still")
    format_feud_stage_trigger = deps.get("format_feud_stage_trigger", lambda _stage, _attacker, _victim: "")

    async def _default_get_feud_state(_db, _chat_id, _user_a, _user_b):
        return {
            "active": False,
            "heat": 0,
            "clash_count": 0,
            "success_count": 0,
            "stage": 0,
            "stage_changed": False,
        }

    async def _default_register_feud_clash(_db, _chat_id, _user_a, _user_b, _success):
        return {
            "active": False,
            "heat": 0,
            "clash_count": 0,
            "success_count": 0,
            "stage": 0,
            "stage_changed": False,
        }

    get_feud_state = deps.get("get_feud_state", _default_get_feud_state)
    register_feud_clash = deps.get("register_feud_clash", _default_register_feud_clash)

    def _cap_success_chance(chance: float, user_id: int) -> float:
        return min(0.97 if user_id == ADMIN_ID else 0.90, max(0.01, chance))

    def _steal_texts() -> dict:
        data = load_json_dict(STEAL_TEXTS_PATH)
        return data if isinstance(data, dict) else {}

    def _pick_text(data: dict, key: str, default: str) -> str:
        value = data.get(key)
        if isinstance(value, list) and value:
            chosen = random.choice(value)
            return chosen if isinstance(chosen, str) and chosen.strip() else default
        if isinstance(value, str) and value.strip():
            return value
        return default

    def _fmt(template: str, **values) -> str:
        try:
            return template.format(**values)
        except Exception:
            return template

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
                return await update.effective_message.reply_text("Kein Pflege-Eintrag für den User.")

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
            await db.execute("UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?", (amount, chat_id, tid))
            await db.commit()
            new = await _get_coins(db, chat_id, tid)
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
            await db.execute("UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?", (amount, chat_id, tid))
            await db.commit()
            new = await _get_coins(db, chat_id, tid)
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

    async def _render_feud_overview(db, chat_id: int) -> str:
        text_cfg = _steal_texts()
        now_ts = __import__("time").time()
        async with db.execute(
            """
            SELECT user_a, user_b, heat, clash_count, success_count, last_attack_ts, active_until_ts
            FROM steal_feuds
            WHERE chat_id=? AND active_until_ts>?
            ORDER BY heat DESC, last_attack_ts DESC
            LIMIT 5
            """,
            (chat_id, int(now_ts))
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return _pick_text(text_cfg, "feud_overview_empty", "Keine aktive Fehde. Klaut euch erst mal warm.")

        lines = [_pick_text(text_cfg, "feud_overview_header", "<b>Aktive Fehden</b>")]
        for user_a, user_b, heat, clash_count, success_count, _last_attack_ts, active_until_ts in rows:
            async with db.execute(
                "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, int(user_a))
            ) as cur_a:
                row_a = await cur_a.fetchone()
            async with db.execute(
                "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, int(user_b))
            ) as cur_b:
                row_b = await cur_b.fetchone()
            stage = FEUD_STAGE_BONUS.get(0)
            stage_id = 0
            heat_value = int(heat or 0)
            if heat_value >= 10:
                stage_id = 3
            elif heat_value >= 6:
                stage_id = 2
            elif heat_value >= 3:
                stage_id = 1
            stage = FEUD_STAGE_BONUS.get(stage_id, FEUD_STAGE_BONUS[0])
            left = max(0, int(active_until_ts or 0) - int(now_ts))
            lines.append(_fmt(
                _pick_text(
                    text_cfg,
                    "feud_overview_item",
                    "- {user_a} vs {user_b} | <b>{stage}</b> | Heat {heat} | Clashes {clashes} | Wins {wins} | Rest {remaining}"
                ),
                user_a=mention_html(int(user_a), row_a[0] if row_a else None),
                user_b=mention_html(int(user_b), row_b[0] if row_b else None),
                stage=escape(stage["label"], quote=False),
                heat=heat_value,
                clashes=int(clash_count or 0),
                wins=int(success_count or 0),
                remaining=escape(format_duration(left), quote=False),
            ))
        return "\n".join(lines)

    async def cmd_fehde(update, context):
        if not is_group(update):
            return
        chat_id = update.effective_chat.id
        viewer = update.effective_user
        text_cfg = _steal_texts()

        async with aiosqlite.connect(DB) as db:
            if not context.args and not (update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user):
                text = await _render_feud_overview(db, chat_id)
                return await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text(
                    _pick_text(text_cfg, "target_not_found", "Ziel nicht gefunden. Nutze Reply, @username oder user_id.")
                )
            if tid == viewer.id:
                return await update.effective_message.reply_text(
                    _pick_text(text_cfg, "feud_self_hint", "Nutze /fehde als Reply auf dein Lieblingsopfer oder mit @username.")
                )

            feud = await get_feud_state(db, chat_id, viewer.id, tid)
            revenge_left = await get_cd_left(db, chat_id, viewer.id, feud_revenge_key(tid))

        viewer_tag = mention_html(viewer.id, viewer.username or None)
        target_tag = mention_html(tid, uname or None)
        if not feud["active"]:
            return await update.effective_message.reply_text(
                _fmt(
                    _pick_text(
                        text_cfg,
                        "feud_report_inactive",
                        "<b>Fehdebericht</b>\n{viewer} vs {target}\nNoch keine aktive Fehde.\nHeat: <b>{heat}</b> | Clashes: <b>{clashes}</b>"
                    ),
                    viewer=viewer_tag,
                    target=target_tag,
                    heat=feud["heat"],
                    clashes=feud["clash_count"],
                ),
                parse_mode=ParseMode.HTML
            )

        stage = int(feud["stage"] or 0)
        bonus = FEUD_STAGE_BONUS.get(stage, FEUD_STAGE_BONUS[0])
        revenge_state = (
            _fmt(
                _pick_text(text_cfg, "feud_revenge_active", "aktiv ({remaining})"),
                remaining=escape(format_duration(revenge_left), quote=False),
            )
            if revenge_left > 0 else
            _pick_text(text_cfg, "feud_revenge_inactive", "aus")
        )
        await update.effective_message.reply_text(
            _fmt(
                _pick_text(
                    text_cfg,
                    "feud_report_active",
                    "<b>Fehdebericht</b>\n{viewer} vs {target}\nStufe: <b>{stage}</b>\nHeat: <b>{heat}</b> | Clashes: <b>{clashes}</b> | Erfolgreiche Klaue: <b>{wins}</b>\nBonus gegeneinander: +{chance_bonus}% Erfolg | +{loot_bonus}% Beute\nRachefenster: {revenge}",
                ),
                viewer=viewer_tag,
                target=target_tag,
                stage=escape(feud_stage_label(stage), quote=False),
                heat=feud["heat"],
                clashes=feud["clash_count"],
                wins=feud["success_count"],
                chance_bonus=int(bonus["chance"] * 100),
                loot_bonus=int(bonus["steal_pct"] * 100),
                revenge=revenge_state,
            ),
            parse_mode=ParseMode.HTML,
        )

    async def cmd_steal(update, context):
        if not is_group(update):
            return
        text_cfg = _steal_texts()
        if not context.args:
            return await update.effective_message.reply_text(
                _pick_text(text_cfg, "steal_usage", "Nutzung: als Reply `/steal 50` oder `/steal @user 50`."),
                parse_mode="Markdown"
            )

        amount = _parse_amount_from_args(context)
        if amount is None or amount <= 0:
            return await update.effective_message.reply_text(
                _pick_text(text_cfg, "steal_invalid_amount", "Bitte gib eine gültige Coin-Zahl an. Beispiel: `/steal @user 50`."),
                parse_mode="Markdown"
            )

        async with aiosqlite.connect(DB) as db:
            tid, uname = await _resolve_target(db, update, context)
            if not tid:
                return await update.effective_message.reply_text(
                    _pick_text(text_cfg, "target_not_found", "Ziel nicht gefunden. Antworte auf den User oder nutze @username bzw. user_id.")
                )
            thief = update.effective_user
            if tid == thief.id:
                return await update.effective_message.reply_text(
                    _pick_text(text_cfg, "steal_self", "Nice try. Dich selbst beklauen geht nicht.")
                )

            chat_id = update.effective_chat.id
            await _ensure_player_entry(db, chat_id, tid, uname)
            await _ensure_player_entry(db, chat_id, thief.id, thief.username or thief.full_name or "")

            left = await get_cd_left(db, chat_id, thief.id, "steal")
            if left > 0:
                return await update.effective_message.reply_text(
                    _fmt(
                        _pick_text(text_cfg, "steal_cooldown", "Cooldown aktiv. Warte noch {remaining}."),
                        remaining=escape(format_duration(left), quote=False),
                        seconds=left,
                    ),
                    parse_mode=ParseMode.HTML
                )

            feud_before = await get_feud_state(db, chat_id, thief.id, tid)
            feud_stage = int(feud_before["stage"] or 0)
            feud_bonus = FEUD_STAGE_BONUS.get(feud_stage, FEUD_STAGE_BONUS[0])
            revenge_left = await get_cd_left(db, chat_id, thief.id, feud_revenge_key(tid))
            revenge_bonus = FEUD_REVENGE_CHANCE_BONUS if revenge_left > 0 else 0.0
            base_chance = 0.90 if thief.id == ADMIN_ID else STEAL_SUCCESS_CHANCE
            success_chance = _cap_success_chance(base_chance + feud_bonus["chance"] + revenge_bonus, thief.id)
            target_tag = mention_html(tid, uname or None)
            thief_tag = mention_html(thief.id, thief.username or None)

            force_fail = tid == ADMIN_ID and thief.id != ADMIN_ID
            if force_fail or random.random() > success_chance:
                thief_old = await _get_coins(db, chat_id, thief.id)
                penalty = max(1, int(thief_old * STEAL_FAIL_PENALTY_RATIO)) if thief_old > 0 else 0
                feud_after = await register_feud_clash(db, chat_id, thief.id, tid, False)
                await db.execute(
                    "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                    (penalty, chat_id, thief.id)
                )
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                lines = [_fmt(
                    _pick_text(
                        text_cfg,
                        "steal_fail",
                        "War wohl nix. {thief} hat versucht {target} zu beklauen - erwischt. (-{penalty} / 20%)"
                    ),
                    thief=thief_tag,
                    target=target_tag,
                    penalty=penalty,
                )]
                if feud_after["stage_changed"]:
                    trigger = _pick_text(text_cfg, f"feud_stage_{feud_after['stage']}", "")
                    if not trigger:
                        trigger = format_feud_stage_trigger(feud_after["stage"], thief_tag, target_tag)
                    else:
                        trigger = _fmt(trigger, attacker=thief_tag, victim=target_tag)
                    if trigger:
                        lines.append(trigger)
                return await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

            victim_coins = await _get_coins(db, chat_id, tid)
            stage_multiplier = 1.0 + float(feud_bonus["steal_pct"])
            boosted_amount = max(1, int(round(amount * stage_multiplier)))
            stolen = min(boosted_amount, victim_coins)
            if stolen <= 0:
                feud_after = await register_feud_clash(db, chat_id, thief.id, tid, False)
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                lines = [_fmt(
                    _pick_text(text_cfg, "steal_empty", "{target} ist sowieso pleite. Nix zu holen."),
                    target=target_tag,
                )]
                if feud_after["stage_changed"]:
                    trigger = _pick_text(text_cfg, f"feud_stage_{feud_after['stage']}", "")
                    if not trigger:
                        trigger = format_feud_stage_trigger(feud_after["stage"], thief_tag, target_tag)
                    else:
                        trigger = _fmt(trigger, attacker=thief_tag, victim=target_tag)
                    if trigger:
                        lines.append(trigger)
                return await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

            feud_after = await register_feud_clash(db, chat_id, thief.id, tid, True)
            await db.execute(
                "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                (stolen, chat_id, tid)
            )
            await db.execute(
                "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                (stolen, chat_id, thief.id)
            )
            await set_cd(db, chat_id, tid, feud_revenge_key(thief.id), FEUD_REVENGE_WINDOW_S)
            await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
            await db.commit()

        lines = [_fmt(
            _pick_text(text_cfg, "steal_success", "{thief} klaut {stolen} Coins von {target}."),
            thief=thief_tag,
            target=target_tag,
            stolen=stolen,
            requested=amount,
        )]
        if feud_stage > 0:
            lines.append(_fmt(
                _pick_text(
                    text_cfg,
                    "steal_feud_bonus",
                    "Fehdenbonus aktiv: <b>{stage}</b> (+{chance_bonus}% Erfolg, +{loot_bonus}% Beute)."
                ),
                stage=escape(feud_stage_label(feud_stage), quote=False),
                chance_bonus=int(feud_bonus["chance"] * 100),
                loot_bonus=int(feud_bonus["steal_pct"] * 100),
            ))
        if revenge_left > 0:
            lines.append(_fmt(
                _pick_text(text_cfg, "steal_revenge_used", "Rachefenster genutzt: +{chance_bonus}% Erfolg."),
                chance_bonus=int(FEUD_REVENGE_CHANCE_BONUS * 100),
            ))
        if feud_after["stage_changed"]:
            trigger = _pick_text(text_cfg, f"feud_stage_{feud_after['stage']}", "")
            if not trigger:
                trigger = format_feud_stage_trigger(feud_after["stage"], thief_tag, target_tag)
            else:
                trigger = _fmt(trigger, attacker=thief_tag, victim=target_tag)
            if trigger:
                lines.append(trigger)
        else:
            lines.append(_fmt(
                _pick_text(
                    text_cfg,
                    "feud_heat_update",
                    "Fehde-Heat jetzt bei <b>{heat}</b> ({stage})."
                ),
                heat=feud_after["heat"],
                stage=escape(feud_stage_label(feud_after["stage"]), quote=False),
            ))
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    return {
        "cmd_adminping": cmd_adminping,
        "cmd_careminus": cmd_careminus,
        "cmd_addcoins": cmd_addcoins,
        "cmd_takecoins": cmd_takecoins,
        "cmd_setcoins": cmd_setcoins,
        "cmd_resetcoins": cmd_resetcoins,
        "cmd_steal": cmd_steal,
        "cmd_fehde": cmd_fehde,
    }
