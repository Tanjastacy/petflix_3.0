import aiosqlite


SCHEMA_VERSION = 22

async def _get_user_version(db) -> int:
    async with db.execute("PRAGMA user_version") as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0

async def _set_user_version(db, v: int):
    await db.execute(f"PRAGMA user_version={v}")

async def _table_has_column(db, table: str, col: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        cols = await cur.fetchall()
    return any(c[1] == col for c in cols)

async def migrate_db(db, daily_curse_enabled=True, auto_curse_enabled=False, pet_level_from_xp_func=None):
    if pet_level_from_xp_func is None:
        pet_level_from_xp_func = lambda xp: max(0, int(xp))
    current = await _get_user_version(db)

    if current < 1:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS players(
          chat_id   INTEGER,
          user_id   INTEGER,
          username  TEXT,
          coins     INTEGER DEFAULT 0,
          price     INTEGER DEFAULT 50, -- alte Default bleibt; ensure_player setzt 100
          gender    TEXT DEFAULT NULL,
          opted_out INTEGER DEFAULT 0,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS settings(
          chat_id INTEGER PRIMARY KEY,
          moraltax_enabled INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS pets(
          chat_id          INTEGER,
          pet_id           INTEGER,
          owner_id         INTEGER,
          acquired_ts      INTEGER DEFAULT NULL,
          last_care_ts     INTEGER DEFAULT NULL,
          care_done_today  INTEGER DEFAULT 0,
          day_ymd          TEXT,
          PRIMARY KEY(chat_id, pet_id)
        );
        CREATE TABLE IF NOT EXISTS cooldowns(
          chat_id INTEGER,
          user_id INTEGER,
          key     TEXT,
          ts      INTEGER,
          PRIMARY KEY(chat_id, user_id, key)
        );
        CREATE TABLE IF NOT EXISTS known_chats(
          chat_id             INTEGER PRIMARY KEY,
          last_seen           INTEGER,
          last_boot_announce  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_players_chat_coins  ON players(chat_id, coins);
        CREATE INDEX IF NOT EXISTS idx_players_chat_price  ON players(chat_id, price);
        CREATE INDEX IF NOT EXISTS idx_pets_owner          ON pets(chat_id, owner_id);
        CREATE INDEX IF NOT EXISTS idx_cd_user             ON cooldowns(chat_id, user_id);
        """)
        await _set_user_version(db, 1)
        current = 1
    
    if current < 2:
        if not await _table_has_column(db, "settings", "moraltax_enabled"):
            await db.execute("ALTER TABLE settings ADD COLUMN moraltax_enabled INTEGER DEFAULT 1")
        if not await _table_has_column(db, "settings", "moraltax_amount"):
            await db.execute("ALTER TABLE settings ADD COLUMN moraltax_amount INTEGER DEFAULT 5")
        await _set_user_version(db, 2)
        current = 2
    
    if current < 3:
        if not await _table_has_column(db, "pets", "purchase_lock_until"):
            await db.execute("ALTER TABLE pets ADD COLUMN purchase_lock_until INTEGER DEFAULT 0")
        await _set_user_version(db, 3)
        current = 3

    if current < 5:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS hass_challenges(
          chat_id      INTEGER,
          user_id      INTEGER,
          username     TEXT,
          triggered_by INTEGER,
          started_ts   INTEGER,
          expires_ts   INTEGER,
          required     INTEGER DEFAULT 3,
          done         INTEGER DEFAULT 0,
          penalty      INTEGER DEFAULT 200,
          active       INTEGER DEFAULT 1,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_hass_expires ON hass_challenges(chat_id, expires_ts);
        CREATE INDEX IF NOT EXISTS idx_hass_active  ON hass_challenges(chat_id, active);
        """)
        await _set_user_version(db, 5)
        current = 5

    if current < 6:
        if not await _table_has_column(db, "players", "gender"):
            await db.execute("ALTER TABLE players ADD COLUMN gender TEXT DEFAULT NULL")
        await _set_user_version(db, 6)
        current = 6

    if current < 7:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS care_events(
          chat_id    INTEGER,
          message_id INTEGER,
          pet_id     INTEGER,
          owner_id   INTEGER,
          action     TEXT,
          ts         INTEGER,
          PRIMARY KEY(chat_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_care_events_ts ON care_events(chat_id, ts);
        """)
        await _set_user_version(db, 7)
        current = 7

    if current < 8:
        if not await _table_has_column(db, "players", "last_seen"):
            await db.execute("ALTER TABLE players ADD COLUMN last_seen INTEGER DEFAULT NULL")
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS love_challenges(
          chat_id      INTEGER,
          user_id      INTEGER,
          username     TEXT,
          triggered_by INTEGER,
          started_ts   INTEGER,
          expires_ts   INTEGER,
          remind_stage INTEGER DEFAULT 0,
          active       INTEGER DEFAULT 1,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_love_expires ON love_challenges(chat_id, expires_ts);
        CREATE INDEX IF NOT EXISTS idx_love_active  ON love_challenges(chat_id, active);
        """)
        await _set_user_version(db, 8)
        current = 8

    if current < 9:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS superwords_found(
          chat_id  INTEGER,
          word     TEXT,
          found_by INTEGER,
          found_ts INTEGER,
          PRIMARY KEY(chat_id, word)
        );
        """)
        await _set_user_version(db, 9)
        current = 9

    if current < 10:
        if not await _table_has_column(db, "pets", "pet_skill"):
            await db.execute("ALTER TABLE pets ADD COLUMN pet_skill TEXT DEFAULT NULL")
        if not await _table_has_column(db, "pets", "care_bonus_day"):
            await db.execute("ALTER TABLE pets ADD COLUMN care_bonus_day TEXT DEFAULT NULL")
        await _set_user_version(db, 10)
        current = 10

    if current < 11:
        if not await _table_has_column(db, "pets", "pet_xp"):
            await db.execute("ALTER TABLE pets ADD COLUMN pet_xp INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "pet_level"):
            await db.execute("ALTER TABLE pets ADD COLUMN pet_level INTEGER DEFAULT 0")
        await _set_user_version(db, 11)
        current = 11

    if current < 12:
        if not await _table_has_column(db, "pets", "acquired_ts"):
            await db.execute("ALTER TABLE pets ADD COLUMN acquired_ts INTEGER DEFAULT NULL")
        await db.execute(
            "UPDATE pets SET acquired_ts=COALESCE(acquired_ts, last_care_ts, CAST(strftime('%s','now') AS INTEGER))"
        )
        await _set_user_version(db, 12)
        current = 12

    if current < 13:
        if not await _table_has_column(db, "settings", "daily_curse_enabled"):
            await db.execute(
                f"ALTER TABLE settings ADD COLUMN daily_curse_enabled INTEGER DEFAULT {1 if daily_curse_enabled else 0}"
            )
        if not await _table_has_column(db, "settings", "auto_curse_enabled"):
            await db.execute(
                f"ALTER TABLE settings ADD COLUMN auto_curse_enabled INTEGER DEFAULT {1 if auto_curse_enabled else 0}"
            )
        await _set_user_version(db, 13)
        current = 13

    if current < 14:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS user_titles(
          chat_id    INTEGER,
          user_id    INTEGER,
          title      TEXT,
          expires_ts INTEGER,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_titles_exp ON user_titles(chat_id, expires_ts);
        """)
        await _set_user_version(db, 14)
        current = 14

    if current < 15:
        await db.executescript("""
        CREATE VIEW IF NOT EXISTS pets_named AS
        SELECT
          p.chat_id,
          p.pet_id,
          pp.username AS pet_username,
          p.owner_id,
          po.username AS owner_username,
          p.acquired_ts,
          p.last_care_ts
        FROM pets p
        LEFT JOIN players pp ON pp.chat_id=p.chat_id AND pp.user_id=p.pet_id
        LEFT JOIN players po ON po.chat_id=p.chat_id AND po.user_id=p.owner_id;
        """)
        await _set_user_version(db, 15)
        current = 15

    if current < 16:
        if not await _table_has_column(db, "pets", "fullcare_streak"):
            await db.execute("ALTER TABLE pets ADD COLUMN fullcare_streak INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "fullcare_last_day"):
            await db.execute("ALTER TABLE pets ADD COLUMN fullcare_last_day TEXT DEFAULT NULL")
        await db.execute("UPDATE pets SET pet_xp=COALESCE(pet_xp, 0) * 5")
        await db.execute("UPDATE pets SET pet_level=MIN(100, CAST(COALESCE(pet_xp, 0) / 5 AS INTEGER))")
        await _set_user_version(db, 16)
        current = 16

    if current < 17:
        if not await _table_has_column(db, "pets", "fullcare_days"):
            await db.execute("ALTER TABLE pets ADD COLUMN fullcare_days INTEGER DEFAULT 0")
        await db.execute(
            "UPDATE pets SET fullcare_days=MAX(COALESCE(fullcare_days, 0), COALESCE(fullcare_streak, 0))"
        )
        async with db.execute("SELECT chat_id, pet_id, COALESCE(pet_xp, 0) FROM pets") as cur:
            pet_rows = await cur.fetchall()
        for row_chat_id, row_pet_id, row_pet_xp in pet_rows:
            await db.execute(
                "UPDATE pets SET pet_level=? WHERE chat_id=? AND pet_id=?",
                (pet_level_from_xp_func(int(row_pet_xp or 0)), row_chat_id, row_pet_id)
            )
        await _set_user_version(db, 17)
        current = 17

    # Sicherheitsnetz: Tabelle muss immer existieren, auch bei Alt-DBs mit inkonsistenter user_version.
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS superwords_found(
      chat_id  INTEGER,
      word     TEXT,
      found_by INTEGER,
      found_ts INTEGER,
      PRIMARY KEY(chat_id, word)
    );
    """)

    if current < 18:
        await db.execute("DELETE FROM superwords_found")
        await _set_user_version(db, 18)
        current = 18

    if current < 19:
        await db.execute("DELETE FROM superwords_found")
        await _set_user_version(db, 19)
        current = 19

    if current < 20:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS steal_feuds(
          chat_id          INTEGER,
          user_a           INTEGER,
          user_b           INTEGER,
          heat             INTEGER DEFAULT 0,
          clash_count      INTEGER DEFAULT 0,
          success_count    INTEGER DEFAULT 0,
          last_attack_ts   INTEGER DEFAULT 0,
          last_attacker_id INTEGER DEFAULT NULL,
          last_victim_id   INTEGER DEFAULT NULL,
          active_until_ts  INTEGER DEFAULT 0,
          PRIMARY KEY(chat_id, user_a, user_b)
        );
        CREATE INDEX IF NOT EXISTS idx_steal_feuds_active ON steal_feuds(chat_id, active_until_ts);
        CREATE INDEX IF NOT EXISTS idx_steal_feuds_last   ON steal_feuds(chat_id, last_attack_ts);
        """)
        await _set_user_version(db, 20)
        current = 20

    if current < 21:
        if not await _table_has_column(db, "pets", "mood_name"):
            await db.execute("ALTER TABLE pets ADD COLUMN mood_name TEXT DEFAULT NULL")
        if not await _table_has_column(db, "pets", "mood_day"):
            await db.execute("ALTER TABLE pets ADD COLUMN mood_day TEXT DEFAULT NULL")
        if not await _table_has_column(db, "pets", "imprint_score"):
            await db.execute("ALTER TABLE pets ADD COLUMN imprint_score INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "rebellious_until"):
            await db.execute("ALTER TABLE pets ADD COLUMN rebellious_until INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "breakout_count"):
            await db.execute("ALTER TABLE pets ADD COLUMN breakout_count INTEGER DEFAULT 0")
        await _set_user_version(db, 21)
        current = 21

    if current < 22:
        if not await _table_has_column(db, "players", "blood_debt"):
            await db.execute("ALTER TABLE players ADD COLUMN blood_debt INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "snatched_until"):
            await db.execute("ALTER TABLE pets ADD COLUMN snatched_until INTEGER DEFAULT 0")
        if not await _table_has_column(db, "pets", "snatched_from_owner_id"):
            await db.execute("ALTER TABLE pets ADD COLUMN snatched_from_owner_id INTEGER DEFAULT NULL")
        if not await _table_has_column(db, "pets", "snatched_from_acquired_ts"):
            await db.execute("ALTER TABLE pets ADD COLUMN snatched_from_acquired_ts INTEGER DEFAULT NULL")
        if not await _table_has_column(db, "pets", "hostage_until"):
            await db.execute("ALTER TABLE pets ADD COLUMN hostage_until INTEGER DEFAULT 0")
        await _set_user_version(db, 22)
        current = 22

    # Sicherheitsnetz für inkonsistente Alt-DBs:
    # Wenn user_version hoch ist, Spalten aber fehlen, ziehen wir sie hier trotzdem nach.
    if not await _table_has_column(db, "pets", "pet_skill"):
        await db.execute("ALTER TABLE pets ADD COLUMN pet_skill TEXT DEFAULT NULL")
    if not await _table_has_column(db, "pets", "care_bonus_day"):
        await db.execute("ALTER TABLE pets ADD COLUMN care_bonus_day TEXT DEFAULT NULL")
    if not await _table_has_column(db, "pets", "pet_xp"):
        await db.execute("ALTER TABLE pets ADD COLUMN pet_xp INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "pet_level"):
        await db.execute("ALTER TABLE pets ADD COLUMN pet_level INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "acquired_ts"):
        await db.execute("ALTER TABLE pets ADD COLUMN acquired_ts INTEGER DEFAULT NULL")
        await db.execute(
            "UPDATE pets SET acquired_ts=COALESCE(acquired_ts, last_care_ts, CAST(strftime('%s','now') AS INTEGER))"
        )
    if not await _table_has_column(db, "pets", "fullcare_streak"):
        await db.execute("ALTER TABLE pets ADD COLUMN fullcare_streak INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "fullcare_last_day"):
        await db.execute("ALTER TABLE pets ADD COLUMN fullcare_last_day TEXT DEFAULT NULL")
    if not await _table_has_column(db, "pets", "fullcare_days"):
        await db.execute("ALTER TABLE pets ADD COLUMN fullcare_days INTEGER DEFAULT 0")
        await db.execute(
            "UPDATE pets SET fullcare_days=MAX(COALESCE(fullcare_days, 0), COALESCE(fullcare_streak, 0))"
        )
    if not await _table_has_column(db, "pets", "mood_name"):
        await db.execute("ALTER TABLE pets ADD COLUMN mood_name TEXT DEFAULT NULL")
    if not await _table_has_column(db, "pets", "mood_day"):
        await db.execute("ALTER TABLE pets ADD COLUMN mood_day TEXT DEFAULT NULL")
    if not await _table_has_column(db, "pets", "imprint_score"):
        await db.execute("ALTER TABLE pets ADD COLUMN imprint_score INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "rebellious_until"):
        await db.execute("ALTER TABLE pets ADD COLUMN rebellious_until INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "breakout_count"):
        await db.execute("ALTER TABLE pets ADD COLUMN breakout_count INTEGER DEFAULT 0")
    if not await _table_has_column(db, "players", "blood_debt"):
        await db.execute("ALTER TABLE players ADD COLUMN blood_debt INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "snatched_until"):
        await db.execute("ALTER TABLE pets ADD COLUMN snatched_until INTEGER DEFAULT 0")
    if not await _table_has_column(db, "pets", "snatched_from_owner_id"):
        await db.execute("ALTER TABLE pets ADD COLUMN snatched_from_owner_id INTEGER DEFAULT NULL")
    if not await _table_has_column(db, "pets", "snatched_from_acquired_ts"):
        await db.execute("ALTER TABLE pets ADD COLUMN snatched_from_acquired_ts INTEGER DEFAULT NULL")
    if not await _table_has_column(db, "pets", "hostage_until"):
        await db.execute("ALTER TABLE pets ADD COLUMN hostage_until INTEGER DEFAULT 0")
    if not await _table_has_column(db, "settings", "daily_curse_enabled"):
        await db.execute(
            f"ALTER TABLE settings ADD COLUMN daily_curse_enabled INTEGER DEFAULT {1 if daily_curse_enabled else 0}"
        )
    if not await _table_has_column(db, "settings", "auto_curse_enabled"):
        await db.execute(
            f"ALTER TABLE settings ADD COLUMN auto_curse_enabled INTEGER DEFAULT {1 if auto_curse_enabled else 0}"
        )
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS steal_feuds(
      chat_id          INTEGER,
      user_a           INTEGER,
      user_b           INTEGER,
      heat             INTEGER DEFAULT 0,
      clash_count      INTEGER DEFAULT 0,
      success_count    INTEGER DEFAULT 0,
      last_attack_ts   INTEGER DEFAULT 0,
      last_attacker_id INTEGER DEFAULT NULL,
      last_victim_id   INTEGER DEFAULT NULL,
      active_until_ts  INTEGER DEFAULT 0,
      PRIMARY KEY(chat_id, user_a, user_b)
    );
    CREATE INDEX IF NOT EXISTS idx_steal_feuds_active ON steal_feuds(chat_id, active_until_ts);
    CREATE INDEX IF NOT EXISTS idx_steal_feuds_last   ON steal_feuds(chat_id, last_attack_ts);
    """)

async def db_init(db_path, daily_curse_enabled=True, auto_curse_enabled=False, pet_level_from_xp_func=None):
    if pet_level_from_xp_func is None:
        pet_level_from_xp_func = lambda xp: max(0, int(xp))
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await migrate_db(
            db,
            daily_curse_enabled=daily_curse_enabled,
            auto_curse_enabled=auto_curse_enabled,
            pet_level_from_xp_func=pet_level_from_xp_func,
        )
        await db.commit()
