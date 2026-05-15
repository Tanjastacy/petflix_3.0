import time


async def set_cd(db, chat_id: int, user_id: int, key: str, seconds: int):
    ts = int(time.time()) + seconds
    await db.execute(
        """
        INSERT INTO cooldowns(chat_id,user_id,key,ts) VALUES(?,?,?,?)
        ON CONFLICT(chat_id,user_id,key) DO UPDATE SET ts=excluded.ts
        """,
        (chat_id, user_id, key, ts),
    )


async def get_cd_left(db, chat_id: int, user_id: int, key: str) -> int:
    async with db.execute(
        "SELECT ts FROM cooldowns WHERE chat_id=? AND user_id=? AND key=?",
        (chat_id, user_id, key)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return 0
        return max(0, row[0] - int(time.time()))
