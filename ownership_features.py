def create_ownership_features(deps: dict):
    aiosqlite = deps["aiosqlite"]
    DB = deps["DB"]
    time = deps["time"]
    escape = deps["escape"]
    MAX_CHUNK = deps["MAX_CHUNK"]
    ALLOWED_CHAT_ID = deps["ALLOWED_CHAT_ID"]
    is_group = deps["is_group"]
    get_user_price = deps["get_user_price"]
    get_pet_skill = deps["get_pet_skill"]
    _skill_label = deps["_skill_label"]
    pet_bond_title = deps.get("pet_bond_title", deps["pet_level_title"])
    pet_bond_percent = deps.get("pet_bond_percent", lambda points: max(0, min(100, int(points or 0))))
    pet_mood_label = deps.get("pet_mood_label", lambda care_done_today, fullcare_streak: "Unruhig")
    render_pet_mood = deps.get("render_pet_mood", lambda mood_name, care_done_today, fullcare_streak, rebellious_until, now_ts: mood_name or pet_mood_label(care_done_today, fullcare_streak))
    pet_imprint_label = deps.get("pet_imprint_label", lambda score: "Loyal")
    pet_status_label = deps.get("pet_status_label", lambda stage, rebellious_until, now_ts: "Wartet auf Fuehrung.")
    get_pet_lock_until = deps["get_pet_lock_until"]
    get_active_titles_map = deps["get_active_titles_map"]
    with_title_suffix = deps["with_title_suffix"]
    _skill_meta = deps["_skill_meta"]
    mention_html = deps.get("mention_html")

    def html_user_tag(user_id: int, username: str | None):
        if mention_html:
            return mention_html(int(user_id), username or None)
        label = f"@{username}" if username else f"ID:{user_id}"
        return f"<a href='tg://user?id={int(user_id)}'>{escape(label, False)}</a>"

    def format_coins(value: int) -> str:
        return f"{int(value or 0):,}".replace(",", ".")

    async def get_brand_details(db, chat_id: int, user_id: int):
        async with db.execute(
            """
            SELECT sb.name, fb.name, ab.forced_by_owner_id, op.username, COALESCE(ab.forced_remove_cost, 0)
            FROM active_brands ab
            LEFT JOIN brand_catalog sb ON sb.id=ab.active_self_brand_id
            LEFT JOIN brand_catalog fb ON fb.id=ab.forced_brand_id
            LEFT JOIN players op ON op.chat_id=? AND op.user_id=ab.forced_by_owner_id
            WHERE ab.user_id=?
            """,
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return "Keine", "Keine", "Keine", 0
        active_brand = row[0] or "Keine"
        forced_brand = row[1] or "Keine"
        forced_by = "Keine"
        if row[1] and row[2]:
            owner_name = f"@{row[3]}" if row[3] else f"ID:{row[2]}"
            forced_by = owner_name
        return active_brand, forced_brand, forced_by, int(row[4] or 0)

    async def resolve_profile_target(db, update, context):
        chat_id = update.effective_chat.id
        if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
            user = update.effective_message.reply_to_message.from_user
            return user.id, user.username or None
        if context.args:
            raw = context.args[0].strip().lstrip("@")
            if raw.isdigit():
                uid = int(raw)
                async with db.execute(
                    "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                    (chat_id, uid),
                ) as cur:
                    row = await cur.fetchone()
                return uid, row[0] if row else None
            async with db.execute(
                "SELECT user_id, username FROM players WHERE chat_id=? AND lower(username)=lower(?)",
                (chat_id, raw),
            ) as cur:
                row = await cur.fetchone()
            if row:
                return int(row[0]), row[1] or raw
            return None, None
        user = update.effective_user
        return user.id, user.username or None

    async def get_brand_labels(db, chat_id: int, user_id: int):
        active_brand, forced_brand, forced_by, _ = await get_brand_details(db, chat_id, user_id)
        if forced_brand != "Keine" and forced_by != "Keine":
            forced_brand = f"{forced_brand} von {forced_by}"
        return active_brand, forced_brand

    async def get_brand_summary_map(db, user_ids: list[int]):
        uniq_ids = sorted({int(uid) for uid in user_ids if uid})
        if not uniq_ids:
            return {}
        placeholders = ",".join("?" for _ in uniq_ids)
        async with db.execute(
            f"""
            SELECT ab.user_id, sb.name, fb.name
            FROM active_brands ab
            LEFT JOIN brand_catalog sb ON sb.id=ab.active_self_brand_id
            LEFT JOIN brand_catalog fb ON fb.id=ab.forced_brand_id
            WHERE ab.user_id IN ({placeholders})
            """,
            uniq_ids,
        ) as cur:
            rows = await cur.fetchall()
        out = {}
        for user_id, self_brand, forced_brand in rows:
            parts = []
            if self_brand:
                parts.append(f"Brand: {self_brand}")
            if forced_brand:
                parts.append(f"Owner-Brand: {forced_brand}")
            out[int(user_id)] = f" [{' | '.join(parts)}]" if parts else ""
        return out

    async def get_owner_id(db, chat_id: int, pet_id: int):
        async with db.execute("SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_owner(db, chat_id: int, pet_id: int, owner_id):
        if owner_id is None:
            await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id))
        else:
            now = int(time.time())
            await db.execute("""
                INSERT INTO pets(chat_id, pet_id, owner_id, acquired_ts, last_care_ts) VALUES(?,?,?,?,?)
                ON CONFLICT(chat_id, pet_id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    acquired_ts=excluded.acquired_ts,
                    last_care_ts=COALESCE(pets.last_care_ts, excluded.last_care_ts)
            """, (chat_id, pet_id, owner_id, now, now))

    async def cmd_top(update, context):
        if update.effective_chat.id != ALLOWED_CHAT_ID:
            return
        chat_id = update.effective_chat.id
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT username, user_id, coins FROM players WHERE chat_id=? ORDER BY coins DESC", (chat_id,)) as cur:
                rows = await cur.fetchall()
            titles = await get_active_titles_map(db, chat_id, [int(r[1]) for r in rows])
            brands = await get_brand_summary_map(db, [int(r[1]) for r in rows])
            await db.commit()
        if not rows:
            await update.effective_message.reply_text("Noch keine Spieler.")
            return
        lines = []
        for i, (uname, uid, c) in enumerate(rows, start=1):
            raw_tag = f"@{uname}" if uname else f"ID:{uid}"
            raw_tag = with_title_suffix(raw_tag, titles.get(int(uid)))
            raw_tag = f"{raw_tag}{brands.get(int(uid), '')}"
            tag = escape(raw_tag, quote=False)
            lines.append(f"{i}. {tag}: {c} Coins")

        text = "Rangliste aller Spieler:\n\n" + "\n".join(lines)
        for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
            await update.effective_message.reply_text(chunk, quote=False)

    async def cmd_owner(update, context):
        if not is_group(update):
            return

        chat_id = update.effective_chat.id
        target_id = None
        if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
            target_id = update.effective_message.reply_to_message.from_user.id
        elif context.args:
            uname = context.args[0].lstrip("@")
            async with aiosqlite.connect(DB) as db:
                async with db.execute(
                    "SELECT user_id FROM players WHERE chat_id=? AND username=?",
                    (chat_id, uname)
                ) as cur:
                    row = await cur.fetchone()
            if row:
                target_id = int(row[0])

        if target_id is None:
            target_id = update.effective_user.id

        async with aiosqlite.connect(DB) as db:
            owner_id = await get_owner_id(db, chat_id, target_id)
            price = await get_user_price(db, chat_id, target_id)
            skill_key = await get_pet_skill(db, chat_id, target_id)
            skill_txt = _skill_label(skill_key)
            async with db.execute(
                "SELECT COALESCE(pet_xp,0), COALESCE(fullcare_days,0), COALESCE(fullcare_streak,0), COALESCE(care_done_today,0), "
                "mood_name, COALESCE(imprint_score,0), COALESCE(rebellious_until,0), COALESCE(breakout_count,0) "
                "FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, target_id)
            ) as cur:
                lrow = await cur.fetchone()
            pet_xp = int(lrow[0]) if lrow else 0
            fullcare_streak = int(lrow[2]) if lrow else 0
            care_done_today = int(lrow[3]) if lrow else 0
            now_ts = int(time.time())
            rebellious_until = int(lrow[6]) if lrow else 0
            rebellion_stage = int(lrow[7]) if lrow else 0
            mood_name = render_pet_mood(lrow[4] if lrow else None, care_done_today, fullcare_streak, rebellious_until, now_ts)
            imprint_name = pet_imprint_label(int(lrow[5]) if lrow else 0)
            status_name = pet_status_label(rebellion_stage, rebellious_until, now_ts)
            bond_txt = (
                f"Laune: {mood_name}\n"
                f"Prägung: {imprint_name}\n"
                f"Bindung: {pet_bond_percent(pet_xp)} %\n"
                f"Status: {status_name}"
            )
            progress_txt = f"Perfekte Tage: {int(lrow[1]) if lrow else 0} | Streak: {fullcare_streak}"

            owner_uname = None
            if owner_id:
                async with db.execute(
                    "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                    (chat_id, owner_id)
                ) as cur:
                    r2 = await cur.fetchone()
                    owner_uname = r2[0] if r2 else None
            title_map = await get_active_titles_map(db, chat_id, [owner_id] if owner_id else [])
            owner_title = title_map.get(int(owner_id)) if owner_id else None
            active_brand, forced_brand, forced_by, forced_remove_cost = await get_brand_details(db, chat_id, target_id)

            lock_until = await get_pet_lock_until(db, chat_id, target_id)
            lock_txt = ""
            now = int(time.time())
            if lock_until and lock_until > now:
                left = lock_until - now
                h = left // 3600
                m = (left % 3600) // 60
                lock_txt = f" [LOCK {h}h{m:02d}m]"
            await db.commit()

        if owner_id:
            raw_tag = f"@{owner_uname}" if owner_uname else f"[ID:{owner_id}](tg://user?id={owner_id})"
            tag = with_title_suffix(raw_tag, owner_title)
            await update.effective_message.reply_text(
                f"Besitzer: {tag}. Aktueller Preis: {price}.{lock_txt}\n"
                f"Brandmarke: {active_brand}\n"
                f"Owner-Brand: {forced_brand}\n"
                f"Aufgezwungen von: {forced_by}\n"
                f"Ablösekosten: {forced_remove_cost} Coins\n"
                f"Skill: {skill_txt}\n{bond_txt}\n{progress_txt}",
                parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text(
                f"Kein Besitzer. Aktueller Preis: {price}.{lock_txt}\n"
                f"Brandmarke: {active_brand}\n"
                f"Owner-Brand: {forced_brand}\n"
                f"Aufgezwungen von: {forced_by}\n"
                f"Ablösekosten: {forced_remove_cost} Coins\n"
                f"Skill: {skill_txt}\n{bond_txt}\n{progress_txt}"
            )

    async def cmd_profil(update, context):
        if not is_group(update):
            return

        chat_id = update.effective_chat.id
        async with aiosqlite.connect(DB) as db:
            target_id, target_uname = await resolve_profile_target(db, update, context)
            if target_id is None:
                return await update.effective_message.reply_text("User nicht gefunden. Nutze /profil @username oder antworte auf eine Nachricht.")

            async with db.execute(
                "SELECT username, COALESCE(coins,0), COALESCE(price,0) FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, target_id),
            ) as cur:
                player = await cur.fetchone()
            if player:
                target_uname = player[0] or target_uname
                coins = int(player[1] or 0)
                price = int(player[2] or 0)
            else:
                coins = 0
                price = await get_user_price(db, chat_id, target_id)

            owner_id = await get_owner_id(db, chat_id, target_id)
            owner_uname = None
            if owner_id:
                async with db.execute(
                    "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                    (chat_id, owner_id),
                ) as cur:
                    row = await cur.fetchone()
                    owner_uname = row[0] if row else None
            own_title_map = await get_active_titles_map(db, chat_id, [target_id])
            own_title = own_title_map.get(int(target_id), "Keine")

            async with db.execute(
                "SELECT COUNT(*) FROM pets WHERE chat_id=? AND owner_id=?",
                (chat_id, target_id),
            ) as cur:
                own_pet_count = int((await cur.fetchone())[0] or 0)

            skill_key = await get_pet_skill(db, chat_id, target_id)
            skill_txt = _skill_label(skill_key)
            async with db.execute(
                "SELECT COALESCE(pet_xp,0), COALESCE(fullcare_days,0), COALESCE(fullcare_streak,0), COALESCE(care_done_today,0), "
                "mood_name, COALESCE(imprint_score,0), COALESCE(rebellious_until,0), COALESCE(breakout_count,0) "
                "FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, target_id),
            ) as cur:
                pet_row = await cur.fetchone()
            now_ts = int(time.time())
            if pet_row:
                pet_xp = int(pet_row[0] or 0)
                fullcare_days = int(pet_row[1] or 0)
                fullcare_streak = int(pet_row[2] or 0)
                care_done_today = int(pet_row[3] or 0)
                rebellious_until = int(pet_row[6] or 0)
                rebellion_stage = int(pet_row[7] or 0)
                mood_name = render_pet_mood(pet_row[4], care_done_today, fullcare_streak, rebellious_until, now_ts)
                imprint_name = pet_imprint_label(int(pet_row[5] or 0))
                status_name = pet_status_label(rebellion_stage, rebellious_until, now_ts)
                bond_percent = pet_bond_percent(pet_xp)
            else:
                fullcare_days = 0
                fullcare_streak = 0
                care_done_today = 0
                mood_name = "Keine"
                imprint_name = "Keine"
                status_name = "Kein Pet-Status vorhanden."
                bond_percent = 0

            active_brand, forced_brand, forced_by, forced_remove_cost = await get_brand_details(db, chat_id, target_id)
            await db.commit()

        target_tag = html_user_tag(target_id, target_uname)
        owner_txt = html_user_tag(owner_id, owner_uname) if owner_id else "Niemand"
        remove_txt = f"{format_coins(forced_remove_cost)} Coins" if forced_brand != "Keine" else "-"
        text = (
            f"<b>Petflix Profil: {target_tag}</b>\n\n"
            f"Coins: <b>{format_coins(coins)}</b>\n"
            f"Kaufpreis: <b>{format_coins(price)}</b> Coins\n\n"
            f"Besitzer: {owner_txt}\n"
            f"Eigene Pets: <b>{own_pet_count}</b>\n\n"
            f"Titel: {escape(own_title or 'Keine', False)}\n"
            f"Brandmarke: {escape(active_brand, False)}\n"
            f"Owner-Brand: {escape(forced_brand, False)}\n"
            f"Aufgezwungen von: {escape(forced_by, False)}\n"
            f"Ablösekosten: {escape(remove_txt, False)}\n\n"
            f"Skill: {escape(skill_txt, False)}\n"
            f"Laune: {escape(mood_name, False)}\n"
            f"Prägung: {escape(imprint_name, False)}\n"
            f"Bindung: <b>{bond_percent} %</b>\n\n"
            f"<b>Pflege:</b>\n"
            f"Heute: {care_done_today}\n"
            f"Perfekte Tage: {fullcare_days}\n"
            f"Streak: {fullcare_streak}\n\n"
            f"<b>Status:</b>\n"
            f"{escape(status_name, False)}"
        )
        await update.effective_message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

    async def cmd_ownerlist(update, context):
        if not is_group(update):
            return
        chat_id = update.effective_chat.id
        now = int(time.time())

        try:
            async with aiosqlite.connect(DB) as db:
                async with db.execute("""
                    SELECT 
                        p.owner_id,
                        ou.username                                 AS owner_username,
                        p.pet_id,
                        pu.username                                 AS pet_username,
                        COALESCE(pl.price, 0)                       AS current_price,
                        COALESCE(p.purchase_lock_until, 0)          AS locked_until,
                        p.pet_skill                                  AS pet_skill,
                        COALESCE(p.pet_xp, 0)                       AS pet_xp,
                        COALESCE(p.fullcare_days, 0)                AS fullcare_days,
                        COALESCE(p.fullcare_streak, 0)              AS fullcare_streak,
                        COALESCE(p.care_done_today, 0)              AS care_done_today,
                        p.mood_name                                  AS mood_name,
                        COALESCE(p.imprint_score, 0)                AS imprint_score,
                        COALESCE(p.rebellious_until, 0)             AS rebellious_until,
                        COALESCE(p.breakout_count, 0)               AS breakout_count
                    FROM pets p
                    LEFT JOIN players ou ON ou.chat_id=p.chat_id AND ou.user_id=p.owner_id
                    LEFT JOIN players pu ON pu.chat_id=p.chat_id AND pu.user_id=p.pet_id
                    LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
                    WHERE p.chat_id=?
                    ORDER BY p.owner_id ASC, current_price DESC, p.pet_id ASC
                """, (chat_id,)) as cur:
                    rows = await cur.fetchall()
                title_user_ids = []
                for owner_id, _, pet_id, _, _, _, _, _, _, _, _, _, _, _, _ in rows:
                    if owner_id:
                        title_user_ids.append(int(owner_id))
                    if pet_id:
                        title_user_ids.append(int(pet_id))
                titles = await get_active_titles_map(db, chat_id, title_user_ids)
                brand_map = {}
                for uid in set(title_user_ids):
                    brand_map[int(uid)] = await get_brand_labels(db, chat_id, int(uid))
                await db.commit()
        except Exception as e:
            return await update.effective_message.reply_text(
                f"Konnte Ownerliste nicht laden: <code>{type(e).__name__}</code> - {escape(str(e), False)}"
            )

        if not rows:
            return await update.effective_message.reply_text("Noch keine Besitzverhältnisse. Kauf dir erstmal jemanden.")

        by_owner = {}
        for owner_id, owner_uname, pet_id, pet_uname, price, locked_until, pet_skill, pet_xp, fullcare_days, fullcare_streak, care_done_today, mood_name, imprint_score, rebellious_until, rebellion_stage in rows:
            by_owner.setdefault((owner_id, owner_uname), []).append(
                (
                    pet_id,
                    pet_uname,
                    int(price or 0),
                    int(locked_until or 0),
                    pet_skill,
                    int(pet_xp or 0),
                    int(fullcare_days or 0),
                    int(fullcare_streak or 0),
                    int(care_done_today or 0),
                    mood_name,
                    int(imprint_score or 0),
                    int(rebellious_until or 0),
                    int(rebellion_stage or 0),
                )
            )

        def tag(uid, uname):
            if uid is None:
                return "-"
            base = f"@{uname}" if uname else f"<a href='tg://user?id={uid}'>ID:{uid}</a>"
            return with_title_suffix(base, titles.get(int(uid)))

        out = ["<b>Ownerliste</b> - gruppiert nach Besitzer:\n"]
        owners_sorted = sorted(by_owner.keys(), key=lambda k: (k[0] is None, k[0] or 0))
        for (owner_id, owner_uname) in owners_sorted:
            pets = by_owner[(owner_id, owner_uname)]
            total_value = sum(p[2] for p in pets)

            out.append(f"<b>{tag(owner_id, owner_uname)}</b>  <i>({len(pets)} Pet(s), Gesamtwert: {total_value})</i>")
            for pet_id, pet_uname, price, locked_until, pet_skill, pet_xp, fullcare_days, fullcare_streak, care_done_today, mood_name, imprint_score, rebellious_until, rebellion_stage in pets:
                pet_tag = tag(pet_id, pet_uname)
                lock_txt = ""
                skill_name = _skill_meta(pet_skill)["name"]
                mood_name = render_pet_mood(mood_name, care_done_today, fullcare_streak, rebellious_until, now)
                imprint_name = pet_imprint_label(imprint_score)
                status_name = pet_status_label(rebellion_stage, rebellious_until, now)
                if locked_until > now:
                    mins_total = (locked_until - now) // 60
                    hrs, mins = divmod(mins_total, 60)
                    lock_txt = f" [LOCK {hrs}h{mins:02d}m]"
                active_brand, forced_brand = brand_map.get(int(pet_id), ("Keine", "Keine"))
                out.append(
                    f" - {pet_tag}  (<b>{price}</b>) [Laune: {escape(mood_name, False)} | Prägung: {escape(imprint_name, False)} | Bindung: {pet_bond_percent(pet_xp)} %] "
                    f"[Brandmarke: {escape(active_brand, False)} | Owner-Brand: {escape(forced_brand, False)}] "
                    f"[Status: {escape(status_name, False)}] [Perfekte Tage: {fullcare_days} | Streak: {fullcare_streak}] "
                    f"[{escape(skill_name, False)}]{lock_txt}"
                )
            out.append("")

        text = "\n".join(out).strip()
        for i in range(0, len(text), MAX_CHUNK):
            await update.effective_message.reply_text(text[i:i+MAX_CHUNK], disable_web_page_preview=True)

    async def cmd_release(update, context):
        if not is_group(update):
            return
        chat_id = update.effective_chat.id
        me = update.effective_user.id

        if not update.effective_message.reply_to_message or not update.effective_message.reply_to_message.from_user:
            await update.effective_message.reply_text("Antworte auf dein Haustier mit /release.")
            return

        pet_id = update.effective_message.reply_to_message.from_user.id

        async with aiosqlite.connect(DB) as db:
            owner = await get_owner_id(db, chat_id, pet_id)
            if owner != me:
                await update.effective_message.reply_text("Das ist nicht dein Haustier.")
                return
            await set_owner(db, chat_id, pet_id, None)
            await db.commit()

        await update.effective_message.reply_text("Freigelassen. Das Band ist durch, die Leine auch.")

    return {
        "get_owner_id": get_owner_id,
        "set_owner": set_owner,
        "cmd_top": cmd_top,
        "cmd_profil": cmd_profil,
        "cmd_owner": cmd_owner,
        "cmd_ownerlist": cmd_ownerlist,
        "cmd_release": cmd_release,
    }
