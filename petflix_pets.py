async def get_care(db, chat_id, pet_id):
    async with db.execute(
        "SELECT last_care_ts, care_done_today, day_ymd, acquired_ts FROM pets WHERE chat_id=? AND pet_id=?",
        (chat_id, pet_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"last": row[0], "done": row[1], "day": row[2], "acquired_ts": row[3]}


async def set_care(db, chat_id, pet_id, last, done, day):
    await db.execute("""
      INSERT INTO pets(chat_id, pet_id, last_care_ts, care_done_today, day_ymd)
      VALUES(?,?,?,?,?)
      ON CONFLICT(chat_id, pet_id) DO UPDATE SET
        last_care_ts=excluded.last_care_ts,
        care_done_today=excluded.care_done_today,
        day_ymd=excluded.day_ymd
    """, (chat_id, pet_id, last, done, day))
    await db.commit()


async def care_count_in_window(db, chat_id: int, pet_id: int, owner_id: int, since_ts: int) -> int:
    async with db.execute(
        """
        SELECT COUNT(*) FROM care_events
        WHERE chat_id=? AND pet_id=? AND owner_id=? AND ts>=?
        """,
        (chat_id, pet_id, owner_id, since_ts)
    ) as cur:
        row = await cur.fetchone()
    raw_events = int(row[0]) if row and row[0] is not None else 0
    return max(0, raw_events // 2)


async def care_count_last_24h(db, chat_id: int, pet_id: int, owner_id: int, now_ts: int) -> int:
    since_ts = now_ts - 24 * 3600
    return await care_count_in_window(db, chat_id, pet_id, owner_id, since_ts)


async def should_runaway(
    db,
    chat_id: int,
    pet_id: int,
    owner_id: int,
    acquired_ts: int | None,
    now_ts: int,
    care_window: int | None = None,
    runaway_hours: int = 72,
    runaway_min_cares: int = 10,
) -> bool:
    if not owner_id:
        return False
    if not acquired_ts:
        return False
    if now_ts - int(acquired_ts) < runaway_hours * 3600:
        return False
    if care_window is None:
        since_ts = now_ts - runaway_hours * 3600
        care_window = await care_count_in_window(db, chat_id, pet_id, owner_id, since_ts)
    return care_window < runaway_min_cares


async def apply_runaway_owner_penalty(db, chat_id: int, owner_id: int):
    await db.execute(
        "UPDATE players SET coins = MAX(0, coins - (coins / 2)) WHERE chat_id=? AND user_id=?",
        (chat_id, owner_id)
    )


async def get_latest_owned_pet_id(db, chat_id: int, owner_id: int):
    async with db.execute("""
        SELECT pet_id
        FROM pets
        WHERE chat_id=? AND owner_id=?
        ORDER BY COALESCE(last_care_ts, 0) DESC, pet_id ASC
        LIMIT 1
    """, (chat_id, owner_id)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else None


async def get_pet_lock_until(db, chat_id: int, pet_id: int) -> int:
    async with db.execute(
        "SELECT COALESCE(purchase_lock_until,0) FROM pets WHERE chat_id=? AND pet_id=?",
        (chat_id, pet_id)
    ) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0
