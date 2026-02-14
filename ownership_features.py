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
    pet_level_title = deps["pet_level_title"]
    get_pet_lock_until = deps["get_pet_lock_until"]
    get_active_titles_map = deps["get_active_titles_map"]
    with_title_suffix = deps["with_title_suffix"]
    _skill_meta = deps["_skill_meta"]

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
            async with db.execute("SELECT username, user_id, coins FROM players WHERE chat_id=? ORDER BY coins DESC LIMIT 10", (chat_id,)) as cur:
                rows = await cur.fetchall()
            titles = await get_active_titles_map(db, chat_id, [int(r[1]) for r in rows])
            await db.commit()
        if not rows:
            await update.effective_message.reply_text("Noch keine Spieler.")
            return
        lines = []
        for i, (uname, uid, c) in enumerate(rows, start=1):
            raw_tag = f"@{uname}" if uname else f"ID:{uid}"
            raw_tag = with_title_suffix(raw_tag, titles.get(int(uid)))
            tag = escape(raw_tag, quote=False)
            lines.append(f"{i}. {tag}: {c} Coins")

        text = "Rangliste Top 10 Spieler:\n\n" + "\n".join(lines)
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
                "SELECT COALESCE(pet_level,0) FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, target_id)
            ) as cur:
                lrow = await cur.fetchone()
            pet_level = int(lrow[0]) if lrow else 0
            level_txt = f"Level {pet_level} - {pet_level_title(pet_level)}"

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
                f"Besitzer: {tag}. Aktueller Preis: {price}.{lock_txt}\nSkill: {skill_txt}\n{level_txt}",
                parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text(
                f"Kein Besitzer. Aktueller Preis: {price}.{lock_txt}\nSkill: {skill_txt}\n{level_txt}"
            )

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
                        COALESCE(p.pet_level, 0)                    AS pet_level
                    FROM pets p
                    LEFT JOIN players ou ON ou.chat_id=p.chat_id AND ou.user_id=p.owner_id
                    LEFT JOIN players pu ON pu.chat_id=p.chat_id AND pu.user_id=p.pet_id
                    LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
                    WHERE p.chat_id=?
                    ORDER BY p.owner_id ASC, current_price DESC, p.pet_id ASC
                """, (chat_id,)) as cur:
                    rows = await cur.fetchall()
                title_user_ids = []
                for owner_id, _, pet_id, _, _, _, _, _ in rows:
                    if owner_id:
                        title_user_ids.append(int(owner_id))
                    if pet_id:
                        title_user_ids.append(int(pet_id))
                titles = await get_active_titles_map(db, chat_id, title_user_ids)
                await db.commit()
        except Exception as e:
            return await update.effective_message.reply_text(
                f"Konnte Ownerliste nicht laden: <code>{type(e).__name__}</code> - {escape(str(e), False)}"
            )

        if not rows:
            return await update.effective_message.reply_text("Noch keine Besitzverhaeltnisse. Kauf dir erstmal jemanden.")

        by_owner = {}
        for owner_id, owner_uname, pet_id, pet_uname, price, locked_until, pet_skill, pet_level in rows:
            by_owner.setdefault((owner_id, owner_uname), []).append(
                (pet_id, pet_uname, int(price or 0), int(locked_until or 0), pet_skill, int(pet_level or 0))
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
            for pet_id, pet_uname, price, locked_until, pet_skill, pet_level in pets:
                pet_tag = tag(pet_id, pet_uname)
                lock_txt = ""
                skill_name = _skill_meta(pet_skill)["name"]
                level_name = pet_level_title(pet_level)
                if locked_until > now:
                    mins_total = (locked_until - now) // 60
                    hrs, mins = divmod(mins_total, 60)
                    lock_txt = f" [LOCK {hrs}h{mins:02d}m]"
                out.append(
                    f" - {pet_tag}  (<b>{price}</b>) [Lvl {pet_level}: {escape(level_name, False)}] "
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
        "cmd_owner": cmd_owner,
        "cmd_ownerlist": cmd_ownerlist,
        "cmd_release": cmd_release,
    }
