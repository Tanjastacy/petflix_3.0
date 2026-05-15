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
    CARES_PER_DAY = deps.get("CARES_PER_DAY", 10)
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
        return min(0.90, max(0.01, chance))

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

    def calculate_intensity(amount: int, victim_coins: int) -> dict:
        base = max(1, int(victim_coins or 0))
        ratio = float(amount) / float(base)
        if ratio <= 0.15:
            return {
                "key": "sneaky",
                "label": "Sneaky",
                "chance_mod": 0.12,
                "penalty_ratio": 0.12,
                "multiplier": 0.90,
            }
        if ratio <= 0.40:
            return {
                "key": "normal",
                "label": "Normal",
                "chance_mod": 0.00,
                "penalty_ratio": 0.20,
                "multiplier": 1.00,
            }
        return {
            "key": "bold",
            "label": "Bold",
            "chance_mod": -0.18,
            "penalty_ratio": 0.35,
            "multiplier": 1.35,
        }

    def calculate_chance(
        base_chance: float,
        feud_bonus: float,
        revenge_bonus: float,
        intensity_mod: float,
        defense_bonus: float,
        user_id: int,
    ) -> float:
        raw = base_chance + feud_bonus + revenge_bonus + intensity_mod - defense_bonus
        return _cap_success_chance(raw, user_id)

    def calculate_penalty(own_coins: int, penalty_ratio: float) -> int:
        if own_coins <= 0:
            return 0
        return max(1, int(own_coins * float(penalty_ratio)))

    def calculate_multiplier(multiplier: float) -> float:
        return float(multiplier)

    def _blood_debt_stage(blood_debt: int) -> int:
        debt = max(0, int(blood_debt or 0))
        if debt >= 20:
            return 5
        if debt >= 14:
            return 4
        if debt >= 8:
            return 3
        if debt >= 4:
            return 2
        if debt >= 1:
            return 1
        return 0

    def _blood_debt_label(stage: int) -> str:
        return {
            0: "Frei",
            1: "Kratzer",
            2: "Giftspur",
            3: "Rachemarke",
            4: "Blutpakt",
            5: "Vendetta",
        }.get(max(0, min(5, int(stage or 0))), "Frei")

    def _pet_bond_percent(points: int) -> int:
        return max(0, min(100, int(points or 0)))

    async def _get_owned_pet_row(db, chat_id: int, owner_id: int):
        async with db.execute(
            """
            SELECT pet_id, pet_xp, COALESCE(fullcare_days, 0), COALESCE(fullcare_streak, 0),
                   COALESCE(care_done_today, 0), mood_name, COALESCE(rebellious_until, 0),
                   COALESCE(breakout_count, 0), COALESCE(hostage_until, 0), COALESCE(snatched_until, 0),
                   COALESCE(acquired_ts, 0)
            FROM pets
            WHERE chat_id=? AND owner_id=?
            ORDER BY COALESCE(acquired_ts, 0) DESC, pet_id DESC
            LIMIT 1
            """,
            (chat_id, owner_id)
        ) as cur:
            return await cur.fetchone()

    async def _get_random_free_pet_candidate(db, chat_id: int, exclude_ids: set[int] | None = None):
        exclude_ids = exclude_ids or set()
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            players = await cur.fetchall()
        async with db.execute("SELECT pet_id FROM pets WHERE chat_id=?", (chat_id,)) as cur:
            owned_rows = await cur.fetchall()
        owned_ids = {int(r[0]) for r in owned_rows if r and r[0] is not None}
        free_rows = [
            r for r in players
            if r and int(r[0]) not in exclude_ids and int(r[0]) not in owned_ids
        ]
        if not free_rows:
            return None, None
        return random.choice(free_rows)

    async def _add_blood_debt(db, chat_id: int, user_id: int, amount: int):
        amount = max(0, int(amount or 0))
        if amount <= 0:
            return
        await db.execute(
            "UPDATE players SET blood_debt=COALESCE(blood_debt,0)+? WHERE chat_id=? AND user_id=?",
            (amount, chat_id, user_id)
        )

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
            return _pick_text(text_cfg, "feud_overview_empty", "Keine aktive Blutrache. Klaut euch erst mal warm.")

        lines = [_pick_text(text_cfg, "feud_overview_header", "<b>Aktive Blutrache</b>")]
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
                        "<b>Blutrachebericht</b>\n{viewer} vs {target}\nNoch keine aktive Blutrache.\nHeat: <b>{heat}</b> | Clashes: <b>{clashes}</b>"
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
                    "<b>Blutrachebericht</b>\n{viewer} vs {target}\nStufe: <b>{stage}</b>\nHeat: <b>{heat}</b> | Clashes: <b>{clashes}</b> | Erfolgreiche Diebstähle: <b>{wins}</b>\nBonus gegeneinander: +{chance_bonus}% Erfolg | +{loot_bonus}% Beute\nRachefenster: {revenge}",
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
        chat_data = getattr(context, "chat_data", None)
        snatch_mode = False
        if chat_data is not None:
            snatch_mode = chat_data.pop("_steal_mode", None) == "snatch"
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

            victim_coins = await _get_coins(db, chat_id, tid)
            victim_pet = await _get_owned_pet_row(db, chat_id, tid)
            thief_pet = await _get_owned_pet_row(db, chat_id, thief.id)
            async with db.execute(
                "SELECT COALESCE(blood_debt, 0) FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, thief.id)
            ) as cur:
                thief_debt_row = await cur.fetchone()
            thief_blood_debt = int(thief_debt_row[0]) if thief_debt_row and thief_debt_row[0] is not None else 0
            thief_debt_stage = _blood_debt_stage(thief_blood_debt)
            intensity = calculate_intensity(amount, victim_coins)
            feud_before = await get_feud_state(db, chat_id, thief.id, tid)
            feud_stage = int(feud_before["stage"] or 0)
            feud_bonus = FEUD_STAGE_BONUS.get(feud_stage, FEUD_STAGE_BONUS[0])
            revenge_left = await get_cd_left(db, chat_id, thief.id, feud_revenge_key(tid))
            revenge_bonus = FEUD_REVENGE_CHANCE_BONUS if revenge_left > 0 else 0.0
            defense_bonus = min(0.12, max(0, int(feud_before.get("success_count") or 0)) * 0.03)
            blood_penalty = min(0.10, thief_debt_stage * 0.02)
            success_chance = calculate_chance(
                STEAL_SUCCESS_CHANCE,
                float(feud_bonus["chance"]),
                revenge_bonus,
                float(intensity["chance_mod"]),
                defense_bonus + blood_penalty,
                thief.id,
            )
            chance_pct = int(round(success_chance * 100))
            target_tag = mention_html(tid, uname or None)
            thief_tag = mention_html(thief.id, thief.username or None)
            intensity_label = escape(str(intensity["label"]), quote=False)
            defense_pct = int(round(defense_bonus * 100))
            blood_label = _blood_debt_label(thief_debt_stage)
            victim_pet_tag = mention_html(int(victim_pet[0]), None) if victim_pet else None
            thief_pet_tag = mention_html(int(thief_pet[0]), None) if thief_pet else None
            victim_pet_name = victim_pet_tag or target_tag
            pet_involved = victim_pet is not None
            pet_blocked = False
            pet_betrayed = False
            pet_hostage = False
            pet_snatched = False
            pet_bonus_loot = 0
            pet_bonus_xp = 0
            pet_event_line = "Snatch-Modus aktiv." if snatch_mode else None

            force_fail = tid == ADMIN_ID and thief.id != ADMIN_ID
            if force_fail or random.random() > success_chance:
                thief_old = await _get_coins(db, chat_id, thief.id)
                penalty = calculate_penalty(thief_old, float(intensity["penalty_ratio"]))
                feud_after = await register_feud_clash(db, chat_id, thief.id, tid, False)
                await db.execute(
                    "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                    (penalty, chat_id, thief.id)
                )
                await _add_blood_debt(db, chat_id, thief.id, 2 if victim_pet else 1)
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                lines = [_fmt(
                    _pick_text(
                        text_cfg,
                        "steal_fail",
                        "War wohl nix. {thief} hat versucht {target} zu beklauen - erwischt. (-{penalty} / {penalty_pct}%)"
                    ),
                    thief=thief_tag,
                    target=target_tag,
                    penalty=penalty,
                    penalty_pct=int(round(float(intensity["penalty_ratio"]) * 100)),
                )]
                lines.append(
                    f"Chance: <b>{chance_pct}%</b> | Intensität: <b>{intensity_label}</b>"
                )
                if defense_bonus > 0:
                    lines.append(f"Defensivbonus von {target_tag}: <b>-{defense_pct}%</b>.")
                lines.append(
                    f"Blutschuld: <b>{_blood_debt_label(_blood_debt_stage(thief_blood_debt + (2 if victim_pet else 1)))}</b>"
                )
                if feud_after["stage_changed"]:
                    trigger = _pick_text(text_cfg, f"feud_stage_{feud_after['stage']}", "")
                    if not trigger:
                        trigger = format_feud_stage_trigger(feud_after["stage"], thief_tag, target_tag)
                    else:
                        trigger = _fmt(trigger, attacker=thief_tag, victim=target_tag)
                    if trigger:
                        lines.append(trigger)
                return await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

            stage_multiplier = 1.0 + float(feud_bonus["steal_pct"])
            intensity_multiplier = calculate_multiplier(float(intensity["multiplier"]))
            boosted_amount = max(1, int(round(amount * stage_multiplier)))
            final_amount = max(1, int(round(boosted_amount * intensity_multiplier)))
            stolen = min(final_amount, victim_coins)
            pet_defended = False
            pet_betray_bonus = 0
            temp_pet_line = None
            hostage_line = None
            pet_event_line = None
            if victim_pet:
                victim_pet_id = int(victim_pet[0])
                victim_pet_xp = int(victim_pet[1] or 0)
                victim_pet_care = int(victim_pet[4] or 0)
                victim_rebellious_until = int(victim_pet[6] or 0)
                victim_breakout = int(victim_pet[7] or 0)
                victim_acquired_ts = int(victim_pet[10] or 0)
                pet_bond = _pet_bond_percent(victim_pet_xp)
                neglect_ratio = max(0.0, (CARES_PER_DAY - victim_pet_care) / float(max(1, CARES_PER_DAY)))
                protect_chance = min(
                    0.20,
                    0.05 + (pet_bond / 1000.0) + (0.02 if victim_rebellious_until > int(__import__("time").time()) else 0.0) + (0.01 if snatch_mode else 0.0),
                )
                betray_chance = min(
                    0.20,
                    0.02 + (neglect_ratio * 0.10) + min(0.05, victim_breakout * 0.01) + (0.02 if victim_rebellious_until > int(__import__("time").time()) else 0.0) - (pet_bond / 1000.0 * 0.35) + (0.03 if snatch_mode else 0.0),
                )
                pet_roll = random.random()
                victim_pet_name = victim_pet_tag or target_tag
                if pet_roll < protect_chance:
                    pet_defended = True
                    temp_pet_line = (
                        f"{victim_pet_name} wirft sich dazwischen und schiebt den Steal von {target_tag} weg."
                    )
                elif pet_roll < protect_chance + betray_chance:
                    pet_betray_bonus = max(1, stolen * 30 // 100)
                    stolen = min(victim_coins, stolen + pet_betray_bonus)
                    temp_pet_line = (
                        f"{victim_pet_name} verrät den Owner und legt <b>+{pet_betray_bonus}</b> Coins frei."
                    )
            if pet_defended:
                thief_old = await _get_coins(db, chat_id, thief.id)
                penalty = max(1, int(calculate_penalty(thief_old, float(intensity["penalty_ratio"])) * 1.25))
                feud_after = await register_feud_clash(db, chat_id, thief.id, tid, False)
                await db.execute(
                    "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                    (penalty, chat_id, thief.id)
                )
                if victim_pet:
                    await db.execute(
                        "UPDATE pets SET pet_xp=COALESCE(pet_xp,0)+15 WHERE chat_id=? AND pet_id=?",
                        (chat_id, int(victim_pet[0]))
                    )
                await _add_blood_debt(db, chat_id, thief.id, 3)
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await db.commit()
                lines = [_fmt(
                    _pick_text(
                        text_cfg,
                        "steal_fail",
                        "War wohl nix. {thief} hat versucht {target} zu beklauen - erwischt. (-{penalty} / {penalty_pct}%)"
                    ),
                    thief=thief_tag,
                    target=target_tag,
                    penalty=penalty,
                    penalty_pct=int(round(float(intensity["penalty_ratio"]) * 100)),
                )]
                lines.append(f"Chance: <b>{chance_pct}%</b> | Intensität: <b>{intensity_label}</b>")
                if defense_bonus > 0:
                    lines.append(f"Defensivbonus von {target_tag}: <b>-{defense_pct}%</b>.")
                lines.append(
                    f"Blutschuld: <b>{_blood_debt_label(_blood_debt_stage(thief_blood_debt + 3))}</b>"
                )
                if temp_pet_line:
                    lines.append(temp_pet_line)
                if feud_after["stage_changed"]:
                    trigger = _pick_text(text_cfg, f"feud_stage_{feud_after['stage']}", "")
                    if not trigger:
                        trigger = format_feud_stage_trigger(feud_after["stage"], thief_tag, target_tag)
                    else:
                        trigger = _fmt(trigger, attacker=thief_tag, victim=target_tag)
                    if trigger:
                        lines.append(trigger)
                return await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
            if stolen <= 0:
                feud_after = await register_feud_clash(db, chat_id, thief.id, tid, False)
                await set_cd(db, chat_id, thief.id, "steal", STEAL_COOLDOWN_S)
                await _add_blood_debt(db, chat_id, thief.id, 2 if victim_pet else 1)
                await db.commit()
                lines = [_fmt(
                    _pick_text(text_cfg, "steal_empty", "{target} ist sowieso pleite. Nix zu holen."),
                    target=target_tag,
                )]
                lines.append(
                    f"Chance: <b>{chance_pct}%</b> | Intensität: <b>{intensity_label}</b>"
                )
                if defense_bonus > 0:
                    lines.append(f"Defensivbonus von {target_tag}: <b>-{defense_pct}%</b>.")
                lines.append(
                    f"Blutschuld: <b>{_blood_debt_label(_blood_debt_stage(thief_blood_debt + (2 if victim_pet else 1)))}</b>"
                )
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
            now_ts = int(__import__("time").time())
            if victim_pet:
                pet_event_gain = 2 + (1 if pet_betray_bonus > 0 else 0)
                await _add_blood_debt(db, chat_id, thief.id, pet_event_gain)
                if pet_betray_bonus > 0:
                    pet_event_gain_msg = f"{victim_pet_name} hat den Owner verraten und macht den Loot dichter."
                else:
                    pet_event_gain_msg = f"{victim_pet_name} hängt als stiller Mitwisser am Steal."
                pet_event_line = pet_event_line or pet_event_gain_msg
                if random.random() < 0.02:
                    pet_host = max(0, now_ts + 3600)
                    await db.execute(
                        "UPDATE pets SET hostage_until=? WHERE chat_id=? AND pet_id=?",
                        (pet_host, chat_id, int(victim_pet[0]))
                    )
                    hostage_line = f"{victim_pet_name} ist fuer 1h als Geisel markiert."
                    await _add_blood_debt(db, chat_id, thief.id, 1)
                elif random.random() < 0.02:
                    temp_until = now_ts + 12 * 3600
                    await db.execute(
                        """
                        UPDATE pets
                        SET owner_id=?, acquired_ts=?, snatched_until=?, snatched_from_owner_id=?, snatched_from_acquired_ts=?, hostage_until=0
                        WHERE chat_id=? AND pet_id=?
                        """,
                        (
                            thief.id,
                            now_ts,
                            temp_until,
                            tid,
                            victim_acquired_ts,
                            chat_id,
                            int(victim_pet[0]),
                        )
                    )
                    temp_pet_line = f"{victim_pet_name} laeuft fuer 12h zum Dieb."
                    await _add_blood_debt(db, chat_id, thief.id, 1)
            else:
                free_uid, free_uname = await _get_random_free_pet_candidate(db, chat_id, exclude_ids={thief.id, tid})
                if free_uid and random.random() < (0.06 if snatch_mode else 0.04):
                    free_now = now_ts
                    free_until = free_now + 24 * 3600
                    await db.execute(
                        """
                        INSERT INTO pets(
                          chat_id, pet_id, owner_id, acquired_ts, last_care_ts, care_done_today, day_ymd,
                          snatched_until, snatched_from_owner_id, snatched_from_acquired_ts
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(chat_id, pet_id) DO UPDATE SET
                          owner_id=excluded.owner_id,
                          acquired_ts=excluded.acquired_ts,
                          last_care_ts=excluded.last_care_ts,
                          care_done_today=excluded.care_done_today,
                          day_ymd=excluded.day_ymd,
                          snatched_until=excluded.snatched_until,
                          snatched_from_owner_id=excluded.snatched_from_owner_id,
                          snatched_from_acquired_ts=excluded.snatched_from_acquired_ts
                        """,
                        (
                            chat_id,
                            int(free_uid),
                            thief.id,
                            free_now,
                            free_now,
                            0,
                            __import__("datetime").date.fromtimestamp(free_now).isoformat(),
                            free_until,
                            None,
                            None,
                        )
                    )
                    temp_pet_line = f"Freies Pet {mention_html(int(free_uid), free_uname)} läuft versehentlich zu {thief_tag}."
                    await _add_blood_debt(db, chat_id, thief.id, 1)
            if thief_pet and random.random() < min(0.25, 0.08 + (_pet_bond_percent(int(thief_pet[1] or 0)) / 200.0)):
                bonus_loot = random.randint(10, 50)
                await db.execute(
                    "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                    (bonus_loot, chat_id, thief.id)
                )
                await db.execute(
                    "UPDATE pets SET pet_xp=COALESCE(pet_xp,0)+? WHERE chat_id=? AND pet_id=?",
                    (max(1, bonus_loot // 2), chat_id, int(thief_pet[0]))
                )
                pet_event_line = pet_event_line or f"{thief_pet_tag or thief_tag} schnüffelt Bonusbeute von <b>{bonus_loot}</b> Coins auf."
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
        lines.append(
            _fmt(
                _pick_text(
                    text_cfg,
                    "steal_chance_line",
                    "Chance: <b>{chance}</b> | Intensität: <b>{intensity}</b> | Beutefaktor: <b>x{multiplier}</b>"
                ),
                chance=f"{chance_pct}%",
                intensity=intensity_label,
                multiplier=f"{intensity_multiplier:.2f}",
            )
        )
        if feud_stage > 0:
            lines.append(_fmt(
                _pick_text(
                    text_cfg,
                    "steal_feud_bonus",
                    "Blutrachebonus aktiv: <b>{stage}</b> (+{chance_bonus}% Erfolg, +{loot_bonus}% Beute)."
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
        if defense_bonus > 0:
            lines.append(_fmt(
                _pick_text(
                    text_cfg,
                    "steal_defense_bonus",
                    "Defensivbonus von {target}: <b>-{defense_bonus}%</b> Erfolg."
                ),
                target=target_tag,
                defense_bonus=defense_pct,
            ))
        if pet_event_line:
            lines.append(pet_event_line)
        if hostage_line:
            lines.append(hostage_line)
        if temp_pet_line:
            lines.append(temp_pet_line)
        if victim_pet:
            lines.append(f"Blutschuld: <b>{_blood_debt_label(_blood_debt_stage(thief_blood_debt + 3))}</b>")
        if thief_pet:
            lines.append(f"Bonuspet: <b>{thief_pet_tag or thief_tag}</b> kann beim Steal helfen.")
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
                    "Blutrache-Heat jetzt bei <b>{heat}</b> ({stage})."
                ),
                heat=feud_after["heat"],
                stage=escape(feud_stage_label(feud_after["stage"]), quote=False),
            ))
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_snatchsteal(update, context):
        if getattr(context, "chat_data", None) is not None:
            context.chat_data["_steal_mode"] = "snatch"
        return await cmd_steal(update, context)

    return {
        "cmd_adminping": cmd_adminping,
        "cmd_careminus": cmd_careminus,
        "cmd_addcoins": cmd_addcoins,
        "cmd_takecoins": cmd_takecoins,
        "cmd_setcoins": cmd_setcoins,
        "cmd_resetcoins": cmd_resetcoins,
        "cmd_steal": cmd_steal,
        "cmd_snatchsteal": cmd_snatchsteal,
        "cmd_fehde": cmd_fehde,
    }
