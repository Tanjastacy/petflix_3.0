from brand_data import (
    BRAND_BUY_LINES,
    BRAND_CATEGORIES,
    BRAND_PET_LINES,
    BRAND_REMOVE_LINES,
    BRAND_SET_LINES,
    FORCED_BRAND_TYPES,
    VOLUNTARY_BRAND_TYPES,
)


def create_brand_features(deps: dict):
    aiosqlite = deps["aiosqlite"]
    datetime = deps["datetime"]
    random = deps["random"]
    escape = deps["escape"]
    DB = deps["DB"]
    ParseMode = deps["ParseMode"]
    is_group = deps["is_group"]
    mention_html = deps["mention_html"]
    _ensure_player_entry = deps["_ensure_player_entry"]
    _get_coins = deps["_get_coins"]

    def _brand_name_from_args(args) -> str:
        return " ".join(args or []).strip()

    def _not_enough(user_tag: str) -> str:
        return f"{user_tag}, du hast nicht genug Coins. Armut schützt vor schlechten Entscheidungen. Heute zumindest."

    async def _change_user_coins(db, chat_id: int, user_id: int, amount: int):
        if amount < 0:
            await db.execute(
                "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                (abs(int(amount)), chat_id, user_id),
            )
        elif amount > 0:
            await db.execute(
                "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                (int(amount), chat_id, user_id),
            )

    async def _get_brand_by_name(db, name: str):
        async with db.execute(
            """
            SELECT id, name, category, price, brand_type
            FROM brand_catalog
            WHERE lower(name)=lower(?) AND COALESCE(is_active, 1)=1
            """,
            (name,),
        ) as cur:
            return await cur.fetchone()

    async def _get_username(db, chat_id: int, user_id: int):
        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def _resolve_brand_pet_target(db, update, context):
        msg = update.effective_message
        if msg.reply_to_message and msg.reply_to_message.from_user:
            user = msg.reply_to_message.from_user
            return user.id, user.username or None, _brand_name_from_args(context.args)

        if not context.args or len(context.args) < 2:
            return None, None, ""

        target_token = context.args[0].strip()
        target_raw = target_token.lstrip("@")
        if target_raw.isdigit():
            target_id = int(target_raw)
            return target_id, await _get_username(db, update.effective_chat.id, target_id), _brand_name_from_args(context.args[1:])

        async with db.execute(
            "SELECT user_id, username FROM players WHERE chat_id=? AND lower(username)=lower(?)",
            (update.effective_chat.id, target_raw),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None, None, _brand_name_from_args(context.args[1:])
        return int(row[0]), row[1] or target_raw, _brand_name_from_args(context.args[1:])

    async def _get_active_brand_rows(db, user_id: int):
        async with db.execute(
            """
            SELECT
              sb.name AS self_name,
              fb.name AS forced_name,
              ab.forced_by_owner_id,
              ab.forced_remove_cost
            FROM active_brands ab
            LEFT JOIN brand_catalog sb ON sb.id=ab.active_self_brand_id
            LEFT JOIN brand_catalog fb ON fb.id=ab.forced_brand_id
            WHERE ab.user_id=?
            """,
            (user_id,),
        ) as cur:
            return await cur.fetchone()

    async def get_active_brand_labels(db, chat_id: int, user_id: int):
        row = await _get_active_brand_rows(db, user_id)
        if not row:
            return "Keine", "Keine"
        self_name = row[0] or "Keine"
        forced_name = row[1] or "Keine"
        if row[1] and row[2]:
            owner_name = await _get_username(db, chat_id, int(row[2]))
            forced_name = f"{row[1]} von {mention_html(int(row[2]), owner_name)}"
        return self_name, forced_name

    async def cmd_brandshop(update, context):
        if not is_group(update):
            return
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                """
                SELECT name, category, price, brand_type
                FROM brand_catalog
                WHERE COALESCE(is_active, 1)=1
                ORDER BY category, price, name COLLATE NOCASE
                """
            ) as cur:
                rows = await cur.fetchall()
            await db.commit()

        by_category = {}
        for name, category, price, brand_type in rows:
            by_category.setdefault(category, []).append((name, int(price), brand_type))

        lines = [
            "<b>Petflix Brandshop</b>",
            "",
            "Kaufe dir eine Brandmarke. Oder lass dir eine aufdrücken, weil diese Gruppe offenbar kollektiv beschlossen hat, Würde sei optional.",
        ]
        for category, label, note in BRAND_CATEGORIES:
            items = by_category.get(category, [])
            if not items:
                continue
            lines.extend(["", f"<b>{label}:</b>"])
            if note:
                lines.append(note)
            for name, price, brand_type in items:
                cmd = "/brandpet @user" if brand_type in FORCED_BRAND_TYPES and category == "Forced-Brands" else "/brandkaufen"
                lines.append(f"{cmd} {escape(name, False)} - {price} Coins")
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_brandkaufen(update, context):
        if not is_group(update):
            return
        user = update.effective_user
        chat_id = update.effective_chat.id
        user_tag = mention_html(user.id, user.username or None)
        brand_name = _brand_name_from_args(context.args)
        if not brand_name:
            return await update.effective_message.reply_text("Nutzung: /brandkaufen <Brandmarkenname>")

        async with aiosqlite.connect(DB) as db:
            await _ensure_player_entry(db, chat_id, user.id, user.username or None)
            brand = await _get_brand_by_name(db, brand_name)
            if not brand:
                return await update.effective_message.reply_text(
                    "Diese Brandmarke existiert nicht. Noch nicht. Gib der Gruppe fünf Minuten, sie macht es schlimmer."
                )
            brand_id, brand_real_name, _, price, brand_type = brand
            if brand_type not in VOLUNTARY_BRAND_TYPES:
                return await update.effective_message.reply_text("Diese Brandmarke kann man sich nicht freiwillig kaufen.")
            async with db.execute(
                "SELECT 1 FROM user_brands WHERE user_id=? AND brand_id=?",
                (user.id, brand_id),
            ) as cur:
                owned = await cur.fetchone()
            if owned:
                return await update.effective_message.reply_text(
                    f'{user_tag}, du besitzt "{escape(brand_real_name, False)}" schon. Doppelte Schande bringt leider keinen Mengenrabatt.',
                    parse_mode=ParseMode.HTML,
                )
            coins = await _get_coins(db, chat_id, user.id)
            if coins < int(price):
                return await update.effective_message.reply_text(_not_enough(user_tag), parse_mode=ParseMode.HTML)
            now = datetime.datetime.utcnow().isoformat(timespec="seconds")
            await _change_user_coins(db, chat_id, user.id, -int(price))
            await db.execute(
                "INSERT INTO user_brands(user_id, brand_id, bought_by_user_id, created_at) VALUES(?,?,?,?)",
                (user.id, brand_id, user.id, now),
            )
            async with db.execute(
                "SELECT active_self_brand_id FROM active_brands WHERE user_id=?",
                (user.id,),
            ) as cur:
                active = await cur.fetchone()
            if not active:
                await db.execute(
                    "INSERT INTO active_brands(user_id, active_self_brand_id) VALUES(?,?)",
                    (user.id, brand_id),
                )
            elif active[0] is None:
                await db.execute(
                    "UPDATE active_brands SET active_self_brand_id=? WHERE user_id=?",
                    (brand_id, user.id),
                )
            await db.commit()
        text = random.choice(BRAND_BUY_LINES).format(
            user=user_tag,
            brand=escape(brand_real_name, False),
            price=int(price),
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_brandsetzen(update, context):
        if not is_group(update):
            return
        user = update.effective_user
        brand_name = _brand_name_from_args(context.args)
        if not brand_name:
            return await update.effective_message.reply_text("Nutzung: /brandsetzen <Brandmarkenname>")

        async with aiosqlite.connect(DB) as db:
            brand = await _get_brand_by_name(db, brand_name)
            if not brand:
                return await update.effective_message.reply_text(
                    "Diese Brandmarke existiert nicht. Noch nicht. Gib der Gruppe fünf Minuten, sie macht es schlimmer."
                )
            brand_id, brand_real_name, _, _, brand_type = brand
            if brand_type not in VOLUNTARY_BRAND_TYPES:
                return await update.effective_message.reply_text("Diese Brandmarke ist aufgezwungen und kann nicht freiwillig gesetzt werden.")
            async with db.execute(
                "SELECT 1 FROM user_brands WHERE user_id=? AND brand_id=?",
                (user.id, brand_id),
            ) as cur:
                owned = await cur.fetchone()
            if not owned:
                return await update.effective_message.reply_text("Du besitzt diese Brandmarke noch nicht.")
            await db.execute(
                """
                INSERT INTO active_brands(user_id, active_self_brand_id)
                VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE SET active_self_brand_id=excluded.active_self_brand_id
                """,
                (user.id, brand_id),
            )
            await db.commit()
        text = random.choice(BRAND_SET_LINES).format(
            user=mention_html(user.id, user.username or None),
            brand=escape(brand_real_name, False),
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_meinebrands(update, context):
        if not is_group(update):
            return
        user = update.effective_user
        chat_id = update.effective_chat.id
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                """
                SELECT bc.name, bc.brand_type
                FROM user_brands ub
                JOIN brand_catalog bc ON bc.id=ub.brand_id
                WHERE ub.user_id=?
                ORDER BY bc.category, bc.price, bc.name COLLATE NOCASE
                """,
                (user.id,),
            ) as cur:
                owned = await cur.fetchall()
            active_self, forced = await get_active_brand_labels(db, chat_id, user.id)
            row = await _get_active_brand_rows(db, user.id)
            remove_cost = int(row[3] or 0) if row and row[1] else 0
            await db.commit()

        owned_lines = [f"- {escape(name, False)} ({brand_type})" for name, brand_type in owned]
        if not owned_lines:
            owned_lines = ["- Keine gekauft"]
        lines = [
            "<b>Meine Brandmarken</b>",
            "",
            f"Brandmarke: {escape(active_self, False)}",
            f"Owner-Brand: {forced}",
            f"Ablegen kostet: {remove_cost} Coins" if remove_cost else "Ablegen kostet: -",
            "",
            "<b>Gekauft:</b>",
            *owned_lines,
        ]
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_brandpet(update, context):
        if not is_group(update):
            return
        owner = update.effective_user
        chat_id = update.effective_chat.id
        owner_tag = mention_html(owner.id, owner.username or None)

        async with aiosqlite.connect(DB) as db:
            pet_id, pet_uname, brand_name = await _resolve_brand_pet_target(db, update, context)
            if not pet_id:
                return await update.effective_message.reply_text("Nutzung: /brandpet @user <Brandmarkenname> oder als Reply.")
            if not brand_name:
                return await update.effective_message.reply_text("Welche Brandmarke soll aufgezwungen werden?")
            async with db.execute(
                "SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, pet_id),
            ) as cur:
                owner_row = await cur.fetchone()
            if not owner_row or int(owner_row[0] or 0) != owner.id:
                return await update.effective_message.reply_text(
                    f"{owner_tag}, das ist nicht dein Pet. Fremde Leute brandmarken ist hier selbst für Petflix zu viel Verwaltungschaos.",
                    parse_mode=ParseMode.HTML,
                )
            brand = await _get_brand_by_name(db, brand_name)
            if not brand:
                return await update.effective_message.reply_text(
                    "Diese Brandmarke existiert nicht. Noch nicht. Gib der Gruppe fünf Minuten, sie macht es schlimmer."
                )
            brand_id, brand_real_name, _, price, brand_type = brand
            if brand_type not in FORCED_BRAND_TYPES:
                return await update.effective_message.reply_text("Diese Brandmarke darf keinem Pet aufgezwungen werden.")
            await _ensure_player_entry(db, chat_id, owner.id, owner.username or None)
            coins = await _get_coins(db, chat_id, owner.id)
            if coins < int(price):
                return await update.effective_message.reply_text(_not_enough(owner_tag), parse_mode=ParseMode.HTML)
            remove_cost = max(100, int(price) * 40 // 100)
            now = datetime.datetime.utcnow().isoformat(timespec="seconds")
            await _change_user_coins(db, chat_id, owner.id, -int(price))
            await db.execute(
                """
                INSERT INTO active_brands(user_id, forced_brand_id, forced_by_owner_id, forced_at, forced_remove_cost)
                VALUES(?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                  forced_brand_id=excluded.forced_brand_id,
                  forced_by_owner_id=excluded.forced_by_owner_id,
                  forced_at=excluded.forced_at,
                  forced_remove_cost=excluded.forced_remove_cost
                """,
                (pet_id, brand_id, owner.id, now, remove_cost),
            )
            await db.commit()
        pet_tag = mention_html(int(pet_id), pet_uname)
        text = random.choice(BRAND_PET_LINES).format(
            owner=owner_tag,
            pet=pet_tag,
            brand=escape(brand_real_name, False),
            price=int(price),
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_brandablegen(update, context):
        if not is_group(update):
            return
        user = update.effective_user
        chat_id = update.effective_chat.id
        user_tag = mention_html(user.id, user.username or None)
        async with aiosqlite.connect(DB) as db:
            async with db.execute(
                """
                SELECT ab.forced_brand_id, ab.forced_by_owner_id, ab.forced_remove_cost, bc.name
                FROM active_brands ab
                LEFT JOIN brand_catalog bc ON bc.id=ab.forced_brand_id
                WHERE ab.user_id=?
                """,
                (user.id,),
            ) as cur:
                row = await cur.fetchone()
            if not row or not row[0]:
                return await update.effective_message.reply_text(
                    f"{user_tag}, du trägst gerade keine aufgezwungene Brandmarke. Glückwunsch, ein seltenes Verwaltungswunder.",
                    parse_mode=ParseMode.HTML,
                )
            remove_cost = int(row[2] or 0)
            brand_name = row[3] or "Unbekannt"
            coins = await _get_coins(db, chat_id, user.id)
            if coins < remove_cost:
                return await update.effective_message.reply_text(
                    f'{user_tag}, du hast nicht genug Coins, um "{escape(brand_name, False)}" abzulegen. Die Schande bleibt kleben. Haushaltsplanung, Leute.',
                    parse_mode=ParseMode.HTML,
                )
            await _change_user_coins(db, chat_id, user.id, -remove_cost)
            await db.execute(
                """
                UPDATE active_brands
                SET forced_brand_id=NULL, forced_by_owner_id=NULL, forced_at=NULL, forced_remove_cost=0
                WHERE user_id=?
                """,
                (user.id,),
            )
            owner_id = int(row[1]) if row[1] else None
            owner_uname = await _get_username(db, chat_id, owner_id) if owner_id else None
            await db.commit()
        text = random.choice(BRAND_REMOVE_LINES).format(
            pet=user_tag,
            brand=escape(brand_name, False),
            price=remove_cost,
        )
        if owner_id:
            text += f"\n{mention_html(owner_id, owner_uname)} ist vermutlich beleidigt. Verwaltung nennt das: erwartbar."
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    return {
        "cmd_brandshop": cmd_brandshop,
        "cmd_brandkaufen": cmd_brandkaufen,
        "cmd_brandsetzen": cmd_brandsetzen,
        "cmd_meinebrands": cmd_meinebrands,
        "cmd_brandpet": cmd_brandpet,
        "cmd_brandablegen": cmd_brandablegen,
        "get_active_brand_labels": get_active_brand_labels,
    }
