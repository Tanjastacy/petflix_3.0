# Petflix 2.0 .py (Refreshed: owner-steal logic, ownerlist, bugfixes)

import asyncio
import os
import random
import time
import logging
import aiosqlite
import datetime
import hashlib
import re
from typing import Optional
from datetime import time as dtime
from zoneinfo import ZoneInfo  # Python 3.9+
from html import escape

from telegram import Update, BotCommand
from telegram.constants import ChatType, ChatMemberStatus, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters, Defaults
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID_RAW = os.getenv("ALLOWED_CHAT_ID", "-1002550303601")
try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID_RAW)
    CHAT_FILTER = filters.Chat(ALLOWED_CHAT_ID)
except ValueError:
    CHAT_FILTER = filters.Chat(ALLOWED_CHAT_ID_RAW)

DB = os.environ.get("DB_PATH", "petflix_2.0.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "data")
MAX_CHUNK = 3500  # unter 4096 bleiben, wegen HTML-Overhead sicher

# =========================
# Konfiguration
# =========================
START_COINS = 0
DAILY_COINS = 0
DAILY_COOLDOWN_S = 22 * 3600
MESSAGE_REWARD = 1
USER_BASE_PRICE = 100
USER_PRICE_STEP = 50  # 100 -> 150 -> 200 ...
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MESSAGE_THROTTLE_S = 1
CARE_COOLDOWN_S = 20
CARES_PER_DAY = 100
RUNAWAY_HOURS = 24
PETFLIX_TZ = os.environ.get("PETFLIX_TZ", "Europe/Berlin")
DAILY_GIFT_COINS = 15
CURRENT_MODE = os.getenv("PETFLIX_MODE", "tame").lower()
if CURRENT_MODE not in ("tame", "spicy"):
    CURRENT_MODE = "tame"


# Konfig Moralische Steuer
MORAL_TAX_DEFAULT = 5
MORAL_TAX_TRIGGERS = [
    r"\bbitte\b",
    r"\bdanke\b",
    r"\bentschuldigung\b",
    r"\bsorry\b",
    r"\bkannst du\b",
    r"\bkönntest du\b",
    r"\bwärst du so lieb\b",
    r"🙏"
]

BOOT_TS = int(time.time())

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
log = logging.getLogger("Petflix_2.0")

# =========================
# DB-Setup 
# =========================

SCHEMA_VERSION = 2

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

async def migrate_db(db):
    current = await _get_user_version(db)

    if current < 1:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS players(
          chat_id   INTEGER,
          user_id   INTEGER,
          username  TEXT,
          coins     INTEGER DEFAULT 0,
          price     INTEGER DEFAULT 50, -- alte Default bleibt; ensure_player setzt 100
          opted_out INTEGER DEFAULT 0,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS pets(
          chat_id          INTEGER,
          pet_id           INTEGER,
          owner_id         INTEGER,
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
        CREATE TABLE IF NOT EXISTS settings(
          chat_id INTEGER PRIMARY KEY,
          nsfw    INTEGER DEFAULT 0
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

async def db_init():
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await migrate_db(db)
        await db.commit()

# Helpers

def nice_name(u) -> str:
    # Anzeige-Name ohne HTML-Sicherheit (wird für Markdown benutzt)
    return f"@{u.username}" if getattr(u, "username", None) else (u.full_name or str(u.id))

def nice_name_html(u) -> str:
    # Für alle Antworten, die mit HTML geparst werden (Default!)
    return escape(nice_name(u), quote=False)

def split_chunks(text, size=MAX_CHUNK):
    for i in range(0, len(text), size):
        yield text[i:i+size]

async def get_moraltax_settings(db, chat_id: int):
    async with db.execute("SELECT moraltax_enabled, moraltax_amount FROM settings WHERE chat_id=?", (chat_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO settings(chat_id, nsfw, moraltax_enabled, moraltax_amount) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET moraltax_enabled=COALESCE(moraltax_enabled,excluded.moraltax_enabled), "
            "moraltax_amount=COALESCE(moraltax_amount,excluded.moraltax_amount)",
            (chat_id, 0, 1, MORAL_TAX_DEFAULT)
        )
        await db.commit()
        return True, MORAL_TAX_DEFAULT
    enabled = bool(row[0]) if row[0] is not None else True
    amount = int(row[1]) if row[1] is not None else MORAL_TAX_DEFAULT
    return enabled, amount

def is_too_nice(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(re.search(pat, t) for pat in MORAL_TAX_TRIGGERS)

async def apply_moraltax_if_needed(db, chat_id: int, user_id: int, text: str) -> Optional[int]:
    if not text or not is_too_nice(text):
        return None
    enabled, amount = await get_moraltax_settings(db, chat_id)
    if not enabled or amount <= 0:
        return None
    async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    coins = row[0] if row else 0
    deduct = min(amount, coins)  # kein negatives Guthaben
    if deduct <= 0:
        return 0
    await db.execute("UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?", (deduct, chat_id, user_id))
    await db.commit()
    log.info(f"[MORALTAX] chat={chat_id} user={user_id} deducted={deduct}")
    return deduct

def today_ymd():
    return datetime.date.today().isoformat()

async def get_care(db, chat_id, pet_id):
    async with db.execute(
        "SELECT last_care_ts, care_done_today, day_ymd FROM pets WHERE chat_id=? AND pet_id=?",
        (chat_id, pet_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"last": row[0], "done": row[1], "day": row[2]}

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

def is_group(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}

def nice_name(u) -> str:
    return f"@{u.username}" if getattr(u, "username", None) else (u.full_name or str(u.id))

async def get_user_price(db, chat_id: int, user_id: int) -> int:
    async with db.execute(
        "SELECT price FROM players WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row and row[0] is not None else USER_BASE_PRICE

async def set_user_price(db, chat_id: int, user_id: int, price: int):
    await db.execute("UPDATE players SET price=? WHERE chat_id=? AND user_id=?", (price, chat_id, user_id))

async def ensure_player(db, chat_id: int, user_id: int, username: str):
    await db.execute(
        """
        INSERT INTO players(chat_id, user_id, username, coins, price)
        VALUES(?,?,?,?,?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET username=excluded.username
        """,
        (chat_id, user_id, username or "", START_COINS, USER_BASE_PRICE),
    )

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

def _secs_until_tomorrow() -> int:
    now = datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).date()
    midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
    return max(1, int((midnight - now).total_seconds()))

# =========================
# Pflegeaktionen (gemeinsamer Handler)
# =========================
async def do_care(update, context, action_key, tame_lines, spicy_lines):
    if not is_group(update): 
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    owner = update.effective_user

    # Ziel bestimmen
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        # Fallback: letztes Haustier des Owners
        async with aiosqlite.connect(DB) as db:
            async with db.execute("""
                SELECT pet_id FROM pets
                WHERE chat_id=? AND owner_id=?
                ORDER BY last_care_ts DESC LIMIT 1
            """, (chat_id, owner.id)) as cur:
                row = await cur.fetchone()
        if not row:
            await msg.reply_text("❌ Antworte auf dein Haustier oder kaufe dir eines mit /buy.")
            return
        class Obj: pass
        pet = Obj()
        pet.id = row[0]
        pet.first_name = "Dein Haustier"
        pet.username = None
    else:
        pet = msg.reply_to_message.from_user

    if pet.id == owner.id:
        await msg.reply_text("Selbstpflege ist wichtig, aber zählt hier nicht.")
        return

    async with aiosqlite.connect(DB) as db:
        # Besitz prüfen
        async with db.execute("SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id)) as cur:
            row = await cur.fetchone()
        if not row or row[0] != owner.id:
            await msg.reply_text("Das ist nicht dein Haustier.")
            return

        # runaway check
        care = await get_care(db, chat_id, pet.id)
        now = int(time.time())
        if care and care["last"] and now - care["last"] >= RUNAWAY_HOURS*3600:
            await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id))
            await db.commit()
            await msg.reply_text(f"{nice_name_html(pet)} hat die Leine durchgebissen. {RUNAWAY_HOURS} Stunden ohne Pflege – und tschüss.")
            return

        # cooldown
        cd_key = f"care:{action_key}:{owner.id}:{pet.id}"
        left = await get_cd_left(db, chat_id, owner.id, cd_key)
        if left > 0:
            await msg.reply_text("Langsam, Casanova. Etwas Geduld.")
            return

        # Tageszähler
        today = today_ymd()
        done = care["done"] if (care and care["day"] == today) else 0
        if done >= CARES_PER_DAY:
            await msg.reply_text("Heute ist das Haustier bereits bestens versorgt. Morgen wieder.")
            return

        done += 1
        await set_care(db, chat_id, pet.id, now, done, today)
        await set_cd(db, chat_id, owner.id, cd_key, CARE_COOLDOWN_S)
        await db.commit()

    # nsfw?
    spicy = False
    try:
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT nsfw FROM settings WHERE chat_id=?", (chat_id,)) as cur:
                srow = await cur.fetchone()
                spicy = bool(srow and srow[0])
    except:
        pass

    lines = tame_lines if CURRENT_MODE == "tame" else spicy_lines
    text = random.choice(lines)
    text = text.replace("{CARES_PER_DAY}", str(CARES_PER_DAY)).replace("{pets}", "{pet}")
    text = text.format(owner=nice_name_html(owner), pet=nice_name_html(pet), n=done)
    await msg.reply_text(text)


# =========================
# Daily Gift
# =========================
async def _pick_random_player(chat_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            rows = await cur.fetchall()
    if not rows:
        return None, None
    return random.choice(rows)

def _mention_from_uid_username(user_id: int, username: str | None) -> str:
    return f"@{username}" if username else f"[ID:{user_id}](tg://user?id={user_id})"

_SAVAGE_LINES = [
    "Guck mal, {user}, {coins} Coins. Damit du endlich Satzzeichen kaufen kannst.",
    "{user}, {coins} Coins vom Haus. Nicht ausgeben wie deine Geduld beim Lesen.",
    "Hier, {user}: {coins} Coins. Damit du nicht nur im Chat arm klingst.",
    "{user} kriegt {coins} Coins. Belohnung fürs konsequente Nichtstun.",
    "{user}, {coins} Coins. Kauf dir was Schönes – z. B. eine Meinung mit Belegen.",
    "Jackpot, {user}: {coins} Coins. Reicht für 3 halbgare Hot Takes.",
    "{user}, {coins} Coins. Schreib was – aber diesmal ohne CAPSLOCK, ok?",
]

async def daily_gift_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = ALLOWED_CHAT_ID
    today = today_ymd()
    cd_key = f"dailygift:{today}"

    async with aiosqlite.connect(DB) as db:
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
    await context.bot.send_message(chat_id=chat_id, text=f"🎁 Tägliche Almosen-Time!\n{line}", parse_mode="Markdown")

# =========================
# Auto-Registrierung + Coins
# =========================
def is_allowed_chat(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.id == ALLOWED_CHAT_ID

async def mark_chat_and_maybe_announce(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    if chat_id != ALLOWED_CHAT_ID:
        return
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO known_chats(chat_id, last_seen, last_boot_announce)
            VALUES(?,?,NULL)
            ON CONFLICT(chat_id) DO UPDATE SET last_seen=excluded.last_seen
        """, (chat_id, now))
        async with db.execute("SELECT last_boot_announce FROM known_chats WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
        last_boot_announce = row[0] if row else None
        if last_boot_announce is None or last_boot_announce < BOOT_TS:
            try:
                await context.bot.send_message(chat_id=chat_id, text="✅ Petflix 2.0 - Human Edition ist jetzt online!", disable_notification=True)
            except Exception as e:
                log.error(f"Fehler bei Boot-Ansage an {chat_id}: {e}")
            await db.execute("UPDATE known_chats SET last_boot_announce=? WHERE chat_id=?", (BOOT_TS, chat_id))
        await db.commit()

async def autoload_and_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or user.is_bot:
        return
    if not getattr(msg, "text", None) or msg.text.startswith("/"):
        return
    if getattr(msg, "forward_date", None):
        return

    await mark_chat_and_maybe_announce(context, chat.id)

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat.id, user.id, user.username or user.full_name or "")

        deducted = await apply_moraltax_if_needed(db, chat.id, user.id, msg.text)
        if deducted is not None:
            try:
                if deducted > 0:
                    await msg.reply_text(f"Du warst zu nett. −{deducted} Coins.")
                else:
                    await msg.reply_text("Nettigkeit erkannt – diesmal 0 Coins, weil du pleite bist. Beim nächsten Mal kassiere ich 😈")
            except Exception:
                pass

        if MESSAGE_THROTTLE_S > 0:
            left = await get_cd_left(db, chat.id, user.id, "msgcoin")
            if left > 0:
                await db.commit()
                return

        await db.execute("UPDATE players SET coins = coins + ? WHERE chat_id = ? AND user_id = ?", (MESSAGE_REWARD, chat.id, user.id))
        if MESSAGE_THROTTLE_S > 0:
            await set_cd(db, chat.id, user.id, "msgcoin", MESSAGE_THROTTLE_S)
        await db.commit()

# =========================
# Preise, Balance, Top
# =========================
async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT username, user_id, price FROM players WHERE chat_id=? ORDER BY price DESC", (chat_id,)) as cur:
            rows = await cur.fetchall()
    if not rows:
        await update.effective_message.reply_text("Keine User gefunden.")
        return
    msg = "Preisliste aller User:\n"
    for username, uid, price in rows:
        uname = f"@{username}" if username else f"ID:{uid}"
        msg += f"{uname}: {price} Coins\n"
    await update.effective_message.reply_text(msg)

# =============== Admin: Coins steuern ===============
def _is_admin_here(update: Update) -> bool:
    return is_allowed_chat(update) and update.effective_user and update.effective_user.id == ADMIN_ID

async def _resolve_target(db, update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, (u.username or None)
    if not context.args:
        return None, None
    first = context.args[0].lstrip("@")
    if first.isdigit():
        return int(first), None
    chat_id = update.effective_chat.id
    async with db.execute("SELECT user_id FROM players WHERE chat_id=? AND username=?", (chat_id, first)) as cur:
        row = await cur.fetchone()
    if row:
        return int(row[0]), first
    return None, None

async def _ensure_player_entry(db, chat_id: int, user_id: int, username: str | None):
    await ensure_player(db, chat_id, user_id, username or "")

async def _get_coins(db, chat_id: int, user_id: int) -> int:
    async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0

def _parse_amount_from_args(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if context.args:
        try:
            return int(context.args[-1])
        except ValueError:
            return None
    return None

async def cmd_addcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nett versucht. Nur der Owner darf auszahlen.")
    amount = _parse_amount_from_args(context)
    if amount is None or amount <= 0:
        return await update.effective_message.reply_text("Nutzung: als Reply `/addcoins 50` oder `/addcoins @user 50`.", parse_mode="Markdown")
    async with aiosqlite.connect(DB) as db:
        tid, uname = await _resolve_target(db, update, context)
        if not tid:
            return await update.effective_message.reply_text("Ziel nicht gefunden. Antworte auf den User oder nutze @username bzw. user_id.")
        chat_id = update.effective_chat.id
        await _ensure_player_entry(db, chat_id, tid, uname)
        old = await _get_coins(db, chat_id, tid)
        new = old + amount
        await db.execute("UPDATE players SET coins=? WHERE chat_id=? AND user_id=?", (new, chat_id, tid))
        await db.commit()
    tag = f"@{uname}" if uname else f"ID:{tid}"
    await update.effective_message.reply_text(
        f"✅ {amount} Coins an {escape(tag, quote=False)} vergeben. Neuer Kontostand: {new}."
    )


async def cmd_takecoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nur der Owner darf abkassieren. Kapitalismus bleibt in der Familie.")
    amount = _parse_amount_from_args(context)
    if amount is None or amount <= 0:
        return await update.effective_message.reply_text("Nutzung: als Reply `/takecoins 50` oder `/takecoins @user 50`.", parse_mode="Markdown")
    async with aiosqlite.connect(DB) as db:
        tid, uname = await _resolve_target(db, update, context)
        if not tid:
            return await update.effective_message.reply_text("Ziel nicht gefunden.")
        chat_id = update.effective_chat.id
        await _ensure_player_entry(db, chat_id, tid, uname)
        old = await _get_coins(db, chat_id, tid)
        new = max(0, old - amount)
        await db.execute("UPDATE players SET coins=? WHERE chat_id=? AND user_id=?", (new, chat_id, tid))
        await db.commit()
    tag = f"@{uname}" if uname else f"ID:{tid}"
    await update.effective_message.reply_text(
        f"🧾 {amount} Coins bei {escape(tag, quote=False)} eingezogen. Neuer Kontostand: {new}."
    )

async def cmd_setcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nur der Owner darf den Kontostand setzen.")
    value = _parse_amount_from_args(context)
    if value is None or value < 0:
        return await update.effective_message.reply_text("Nutzung: als Reply `/setcoins 123` oder `/setcoins @user 123`.", parse_mode="Markdown")
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
        f"✏️ Kontostand von {escape(tag, quote=False)} auf {value} Coins gesetzt."
    )

async def cmd_resetcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
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
        f"🧨 Kontostand von {escape(tag, quote=False)} auf 0 gesetzt."
    )

async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CURRENT_MODE
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("🚫 Nur der Bot-Admin darf das.")
    if context.args:
        m = context.args[0].lower()
        if m in ("tame", "spicy"):
            CURRENT_MODE = m
            return await update.effective_message.reply_text(f"Modus auf {CURRENT_MODE} gestellt.")
    await update.effective_message.reply_text(f"Aktueller Modus: {CURRENT_MODE}")


# =========================
# Commands
# =========================
async def register_commands(application: Application):
    commands = [
        BotCommand("start", "Hilfe & Regeln"),
        BotCommand("ping", "Ping-Test (Antwort: pong)"),
        BotCommand("balance", "Zeigt deinen Coin-Kontostand"),
        BotCommand("buy", "Kaufe einen anderen User"),
        BotCommand("release", "Gib dein Haustier frei"),
        BotCommand("owner", "Zeigt den Besitzer eines Users"),
        BotCommand("ownerlist", "Zeigt alle Besitzverhältnisse + Wert"),
        BotCommand("prices", "Zeigt Kaufpreise aller User"),
        BotCommand("top", "Top 10 Spieler nach Coins"),

        # Pflege & Fun
        BotCommand("pet", "Streicheln"),
        BotCommand("walk", "Spazieren gehen"),
        BotCommand("kiss", "Küssen"),
        BotCommand("dine", "Dinner servieren"),
        BotCommand("massage", "Massage geben"),
        BotCommand("lapdance", "Lapdance"),

        # Skurril / BDSM
        BotCommand("knien", "Auf die Knie"),
        BotCommand("kriechen", "Auf allen Vieren kriechen"),
        BotCommand("klaps", "5 symbolische Hiebe"),
        BotCommand("knabbern", "Mit den Zähnen spielen"),
        BotCommand("leine", "Virtuelle Leine anlegen"),
        BotCommand("halsband", "Halsband anlegen"),
        BotCommand("lecken", "Dienst: lecken (teuer)"),
        BotCommand("verweigern", "Belohnung verweigern"),
        BotCommand("kaefig", "Ab in den Käfig"),
        BotCommand("schande", "Schande + Username"),
        BotCommand("erregen", "Anheizen bis zur Verzweiflung"),
        BotCommand("betteln", "Flehen & Winseln"),
        BotCommand("stumm", "Schweigepflicht (Posts kosten)"),
        BotCommand("bestrafen", "Strafe aus der Bot-Hölle"),
        BotCommand("loben", "Kleines Lob verteilen"),
        BotCommand("dienen", "Dienen (z. B. Fußmassage)"),
        BotCommand("demuetigen", "Peinlichen Satz posten"),
        BotCommand("melken", "Anzüglich melken"),
        BotCommand("ohrfeige", "Virtuelle Ohrfeige"),
        BotCommand("belohnen", "Leckerli geben"),

        # Special
        BotCommand("treasure", "Tägliche Schatzsuche starten")
    ]
    await application.bot.set_my_commands(commands)

# =========================
# Pflege-/Fun-Commands (benötigen do_care)
# =========================

async def cmd_pet(update, context):
    tame = [
        "{owner} streichelt {pet} so liebevoll, dass selbst der Kühlschrank eifersüchtig wird. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} krault {pet}… und alle denken: 'Was läuft da?'. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt {pet} sanfte Kopfmassagen. Der Chat errötet kollektiv. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} fährt mit den Fingern langsam über {pet}s Rücken – bis der Chat sich räuspert. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt {pet} an Stellen, wo Unschuld Urlaub macht. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt die Hände wandern… und {pet} lächelt verdächtig. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "pet", tame, spicy)

async def cmd_walk(update, context):
    tame = [
        "{owner} führt {pet} durchs Rotlichtviertel – rein aus… kulturellem Interesse. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nimmt {pet} mit auf einen Spaziergang. Drei Gassen später wissen beide zu viel. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} und {pet} gehen 'frische Luft schnappen'. Die Luft war nicht das Frischeste. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} spaziert mit {pet} Hand in Hand… und zwischendurch eher Lippen an Lippen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nimmt {pet} auf eine 'Runde' mit – zurück kommen beide mit verwuschelten Haaren. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} führt {pet} an der kurzen Leine durch dunkle Gassen. Kichern inklusive. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "walk", tame, spicy)

async def cmd_kiss(update, context):
    tame = [
        "{owner} drückt {pet} einen Kuss auf – so laut, dass die Nachbarn klatschen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} küsst {pet}, als gäbe es Bonuspunkte. Spoiler: gibt es. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} und {pet} tauschen Zuneigung aus, die selbst Emojis erröten lässt. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} küsst {pet} so lange, bis der Bot errötet. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert {pet} etwas zu… Sekunden später sind beide mit den Lippen beschäftigt. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} küsst {pet} so tief, dass der Chat nach Luft ringt. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kiss", tame, spicy)

async def cmd_dine(update, context):
    tame = [
        "{owner} füttert {pet} – Löffel für Löffel, Blick für Blick. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} serviert {pet} ein Dinner, das fast so heiß ist wie ihre Chats. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bringt {pet} Essen… und eine Portion zweideutige Kommentare. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} füttert {pet} langsam… und lässt den Löffel extra lange im Mund. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} serviert {pet} etwas, das auf der Zunge schmilzt – und nicht nur da. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reicht {pet} Häppchen zwischen langen Blicken. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dine", tame, spicy)

async def cmd_massage(update, context):
    tame = [
        "{owner} knetet {pet} die Schultern, bis alle Sorgen auswandern. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt {pet} eine Massage – professionell unprofessionell. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} massiert {pet} so gut, dass Netflix kurz pausiert. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner}s Hände erkunden {pet}… und finden jedes spannende Plätzchen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} massiert {pet} dort, wo normale Hände nicht hinfinden. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knetet {pet} langsam und genießt jede Reaktion. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "massage", tame, spicy)

async def cmd_lapdance(update, context):
    tame = [
        "{owner} schenkt {pet} einen Lap Dance – Stuhl knarzt, Moral auch. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} tanzt auf {pet}s Komfortzone. Standing Ovations von der inneren Stimme. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bewegt sich so, dass selbst der Bot den Takt mitklopft. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} liefert einen Lap Dance, bei dem sogar GIFs schwitzen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bewegt sich langsam… {pet} atmet schneller. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} tanzt wie ein Geheimnis, das man nie erzählen will. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lapdance", tame, spicy)

# =========================
# BDSM / Skurrile Pet-Commands (Deutsch)
# =========================
async def cmd_knien(update, context):
    tame = [
        "{pet} geht auf die Knie. {owner} nickt zufrieden. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hebt nur die Augenbraue – {pet} kniet. Pflege {n}/{CARES_PER_DAY}.",
        "Knie stauben ab, Ego auch ein bisschen. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} tippt mit dem Finger – {pet} kniet sofort. Blickkontakt verboten. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kniet vor {owner}. Haltung: perfekt, Stolz: weg. Pflege {n}/{CARES_PER_DAY}.",
        "Knie am Boden, Puls oben. {owner} lächelt dünn. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zwingt {pet} auf die Knie. Wo ist Platz? Knie nieder du Sklavensau! Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knien", tame, spicy)

async def cmd_kriechen(update, context):
    tame = [
        "{pet} kriecht ein Stück nach vorn. Der Chat schaut lieber weg. Pflege {n}/{CARES_PER_DAY}.",
        "Auf allen Vieren? {pet} seufzt, {owner} zählt. Pflege {n}/{CARES_PER_DAY}.",
        "Der Boden ist sauberer als {pet}s Ruf. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{pet} kriecht langsam zu {owner} und hält den Blick unten. Pflege {n}/{CARES_PER_DAY}.",
        "Jedes Kniegeräusch ein Geständnis. {owner} genießt. Pflege {n}/{CARES_PER_DAY}.",
        "Kriechen, anhalten, warten. {owner} entscheidet die nächsten Zentimeter. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht auf allen Vieren zu {owner} und zeigt den Arsch. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht zu {owner} und küsst die Füße. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kriechen", tame, spicy)

async def cmd_klaps(update, context):
    tame = [
        "{owner} klopft {pet} symbolisch auf den Hintern. Echo: peinlich. Pflege {n}/{CARES_PER_DAY}.",
        "Fünf sanfte Klapse. Der Chat nickt wertend. Pflege {n}/{CARES_PER_DAY}.",
        "Klaps, Klaps, Klaps… Würde bleibt gerade so. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} verteilt fünf deutliche Klapse. {pet} zählt mit zitternder Stimme. Pflege {n}/{CARES_PER_DAY}.",
        "Handabdruck inklusive. {pet} knurrt leise. Pflege {n}/{CARES_PER_DAY}.",
        "Jeder Klaps eine Erinnerung, wer hier entscheidet. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "klaps", tame, spicy)

async def cmd_knabbern(update, context):
    tame = [
        "{pet} darf vorsichtig knabbern. {owner} setzt Grenzen. Pflege {n}/{CARES_PER_DAY}.",
        "Kleines Knabbern, große Aufregung. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} kurz… dann Stopp. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{pet} knabbert frech – {owner}s Blick sagt: genau so. Pflege {n}/{CARES_PER_DAY}.",
        "Zähne spüren, Grenzen testen. {owner} entscheidet Tempo. Pflege {n}/{CARES_PER_DAY}.",
        "Knabbern, innehalten, Befehl abwarten. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knabbern", tame, spicy)

async def cmd_leine(update, context):
    tame = [
        "{owner} klickt die Leine ein. Spaziergang der Kontrolle. Pflege {n}/{CARES_PER_DAY}.",
        "Leine dran, Freiheit aus. {pet} folgt dicht. Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises Klicken – {pet} gehorcht. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} führt {pet} an kurzer Leine. Jede Bewegung ein Befehl. Pflege {n}/{CARES_PER_DAY}.",
        "Leine spannt, {pet} hält still. Die Regeln sind klar. Pflege {n}/{CARES_PER_DAY}.",
        "Zwei Schritte vor, Stopp. {owner} bestimmt den Takt. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "leine", tame, spicy)

async def cmd_halsband(update, context):
    tame = [
        "{owner} legt {pet} ein Halsband an. Passt erschreckend gut. Pflege {n}/{CARES_PER_DAY}.",
        "Klick. Besitzverhältnis sichtbar. Pflege {n}/{CARES_PER_DAY}.",
        "Halsband sitzt, Haltung besser. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Das Halsband schnappt zu. {pet} atmet ruhiger, {owner} lächelt. Pflege {n}/{CARES_PER_DAY}.",
        "Markiert und geführt. {pet} gehört sichtbar {owner}. Pflege {n}/{CARES_PER_DAY}.",
        "Das Etikett: 'brav'. Das Gefühl: abhängig. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "halsband", tame, spicy)

async def cmd_lecken(update, context):
    tame = [
        "{pet} leckt artig die Finger. {owner} prüft Sauberkeit. Pflege {n}/{CARES_PER_DAY}.",
        "Ein bisschen zu eifrig. {owner} hebt die Hand. Pflege {n}/{CARES_PER_DAY}.",
        "Dienst mit Zunge, Disziplin im Blick. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{pet} leckt langsam, wartet auf Anerkennung. Pflege {n}/{CARES_PER_DAY}.",
        "Zungenarbeit nach Vorschrift. {owner} gibt knappe Kommandos. Pflege {n}/{CARES_PER_DAY}.",
        "Tempo runter, Blick hoch. {owner} entscheidet, wann genug ist. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lecken", tame, spicy)

async def cmd_verweigern(update, context):
    tame = [
        "{owner} schiebt die Belohnung weg. 'Nicht heute.' Pflege {n}/{CARES_PER_DAY}.",
        "Tür zu. Erwartung bleibt draußen. Pflege {n}/{CARES_PER_DAY}.",
        "Verweigerung als Lektion. {pet} nickt… zähneknirschend. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Tease ohne Erlösung. {pet} beisst sich auf die Lippe. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert 'später' und meint 'gar nicht'. Pflege {n}/{CARES_PER_DAY}.",
        "Versprochen war nichts. Gehalten wurde alles. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "verweigern", tame, spicy)

async def cmd_kaefig(update, context):
    tame = [
        "{pet} in den Käfig. Kurze Pause von Entscheidungen. Pflege {n}/{CARES_PER_DAY}.",
        "Tür zu, Schlüssel klimpert. Ruhe kehrt ein. Pflege {n}/{CARES_PER_DAY}.",
        "Käfigzeit: Ordnung im Kopf. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Gitter klirren leise, {pet} atmet flach. {owner} prüft die Haltung. Pflege {n}/{CARES_PER_DAY}.",
        "Käfig ist klein, Lektion groß. Pflege {n}/{CARES_PER_DAY}.",
        "Schlüssel dreht, Augen senken. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kaefig", tame, spicy)

async def cmd_schande(update, context):
    tame = [
        "{owner} versieht {pet} mit einem 'Schand'-Tag. Der Chat merkt es sich. Pflege {n}/{CARES_PER_DAY}.",
        "Neues Label, gleiche Person: 'Heute unartig'. Pflege {n}/{CARES_PER_DAY}.",
        "Scham als Accessoire. Passt dir leider. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Öffentliche Schande. {pet} hält still, {owner} genießt die Röte. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Tag, ein Blick, ein Befehl: Kopf runter. Pflege {n}/{CARES_PER_DAY}.",
        "Schande sitzt fester als das Halsband. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "schande", tame, spicy)

async def cmd_erregen(update, context):
    tame = [
        "Anheizen ohne Finale. {pet} jault leise. Pflege {n}/{CARES_PER_DAY}.",
        "Kurz davor, lange warten. {owner} zählt Rückwärts. Pflege {n}/{CARES_PER_DAY}.",
        "Tease bis zur Vernunft. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "{owner} spielt mit Geduld und Nerven. {pet} bettelt stumm. Pflege {n}/{CARES_PER_DAY}.",
        "Randnah, niemals drüber. Das ist die Kunst. Pflege {n}/{CARES_PER_DAY}.",
        "Jeder Atemzug ein Verbot. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "erregen", tame, spicy)

async def cmd_betteln(update, context):
    tame = [
        "{pet} sagt bitte. {owner} sagt: noch nicht. Pflege {n}/{CARES_PER_DAY}.",
        "Betteln in ganzen Sätzen. Grammatik sitzt, Belohnung nicht. Pflege {n}/{CARES_PER_DAY}.",
        "Wimmern bringt Punkte. Manchmal. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Knie tiefer, Stimme leiser. Jetzt klingt es überzeugend. Pflege {n}/{CARES_PER_DAY}.",
        "Betteln mit Blicken. {owner} bleibt kalt. Pflege {n}/{CARES_PER_DAY}.",
        "Die Worte sind richtig, der Zeitpunkt nicht. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "betteln", tame, spicy)

async def cmd_stumm(update, context):
    tame = [
        "{owner} erhebt die Hand: Ruhe. {pet} schweigt. Pflege {n}/{CARES_PER_DAY}.",
        "Schweigeminute. Der Chat dankt. Pflege {n}/{CARES_PER_DAY}.",
        "Stille als Befehl. Funktioniert erstaunlich. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Stumm bedeutet stumm, halts Maul! Pflege {n}/{CARES_PER_DAY}.",
        "Worte verboten, nur Gehorsam! Pflege {n}/{CARES_PER_DAY}.",
        "Ruhe. {owner} hört gern das Zittern. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "stumm", tame, spicy)

async def cmd_bestrafen(update, context):
    tame = [
        "{owner} verhängt eine Strafe aus der milden Hölle. Pflege {n}/{CARES_PER_DAY}.",
        "Strafe mit Stil, nicht mit Wut. Pflege {n}/{CARES_PER_DAY}.",
        "Ordnung wiederhergestellt. Zähne zusammenbeißen. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Zufällige Strafe, gezielte Wirkung. {pet} nickt klein. Pflege {n}/{CARES_PER_DAY}.",
        "Weniger Jammern, mehr Lernen. Pflege {n}/{CARES_PER_DAY}.",
        "Strafe sitzt, Lektion bleibt. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "bestrafen", tame, spicy)

async def cmd_loben(update, context):
    tame = [
        "{owner} sagt: brav. Kurz, knapp, verdient. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lob wie ein Sonnenstrahl im Keller. Pflege {n}/{CARES_PER_DAY}.",
        "Gutes Timing, gute Haltung. Lob erteilt. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Knappes Lob flüstert über {pet}s Nacken. Gänsehaut inklusive. Pflege {n}/{CARES_PER_DAY}.",
        "Anerkennung als kleine Droge. Nicht überdosieren. Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises 'gut' – mehr braucht es nicht. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "loben", tame, spicy)

async def cmd_dienen(update, context):
    tame = [
        "{pet} dient {owner} mit Hingabe. To-do: alles. Pflege {n}/{CARES_PER_DAY}.",
        "Diener-Haltung sitzt. {owner} wirkt entspannter. Pflege {n}/{CARES_PER_DAY}.",
        "Service mit Haltung, kein Murren. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Dienen ohne Widerwort. {owner} entscheidet jeden Handgriff. Pflege {n}/{CARES_PER_DAY}.",
        "Auftrag, Ausführung, Augen runter. Pflege {n}/{CARES_PER_DAY}.",
        "Dienst an der Grenze zur Versuchung. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dienen", tame, spicy)

async def cmd_demuetigen(update, context):
    tame = [
        "Ein peinlicher Satz, sauber platziert. {pet} wird rot. Pflege {n}/{CARES_PER_DAY}.",
        "Demütigung light. Wirkung heavy. Pflege {n}/{CARES_PER_DAY}.",
        "Ein kleiner Stich ins Ego. Pädagogisch wertvoll. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Demütigung im richtigen Ton. {pet} nickt… und lernt. Pflege {n}/{CARES_PER_DAY}.",
        "Öffentlichkeit macht’s schärfer. {owner} dosiert. Pflege {n}/{CARES_PER_DAY}.",
        "Rang klären, Stolz falten. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "demuetigen", tame, spicy)

async def cmd_melken(update, context):
    tame = [
        "{owner} 'erntet' Ergebnistreue. {pet} erledigt den Rest. Pflege {n}/{CARES_PER_DAY}.",
        "Produktivität hat viele Formen. Heute diese. Pflege {n}/{CARES_PER_DAY}.",
        "Ergebnis wird pflichtbewusst abgeliefert. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Ruhig bleiben, atmen, liefern. {owner} zählt. Pflege {n}/{CARES_PER_DAY}.",
        "Ausdauertraining mit eindeutiger Bilanz. Pflege {n}/{CARES_PER_DAY}.",
        "Ziel erreicht. {owner} ist zufrieden, {pet} erschöpft. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "melken", tame, spicy)

async def cmd_ohrfeige(update, context):
    tame = [
        "Ein schneller Klapps ins Gesicht. Respekt wächst plötzlich. Pflege {n}/{CARES_PER_DAY}.",
        "{owner}s Hand trifft sanft, Wirkung sitzt. Pflege {n}/{CARES_PER_DAY}.",
        "Impuls, Blick, Ruhe. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Die Wange brennt, der Blick gehorcht. Pflege {n}/{CARES_PER_DAY}.",
        "Eine klare Linie, ein klares Signal. Pflege {n}/{CARES_PER_DAY}.",
        "Stille nach dem Schlag. Nur Gehorsam bleibt. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "ohrfeige", tame, spicy)

async def cmd_belohnen(update, context):
    tame = [
        "{owner} gibt {pet} ein Leckerli. Geschmack: Pflicht. Pflege {n}/{CARES_PER_DAY}.",
        "Belohnung klein, Wirkung groß. Pflege {n}/{CARES_PER_DAY}.",
        "Heute gibt’s was Nettes. Nicht einbilden. Pflege {n}/{CARES_PER_DAY}."
    ]
    spicy = [
        "Belohnung nach Regelbruch? Sicher nicht. Nach Gehorsam? Vielleicht. Pflege {n}/{CARES_PER_DAY}.",
        "Ein kaum verdientes Geschenk. {owner} bleibt streng. Pflege {n}/{CARES_PER_DAY}.",
        "Belohnung dosiert, Sehnsucht nicht. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "belohnen", tame, spicy)

# =========================
# Moralsteuer Commands
# =========================
async def cmd_moraltax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update) or not update.effective_user or update.effective_user.id != ADMIN_ID:
        return await update.effective_message.reply_text("🚫 Nur der Bot-Admin darf das hier.")
    chat_id = update.effective_chat.id
    arg = (context.args[0].lower() if context.args else "status")
    async with aiosqlite.connect(DB) as db:
        enabled, amount = await get_moraltax_settings(db, chat_id)
        if arg in ("on", "off"):
            val = 1 if arg == "on" else 0
            await db.execute("INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
            await db.execute("UPDATE settings SET moraltax_enabled=? WHERE chat_id=?", (val, chat_id))
            await db.commit()
            return await update.effective_message.reply_text(f"🧾 Moralische Steuer: {'AKTIV' if val else 'deaktiviert'} (aktueller Betrag: {amount} Coins).")
        if arg == "status":
            return await update.effective_message.reply_text(
                f"🧾 Moralische Steuer ist {'AKTIV' if enabled else 'deaktiviert'} – Betrag: {amount} Coins.\n"
                f"Nutze `/moraltax on|off` oder `/moraltaxset <betrag>`.",
                parse_mode="Markdown"
            )
        return await update.effective_message.reply_text("Nutzung: /moraltax on | off | status")

async def cmd_moraltaxset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not is_group(update): return
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Nutzung: /moraltaxset <betrag in coins>")
    amount = int(context.args[0])
    if amount < 0: amount = 0
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
        await db.execute("UPDATE settings SET moraltax_amount=? WHERE chat_id=?", (amount, chat_id))
        await db.commit()
    await update.effective_message.reply_text(f"Moralische Steuer gesetzt auf {amount} Coins. Nettigkeit hat jetzt Preisschild.")

# =========================
# Schatzsuche
# =========================
def _daily_treasure_amount(user_id: int, chat_id: int, day_ymd: str) -> int:
    seed = f"{user_id}:{chat_id}:{day_ymd}".encode("utf-8")
    h = hashlib.sha256(seed).hexdigest()
    return (int(h[:8], 16) % 50) + 1

_WORLD_PLACES = [
    "den Dünen der Sahara", "unter dem Eiffelturm", "im Central Park", "am Fuji",
    "im Amazonasdschungel", "unter der Golden-Gate-Bridge", "am Great Barrier Reef",
    "in der Atacama", "auf Island zwischen Geysiren", "an der Chinesischen Mauer",
    "in Venedig, zwischen zu teuren Gelati", "in der Wüste Gobi", "am Tafelberg",
    "in den Alpen, da wo keiner hinläuft", "bei den Pyramiden von Gizeh",
    "in Neuschwanstein, Touri-Falle inklusive", "am Nordkap", "in der Serengeti",
    "in Petra, Jordanien", "in Machu Picchu", "auf Santorini", "in Dubrovniks Gassen",
    "in Angkor Wat", "am Kilimandscharo", "am Bodensee, warum nicht",
    "auf den Lofoten", "in der Toskana", "am Grand Canyon", "in Barcelona, irgendwo zwischen Tapas",
    "in Seoul, im Nachtmarkt", "in Phuket am Strand", "in Kopenhagen am Nyhavn",
    "in Amsterdam, nein nicht da", "in Prag auf der Karlsbrücke",
]

_TREASURE_METHODS = {
    "graben": "gräbt wie ein Maulwurf",
    "buddeln": "buddeln wie ein Terrier",
    "tauchen": "taucht zwischen Korallen",
    "karte": "folgt einer mysteriösen Karte",
    "hacken": "hackt eine verrostete Truhe auf",
    "klauen": "stibitzt sie einem Piraten",
    "pendeln": "pendelt mit fragwürdiger Esoterik",
    "orakel": "befragt ein übermüdetes Orakel",
    "klettern": "klettert an einer bröseligen Klippe",
}

def _pick_method(args) -> str:
    if not args:
        return random.choice(list(_TREASURE_METHODS.values()))
    key = args[0].lower()
    return _TREASURE_METHODS.get(key, random.choice(list(_TREASURE_METHODS.values())))

_TREASURE_STORIES = [
    "{user} {method} bei {place} und zieht eine Truhe raus. Inhalt: {coins} Coins. Produktivität besiegt Reality-TV, knapp.",
    "{user} stolpert bei {place} über eine halb vergrabene Kiste. {coins} Coins später fühlt sich Faulheit plötzlich clever an.",
    "{user} folgt Spuren bis {place}, reißt die Truhe auf und findet {coins} Coins. Steuer frei, Moral fraglich.",
    "{user} wühlt bei {place} im Dreck und fischt {coins} Coins raus. Schatz 1, Realismus 0.",
    "{user} macht bei {place} kurz auf Pirat: Truhe auf, {coins} Coins raus, Würde wieder zu.",
]

async def cmd_treasure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    uid = user.id
    today = today_ymd()
    cd_key = f"treasure:{today}"

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, uid, user.username or user.full_name or "")
        left = await get_cd_left(db, chat_id, uid, cd_key)
        if left > 0:
            h = left // 3600
            m = (left % 3600) // 60
            return await update.effective_message.reply_text(f"Du hast heute schon gegraben. Wieder möglich in {h}h {m}m.")
        amount = _daily_treasure_amount(uid, chat_id, today)
        await db.execute("UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?", (amount, chat_id, uid))
        await set_cd(db, chat_id, uid, cd_key, _secs_until_tomorrow())
        await db.commit()

    place = random.choice(_WORLD_PLACES)
    method = _pick_method(context.args)
    story = random.choice(_TREASURE_STORIES).format(
        user=nice_name_html(user),  # HTML-sicher
        method=escape(method, quote=False),
        place=escape(place, quote=False),
        coins=amount
    )
    await update.effective_message.reply_text(story)

# =========================
# Kern-Spiel: Kaufen/Owner/Listen
# =========================
async def get_owner_id(db, chat_id: int, pet_id: int) -> Optional[int]:
    async with db.execute("SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None

async def set_owner(db, chat_id: int, pet_id: int, owner_id: Optional[int]):
    if owner_id is None:
        await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id))
    else:
        await db.execute("""
            INSERT INTO pets(chat_id, pet_id, owner_id) VALUES(?,?,?)
            ON CONFLICT(chat_id, pet_id) DO UPDATE SET owner_id=excluded.owner_id
        """, (chat_id, pet_id, owner_id))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        await update.effective_message.reply_text("❌ Dieses Spiel läuft nur in der vorgesehenen Gruppe.")
        return
    await update.effective_message.reply_text("✅ Petflix Starterpaket kommt gleich…")
    legende = (
        "🐾 <b>Willkommen bei Petflix – Deinem verruchten Haustier-Spiel</b> 🐾\n\n"
        "💋 <b>Klassische Pflege-Befehle</b>\n"
        "/pet, /walk, /kiss, /dine, /massage, /lapdance\n\n"
        "⛓️ <b>Skurril-BDSM</b>\n"
        "/knien, /kriechen, /klaps, /knabbern, /leine, /halsband, /lecken, /verweigern,\n"
        "/kaefig, /schande, /erregen, /betteln, /stumm, /bestrafen, /loben, /dienen,\n"
        "/demuetigen, /melken, /ohrfeige, /belohnen\n\n"
        "💰 <b>Tägliche Schatzsuche</b>\n"
        "/treasure [methode]\n\n"
        "⚙️ <b>Standard</b>\n"
        "/start, /balance, /buy, /owner, /ownerlist, /prices, /release, /top\n\n"
        "💸 <b>Coins</b>\n"
        "1 Coin pro Nachricht (1s Drosselung)."
    )
    try:
        for chunk in split_chunks(legende):
            await update.effective_message.reply_text(chunk, disable_web_page_preview=True)
    except Exception as e:
        await update.effective_message.reply_text(
            f"⚠️ Starttext-Fehler: <code>{type(e).__name__}</code> — {getattr(e, 'message', str(e))}",
            parse_mode=ParseMode.HTML
        )

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, uid)) as cur:
            row = await cur.fetchone()
    coins = row[0] if row else 0
    await update.effective_message.reply_text(f"Dein Kontostand: {coins} Coins.")

async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, uid, update.effective_user.username or update.effective_user.full_name or "")
        left = await get_cd_left(db, chat_id, uid, "daily")
        if left > 0:
            await db.commit()
            return await update.effective_message.reply_text(f"Daily wieder in {left // 60} Min.")
        await db.execute("UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?", (DAILY_COINS, chat_id, uid))
        await set_cd(db, chat_id, uid, "daily", DAILY_COOLDOWN_S)
        await db.commit()
    await update.effective_message.reply_text(f"+{DAILY_COINS} Coins Tagesbonus.")

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): 
        return
    chat_id = update.effective_chat.id
    buyer = update.effective_user
    buyer_id = buyer.id

    target_id = None
    target_username = None
    if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
        target = update.effective_message.reply_to_message.from_user
        target_id = target.id
        target_username = target.username
    elif context.args:
        target_username = context.args[0].lstrip("@")

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, buyer_id, buyer.username or buyer.full_name or "")

        if target_id is None:
            if not target_username:
                await update.effective_message.reply_text("Benutze /buy als Antwort auf die Nachricht der Person ODER /buy <username>.")
                return
            async with db.execute("SELECT user_id FROM players WHERE chat_id=? AND username=?", (chat_id, target_username)) as cur:
                row = await cur.fetchone()
            if not row:
                await update.effective_message.reply_text("User nicht gefunden oder noch nicht aktiv.")
                return
            target_id = row[0]

        if target_id == buyer_id:
            await update.effective_message.reply_text("Dich selbst kaufen? Entspann dich.")
            return

        if target_username is None and update.effective_message.reply_to_message:
            target_username = update.effective_message.reply_to_message.from_user.username
        await ensure_player(db, chat_id, target_id, target_username or "")

        price = await get_user_price(db, chat_id, target_id)
        prev_owner = await get_owner_id(db, chat_id, target_id)
        if prev_owner == buyer_id:
            await update.effective_message.reply_text("Du besitzt das Haustier bereits.")
            await db.commit()
            return

        async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, buyer_id)) as cur:
            row = await cur.fetchone()
        buyer_coins = row[0] if row else 0
        if buyer_coins < price:
            await update.effective_message.reply_text(f"Zu teuer. Preis: {price} Coins. Dein Guthaben: {buyer_coins}.")
            await db.commit()
            return

        # Zahl abziehen
        await db.execute("UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?", (price, chat_id, buyer_id))

        # KEIN Pay-out an Vorbesitzer (neue Regel: stehlen ohne Entschädigung)
        await set_owner(db, chat_id, target_id, buyer_id)

        new_price = price + USER_PRICE_STEP
        await set_user_price(db, chat_id, target_id, new_price)

        await db.commit()

    target_tag = f"@{target_username}" if target_username else f"ID:{target_id}"
    await update.effective_message.reply_text(
        f"{nice_name_html(buyer)} hat {escape(target_tag, quote=False)} für {price} Coins gekauft. Neuer Preis: {new_price}."
    )


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT username, user_id, coins FROM players WHERE chat_id=? ORDER BY coins DESC LIMIT 10", (chat_id,)) as cur:
            rows = await cur.fetchall()
    if not rows:
        await update.effective_message.reply_text("Noch keine Spieler.")
        return
    lines = []
    for i, (uname, uid, c) in enumerate(rows, start=1):
        raw_tag = f"@{uname}" if uname else f"ID:{uid}"
        tag = escape(raw_tag, quote=False)
        lines.append(f"{i}. {tag}: {c} 💰")

    text = "📋 Rangliste Top 10 Spieler:\n\n" + "\n".join(lines)
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await update.effective_message.reply_text(chunk, quote=False)


# Auto-Purge bei Austritt
async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if not cmu:
        return
    chat_id = cmu.chat.id
    if chat_id != ALLOWED_CHAT_ID:
        return
    old_status = getattr(cmu.old_chat_member, "status", None)
    new_status = getattr(cmu.new_chat_member, "status", None)
    user = cmu.new_chat_member.user
    leftish = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    still_in = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
    if (old_status in still_in or old_status is None) and (new_status in leftish):
        try:
            await purge_user_from_db(chat_id, user.id)
        except Exception as e:
            log.error(f"Purge für {user.id} scheiterte: {e}")
        else:
            bye = f"👋 {nice_name_html(user)} ist weg. Daten weg, Coins weg – Konsequenzen lernen ist auch ein Feature."

            try:
                await context.bot.send_message(chat_id=chat_id, text=bye)
            except Exception as e:
                log.error(f"Bye-Message für {user.id} scheiterte: {e}")
        log.info(f"Purged user {user.id} ({getattr(user, 'username', None)}) from chat {chat_id} due to leave/kick.")

async def purge_user_from_db(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM players  WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.execute("DELETE FROM pets     WHERE chat_id=? AND (pet_id=? OR owner_id=?)", (chat_id, user_id, user_id))
        await db.execute("DELETE FROM cooldowns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.commit()

async def cmd_purgeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nur der Owner darf löschen. Versuch niedlich, aber nein.")
    async with aiosqlite.connect(DB) as db:
        tid, uname = await _resolve_target(db, update, context)
    if not tid:
        return await update.effective_message.reply_text("Ziel nicht gefunden. Nutze Reply, @username oder user_id.")
    chat_id = update.effective_chat.id
    await purge_user_from_db(chat_id, tid)
    tag = f"@{uname}" if uname else f"ID:{tid}"
    await update.effective_message.reply_text(
        f"🗑️ {escape(tag, quote=False)} aus allen Petflix-Tabellen entfernt."
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("pong")

# =========================
# Besitzer-Abfragen & Listen
# =========================
async def cmd_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return

    chat_id = update.effective_chat.id

    # Ziel bestimmen: Reply > Argument > Self
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

        owner_uname = None
        if owner_id:
            async with db.execute(
                "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, owner_id)
            ) as cur:
                r2 = await cur.fetchone()
                owner_uname = r2[0] if r2 else None

    if owner_id:
        tag = f"@{owner_uname}" if owner_uname else f"[ID:{owner_id}](tg://user?id={owner_id})"
        await update.effective_message.reply_text(
            f"Besitzer: {tag}. Aktueller Preis: {price}.",
            parse_mode="Markdown"
        )
    else:
        await update.effective_message.reply_text(f"Kein Besitzer. Aktueller Preis: {price}.")

async def cmd_ownerlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt alle aktuellen Besitzverhältnisse mit aktuellem Wert des jeweiligen Pets."""
    if not is_group(update):
        return
    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        async with db.execute("""
            SELECT 
                p.pet_id,
                pu.username AS pet_username,
                p.owner_id,
                ou.username AS owner_username,
                pl.price AS current_price
            FROM pets p
            LEFT JOIN players pu ON pu.chat_id=p.chat_id AND pu.user_id=p.pet_id
            LEFT JOIN players ou ON ou.chat_id=p.chat_id AND ou.user_id=p.owner_id
            LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
            WHERE p.chat_id=?
            ORDER BY pl.price DESC, p.pet_id ASC
        """, (chat_id,)) as cur:
            rows = await cur.fetchall()

    if not rows:
        return await update.effective_message.reply_text("Noch keine Besitzverhältnisse. Kauf dir erstmal jemanden. 🐾")

    lines = ["📜 <b>Ownerliste</b> (wer gehört wem, inkl. aktuellem Wert):\n"]
    for pet_id, pet_uname, owner_id, owner_uname, price in rows:
        pet_tag = f"@{pet_uname}" if pet_uname else f"<a href='tg://user?id={pet_id}'>ID:{pet_id}</a>"
        owner_tag = f"@{owner_uname}" if owner_uname else (f"<a href='tg://user?id={owner_id}'>ID:{owner_id}</a>" if owner_id else "—")
        lines.append(f"• {pet_tag} → {owner_tag}  |  Wert: <b>{price}</b>")

    text = "\n".join(lines)
    for i in range(0, len(text), MAX_CHUNK):
        await update.effective_message.reply_text(text[i:i+MAX_CHUNK], disable_web_page_preview=True)

async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gibt dein aktuelles Haustier frei. Muss als Reply auf das Pet genutzt werden."""
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

# =========================
# Bot-Mitgliedschaftsänderungen
# =========================
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member and update.my_chat_member.chat:
        await mark_chat_and_maybe_announce(context, update.my_chat_member.chat.id)

# =========================
# Befehle in falschen Chats abfangen
# =========================
async def deny_other_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Dieses Spiel läuft nur in unserer Stammgruppe.",
            disable_notification=True
        )
    except Exception:
        pass

# Debug/Echo
async def echo_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        return
    msg = update.effective_message
    txt = getattr(msg, "text", None)
    if txt:
        log.info(f"[echo] {update.effective_user.id}: {txt[:60]}")

# =========================
# App-Setup / main()
# =========================
def main():
    asyncio.run(db_init())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .build()
    )

    # Telegram-Befehlsliste
    app.post_init = register_commands

    # Standard-Commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_start))  # Alias
    app.add_handler(CommandHandler("ping",     cmd_ping,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("balance",  cmd_balance,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler("daily",    cmd_daily,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("id",       cmd_id,       filters=CHAT_FILTER))

    # Kernspiel
    app.add_handler(CommandHandler("buy",       cmd_buy,       filters=CHAT_FILTER))
    app.add_handler(CommandHandler("owner",     cmd_owner,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("ownerlist", cmd_ownerlist, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("release",   cmd_release,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("prices",    cmd_prices,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("top",       cmd_top,       filters=CHAT_FILTER))

    # Schatzsuche
    app.add_handler(CommandHandler(["treasure", "hunt"], cmd_treasure, filters=CHAT_FILTER))

    # Moralsteuer
    app.add_handler(CommandHandler("moraltax",    cmd_moraltax,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("moraltaxset", cmd_moraltaxset, filters=CHAT_FILTER))

    # Pflege-/Fun-Commands
    app.add_handler(CommandHandler("pet",      cmd_pet,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("walk",     cmd_walk,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("kiss",     cmd_kiss,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("dine",     cmd_dine,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("massage",  cmd_massage,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler("lapdance", cmd_lapdance, filters=CHAT_FILTER))

    # Skurril/BDSM
    app.add_handler(CommandHandler("knien",      cmd_knien,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("kriechen",   cmd_kriechen,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("klaps",      cmd_klaps,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("knabbern",   cmd_knabbern,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("leine",      cmd_leine,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("halsband",   cmd_halsband,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("lecken",     cmd_lecken,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("verweigern", cmd_verweigern, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("kaefig",     cmd_kaefig,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("schande",    cmd_schande,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("erregen",    cmd_erregen,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("betteln",    cmd_betteln,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("stumm",      cmd_stumm,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("bestrafen",  cmd_bestrafen,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler("loben",      cmd_loben,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("dienen",     cmd_dienen,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("demuetigen", cmd_demuetigen, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("melken",     cmd_melken,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("ohrfeige",   cmd_ohrfeige,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("belohnen",   cmd_belohnen,   filters=CHAT_FILTER))

    # ADMIN: Coins steuern (die, die dir gefehlt haben)
    app.add_handler(CommandHandler("addcoins",   cmd_addcoins,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("takecoins",  cmd_takecoins,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler("setcoins",   cmd_setcoins,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("resetcoins", cmd_resetcoins, filters=CHAT_FILTER))

    # Admin: manuell purgen
    app.add_handler(CommandHandler("purgeuser", cmd_purgeuser,   filters=CHAT_FILTER))
    # Admin: tame oder spicy Modus wechseln
    app.add_handler(CommandHandler("mode",      cmd_mode,        filters=CHAT_FILTER))


    # Member-Events
    app.add_handler(ChatMemberHandler(on_chat_member,     ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_my_chat_member,  ChatMemberHandler.MY_CHAT_MEMBER))

    # Coins-Handler: nur erlaubte Gruppe, nur Text, keine Commands/Forwards
    app.add_handler(
        MessageHandler(
            filters.Chat(ALLOWED_CHAT_ID) & filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED,
            autoload_and_reward
        ),
        group=1
    )

    # Befehle in falschen Chats abfangen
    app.add_handler(
        MessageHandler(filters.COMMAND & ~filters.Chat(ALLOWED_CHAT_ID), deny_other_chats),
        group=0
    )

    # Tägliches Gift um 10:00 planen
    gift_time = dtime(hour=10, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_gift_job, time=gift_time, name="daily_gift_10am")

    log.info("Bot startet, warte auf Updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
