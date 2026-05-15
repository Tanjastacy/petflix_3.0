async def get_user_price(db, chat_id: int, user_id: int, default_price: int = 100) -> int:
    async with db.execute(
        "SELECT price FROM players WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row and row[0] is not None else default_price


async def set_user_price(db, chat_id: int, user_id: int, price: int):
    await db.execute("UPDATE players SET price=? WHERE chat_id=? AND user_id=?", (price, chat_id, user_id))


async def ensure_player(
    db,
    chat_id: int,
    user_id: int,
    username: str,
    start_coins: int = 0,
    base_price: int = 100,
):
    await db.execute(
        """
        INSERT INTO players(chat_id, user_id, username, coins, price)
        VALUES(?,?,?,?,?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
          username=CASE
            WHEN TRIM(COALESCE(excluded.username, '')) <> '' THEN excluded.username
            ELSE players.username
          END
        """,
        (chat_id, user_id, username or "", start_coins, base_price),
    )


async def ensure_player_entry(
    db,
    chat_id: int,
    user_id: int,
    username: str | None,
    start_coins: int = 0,
    base_price: int = 100,
):
    await ensure_player(db, chat_id, user_id, username or "", start_coins, base_price)


async def get_coins(db, chat_id: int, user_id: int) -> int:
    async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0
