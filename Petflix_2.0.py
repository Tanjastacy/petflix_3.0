# Petflix 2.0 .py

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


from telegram import Update
from telegram.constants import ChatType, ChatMemberStatus
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "-1002550303601"))
DB = os.environ.get("DB_PATH", "petflix_2.0.db")


# =========================
# Konfiguration
# =========================
START_COINS = 0           # Jeder User startet mit 0 Coins
DAILY_COINS = 0
DAILY_COOLDOWN_S = 22 * 3600
MESSAGE_REWARD = 1      # Pro Nachricht gibt es 1 Coin
USER_BASE_PRICE = 100      # Kaufpreis für jeden User
USER_PRICE_STEP = 50     # Nach jedem Kauf steigt der Preis um 100 Coins
ADMIN_ID = 8172388048  # Deine Telegram User-ID
MESSAGE_THROTTLE_S = 1   # Zeit in Sekunden zwischen Nachrichten-Coins
CARE_COOLDOWN_S = 120   # 2 Minuten zwischen Pflegeaktionen pro Besitzer×Haustier
RUNAWAY_HOURS = 48
PETFLIX_TZ = os.environ.get("PETFLIX_TZ", "Europe/Berlin")  # Serverzeit, per Env änderbar
DAILY_GIFT_COINS = 15

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

# Boot-Timestamp, um nur EINMAL pro Neustart eine Startmeldung je Chat zu schicken
BOOT_TS = int(time.time())

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
log = logging.getLogger("Petflix_2.0")

# =========================
# DB-Setup 
# =========================

# === Migration helpers ===
SCHEMA_VERSION = 2  # erhöhe bei jedem Schema-Upgrade

async def _get_user_version(db) -> int:
    async with db.execute("PRAGMA user_version") as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0

async def _set_user_version(db, v: int):
    await db.execute(f"PRAGMA user_version={v}")

async def _table_has_column(db, table: str, col: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        cols = await cur.fetchall()
    return any(c[1] == col for c in cols)  # (cid, name, type, notnull, dflt_value, pk)

async def migrate_db(db):
    current = await _get_user_version(db)

    # v0 -> v1: (Beispiel) sicherstellen, dass alle Tabellen existieren
    if current < 1:
        # Deine bestehenden CREATEs sind idempotent:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS players(
          chat_id   INTEGER,
          user_id   INTEGER,
          username  TEXT,
          coins     INTEGER DEFAULT 0,
          price     INTEGER DEFAULT 50,
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
    
    # v1 -> v2: Moralische Steuer Spalten ergänzen
    if current < 2:
        if not await _table_has_column(db, "settings", "moraltax_enabled"):
            await db.execute("ALTER TABLE settings ADD COLUMN moraltax_enabled INTEGER DEFAULT 1")
        if not await _table_has_column(db, "settings", "moraltax_amount"):
            await db.execute("ALTER TABLE settings ADD COLUMN moraltax_amount INTEGER DEFAULT 5")
        await _set_user_version(db, 2)
        current = 2

async def db_init():
    async with aiosqlite.connect(DB) as db:
        # Pragmas
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        # Migrationen laufen IMMER, keine Drops!
        await migrate_db(db)

        await db.commit()


# Helpers (falls noch nicht vorhanden)

async def get_moraltax_settings(db, chat_id: int):
    async with db.execute("SELECT moraltax_enabled, moraltax_amount FROM settings WHERE chat_id=?", (chat_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        # Defaults anlegen
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
    """Zieht Coins ab, wenn 'zu nett'. Gibt abgezogene Höhe zurück oder None."""
    if not text or not is_too_nice(text):
        return None
    enabled, amount = await get_moraltax_settings(db, chat_id)
    if not enabled or amount <= 0:
        return None
    # aktuelles Guthaben holen
    async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    coins = row[0] if row else 0
    deduct = min(amount, max(coins, amount))  # wir lassen auch negatives Guthaben zu? Wenn nicht: min(amount, coins)
    # wenn du KEIN negatives Guthaben willst, nimm:
    deduct = min(amount, coins)
    if deduct <= 0:
        return 0
    await db.execute("UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?", (deduct, chat_id, user_id))
    await db.commit()
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

async def do_care(update, context, action_key, tame_lines, spicy_lines):
    if not is_group(update): return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    owner = update.effective_user
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        await msg.reply_text("Antworte auf dein Haustier mit diesem Befehl.")
        return
    pet = msg.reply_to_message.from_user
    if pet.id == owner.id:
        await msg.reply_text("Selbstpflege ist wichtig, aber zählt hier nicht.")
        return

    async with aiosqlite.connect(DB) as db:
        # gehört dir dieses Haustier?
        async with db.execute("SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id)) as cur:
            row = await cur.fetchone()
        if not row or row[0] != owner.id:
            await msg.reply_text("Das ist nicht dein Haustier.")
            return

        # runaway check
        care = await get_care(db, chat_id, pet.id)
        now = int(time.time())
        if care and care["last"] and now - care["last"] >= RUNAWAY_HOURS*3600:
            # läuft weg
            await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id))
            await db.commit()
            await msg.reply_text(f"{nice_name(pet)} hat die Leine durchgebissen. 48 Stunden ohne Pflege – und tschüss.")
            return

        # cooldown pro owner×pet
        cd_key = f"care:{action_key}:{owner.id}:{pet.id}"
        # Reuse deiner Cooldown-Funktionen
        left = await get_cd_left(db, chat_id, owner.id, cd_key)
        if left > 0:
            await msg.reply_text("Langsam, Casanova. Etwas Geduld.")
            return

        # Tageszähler
        today = today_ymd()
        if not care or care["day"] != today:
            done = 0
        else:
            done = care["done"]

        if done >= 2:
            await msg.reply_text("Heute ist das Haustier bereits bestens versorgt. Morgen wieder.")
            return

        done += 1
        await set_care(db, chat_id, pet.id, now, done, today)
        await set_cd(db, chat_id, owner.id, cd_key, CARE_COOLDOWN_S)
        await db.commit()

    # Textauswahl abhängig von NSFW
    spicy = False
    try:
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT nsfw FROM settings WHERE chat_id=?", (chat_id,)) as cur:
                srow = await cur.fetchone()
                spicy = bool(srow and srow[0])
    except:
        pass

    lines = spicy_lines if spicy else tame_lines
    text = random.choice(lines).format(owner=nice_name(owner), pet=nice_name(pet), n=done)
    await msg.reply_text(text)

async def cmd_carestatus(update, context):
    if not is_group(update):
        await update.effective_message.reply_text("Das läuft nur in der Gruppe, Süße/r. 😉")
        return

    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    async with aiosqlite.connect(DB) as db:
        # Hole den EINEN Pet-Eintrag, bei dem der User owner ist (wenn mehrere möglich, nimm irgendeinen)
        async with db.execute("""
            SELECT last_care_ts, care_done_today, day_ymd
            FROM pets
            WHERE chat_id=? AND owner_id=?
            LIMIT 1
        """, (chat_id, uid)) as cur:
            row = await cur.fetchone()

    if not row:
        await update.effective_message.reply_text(
            "Du besitzt nicht mal ein Haustier. Erst eins schnappen, dann pflegen. 😏"
        )
        return

    last_ts, care_done_today, day_ymd = row
    now = int(time.time())
    today = today_ymd()
    care_today = care_done_today if day_ymd == today else 0

    hours_since = (now - last_ts) // 3600 if last_ts else None

    if hours_since is None:
        comment = "Dein Haustier kennt dich nur vom Hörensagen."
    elif hours_since < 12:
        comment = "Dein Haustier ist aktuell ganz zufrieden – vielleicht zu sehr."
    elif hours_since < 24:
        comment = "Dein Haustier fängt an, dich komisch anzusehen. 😼"
    elif hours_since < 36:
        comment = "Dein Haustier packt schon heimlich seine Koffer."
    else:
        comment = "💔 Dein Haustier ist schon fast weg… es übt schon den Abgang."

    pflege_sprüche = [
        f"Du hast heute {care_today}/2 Pflegeaktionen gemacht. Ein bisschen mager, findest du nicht?",
        f"Heute {care_today} von 2 Pflegepunkten erledigt – das ist wie halber Sex: enttäuschend.",
        f"{care_today}/2 heute… immerhin kein Totalausfall, aber so wird das nix im Tierporno."
    ]

    await update.effective_message.reply_text(
        f"📊 Pflege-Status für dein Haustier:\n"
        f"Letzte Pflege: {'noch nie' if hours_since is None else str(hours_since) + 'h her'}\n"
        f"{random.choice(pflege_sprüche)}\n"
        f"{comment}"
    )

async def _pick_random_player(chat_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id, username FROM players WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return None, None
    return random.choice(rows)

def _mention_from_uid_username(user_id: int, username: str | None) -> str:
    # @name wenn vorhanden, sonst klickbare Mention per ID
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

    # Einmal-pro-Tag-Guard (falls der Bot rund um 10:00 rumzickt)
    async with aiosqlite.connect(DB) as db:
        left = await get_cd_left(db, chat_id, 0, cd_key)  # user_id=0 als Sentinel
        if left > 0:
            return  # heute schon erledigt

        uid, uname = await _pick_random_player(chat_id)
        if not uid:
            # trotzdem markieren, damit er nicht dauernd spammt, wenn noch keiner spielt
            await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
            await db.commit()
            return

        # Coins gutschreiben
        await db.execute(
            "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
            (DAILY_GIFT_COINS, chat_id, uid)
        )

        # Markieren bis Mitternacht
        await set_cd(db, chat_id, 0, cd_key, _secs_until_tomorrow())
        await db.commit()

    user_mention = _mention_from_uid_username(uid, uname)
    line = random.choice(_SAVAGE_LINES).format(
        user=user_mention, coins=DAILY_GIFT_COINS
    )

    # Markdown für tg://user Mention aktivieren
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎁 Tägliche Almosen-Time!\n{line}",
        parse_mode="Markdown"
    )


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
    await db.execute(
        "UPDATE players SET price=? WHERE chat_id=? AND user_id=?",
        (price, chat_id, user_id)
    )

async def ensure_player(db, chat_id: int, user_id: int, username: str):
    await db.execute(
        """
        INSERT INTO players(chat_id, user_id, username, coins, price)
        VALUES(?,?,?,?,?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET username=excluded.username
        """,
        (chat_id, user_id, username or "", START_COINS, USER_BASE_PRICE),
    )

async def echo_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update): return
    msg = update.effective_message
    txt = getattr(msg, "text", None)
    print(f"Nachricht empfangen: {txt}")

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
    

# =========================
# Schatzsuche: Helfer & Texte
# =========================

def _secs_until_tomorrow() -> int:
    now = datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).date()
    midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
    return max(1, int((midnight - now).total_seconds()))

def _daily_treasure_amount(user_id: int, chat_id: int, day_ymd: str) -> int:
    # deterministisch: 1..50, ändert sich täglich je User/Chat
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

# =========================
# Boot-Ansage: Chat-ID automatisch erkennen
# =========================
async def mark_chat_and_maybe_announce(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Merkt die Gruppe und sendet 'Bot online' genau 1x pro Neustart."""
    now = int(time.time())

    # ✅ Nur die erlaubte Gruppe merken
    if chat_id != ALLOWED_CHAT_ID:
        return

    async with aiosqlite.connect(DB) as db:
        # last_seen aktualisieren / Chat eintragen
        await db.execute(
            """
            INSERT INTO known_chats(chat_id, last_seen, last_boot_announce)
            VALUES(?,?,NULL)
            ON CONFLICT(chat_id) DO UPDATE SET last_seen=excluded.last_seen
            """,
            (chat_id, now),
        )

        # Prüfen, ob wir für diesen Boot schon announced haben
        async with db.execute(
            "SELECT last_boot_announce FROM known_chats WHERE chat_id=?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()

        last_boot_announce = row[0] if row else None
        if last_boot_announce is None or last_boot_announce < BOOT_TS:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Petflix 2.0 - Human Edition ist jetzt online!",
                    disable_notification=True   # nicht nervig pingen
                )
                log.info(f"Boot-Ansage gesendet in Chat {chat_id}")
            except Exception as e:
                log.error(f"Fehler bei Boot-Ansage an {chat_id}: {e}")

            await db.execute(
                "UPDATE known_chats SET last_boot_announce=? WHERE chat_id=?",
                (BOOT_TS, chat_id),
            )

        await db.commit()


# =========================
# Auto-Registrierung + Coins
# =========================
async def autoload_and_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur Super-/Gruppenchat + richtige Gruppe
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    # Harte Guards
    if not msg or not user or user.is_bot:
        return
    if not msg.text or msg.text.startswith("/"):
        return
    if getattr(msg, "forward_date", None):
        return

    # Boot-Ansage nur für erlaubten Chat
    await mark_chat_and_maybe_announce(context, chat.id)

    async with aiosqlite.connect(DB) as db:
        # Spieler einmalig registrieren (überschreibt NICHT coins)
        await ensure_player(db, chat.id, user.id, user.username or user.full_name or "")

        # Moralsteuer prüfen und ggf. abziehen
        deducted = await apply_moraltax_if_needed(db, chat.id, user.id, msg.text)
        if deducted:
            try:
                await msg.reply_text(f"Du hast gerade 'nett' gesagt. Minus {deducted} Coins für diese Schwäche.")
            except Exception:
                pass

        # Optional: Throttle pro User, damit Spammer nicht eskalieren
        if MESSAGE_THROTTLE_S > 0:
            left = await get_cd_left(db, chat.id, user.id, "msgcoin")
            if left > 0:
                await db.commit()
                return

        # Coin nur für den Absender, niemand sonst
        await db.execute(
            "UPDATE players SET coins = coins + ? WHERE chat_id = ? AND user_id = ?",
            (MESSAGE_REWARD, chat.id, user.id),
        )

        if MESSAGE_THROTTLE_S > 0:
            await set_cd(db, chat.id, user.id, "msgcoin", MESSAGE_THROTTLE_S)

        await db.commit()

# =========================
# Preise aller User im Chat abfragen
# =========================
async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT username, price FROM players WHERE chat_id=? ORDER BY price DESC", (chat_id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await update.effective_message.reply_text("Keine User gefunden.")
        return
    msg = "Preisliste aller User:\n"
    for username, price in rows:
        uname = f"@{username}" if username else "Unbekannt"
        msg += f"{uname}: {price} Coins\n"
    await update.effective_message.reply_text(msg)

# =============== Admin: Coins steuern ===============

def _is_admin_here(update: Update) -> bool:
    return is_allowed_chat(update) and update.effective_user and update.effective_user.id == ADMIN_ID

async def _resolve_target(db, update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # 1) Reply?
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, (u.username or None)

    # 2) Args?
    if not context.args:
        return None, None

    first = context.args[0].lstrip("@")

    # numerische ID
    if first.isdigit():
        return int(first), None

    # Username im aktuellen Chat auflösen
    chat_id = update.effective_chat.id
    async with db.execute(
        "SELECT user_id FROM players WHERE chat_id=? AND username=?",
        (chat_id, first)
    ) as cur:
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

def _parse_amount_from_args(context: ContextTypes.DEFAULT_TYPE, needs_two_args_when_no_reply: bool = True) -> int | None:
    # Reply: Wert ist args[0]; Ohne Reply: Wert ist letztes Argument
    if context.args:
        try:
            return int(context.args[-1])
        except ValueError:
            return None
    return None

async def cmd_addcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    """ /addcoins <@user|id> <amount>   oder als Reply: /addcoins <amount> """
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
    await update.effective_message.reply_text(f"✅ {amount} Coins an {tag} vergeben. Neuer Kontostand: {new}.")

async def cmd_takecoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    """ /takecoins <@user|id> <amount>   oder als Reply: /takecoins <amount> """
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
    await update.effective_message.reply_text(f"🧾 {amount} Coins bei {tag} eingezogen. Neuer Kontostand: {new}.")

async def cmd_setcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    """ /setcoins <@user|id> <value>   oder als Reply: /setcoins <value> """
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
    await update.effective_message.reply_text(f"✏️ Kontostand von {tag} auf {value} Coins gesetzt.")

async def cmd_resetcoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    """ /resetcoins <@user|id>   oder als Reply: /resetcoins """
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
    await update.effective_message.reply_text(f"🧨 Kontostand von {tag} auf 0 gesetzt.")


# =========================
# Commands
# =========================

# =========================
# moral steuer Command
# =========================

async def cmd_moraltax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not is_group(update): return
    chat_id = update.effective_chat.id
    if not context.args or context.args[0] not in ("on","off"):
        return await update.effective_message.reply_text("Nutzung: /moraltax on|off")
    val = 1 if context.args[0] == "on" else 0
    async with aiosqlite.connect(DB) as db:
        # ensure row
        await db.execute("INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
        await db.execute("UPDATE settings SET moraltax_enabled=? WHERE chat_id=?", (val, chat_id))
        await db.commit()
    await update.effective_message.reply_text(
        f"Moralische Steuer: {'aktiv' if val else 'deaktiviert'}. Zu nett sein bleibt eine Entscheidung, keine Tugend."
    )

async def cmd_moraltaxset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
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
    await update.effective_message.reply_text(
        f"Moralische Steuer gesetzt auf {amount} Coins. Nettigkeit hat jetzt Preisschild."
    )



# =========================
# Schatzsuche Command
# =========================
async def cmd_treasure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # nur in erlaubter Gruppe
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    uid = user.id
    today = today_ymd()
    cd_key = f"treasure:{today}"

    async with aiosqlite.connect(DB) as db:
        # Spieler anlegen falls neu
        await ensure_player(db, chat_id, uid, user.username or user.full_name or "")

        # Schon heute gesucht?
        left = await get_cd_left(db, chat_id, uid, cd_key)
        if left > 0:
            h = left // 3600
            m = (left % 3600) // 60
            return await update.effective_message.reply_text(
                f"Du hast heute schon gegraben. Wieder möglich in {h}h {m}m."
            )

        # Betrag deterministisch für heute
        amount = _daily_treasure_amount(uid, chat_id, today)

        # Coins gutschreiben
        await db.execute(
            "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
            (amount, chat_id, uid)
        )

        # Cooldown bis Mitternacht
        await set_cd(db, chat_id, uid, cd_key, _secs_until_tomorrow())
        await db.commit()

    place = random.choice(_WORLD_PLACES)
    method = _pick_method(context.args)
    story = random.choice(_TREASURE_STORIES).format(
        user=nice_name(user), method=method, place=place, coins=amount
    )
    await update.effective_message.reply_text(story)


# Pet Aktionen
# =========================

# === Pflegeaktionen ===

async def cmd_pet(update, context):
    tame = [
        "{owner} streichelt {pet} so liebevoll, dass selbst der Kühlschrank eifersüchtig wird. Pflege {n}/2.",
        "{owner} krault {pet}… und alle denken: 'Was läuft da?'. Pflege {n}/2.",
        "{owner} gibt {pet} sanfte Kopfmassagen. Der Chat errötet kollektiv. Pflege {n}/2."
    ]
    spicy = [
        "{owner} fährt mit den Fingern langsam über {pet}s Rücken – bis der Chat sich räuspert. Pflege {n}/2.",
        "{owner} streichelt {pet} an Stellen, wo Unschuld Urlaub macht. Pflege {n}/2.",
        "{owner} lässt die Hände wandern… und {pet} lächelt verdächtig. Pflege {n}/2."
    ]
    await do_care(update, context, "pet", tame, spicy)

async def cmd_walk(update, context):
    tame = [
        "{owner} führt {pet} durchs Rotlichtviertel – rein aus… kulturellem Interesse. Pflege {n}/2.",
        "{owner} nimmt {pet} mit auf einen Spaziergang. Drei Gassen später wissen beide zu viel. Pflege {n}/2.",
        "{owner} und {pet} gehen 'frische Luft schnappen'. Die Luft war nicht das Frischeste. Pflege {n}/2."
    ]
    spicy = [
        "{owner} spaziert mit {pet} Hand in Hand… und zwischendurch eher Lippen an Lippen. Pflege {n}/2.",
        "{owner} nimmt {pet} auf eine 'Runde' mit – zurück kommen beide mit verwuschelten Haaren. Pflege {n}/2.",
        "{owner} führt {pet} an der kurzen Leine durch dunkle Gassen. Kichern inklusive. Pflege {n}/2."
    ]
    await do_care(update, context, "walk", tame, spicy)

async def cmd_kiss(update, context):
    tame = [
        "{owner} drückt {pet} einen Kuss auf – so laut, dass die Nachbarn klatschen. Pflege {n}/2.",
        "{owner} küsst {pet}, als gäbe es Bonuspunkte. Spoiler: gibt es. Pflege {n}/2.",
        "{owner} und {pet} tauschen Zuneigung aus, die selbst Emojis erröten lässt. Pflege {n}/2."
    ]
    spicy = [
        "{owner} küsst {pet} so lange, bis der Bot errötet. Pflege {n}/2.",
        "{owner} flüstert {pet} etwas zu… Sekunden später sind beide mit den Lippen beschäftigt. Pflege {n}/2.",
        "{owner} küsst {pet} so tief, dass der Chat nach Luft ringt. Pflege {n}/2."
    ]
    await do_care(update, context, "kiss", tame, spicy)

async def cmd_dine(update, context):
    tame = [
        "{owner} füttert {pet} – Löffel für Löffel, Blick für Blick. Pflege {n}/2.",
        "{owner} serviert {pet} ein Dinner, das fast so heiß ist wie ihre Chats. Pflege {n}/2.",
        "{owner} bringt {pet} Essen… und eine Portion zweideutige Kommentare. Pflege {n}/2."
    ]
    spicy = [
        "{owner} füttert {pet} langsam… und lässt den Löffel extra lange im Mund. Pflege {n}/2.",
        "{owner} serviert {pet} etwas, das auf der Zunge schmilzt – und nicht nur da. Pflege {n}/2.",
        "{owner} reicht {pet} Häppchen zwischen langen Blicken. Pflege {n}/2."
    ]
    await do_care(update, context, "dine", tame, spicy)

async def cmd_massage(update, context):
    tame = [
        "{owner} knetet {pet} die Schultern, bis alle Sorgen auswandern. Pflege {n}/2.",
        "{owner} gibt {pet} eine Massage – professionell unprofessionell. Pflege {n}/2.",
        "{owner} massiert {pet} so gut, dass Netflix kurz pausiert. Pflege {n}/2."
    ]
    spicy = [
        "{owner}s Hände erkunden {pet}… und finden jedes spannende Plätzchen. Pflege {n}/2.",
        "{owner} massiert {pet} dort, wo normale Hände nicht hinfinden. Pflege {n}/2.",
        "{owner} knetet {pet} langsam und genießt jede Reaktion. Pflege {n}/2."
    ]
    await do_care(update, context, "massage", tame, spicy)

async def cmd_lapdance(update, context):
    tame = [
        "{owner} schenkt {pet} einen Lap Dance – Stuhl knarzt, Moral auch. Pflege {n}/2.",
        "{owner} tanzt auf {pet}s Komfortzone. Standing Ovations von der inneren Stimme. Pflege {n}/2.",
        "{owner} bewegt sich so, dass selbst der Bot den Takt mitklopft. Pflege {n}/2."
    ]
    spicy = [
        "{owner} liefert einen Lap Dance, bei dem sogar GIFs schwitzen. Pflege {n}/2.",
        "{owner} bewegt sich langsam… {pet} atmet schneller. Pflege {n}/2.",
        "{owner} tanzt wie ein Geheimnis, das man nie erzählen will. Pflege {n}/2."
    ]
    await do_care(update, context, "lapdance", tame, spicy)

# =========================


async def cmd_nsfw(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 Nur der Bot-Admin darf das.")
        return
    if not is_group(update): return
    chat_id = update.effective_chat.id
    if not context.args or context.args[0] not in ("on","off"):
        await update.effective_message.reply_text("Nutzung: /nsfw on|off")
        return
    val = 1 if context.args[0]=="on" else 0
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO settings(chat_id, nsfw) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET nsfw=excluded.nsfw", (chat_id, val))
        await db.commit()
    await update.effective_message.reply_text(f"NSFW-Modus: {'an' if val else 'aus'}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur in der erlaubten Gruppe
    if not is_allowed_chat(update):
        await update.effective_message.reply_text(
            "❌ Dieses Spiel läuft nur in einer speziellen Gruppe.",
            quote=False
        )
        return   # <<< WICHTIG! Stoppt hier, wenn Gruppe nicht erlaubt ist
    
    legende = """
🐾 **Willkommen bei Petflix – Deinem verruchten Haustier-Spiel** 🐾

💋 **Befehle & ihre Bedeutung**  
/pet – Dein Haustier streicheln (von süß bis „wo war deine Hand gerade?“)  
/walk – Mit deinem Haustier „spazieren gehen“… die Orte sind diskret.  
/kiss – Küssen, knutschen und den Chat in Verlegenheit bringen.  
/dine – Dein Haustier mit einem heißen Dinner verwöhnen.  
/massage – Massieren… manchmal an Stellen, die Google nicht zeigen darf.  
/lapdance – Du weißt, was das ist. Der Stuhl überlebt vielleicht.  

** Tägliche Schatzsuche: **
/treasure [methode] – Einmal täglich Schatzsuche 
Probiere mal: graben, tauchen, karte, hacken, klauen, pendeln, orakel, klettern.

📅 **Regeln**  
• Du musst dich **2x am Tag** um dein Haustier kümmern  
• Wenn du es **48 Stunden ignorierst**, läuft es weg (und zwar mit frechem Kommentar)  
• Pflege-Fortschritt: Jede Aktion zählt 1 von 2  

😏 **Tipp**  
Je würziger deine Aktion, desto mehr Spaß hat dein Haustier… und der Chat.

**Standard Befehle**

Hier sind alle Befehle:
• /start – Zeigt diese Hilfe
• /balance – Zeigt deinen aktuellen Kontostand
• /buy <username> oder als Antwort – Kaufe einen anderen User, wenn du genug Coins hast
• /prices – Zeigt die Kaufpreise aller User im Chat
• /owner <username> oder als Antwort – Zeigt den Besitzer eines Users
• /release als Antwort – Gib dein Haustier wieder frei
• /top – Top-10-Spieler nach Coins

Coins bekommst du für normale Nachrichten (1 Coin pro Nachricht, leicht gedrosselt 1sec.).
    """
    await update.effective_message.reply_text(legende, parse_mode="Markdown")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT coins FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, uid)
        ) as cur:
            row = await cur.fetchone()
    coins = row[0] if row else 0
    await update.effective_message.reply_text(f"Dein Kontostand: {coins} Coins.")

async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    async with aiosqlite.connect(DB) as db:
        # Spieler sicherstellen
        await ensure_player(db, chat_id, uid, update.effective_user.username or update.effective_user.full_name or "")
        left = await get_cd_left(db, chat_id, uid, "daily")
        if left > 0:
            await db.commit()
            return await update.effective_message.reply_text(f"Daily wieder in {left // 60} Min.")
        await db.execute(
            "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
            (DAILY_COINS, chat_id, uid)
        )
        await set_cd(db, chat_id, uid, "daily", DAILY_COOLDOWN_S)
        await db.commit()
    await update.effective_message.reply_text(f"+{DAILY_COINS} Coins Tagesbonus.")

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nützlich, wenn du die Chat-ID explizit sehen willst
    await update.effective_message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): 
        return
    chat_id = update.effective_chat.id
    buyer = update.effective_user
    buyer_id = buyer.id

    # Ziel aus Reply oder Argumenten ermitteln
    target_id = None
    target_username = None

    if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
        target = update.effective_message.reply_to_message.from_user
        target_id = target.id
        target_username = target.username
    elif context.args:
        target_username = context.args[0].lstrip("@")

    async with aiosqlite.connect(DB) as db:
        # Käufer sicherstellen
        await ensure_player(db, chat_id, buyer_id, buyer.username or buyer.full_name or "")

        if target_id is None:
            if not target_username:
                await update.effective_message.reply_text("Benutze /buy als Antwort auf die Nachricht der Person ODER /buy <username>.")
                return
            # Suche Ziel via Username
            async with db.execute(
                "SELECT user_id FROM players WHERE chat_id=? AND username=?",
                (chat_id, target_username)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await update.effective_message.reply_text("User nicht gefunden oder noch nicht aktiv.")
                return
            target_id = row[0]

        if target_id == buyer_id:
            await update.effective_message.reply_text("Dich selbst kaufen? Entspann dich.")
            return

        # Zielspieler sicherstellen (falls gerade erster Kontakt)
        # username holen, falls Reply genutzt wurde
        if target_username is None and update.effective_message.reply_to_message:
            target_username = update.effective_message.reply_to_message.from_user.username
        await ensure_player(db, chat_id, target_id, target_username or "")

        # Preis lesen
        price = await get_user_price(db, chat_id, target_id)

        # Besitzer prüfen
        prev_owner = await get_owner_id(db, chat_id, target_id)
        if prev_owner == buyer_id:
            await update.effective_message.reply_text("Du besitzt das Haustier bereits.")
            await db.commit()
            return

        # Guthaben prüfen
        async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, buyer_id)) as cur:
            row = await cur.fetchone()
        buyer_coins = row[0] if row else 0
        if buyer_coins < price:
            await update.effective_message.reply_text(f"Zu teuer. Preis: {price} Coins. Dein Guthaben: {buyer_coins}.")
            await db.commit()
            return

        # Zahlen
        await db.execute("UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?", (price, chat_id, buyer_id))

        # Vorbesitzer auszahlen (optional: Steuer einbehalten)
        if prev_owner and prev_owner != buyer_id:
            payout = price  # oder z. B. price - price//10 für 10% Steuer
            await db.execute("UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?", (payout, chat_id, prev_owner))

        # Besitzer setzen und Preis erhöhen
        await set_owner(db, chat_id, target_id, buyer_id)
        new_price = price + USER_PRICE_STEP
        await set_user_price(db, chat_id, target_id, new_price)

        await db.commit()

    target_tag = f"@{target_username}" if target_username else f"ID:{target_id}"
    await update.effective_message.reply_text(
        f"{nice_name(buyer)} hat {target_tag} für {price} Coins gekauft. Neuer Preis: {new_price}."
    )

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur in erlaubter Gruppe
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT username, user_id, coins FROM players WHERE chat_id=? ORDER BY coins DESC LIMIT 10",
            (chat_id,)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await update.effective_message.reply_text("Noch keine Spieler.")
        return

    lines = []
    for i, (uname, uid, c) in enumerate(rows, start=1):
        tag = f"@{uname}" if uname else f"ID:{uid}"
        lines.append(f"{i}. {tag}: {c} 💰")

    # Telegram erlaubt max. ~4096 Zeichen pro Nachricht → ggf. splitten
    text = "📋 Rangliste Top 10 Spieler:\n\n" + "\n".join(lines)
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await update.effective_message.reply_text(chunk, quote=False)

# =========================
# Auto-Purge bei Austritt
# =========================
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

    # robust: alles was nicht mehr "drin" ist, zählt als raus
    leftish = {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED
    }
    still_in = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR
    }

    # nur reagieren, wenn der Status wirklich von "drin" -> "draußen" wechselt
    if (old_status in still_in or old_status is None) and (new_status in leftish):
        try:
            await purge_user_from_db(chat_id, user.id)
        except Exception as e:
            log.error(f"Purge für {user.id} scheiterte: {e}")
        else:
            # bissige Abschiedsbotschaft
            bye = f"👋 {nice_name(user)} ist weg. Daten weg, Coins weg – Konsequenzen lernen ist auch ein Feature."
            try:
                await context.bot.send_message(chat_id=chat_id, text=bye)
            except Exception as e:
                log.error(f"Bye-Message für {user.id} scheiterte: {e}")

        log.info(f"Purged user {user.id} ({getattr(user, 'username', None)}) from chat {chat_id} due to leave/kick.")


# =========================
# User vollständig purgen
# =========================
async def purge_user_from_db(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB) as db:
        # Spieler-Datensatz
        await db.execute("DELETE FROM players  WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        # Besitz-Beziehungen (als Pet oder Owner)
        await db.execute("DELETE FROM pets     WHERE chat_id=? AND (pet_id=? OR owner_id=?)", (chat_id, user_id, user_id))
        # Cooldowns
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
    await update.effective_message.reply_text(f"🗑️ {tag} aus allen Petflix-Tabellen entfernt.")


# =========================
# Helferfunktionen für Besitz
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

# =========================
# Handlers für Mitgliedsstatus (falls Bot neu hinzugefügt wird)
# =========================
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Wenn der Bot in eine Gruppe hinzugefügt wird oder Rechte geändert werden,
    # markieren wir die Gruppe sofort und versuchen die Boot-Ansage.
    if update.my_chat_member and update.my_chat_member.chat:
        await mark_chat_and_maybe_announce(context, update.my_chat_member.chat.id)

async def cmd_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id

    # Ziel aus Reply oder arg
    target_id = None
    if update.effective_message.reply_to_message and update.effective_message.reply_to_message.from_user:
        target_id = update.effective_message.reply_to_message.from_user.id
    elif context.args:
        uname = context.args[0].lstrip("@")
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT user_id FROM players WHERE chat_id=? AND username=?", (chat_id, uname)) as cur:
                row = await cur.fetchone()
        if row: target_id = row[0]
    if target_id is None:
        target_id = update.effective_user.id

    async with aiosqlite.connect(DB) as db:
        owner = await get_owner_id(db, chat_id, target_id)
        price = await get_user_price(db, chat_id, target_id)
    if owner:
        await update.effective_message.reply_text(f"Besitzer von ID {target_id}: {owner}. Aktueller Preis: {price}.")
    else:
        await update.effective_message.reply_text(f"ID {target_id} hat keinen Besitzer. Preis: {price}.")

async def cmd_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
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
    await update.effective_message.reply_text("Freigelassen.")

def is_allowed_chat(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.id == ALLOWED_CHAT_ID

async def deny_other_chats(update, context):
    # Nicht zitieren, sonst 400er in Service-Events
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Dieses Spiel läuft nur in unserer Stammgruppe.",
            disable_notification=True
        )
    except Exception:
        pass  # im Zweifel einfach schweigen

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur in der erlaubten Gruppe
    if not is_allowed_chat(update):
        await update.effective_message.reply_text("Der Bot kann nur in der Hauptgruppe gestoppt werden.")
        return

    # Nur der ADMIN darf stoppen
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("🚫 Nur der Bot-Admin darf den Bot stoppen.")
        return

    await update.effective_message.reply_text("⛔ Bot wird gestoppt...")
    async def _shutdown():
        await asyncio.sleep(1)
        await context.application.stop()
        await context.application.shutdown()
        import os
        os._exit(0)
    asyncio.create_task(_shutdown())

# =========================
# App-Setup (final für PTB 20.7 + systemd)
# =========================

def main():
    # 1) DB einmalig initialisieren (async -> synchron ausführen)
    asyncio.run(db_init())

    # 2) Eigene Event-Loop setzen, damit run_polling() unter systemd nicht mault
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 3) Application bauen
    app = Application.builder().token(BOT_TOKEN).build()

    # 4) Handlers registrieren (JEDE Zeile genau einmal)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("owner", cmd_owner))
    app.add_handler(CommandHandler("release", cmd_release))
    app.add_handler(CommandHandler("prices", cmd_prices))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("carestatus", cmd_carestatus))
    app.add_handler(CommandHandler("nsfw", cmd_nsfw))
    app.add_handler(CommandHandler("stop", cmd_stop))
    
    # Schatzsuche (Alias /hunt optional)
    app.add_handler(CommandHandler(["treasure", "hunt"], cmd_treasure, filters=filters.Chat(ALLOWED_CHAT_ID)))

    # Moral steuer 
    app.add_handler(CommandHandler("moraltax", cmd_moraltax, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("moraltaxset", cmd_moraltaxset, filters=filters.Chat(ALLOWED_CHAT_ID)))

    # Pet Aktionen
    app.add_handler(CommandHandler("pet", cmd_pet, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("walk", cmd_walk, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("kiss", cmd_kiss, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("dine", cmd_dine, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("massage", cmd_massage, filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("lapdance", cmd_lapdance, filters=filters.Chat(ALLOWED_CHAT_ID)))

    # ADMIN Commands
    app.add_handler(CommandHandler("addcoins",   cmd_addcoins,   filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("takecoins",  cmd_takecoins,  filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("setcoins",   cmd_setcoins,   filters=filters.Chat(ALLOWED_CHAT_ID)))
    app.add_handler(CommandHandler("resetcoins", cmd_resetcoins, filters=filters.Chat(ALLOWED_CHAT_ID)))
    # Admin: manuell purgen
    app.add_handler(CommandHandler("purgeuser", cmd_purgeuser, filters=filters.Chat(ALLOWED_CHAT_ID)))
    # Auto-Purge bei Austritt
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))


    # Bot hinzugefügt/Rechte geändert → Boot-Ansage
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

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

    #  Daily Gift um 10:00 einplanen 
    gift_time = dtime(hour=10, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(
        daily_gift_job,
        time=gift_time,
        name="daily_gift_10am"
    )

    # Debug/Echo zuletzt
    app.add_handler(MessageHandler(filters.ALL, echo_all), group=2)

    log.info("Bot startet, warte auf Updates...")

    # 5) Der EINZIGE Lifecycle-Call in PTB 20.7
    app.run_polling()  # kein await, kein updater, kein start_polling/wait_closed

if __name__ == "__main__":
    main()