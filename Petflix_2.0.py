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
MESSAGE_REWARD = 5
USER_BASE_PRICE = 100
USER_PRICE_STEP = 50  # 100 -> 150 -> 200 ...
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MESSAGE_THROTTLE_S = 1
CARE_COOLDOWN_S = 5  # Sekunden zwischen Pflegeaktionen
CARES_PER_DAY = 25
RUNAWAY_HOURS = 48
LOCK_SECONDS = 0 * 3600  # 48h Mindestbesitz
PETFLIX_TZ = os.environ.get("PETFLIX_TZ", "Europe/Berlin")
DAILY_GIFT_COINS = 15

# =========================
# Fluch + Brandmarken
# =========================

AUTO_CURSE_ENABLED = True
AUTO_CURSE_CHANCE_PER_MESSAGE = 0.3  # 2% pro normaler Nachricht
AUTO_CURSE_COOLDOWN_S = 30 * 60       # 30 Minuten globaler Cooldown im Chat

FLUCH_LINES = [
    "{user} wird heute Nacht von Albträumen gefickt, bis die Seele kratzt. 🖤💀",
    "{user}s Fotze fault von innen, Maden kriechen raus und fressen den Rest deines wertlosen Lebens. 🩸🪰",
    "{user} erstickt langsam an eigenem Erbrochenem, während Geister deinen Hals zudrücken und in dein Ohr pissen. 💀🤮",
    "{user}s Augen platzen in der Nacht, Würmer fressen sich durch die Höhlen bis ins Hirn – endlich mal was drin. 👁️🧠",
    "{user} wird lebendig begraben, Erde fullt den Mund, und Ratten nagen an deiner Klitoris bis du kommst und stirbst. 🪦🐀",
    "{user}s Darm reißt auf, Scheiße mischt sich mit Blut, und du leckst es auf, weil du es verdienst, du Made. 💩🩸",
    "{user} verrottet bei lebendigem Leib, Haut fällt in Fetzen, und niemand hört dein Winseln, weil du eh nichts wert bist. 🖤🍖",
    "{user}s Kinder – falls du je welche zeugst – werden mit Messern geboren und schneiden dich von innen auf. 🔪🤰",
    "{user} wird von Dämonen geschändet, Schwänze mit Stacheln reißen dich auf, und du bettelst um mehr, du perverse Hure. 😈🩸",
    "{user}s Leiche wird gefickt von Nekrophilen, bis nur Knochen übrig sind – und selbst die spucken drauf. ⚰️🍆",
    "{user} stirbt allein, verfault unbeachtet, und selbst die Fliegen kotzen, wenn sie dich riechen. 🪰💀"
]

BRAND_LABEL = "🩸🔥"
BRAND_DURATION_S = 24 * 3600

# =========================
# /hass + /selbst
# =========================
HASS_DURATION_S = 0 * 3600
HASS_REQUIRED = 3
HASS_PENALTY = 200

SELF_LINES = [
    "{user} schlägt sich selbst 20 Mal hart ins Gesicht und filmt es: 'Das ist für jede Sekunde, die ich heute vergeudet habe, du nutzloses Stück.'",
    "{user} kniet 30 Minuten auf Reis oder Glasscherben und wiederholt laut: 'Ich bin nur ein wertloses Loch, das Schmerz verdient.'",
    "{user} zieht sich mit einer Gürtelschnalle 15 Striemen über den Arsch und sagt dabei: 'Jeder Treffer für meine Faulheit, danke, dass ich scheiße bin.'",
    "{user} hält eine brennende Kerze unter die eigene Brustwarze, bis die Haut blasen wirft: 'Das brennt für jede Lüge, die ich mir selbst erzählt habe.'",
    "{user} pisst in ein Glas, trinkt es langsam aus und flüstert: 'Meine eigene Pisse schmeckt besser als mein Leben.'",
    "{user} steckt sich eine Ingwerwurzel in den Arsch und lässt sie 20 Minuten brennen: 'Feuer im Loch für jede Ausrede heute.'",
    "{user} ritzt sich 'Versagerin' in den Oberschenkel und leckt das Blut ab: 'Schmeckt nach Wahrheit, du Made.'",
    "{user} würgt sich selbst mit einem Gürtel bis fast ohnmächtig und keucht: 'Atmen ist ein Privileg, das ich nicht verdiene.'",
    "{user} schlägt sich mit einem Lineal 50 Mal auf die Klitoris und zählt laut mit: 'Für jede Sekunde, die ich schwach war.'",
    "{user} isst eine rohe Zwiebel ohne zu blinzeln und schluchzt: 'Tränen sind das Einzige, was ich gut kann.'",
    "{user} klemmt sich Wäscheklammern an die Nippel und Labien, 45 Minuten lang: 'Schmerz ist die einzige Umarmung, die ich verdiene.'",
    "{user} schreibt 100 Mal mit Blut aus dem Finger: 'Ich bin ein wertloses Stück Scheiße' und liest es laut vor.",
    "{user} hält den Kopf unter eiskaltes Wasser, bis Panik kommt: 'Ertränke deine Schwäche, du erbärmliches Ding.'",
    "{user} beißt sich selbst in die Innenschenkel, bis blaue Flecken entstehen: 'Mein eigener Biss ist der einzige, den ich verdiene.'",
    "{user} masturbiert bis kurz vor dem Orgasmus und hört dann auf – 10 Mal hintereinander: 'Kommen darfst du erst, wenn du perfekt bist. Nie also.'",
    "{user} schlägt sich mit einem nassen Handtuch über den Rücken, bis Striemen glühen: 'Peitsche dich selbst, du faule Hure.'",
    "{user} steckt sich Nadeln unter die Fingernägel und flüstert: 'Jede Nadel für ein Versprechen, das ich gebrochen habe.'",
    "{user} leckt den Boden sauber, wo sie gerade gespuckt hat: 'Selbst dein Speichel ist zu gut für dich.'",
    "{user} zieht sich mit einer Zange an den Schamlippen, bis es reißt: 'Dehn dich selbst, du nutzloses Fickloch.'",
    "{user} hält eine Chilischote an die Klitoris, bis sie brennt wie Hölle: 'Feuer für jede Träne, die du nicht wert bist.'",
    "{user} schneidet sich eine Haarsträhne ab und verbrennt sie vor dem Spiegel: 'Du bist nicht mal dein Haar wert.'",
    "{user} drückt Zigaretten auf der Innenschenkelhaut aus (oder heißes Metall): 'Brandmarke für die Versagerin.'",
    "{user} kniet nackt vor dem Spiegel und ohrfeigt sich abwechselnd links und rechts: 'Sieh hin, wie hässlich Schwäche aussieht.'",
    "{user} trinkt eine Mischung aus Essig und Salz und würgt: 'Säure für dein wertloses Inneres.'",
    "{user} bindet sich die Brüste ab, bis sie blau werden: 'Ersticke deine nutzlosen Titten.'",
    "{user} steckt sich Eiswürfel in die Fotze und lässt sie schmelzen: 'Kälte für dein kaltes, leeres Herz.'",
    "{user} schreit 10 Minuten lang ins Kissen: 'Ich hasse mich' – bis die Stimme weg ist.",
    "{user} ritzt sich ein kleines Herz in die Handfläche und presst Salz rein: 'Liebe tut weh – besonders von dir selbst.'",
    "{user} zwingt sich, 50 Liegestütze zu machen – bei jedem Versagen 10 zusätzliche Ohrfeigen: 'Schwachkörper für schwachen Geist.'",
    "{user} filmt sich nackt beim Winseln: 'Bitte verachte mich, ich verdiene nichts anderes' – und speichert es für immer."
]


# Konfig Moralische Tax
MORAL_TAX_DEFAULT = 5
MORAL_TAX_TRIGGERS = [
    r"\bbitte\b",
    r"\bdanke\b",
    r"\bentschuldigung\b",
    r"\bsorry\b",
    r"\bkannst du\b",
    r"\bkönntest du\b",
    r"\bwärst du so lieb\b",
    r"\bthx\b",
    r"\bthank you\b",
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

SCHEMA_VERSION = 4

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
        CREATE TABLE IF NOT EXISTS settings(
          chat_id INTEGER PRIMARY KEY,
          moraltax_enabled INTEGER DEFAULT 1
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

    if current < 4:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS brandmarks(
          chat_id     INTEGER,
          user_id     INTEGER,
          label       TEXT,
          expires_ts  INTEGER,
          PRIMARY KEY(chat_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_brandmarks_expires ON brandmarks(chat_id, expires_ts);
        """)
        await _set_user_version(db, 4)
        current = 4

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

async def db_init():
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await migrate_db(db)
        await db.commit()

# Helpers

async def _get_active_hass_for_chat(db, chat_id: int):
    async with db.execute("""
        SELECT user_id, username, triggered_by, started_ts, expires_ts, required, done, penalty
        FROM hass_challenges
        WHERE chat_id=? AND active=1
        ORDER BY started_ts DESC
        LIMIT 1
    """, (chat_id,)) as cur:
        return await cur.fetchone()

async def _get_hass_for_user(db, chat_id: int, user_id: int):
    async with db.execute("""
        SELECT user_id, username, triggered_by, started_ts, expires_ts, required, done, penalty, active
        FROM hass_challenges
        WHERE chat_id=? AND user_id=?
        LIMIT 1
    """, (chat_id, user_id)) as cur:
        return await cur.fetchone()

async def _start_hass(db, chat_id: int, user_id: int, username: str | None, triggered_by: int):
    now = int(time.time())
    expires = now + HASS_DURATION_S
    await db.execute("""
        INSERT INTO hass_challenges(chat_id, user_id, username, triggered_by, started_ts, expires_ts, required, done, penalty, active)
        VALUES(?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
          username=excluded.username,
          triggered_by=excluded.triggered_by,
          started_ts=excluded.started_ts,
          expires_ts=excluded.expires_ts,
          required=excluded.required,
          done=0,
          penalty=excluded.penalty,
          active=1
    """, (chat_id, user_id, username or "", triggered_by, now, expires, HASS_REQUIRED, 0, HASS_PENALTY))
    return expires

async def _finish_hass(db, chat_id: int, user_id: int):
    await db.execute("UPDATE hass_challenges SET active=0 WHERE chat_id=? AND user_id=?", (chat_id, user_id))

async def _increment_selbst(db, chat_id: int, user_id: int):
    await db.execute("""
        UPDATE hass_challenges
        SET done = COALESCE(done,0) + 1
        WHERE chat_id=? AND user_id=? AND active=1
    """, (chat_id, user_id))
    async with db.execute("""
        SELECT done, required, expires_ts
        FROM hass_challenges
        WHERE chat_id=? AND user_id=? AND active=1
    """, (chat_id, user_id)) as cur:
        return await cur.fetchone()

async def _apply_hass_penalty(db, chat_id: int, user_id: int, penalty: int):
    # Spieler sicherstellen
    async with db.execute("SELECT username FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await ensure_player(db, chat_id, user_id, "")
    await db.execute("UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?", (penalty, chat_id, user_id))


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
            "INSERT INTO settings(chat_id, moraltax_enabled, moraltax_amount) VALUES(?,?,?) "
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

# 48h Mindestbesitz
async def get_pet_lock_until(db, chat_id: int, pet_id: int) -> int:
    async with db.execute(
        "SELECT COALESCE(purchase_lock_until,0) FROM pets WHERE chat_id=? AND pet_id=?",
        (chat_id, pet_id)
    ) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0

async def pick_random_player_excluding(chat_id: int, exclude_ids: set[int] | None = None):
    exclude_ids = exclude_ids or set()
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            rows = await cur.fetchall()
    rows = [r for r in rows if r and int(r[0]) not in exclude_ids]
    if not rows:
        return None, None
    return random.choice(rows)

def mention_html(user_id: int, username: str | None) -> str:
    return f"@{escape(username, quote=False)}" if username else f"<a href='tg://user?id={user_id}'>ID:{user_id}</a>"

async def set_brandmark(chat_id: int, user_id: int, label: str, duration_s: int):
    expires = int(time.time()) + duration_s
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            INSERT INTO brandmarks(chat_id, user_id, label, expires_ts)
            VALUES(?,?,?,?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
              label=excluded.label,
              expires_ts=excluded.expires_ts
        """, (chat_id, user_id, label, expires))
        await db.commit()
    return expires

async def get_active_brandmark(chat_id: int, user_id: int) -> str | None:
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        async with db.execute("""
            SELECT label, expires_ts FROM brandmarks
            WHERE chat_id=? AND user_id=?
        """, (chat_id, user_id)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        label, expires_ts = row[0], int(row[1] or 0)
        if expires_ts <= now:
            await db.execute("DELETE FROM brandmarks WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            await db.commit()
            return None
        return str(label)


# =========================
# Pflegeaktionen (gemeinsamer Handler)
# =========================
async def do_care(update, context, action_key, tame_lines):
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

    lines = tame_lines
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

# ==============================================================================
# hass watchdog
# ==============================================================================
async def hass_watchdog_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = ALLOWED_CHAT_ID
    now = int(time.time())

    async with aiosqlite.connect(DB) as db:
        async with db.execute("""
            SELECT user_id, username, expires_ts, required, done, penalty
            FROM hass_challenges
            WHERE chat_id=? AND active=1 AND expires_ts <= ?
        """, (chat_id, now)) as cur:
            rows = await cur.fetchall()

        if not rows:
            return

        for user_id, username, expires_ts, required, done, penalty in rows:
            user_id = int(user_id)
            required = int(required)
            done = int(done)
            penalty = int(penalty)

            if done < required:
                await _apply_hass_penalty(db, chat_id, user_id, penalty)
                msg = f"⌛ Hass-Deadline vorbei. {mention_html(user_id, username or None)} hat nur {done}/{required}. −{penalty} Coins."
            else:
                msg = f"✅ Hass-Check: {mention_html(user_id, username or None)} war rechtzeitig ({done}/{required})."

            await _finish_hass(db, chat_id, user_id)

            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass

        await db.commit()


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

# =========================
# Auto-Curse
# =========================
async def maybe_auto_curse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not AUTO_CURSE_ENABLED:
        return
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.effective_message
    if not msg or not getattr(msg, "text", None) or msg.text.startswith("/"):
        return

    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        left = await get_cd_left(db, chat_id, 0, "autocurse")
        if left > 0:
            return

        if random.random() > AUTO_CURSE_CHANCE_PER_MESSAGE:
            return

        uid, uname = await pick_random_player_excluding(chat_id, exclude_ids={update.effective_user.id})
        if not uid:
            return

        action = random.choice(["verfluchen", "brandmarken"])

        if action == "brandmarken":
            await set_brandmark(chat_id, uid, BRAND_LABEL, BRAND_DURATION_S)
            user = mention_html(uid, uname)
            label = await get_active_brandmark(chat_id, uid)
            if label:
                user = f"{user} <i>({escape(label, quote=False)})</i>"
            await context.bot.send_message(chat_id=chat_id, text=f"🔥 Brandmarke gesetzt: {user}", parse_mode=ParseMode.HTML)
        else:
            user = mention_html(uid, uname)
            label = await get_active_brandmark(chat_id, uid)
            if label:
                user = f"{user} <i>({escape(label, quote=False)})</i>"
            line = random.choice(FLUCH_LINES).format(user=user)
            await context.bot.send_message(chat_id=chat_id, text=line, parse_mode=ParseMode.HTML)

        await set_cd(db, chat_id, 0, "autocurse", AUTO_CURSE_COOLDOWN_S)
        await db.commit()

# =========================
# Auto-Registrierung + Coins
# =========================
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
    await maybe_auto_curse(update, context)

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
# verfluchen und brandmarken
# =========================

async def _resolve_target_user_for_fun(db, update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, (u.username or None)

    if context.args:
        first = context.args[0].lstrip("@")
        if first.isdigit():
            return int(first), None
        chat_id = update.effective_chat.id
        async with db.execute("SELECT user_id FROM players WHERE chat_id=? AND username=?", (chat_id, first)) as cur:
            row = await cur.fetchone()
        if row:
            return int(row[0]), first

    return None, None

async def cmd_verfluchen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        tid, tname = await _resolve_target_user_for_fun(db, update, context)
        if not tid:
            uid, uname = await pick_random_player_excluding(chat_id, exclude_ids={update.effective_user.id})
            if not uid:
                return await update.effective_message.reply_text("Keine Opfer verfügbar. Postet mehr, dann kann ich euch schlimmer behandeln.")
            tid, tname = uid, uname

    user = mention_html(tid, tname)
    label = await get_active_brandmark(chat_id, tid)
    if label:
        user = f"{user} <i>({escape(label, quote=False)})</i>"
    line = random.choice(FLUCH_LINES).format(user=user)
    await update.effective_message.reply_text(line, parse_mode=ParseMode.HTML)

async def cmd_brandmarken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        tid, tname = await _resolve_target_user_for_fun(db, update, context)
        if not tid:
            uid, uname = await pick_random_player_excluding(chat_id, exclude_ids={update.effective_user.id})
            if not uid:
                return await update.effective_message.reply_text("Keine Kandidaten zum Brandmarken gefunden.")
            tid, tname = uid, uname

    expires = await set_brandmark(chat_id, tid, BRAND_LABEL, BRAND_DURATION_S)
    user = mention_html(tid, tname)
    until = datetime.datetime.fromtimestamp(expires, tz=ZoneInfo(PETFLIX_TZ)).strftime("%d.%m.%Y %H:%M")
    await update.effective_message.reply_text(
        f"{user} trägt jetzt unsichtbar <b>{escape(BRAND_LABEL, quote=False)}</b> auf der Haut, bis <b>{until}</b>. 🔥",
        parse_mode=ParseMode.HTML
    )


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

# ==============Hass & Selbst

async def cmd_hass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("🚫 Admin-only. Du nicht. Setz dich wieder hin.")

    chat_id = update.effective_chat.id
    admin = update.effective_user

    async with aiosqlite.connect(DB) as db:
        # Nur eine aktive Hass-Runde gleichzeitig
        active = await _get_active_hass_for_chat(db, chat_id)
        if active:
            uid, uname, _, _, expires_ts, required, done, penalty = active
            left = max(0, int(expires_ts) - int(time.time()))
            h = left // 3600
            m = (left % 3600) // 60
            mention = mention_html(int(uid), uname if uname else None)
            return await update.effective_message.reply_text(
                f"⏳ Läuft schon: {mention} hat Hass-Status. ({done}/{required}) Noch {h}h {m}m. Strafe: −{penalty} Coins.",
                parse_mode=ParseMode.HTML
            )

        # Kandidaten: aus players, Admin ausgeschlossen
        uid, uname = await pick_random_player_excluding(chat_id, exclude_ids={admin.id})
        if not uid:
            return await update.effective_message.reply_text("Keine Kandidaten. Müssen halt Leute schreiben, bevor du sie quälen kannst.")

        expires = await _start_hass(db, chat_id, int(uid), uname, admin.id)
        await db.commit()

    until = datetime.datetime.fromtimestamp(expires, tz=ZoneInfo(PETFLIX_TZ)).strftime("%d.%m.%Y %H:%M")
    target = mention_html(int(uid), uname if uname else None)

    await update.effective_message.reply_text(
        f"🖤 <b>/hass</b> aktiviert.\n"
        f"Ziel: {target}\n"
        f"Regel: 2 Stunden Zeit, <b>{HASS_REQUIRED}× /selbst</b>.\n"
        f"Deadline: <b>{until}</b>\n"
        f"Wenn nicht geschafft: <b>−{HASS_PENALTY} Coins</b>.\n"
        f"Alles transparent, weil Demütigung ohne Publikum ja sinnlos wäre.",
        parse_mode=ParseMode.HTML
    )

async def cmd_selbst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    uid = user.id

    async with aiosqlite.connect(DB) as db:
        row = await _get_hass_for_user(db, chat_id, uid)
        if not row or int(row[8]) != 1:
            return await update.effective_message.reply_text("Nö. /selbst zählt nur, wenn du gerade Hass-Status hast.")

        _, uname, _, _, expires_ts, required, done, penalty, active = row
        now = int(time.time())

        # Falls abgelaufen, direkt kassieren (Job macht das auch, aber so ist es sofort transparent)
        if int(expires_ts) <= now:
            if int(done) < int(required):
                await _apply_hass_penalty(db, chat_id, uid, int(penalty))
                await _finish_hass(db, chat_id, uid)
                await db.commit()
                return await update.effective_message.reply_text(
                    f"⌛ Zeit um. {mention_html(uid, uname if uname else None)} hat’s nicht geschafft. −{penalty} Coins.",
                    parse_mode=ParseMode.HTML
                )
            await _finish_hass(db, chat_id, uid)
            await db.commit()
            return await update.effective_message.reply_text("Zu spät, aber du warst eh fertig. Challenge geschlossen.")

        # In Zeit: zählen
        inc = await _increment_selbst(db, chat_id, uid)
        await db.commit()

    # inc: (done, required, expires_ts)
    new_done, req, exp = int(inc[0]), int(inc[1]), int(inc[2])
    left = max(0, exp - int(time.time()))
    m = left // 60
    s = left % 60

    line = random.choice(SELF_LINES).format(user=mention_html(uid, user.username or None))
    await update.effective_message.reply_text(f"{line}\nFortschritt: <b>{new_done}/{req}</b>. Restzeit: {m}m {s}s.", parse_mode=ParseMode.HTML)

    if new_done >= req:
        async with aiosqlite.connect(DB) as db:
            await _finish_hass(db, chat_id, uid)
            await db.commit()
        await update.effective_message.reply_text(
            f"✅ {mention_html(uid, user.username or None)} hat’s geschafft. Hass-Status beendet. Widerlich effizient.",
            parse_mode=ParseMode.HTML
        )

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
        BotCommand("treasure", "Tägliche Schatzsuche starten"),

        #hass und selbst
        BotCommand("hass", "Admin-only: startet Hass-Status (2h, 3 mal /selbst)"),
        BotCommand("selbst", "Nur für betroffenen User: zählt 1/3 Strafen"),

    ]
    await application.bot.set_my_commands(commands)

# =========================
# Pflege-/Fun-Commands (benötigen do_care)
# =========================

async def cmd_pet(update, context):
    tame = [
        "{owner} gräbt die Finger brutal in {pet}s Haar, reißt den Kopf zurück und zwingt den Blickkontakt – nur um zu zeigen, wer hier atmet und wer nur darf. Pflege {n}/{CARES_PER_DAY}.",
        "Die Hand gleitet über {pet}s Rücken, Nägel ritzen rote Linien in die Haut – eine Karte des Besitzes, die morgen noch brennt.. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streicht langsam über {pet}s Kehle, drückt gerade so fest zu, dass die Panik aufsteigt – und lässt dann los. Gnade? Nur für heute. Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme:
        "{owner} vergräbt die Faust in {pet}s Haaren, reißt so hart, dass Büschel ausfallen – 'Schau mich an, während du merkst, wie wertlos du bist.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} spürt {owner}s Fingernägel, die tiefe Furchen in den Rücken reißen, Blut perlt – 'Das ist mein Autogramm auf deinem Kadaver.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} würgt {pet} bis die Augen hervortreten, lässt los und lacht: 'Noch am Leben? Wie enttäuschend.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} krault {pet} wie einen Hund, nur um dann die Klauen in die Kopfhaut zu schlagen – 'Gutes Tier... bis es blutet.' Pflege {n}/{CARES_PER_DAY}.",
        "Finger um den Hals, Druck steigend, bis {pet} kotzt vor Angst – 'Pflege bedeutet, ich entscheide, ob du erstickst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt die Wange – und schlägt dann zu: 'Zärtlichkeit? Nur der Einstieg ins Grab.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird am Nacken gepackt, Gesicht in den Schoß gedrückt – 'Atme meinen Geruch ein, das ist dein neuer Sauerstoff.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "pet", tame)

async def cmd_walk(update, context):
    tame = [
        "{owner} zerrt {pet} an der unsichtbaren Leine durch den Chat – jeder Schritt eine Erinnerung, dass Freiheit nur ein Wort ist, das {pet} vergessen hat. Pflege {n}/{CARES_PER_DAY}.",
        "Draußen an der frischen Luft, wo jeder sehen kann, wie {pet} mit gesenktem Kopf hinter {owner} hertrottet – ein gebrochenes Ding auf zwei Beinen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} führt {pet} langsam, lässt die Kette klirren, flüstert: 'Noch ein falscher Schritt und du kriechst den Rest des Weges.' Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme:
        "{owner} reißt an der imaginären Leine, {pet} stolpert und fällt hin – 'Steh auf, oder ich trete dich den Weg entlang.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird nackt durch die Straßen gezerrt, Blicke aller auf dem Arsch – 'Zeig ihnen, was für ein nutzloses Loch du bist.' Pflege {n}/{CARES_PER_DAY}.",
        "Jeder Ruck der Leine lässt {pet} würgen – 'Lauf schneller, Schlampe, oder ich schleif dich über Asphalt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} führt {pet} wie einen Köter, pisst markierend an Laternen – 'Dein Revier? Mein Urin drauf.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht schon nach fünf Schritten, Knie blutig – 'Guter Spaziergang, bis du nicht mehr laufen kannst.' Pflege {n}/{CARES_PER_DAY}.",
        "Die Leine straff, {pet} keucht: 'Noch ein Winseln, und ich lass dich von Fremden ficken.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} geht langsam, lässt {pet} hinterherrobben – 'Frische Luft? Nur für mich, du atme Staub.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "walk", tame)

async def cmd_kiss(update, context):
    tame = [
        "{owner} packt {pet} am Kiefer, zwingt die Lippen auseinander und nimmt sich den Kuss – tief, brutal, bis {pet} nach Luft ringt und Blut schmeckt. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss, der mehr Biss als Zärtlichkeit ist – {owner} beißt in die Unterlippe, bis {pet} wimmert und der metallische Geschmack von Tränen und Blut sich mischt. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} küsst {pet} nur, um zu beweisen, dass selbst Atem ein Geschenk ist – und nimmt ihn sich wieder, wenn er will. Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme:
        "{owner} beißt in die Zunge, reißt dran, Blut spritzt – 'Küss mich richtig, oder ich beiß sie ab.' Pflege {n}/{CARES_PER_DAY}.",
        "Mund aufgezwungen, {owner} spuckt rein und küsst dann zu – 'Schmeck mich in deinem Blut.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird erstickt geküsst, bis Bewusstlosigkeit droht – 'Romantik? Nur mit Toten.' Pflege {n}/{CARES_PER_DAY}.",
        "Zähne knirschen auf Lippen, bis sie platzen – 'Dein Kussgeschmack? Immer Blut.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} saugt an der Kehle, hinterlässt Würgemale – 'Kuss oder Erstickung, du entscheidest nicht.' Pflege {n}/{CARES_PER_DAY}.",
        "Brutaler Zungenfick, bis {pet} kotzt – 'Schluck's runter, das ist Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} küsst und schlägt gleichzeitig – 'Jede Zärtlichkeit mit Schmerz.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kiss", tame)

async def cmd_dine(update, context):
    tame = [
        "{owner} hält den Happen hoch, lässt {pet} darum betteln – erst wenn die Demütigung perfekt ist, darf die Zunge ran. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kniet, Mund offen, während {owner} langsam kaut und dann den Bissen direkt in den hungrigen Schlund spuckt – Mahlzeit, Liebling. Pflege {n}/{CARES_PER_DAY}.",
        "Heute gibt’s nur das, was von {owner}s Teller runterfällt – auf den Boden, wo {pet} es wie der Hund aufleckt, den es ist. Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – richtig dreckig:
        "{owner} kaut den Bissen, spuckt ihn halbzerkaut in {pet}s offenen Mund und drückt zu: 'Schluck meinen Speichel, oder du verhungerst.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} frisst aus {owner}s Hand wie ein Tier, beißt versehentlich zu – Strafe: der nächste Bissen kommt mit Asche gemischt. Pflege {n}/{CARES_PER_DAY}.",
        "Essen vom Boden, aber erst, nachdem {owner} draufgespuckt hat – 'Mein Speichel macht's nahrhafter, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} füttert {pet} mit Abfällen, lacht: 'Das ist alles, was ein wertloses Loch wie du verdient.' Pflege {n}/{CARES_PER_DAY}.",
        "Der Happen wird in {owner}s Arsch geschoben, {pet} muss ihn rausholen – mit dem Mund. 'Frisch aus der Quelle.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt stundenlang, bekommt nur {owner}s Pisse als Getränk – 'Heute proteinreich, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zertritt das Essen auf dem Boden, {pet} leckt es mit Dreck und Blut von den Sohlen – 'Bon appétit, du Made.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dine", tame)

async def cmd_massage(update, context):
    tame = [
        "{owner}s Hände kneten brutal in verspannte Muskeln, finden jeden Schmerzpunkt und drücken zu – bis {pet} vor Erleichterung und Qual gleichzeitig stöhnt. Pflege {n}/{CARES_PER_DAY}.",
        "Eine Massage, die blaue Flecken hinterlässt – {owner} gräbt Daumen in die Schultern, flüstert: 'Das ist der Preis für meine Berührung.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} liegt da, zitternd, während {owner} jeden Knoten löst – und neue schafft, tiefer, schärfer, bleibender. Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Schmerz pur:
        "{owner} drückt Daumen in alte Narben, reißt sie auf – 'Massage bedeutet, ich mach dich wieder ganz... kaputt.' Pflege {n}/{CARES_PER_DAY}.",
        "Knöchel graben sich in den Rücken, bis {pet} schreit – 'Entspann dich, oder ich brech dir was.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} massiert mit Fäusten, hinterlässt Nierenprellungen – 'Innere Organe brauchen auch Pflege.' Pflege {n}/{CARES_PER_DAY}.",
        "Ellbogen in die Rippen, langsam drehend – {pet} kotzt vor Schmerz, {owner} lacht: 'Besserer Durchblutung.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird mit heißem Öl übergossen, dann geknetet – Haut blättert ab. 'Peeling inklusive.' Pflege {n}/{CARES_PER_DAY}.",
        "Finger bohren in Triggerpunkte, bis {pet} ohnmächtig wird – 'Schlaf schön, ich mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} massiert den Hals, würgt zwischendurch – 'Das ist die ultimative Entspannung: fast tot.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "massage", tame)

async def cmd_lapdance(update, context):
    tame = [
        "{pet} windet sich auf {owner}s Schoß, Arsch hoch, Gesicht rot vor Scham – jede Bewegung nur, weil der Befehl es verlangt. Pflege {n}/{CARES_PER_DAY}.",
        "Langsam, quälend, Haut an Haut – {owner} hält die Hüften fest, steuert den Rhythmus, bis {pet} nass vor Verzweiflung und Lust ist. Pflege {n}/{CARES_PER_DAY}.",
        "Der Tanz endet nicht mit Applaus – sondern mit {owner}s Hand in {pet}s Haar, Kopf runtergedrückt: 'Nochmal. Und diesmal richtig.' Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – pure Geilheit und Demütigung:
        "{pet} tanzt nackt, {owner} schlägt bei jedem Fehltritt auf den Arsch – bis er blau und {pet} heult. Pflege {n}/{CARES_PER_DAY}.",
        "Hüften gepackt, brutal gerieben an {owner}s Schwanz – 'Mach mich hart, oder ich fick dich trocken.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss strippen während des Tanzes, jedes Kleidungsstück wird zerrissen – 'Nackt bist du eh am besten.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt in die Titten während {pet} reibt – Blut läuft runter. 'Dekoration für den Tanz.' Pflege {n}/{CARES_PER_DAY}.",
        "Der Lapdance endet mit {pet}s Gesicht im Schritt – 'Atme ein, das ist dein Applaus.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} tanzt mit Gewichten an den Nippeln, jede Bewegung Schmerz – 'Schwing sie schöner, Hure.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt den Tanz, droht mit Veröffentlichung – 'Dein Publikum wartet schon.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lapdance", tame)

# =========================
# BDSM / Skurrile Pet-Commands (Deutsch)
# =========================
async def cmd_knien(update, context):
    tame = [
        "{pet} sinkt langsam auf die Knie, der Boden kalt unter der Haut, während {owner}s Blick sagt: 'Hier gehörst du hin – für immer.' 🥀 Pflege {n}/{CARES_PER_DAY}.",
        "Knie hart auf Stein, Hände auf dem Rücken, Kopf gesenkt – {owner} tritt näher und flüstert: 'So sieht Unterwerfung aus, du wertloses Stück.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kniet zitternd, Tränen tropfen auf den Boden, weil {owner} nur zusieht und wartet, bis der Stolz endgültig bricht. 💧 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Knie kaputt, Seele tot:
        "{owner} tritt {pet} in die Kniekehlen, bis sie kracht und auf dem Boden aufschlägt – 'Runter, wo Müll hingehört.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kniet auf Reis oder Glasscherben, Blut sickert in den Boden – 'Jede Träne weniger wert als dein Schmerz.' Pflege {n}/{CARES_PER_DAY}.",
        "Stundenlang knien, Beine taub, {owner} pisst langsam über den Kopf – 'Taufe für eine neue Sklavin.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} drückt den Stiefelabsatz in {pet}s Oberschenkel, bis Fleisch platzt – 'Das ist dein neuer Thron.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kniet mit gespreizten Beinen, {owner} schlägt dazwischen – 'Betest du mich an? Dann zeig’s richtig.' Pflege {n}/{CARES_PER_DAY}.",
        "Kopf auf den Boden gedrückt, bis die Nase blutet – 'So tief, dass du deinen eigenen Dreck riechst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} knien, bis es ohnmächtig wird – 'Wach auf, die Hölle wartet nicht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knien", tame)

async def cmd_kriechen(update, context):
    tame = [
        "{pet} kriecht auf allen Vieren, Arsch hoch, Gesicht rot vor Scham – jeder Zentimeter eine Erinnerung daran, dass Laufen ein Privileg war. 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam über den Boden, Nägel kratzen, während {owner} die Leine straff hält: „Schneller, Hure, oder ich zieh dich an den Haaren.“ 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht bis zu {owner}s Füßen, leckt den Staub von den Schuhen – weil alles andere schon lange verboten ist. 👅 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Kriechen wie ein Wurm:
        "{pet} kriecht über Salz, offene Knie bluten – 'Jede Spur dein Abschied von Würde.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} tritt bei jedem zu langsamen Meter in den Arsch – 'Vorwärts, Made, oder ich zerquetsch dich.' Pflege {n}/{CARES_PER_DAY}.",
        "Kriechen mit Gewichten an den Nippeln, die über den Boden schleifen – 'Zieh deine Titten lang, das macht sie hübscher.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht durch {owner}s Pisse auf dem Boden – 'Schwimm, kleine Ratte.' Pflege {n}/{CARES_PER_DAY}.",
        "Leine am Halsband, {owner} reitet drauf – 'Mein Pony kriecht heute.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss rückwärts kriechen, Arsch zuerst – 'Zeig mir dein Loch, das ist dein neues Gesicht.' Pflege {n}/{CARES_PER_DAY}.",
        "Kriechen bis zur Erschöpfung, dann weiter – 'Tot kriechen kannst du immer noch.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kriechen", tame)

async def cmd_klaps(update, context):
    tame = [
        "{owner}s Hand kracht auf {pet}s Arsch, fünfmal, hart, bis die Haut glüht und die Schreie im Hals stecken bleiben. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Jeder Klaps eine Lektion: „Das fürs Reden. Das fürs Atmen. Das, weil ich es kann.“ {pet} zählt mit gebrochener Stimme. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "Der letzte Schlag lässt {pet} zusammenbrechen – {owner} lacht leise: „Nochmal, bis du endlich lernst, still zu sein.“ 💥 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Arsch in Fetzen:
        "{owner} schlägt mit dem Gürtel, bis Haut platzt und Blut spritzt – 'Zähl laut, oder ich fang von vorne an.' Pflege {n}/{CARES_PER_DAY}.",
        "Klapse auf die Fotze, bis sie anschwillt und {pet} bettelt – 'Das ist die einzige Klitoris-Massage, die du verdienst.' Pflege {n}/{CARES_PER_DAY}.",
        "Mit der flachen Hand auf die Nieren, bis {pet} kotzt – 'Innere Reinigung, gratis.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schlägt abwechselnd Arsch und Gesicht – 'Damit beide Seiten gleich rot werden.' Pflege {n}/{CARES_PER_DAY}.",
        "Heißes Wachs vorher, dann Klapse – Haut reißt ab. 'Peeling für Schlampen.' Pflege {n}/{CARES_PER_DAY}.",
        "Klapse mit einem Brett, bis Knochen vibrieren – 'Das hallt schön in deinem leeren Kopf.' Pflege {n}/{CARES_PER_DAY}.",
        "Nach 50 Klapsen muss {pet} danken – 'Und wehe, du lügst.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "klaps", tame)

async def cmd_knabbern(update, context):
    tame = [
        "{owner} beißt in {pet}s Schulter, hart genug für Blut, langsam genug für Panik – der Geschmack von Angst ist süß. 👅 Pflege {n}/{CARES_PER_DAY}.",
        "Zähne graben sich in die Brustwarze, ziehen, drehen – {pet} wimmert, aber Bewegung würde alles nur schlimmer machen. 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Biss in die Innenschenkel, nah genug, um zu drohen – {owner} flüstert: „Beim nächsten Mal tiefer.“ 😈 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – richtiges Fressen:
        "{owner} beißt ein Stück aus {pet}s Arschbacke, spuckt es nicht aus – 'Frühstück, direkt von der Quelle.' Pflege {n}/{CARES_PER_DAY}.",
        "Zähne in die Kehle, langsam zudrücken, Blut läuft – 'Ich probier mal, wie dein Puls schmeckt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} kaut an {pet}s Lippe, bis sie platzt, dann tiefer in die Zunge – 'Küss mich mit deinem eigenen Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
        "Biss in die Klitoris, ziehen, bis {pet} schreit – 'Die kleine Perle wird heute abgerissen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt sich durch die Haut am Bauch, leckt die Innereien – 'Ich wollte schon immer wissen, wie du von innen schmeckst.' Pflege {n}/{CARES_PER_DAY}.",
        "Zähne in die Achillessehne, reißen – 'Jetzt kannst du nie wieder weglaufen, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} kaut langsam an {pet}s Ohr, flüstert dabei: 'Van Gogh war Amateur.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knabbern", tame)

async def cmd_leine(update, context):
    tame = [
        "Die Leine klickt ein, straff um {pet}s Hals – ein Ruck, und die Welt wird klein auf {owner}s Schritte. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht brutal, {pet} stolpert hinterher, Atem knapp – „Du gehst nur, wenn ich es will, verstanden?“ 💀 Pflege {n}/{CARES_PER_DAY}.",
        "Die Leine liegt locker in {owner}s Hand – aber {pet} weiß: Ein Wort, und sie schnürt zu, bis alles schwarz wird. 🌑 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Erstickung pur:
        "{owner} wickelt die Leine zweimal um den Hals, zieht langsam zu – 'Atme, solange ich es erlaube.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Ruck, {pet} fällt auf die Knie, Gesicht blau – 'Schön, wie deine Augen hervortreten.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet die Leine an einen Haken, lässt {pet} auf Zehenspitzen hängen – 'Tanz für mich, bis du abschaltest.' Pflege {n}/{CARES_PER_DAY}.",
        "Leine straff durch die Fotze gezogen, dann am Hals – 'Jetzt steuerst du dich selbst, Hure.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht {pet} rückwärts, bis der Kehlkopf knackt – 'Musik in meinen Ohren.' Pflege {n}/{CARES_PER_DAY}.",
        "Die Leine wird mit Stacheldraht verstärkt – jeder Ruck reißt Fleisch – 'Dekoration für deinen Hals.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt los, nur um sofort wieder zuzuziehen – 'Herzstillstand-Training, kostenlos.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "leine", tame)

async def cmd_halsband(update, context):
    tame = [
        "Das Halsband schnappt zu, Metall kalt auf Haut – graviert mit {owner}s Namen, für immer. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht es enger, bis {pet} keucht: „Das ist dein neuer Schmuck, Schlampe. Und dein Grab.“ ⚰️ Pflege {n}/{CARES_PER_DAY}.",
        "Ringe klirren, wenn {pet} den Kopf bewegt – eine ständige Erinnerung, dass Freiheit nur ein Traum war. ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Markierung bis zum Tod:
        "{owner} schließt das Halsband mit einem Vorhängeschloss – Schlüssel runtergeschluckt. 'Für immer bedeutet für immer.' Pflege {n}/{CARES_PER_DAY}.",
        "Stacheln innen, jede Bewegung ritzt den Hals – 'Blutperlen als Schmuck.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht es so eng, dass {pet} nur noch flüstern kann – 'Deine Stimme gehört jetzt mir.' Pflege {n}/{CARES_PER_DAY}.",
        "Halsband mit integriertem Elektroschocker – {owner} drückt den Knopf: 'Guten Morgen, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "Graviert: 'Eigentum – bei Verlust töten' – {owner} lacht: 'Und ich verliere nie.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hängt Gewichte dran, Hals dehnt sich – 'Mach dich lang, wie eine gute Leiche.' Pflege {n}/{CARES_PER_DAY}.",
        "Das Halsband wird mit Kleber fixiert – 'Abnehmen? Nur mit deinem Kopf.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "halsband", tame)

async def cmd_lecken(update, context):
    tame = [
        "{pet} leckt {owner}s Stiefel sauber, Zunge schwarz vor Dreck – Demütigung schmeckt bitter und geil zugleich. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam über die Finger, dann höher – {owner} drückt den Kopf runter: „Tiefer, oder ich helf nach.“ 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die Tränen vom eigenen Gesicht, weil {owner} befiehlt: „Schmeck deine Niederlage.“ 🥀 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Zunge in Dreck und Blut:
        "{pet} leckt den Boden sauber, wo {owner} gerade reingepisst hat – 'Meine Pisse ist dein Heilwasser, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} tritt in Scheiße und hält den Stiefel hin – {pet} leckt alles ab, würgt, leckt weiter. 'Proteinreich heute.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt das Blut von {owner}s Messer, das gerade in ihr drin war – 'Schmeck dich selbst, das ist Recycling.' Pflege {n}/{CARES_PER_DAY}.",
        "Zunge tief in {owner}s Arsch, während er furzt – 'Atme ein, das ist dein neuer Duft.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die eigenen Wunden sauber, nachdem {owner} sie aufgerissen hat – 'Selbstbedienung, du faule Hure.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} spuckt in {pet}s offenen Mund und befiehlt: 'Schluck und leck dann meine Hand – doppelter Geschmack.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt den Käfigboden, wo es tagelang gelegen hat – 'Dein eigener Urin ist der beste Durstlöscher.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lecken", tame)

async def cmd_verweigern(update, context):
    tame = [
        "{owner} verweigert Berührung, Wasser, Worte – {pet} windet sich stundenlang, bettelt stumm um Gnade. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "Essen vor {pet}s Nase, aber der Mund bleibt leer – „Hunger ist die beste Dressur.“ 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Orgasmus verweigert, wieder und wieder – bis {pet} vor Verzweiflung heult und alles versprechen würde. 💔 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – psychischer Totalbruch:
        "{owner} lässt {pet} zuschauen, wie er eine andere fickt – Berührung nur für sie, {pet} bleibt leer und nass. Pflege {n}/{CARES_PER_DAY}.",
        "Wasserflasche vor der Nase, aber zugeschraubt – {pet} heult vor Durst, {owner} trinkt daraus und spuckt daneben. Pflege {n}/{CARES_PER_DAY}.",
        "Orgasmus bis an den Rand, dann Stopp – tagelang. {pet} bettelt um Erlösung oder Tod, bekommt keins. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} redet stundenlang mit {pet}, nur um dann tagelang komplett zu schweigen – 'Deine Existenz ist jetzt optional.' Pflege {n}/{CARES_PER_DAY}.",
        "Schlaf verweigert – Licht an, Geräusche, {pet} halluziniert nach drei Tagen. 'Träum wach, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zeigt {pet} Fotos von Freiheit, dann verbrennt sie – 'Erinnerungen sind auch nur Folter.' Pflege {n}/{CARES_PER_DAY}.",
        "Luft verweigert – Plastiktüte über den Kopf, bis Ohnmacht, dann wieder ab. 'Atmen ist ein Privileg.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "verweigern", tame)

async def cmd_kaefig(update, context):
    tame = [
        "{owner} schließt die Tür, {pet} kauert in der Ecke – Dunkelheit und Stille, nur das eigene Herz schlägt laut. 🌑 Pflege {n}/{CARES_PER_DAY}.",
        "Stunden im Käfig, nackt, zitternd – {owner} schaut nur zu: „Gute Tiere lernen schnell.“ 🐕 Pflege {n}/{CARES_PER_DAY}.",
        "Die Gitter werfen Schatten auf {pet}s Haut – ein Muster aus Gefangenschaft, das nie wieder weggeht. ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Enge, Dreck, Wahnsinn:
        "Käfig so klein, dass {pet} nur fetal liegen kann – eigene Scheiße unter sich, tagelang. 'Gemütlich, oder?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} stellt den Käfig in die pralle Sonne – {pet} brutzelt langsam, durstig, wahnsinnig. 'Bräunung inklusive.' Pflege {n}/{CARES_PER_DAY}.",
        "Ratten reingelassen nachts – {pet} schreit stumm, während sie an ihr knabbern. 'Neue Spielkameraden.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig im Keller, Wasser tropft ständig – {pet} wird wahnsinnig vom Geräusch, schläft nie. 'Wassertortur light.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} vergisst {pet} wochenlang – kommt zurück, findet ein gebrochenes Ding. 'Zeitreise erfolgreich.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig mit Stacheln innen – jede Bewegung blutig. 'Umarmung rundum.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt {pet} im Käfig und zeigt es Fremden – 'Dein neues Zuhause geht viral.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kaefig", tame)

async def cmd_schande(update, context):
    tame = [
        "{pet} steht nackt in der Ecke, Schande brennt heißer als jeder Schlag – alle dürfen zusehen. 👁️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzählt laut {pet}s Geheimnisse, lacht dabei – bis die Scham in den Knochen sitzt. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Schild um den Hals: „Gebrauchtes Eigentum“ – {pet} trägt es stolz, weil Stolz schon lange tot ist. 🪦 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – öffentliche Zerstörung:
        "{owner} filmt {pet} nackt mit dem Schild 'Billige Hure – gratis benutzen' und postet es online – 'Dein Ruhm ist jetzt ewig.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss vor Fremden masturbieren und dabei laut ihre perversesten Geheimnisse gestehen – 'Applaus gibt's erst, wenn du kommst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest alte Chatverläufe vor, lacht über jede peinliche Nachricht – {pet} wird rot bis in die Zehen, für immer. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Tattoo 'Nutzlose Fotze' frisch gestochen, {pet} muss es allen zeigen – 'Deine neue Visitenkarte.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zwingt {pet} Fotos von früher zu verbrennen – 'Dein altes Ich stirbt heute öffentlich.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} steht stundenlang nackt am Fenster, Nachbarn dürfen Fotos machen – 'Dein Viertel kennt dich jetzt besser.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzählt {pet}s Familie per Sprachnachricht die dreckigsten Details – 'Frohe Weihnachten von deiner Schlampe.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "schande", tame)

async def cmd_erregen(update, context):
    tame = [
        "{owner} berührt genau da, wo es wehtut und geil macht – bis {pet} hasst, wie sehr es will. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam, quälend, ohne Erlösung – {pet} bettelt um mehr, hasst sich dafür. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "Finger tief, Worte dreckig – {owner} flüstert: „Du kommst erst, wenn ich sage, dass du darfst. Vielleicht nie.“ ⏳ Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Hass und Sucht:
        "{owner} reibt die Klitoris roh, bis sie blutet und {pet} trotzdem bettelt – 'Schmerz ist dein neues Vorspiel.' Pflege {n}/{CARES_PER_DAY}.",
        "Finger mit Salz drin, tief in die wunde Fotze – {pet} schreit vor Lust und Qual gleichzeitig. 'Desinfektion für Schlampen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fickt {pet} mit der Faust, flüstert dabei 'Du bist nur ein Loch' – bis {pet} kommt und sich dafür hasst. Pflege {n}/{CARES_PER_DAY}.",
        "Nippel mit Klammern, Gewichte dran, während {owner} leckt – 'Jede Bewegung macht dich nasser, du perverse Sau.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} benutzt eine Bürste statt Finger – Borsten ritzen innen, {pet} kommt trotzdem explodiert. 'Putzen von innen.' Pflege {n}/{CARES_PER_DAY}.",
        "Elektroden an Klit und Nippeln, Stromstöße im Rhythmus – {pet} zuckt, kommt, hasst ihren Körper dafür. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} pisst auf die Fotze und reibt dann weiter – 'Meine Pisse macht dich glitschiger, Liebling.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "erregen", tame)

async def cmd_betteln(update, context):
    tame = [
        "{pet} bettelt auf Knien, Stimme bricht – {owner} hört nur zu und lächelt kalt. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "'Bitte, bitte, bitte' – wieder und wieder, bis die Worte nichts mehr bedeuten und nur noch Scham übrig ist. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Belohnung hoch, lässt {pet} darum winseln wie ein Tier – und nimmt sie dann weg. 🚫 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Betteln bis zur Zerstörung:
        "{pet} bettelt stundenlang um einen Orgasmus, {owner} filmt es – 'Dein neues Demütigungsvideo.' Pflege {n}/{CARES_PER_DAY}.",
        "Muss 'Ich bin eine wertlose Hure' 1000 Mal sagen, bevor vielleicht Gnade kommt – Stimme weg, Würde weg. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält ein Glas Wasser hoch, {pet} winselt durstig – dann gießt er es auf den Boden. 'Leck's auf.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt um Schmerz statt Lust – weil Lust verweigert wird. 'Schlag mich, bitte, ich halt's nicht aus.' Pflege {n}/{CARES_PER_DAY}.",
        "Betteln mit der Leine im Mund, sabbernd, tierisch – {owner} lacht nur. 'Noch lauter, Köter.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss um die Erlaubnis betteln, pissen zu dürfen – hält es stundenlang. 'Gute Blase, schlechte Sklavin.' Pflege {n}/{CARES_PER_DAY}.",
        "Letztes Betteln: um den Tod – {owner} verweigert sogar das. 'Du stirbst erst, wenn ich's sage.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "betteln", tame)

async def cmd_stumm(update, context):
    tame = [
        "{owner} befiehlt Schweigen – {pet} beißt sich auf die Lippe, bis Blut fließt, nur um nicht zu schreien. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Kein Wort, kein Stöhnen – nur der Blick sagt alles, während {owner} tut, was er will. 👁️ Pflege {n}/{CARES_PER_DAY}.",
        "Mund zugeklebt, Augen verbunden – Stille ist die schlimmste Strafe. 🌑 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – kein Laut, nur Leid:
        "{owner} näht {pet} den Mund mit grobem Faden zu – 'Jetzt bist du wirklich still, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "Knebel aus {owner}s getragener Unterhose, tief in den Rachen – {pet} würgt stumm, sabbert, erträgt. 'Atme meinen Geruch.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Hand fest auf {pet}s Mund, drückt die Nase zu – bis die Panik kommt und wieder geht. 'Schweigen oder sterben.' Pflege {n}/{CARES_PER_DAY}.",
        "Mund vollgepisst und dann zugeklebt – {pet} schluckt oder erstickt. 'Dein neues Getränk, leise genießen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bricht {pet} den Kiefer, damit kein Ton mehr rauskommt – 'Jetzt bist du perfekt leise.' Pflege {n}/{CARES_PER_DAY}.",
        "Stundenlang schreien dürfen – aber nur innerlich, während {owner} zusieht und lächelt. 'Deine Gedanken sind laut genug.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss stumm kommen, kein Stöhnen – bei jedem Laut fängt die Strafe von vorne an. 'Orgasmus in Stille oder gar nicht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "stumm", tame)

async def cmd_bestrafen(update, context):
    tame = [
        "{owner} wählt das Werkzeug – heute die Peitsche, morgen die Nadeln – {pet} zählt jeden Treffer mit. 💥 Pflege {n}/{CARES_PER_DAY}.",
        "Strafe ohne Grund, nur weil {owner} Lust hat – {pet} nimmt sie hin, weil Widerstand sinnlos ist. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Danach die Tränen lecken, die Wunden küssen – „Das ist Liebe, Liebling.“ 😈 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Schmerz mit Andenken:
        "{owner} brennt Initialen in {pet}s Arsch – 'Damit du immer weißt, wem du gehörst, wenn du sitzt.' Pflege {n}/{CARES_PER_DAY}.",
        "Nadeln unter die Fingernägel, langsam, eine nach der anderen – {pet} zählt mit zitternder Stimme. 'Maniküre der Hölle.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schneidet tiefe Linien in den Rücken – 'Deine neue Landkarte, nur für mich lesbar.' Pflege {n}/{CARES_PER_DAY}.",
        "Knochen brechen, langsam, mit Hammer – 'Das knackt so schön, findest du nicht?' Pflege {n}/{CARES_PER_DAY}.",
        "Säure auf die Nippel, tropfenweise – {pet} riecht ihr eigenes Fleisch verbrennen. 'Duftkerze aus Fotze.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt Fremde mitmachen – 'Heute ist Gruppenstrafe, du glückliches Stück.' Pflege {n}/{CARES_PER_DAY}.",
        "Danach muss {pet} die Werkzeuge sauber lecken – 'Blut ist der beste Dank.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "bestrafen", tame)

async def cmd_loben(update, context):
    tame = [
        "{owner} lobt leise: „Gutes Mädchen“ – und {pet} hasst, wie sehr es danach lechzt. 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Streicheln nach der Strafe – {pet} zittert vor Dankbarkeit, obwohl es kaputt ist. 💧 Pflege {n}/{CARES_PER_DAY}.",
        "„Du hast es gut gemacht“ – Worte süßer als Honig, giftiger als alles andere. 🥀 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Lob, das noch mehr kaputt macht:
        "{owner} flüstert 'Brave Schlampe' und {pet} kommt allein von den Worten – hasst sich sofort dafür. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss auf die frische Wunde – 'Du bist perfekt, wenn du blutest.' {pet} heult vor Dankbarkeit. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} sagt 'Ich bin stolz auf dich' – einmal im Jahr, und {pet} würde dafür sterben. Pflege {n}/{CARES_PER_DAY}.",
        "Streicheln über die Narben – 'Die hab ich für dich gemacht, und du trägst sie so schön.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen' geflüstert, während {owner} die nächste Strafe vorbereitet – 'Belohnung und Vorfreude zugleich.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt {pet} seinen Namen zu sagen – nur dieses eine Mal. {pet} weint vor Glück. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lächeln von {owner} – selten, tödlich süß. {pet} würde alles tun, um es nochmal zu sehen. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "loben", tame)

async def cmd_dienen(update, context):
    tame = [
        "{pet} dient auf Knien, bringt, holt, erträgt – alles, weil {owner} es befiehlt. ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        "Jede Aufgabe eine Demütigung – {pet} erledigt sie perfekt, weil Fehler teuer sind. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Am Ende des Tages: „Danke, dass ich dienen durfte“ – und {pet} meint es ernst.💔 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – totale Entmenschlichung:
        "{pet} dient als menschlicher Fußabtreter, Fremde wischen den Dreck an ihr ab – 'Willkommen, benutzt mich.' Pflege {n}/{CARES_PER_DAY}.",
        "Als Aschenbecher: {owner} drückt Zigaretten auf ihrer Zunge aus – {pet} sagt danach artig Danke. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} trägt den ganzen Tag ein Tablett mit {owner}s Getränk, Hände gefesselt – ein Tropfen verschüttet = Strafe. Pflege {n}/{CARES_PER_DAY}.",
        "Als Möbelstück: {owner} sitzt stundenlang auf ihrem Rücken – 'Beweg dich nicht, Tisch.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} putzt den Boden mit der Zunge, während {owner} zusieht und kommentiert – 'Gründlicher, du faule Sau.' Pflege {n}/{CARES_PER_DAY}.",
        "Als Toilettenpapier-Ersatz nach {owner}s Geschäft – 'Leck sauber, das ist dein neuer Job.' Pflege {n}/{CARES_PER_DAY}.",
        "Am Ende jedes Dienstes muss {pet} betteln, weiter dienen zu dürfen – 'Ohne dich bin ich nichts.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dienen", tame)

async def cmd_demuetigen(update, context):
    tame = [
        "{owner} demütigt laut vor allen – {pet} steht da, rot, nass, gebrochen. 👁️ {pet} wird rot. Pflege {n}/{CARES_PER_DAY}.",
        "Worte wie Messerstiche: „Du bist nichts ohne mich.“ {pet} nickt, weil es stimmt. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Die ultimative Demütigung: {pet} bedankt sich dafür. 😭 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Seele in Fetzen:
        "{owner} zwingt {pet} laut ihre größten Ängste und Versagen zu wiederholen – vor Fremden, bis sie heult. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss sich selbst als 'wertlose Spermaschlampe' vorstellen – bei jedem neuen Menschen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest {pet}s alte Liebesbriefe vor und lacht – 'Das hast du mal geglaubt? Süß.' Pflege {n}/{CARES_PER_DAY}.",
        "Öffentlich pissen lassen, während alle zusehen – {pet} bedankt sich danach für die Aufmerksamkeit. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nennt {pet} nur noch 'Es' oder 'Ding' – bis {pet} vergisst, dass sie je einen Namen hatte. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss Fremden erzählen, wie oft sie schon gekommen ist heute – und lügen darf sie nicht. Pflege {n}/{CARES_PER_DAY}.",
        "Ultimative Worte: 'Du bist mein größter Fehler – und ich behalte dich trotzdem.' {pet} weint vor Dankbarkeit. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "demuetigen", tame)

async def cmd_melken(update, context):
    tame = [
        "{owner} melkt {pet} langsam, gnadenlos – bis nichts mehr kommt und die Scham überfließt. 💧 Pflege {n}/{CARES_PER_DAY}.",
        "Hände fest, Rhythmus brutal – {pet} wimmert, hasst, kommt trotzdem. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Danach leer, zittern, gedemütigt – {owner} wischt ab: „Gute Kuh.“ 🐄 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Viehbehandlung deluxe:
        "{owner} melkt {pet} in einen Eimer, zwingt sie danach alles auszutrinken – 'Recycling, du geile Sau.' Pflege {n}/{CARES_PER_DAY}.",
        "Mit Melkmaschine, Saugnäpfe brutal – {pet} schreit, kommt mehrmals, hasst ihren Körper. Pflege {n}/{CARES_PER_DAY}.",
        "Öffentlich gemolken, Fremde dürfen zugucken – 'Zeig ihnen, wie nützlich du bist.' Pflege {n}/{CARES_PER_DAY}.",
        "Nippel mit Nadeln vorgedehnt, dann gemolken bis Blut mitmischt – 'Proteinshake spezial.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt sie trocken, bis sie bettelt aufzuhören – und melkt dann weiter. Pflege {n}/{CARES_PER_DAY}.",
        "Danach angeleint wie eine Kuh, Euter geschwollen – 'Morgen wieder, Liebling.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss 'Muh' machen bei jedem Orgasmus – {owner} lacht und melkt härter. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "melken", tame)

async def cmd_ohrfeige(update, context):
    tame = [
        "Die Ohrfeige kommt schnell, lässt {pet}s Kopf zur Seite fliegen – Wangen glühen, Stolz tot. 🩸 Pflege {n}/{CARES_PER_DAY}.",
        "Links, rechts, wieder links – bis {pet} nicht mehr weiß, wo oben ist. 😵 Pflege {n}/{CARES_PER_DAY}.",
        "Die letzte lässt Tränen fließen – {owner} lächelt: „Jetzt bist du schön.“ 🥀 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Gesicht in Trümmern:
        "{owner} schlägt mit der flachen Hand, dann mit der Faust – {pet}s Lippe platzt, Blut läuft übers Kinn. 'Schmink dich mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
        "Ohrfeigen mit Ring am Finger, tiefe Schnitte in die Wange – 'Mein Autogramm, damit jeder sieht, wem du gehörst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt {pet} vor dem Spiegel, zwingt sie hinzuschauen – 'Sieh zu, wie dein hübsches Gesicht kaputtgeht.' Pflege {n}/{CARES_PER_DAY}.",
        "So hart, dass {pet} zu Boden geht – {owner} tritt nach: 'Steh auf, die zweite Runde kommt.' Pflege {n}/{CARES_PER_DAY}.",
        "Mit Handschuhen voller Splitt – Haut reißt auf, {pet} schmeckt eigenes Blut. 'Peeling für Schlampen.' Pflege {n}/{CARES_PER_DAY}.",
        "Letzte Serie, bis das Auge zuschwillt – {owner} flüstert: 'Jetzt bist du wirklich nur noch ein Loch mit Gesicht.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss nach jeder Ohrfeige 'Danke' sagen – mit geschwollener Zunge klingt es perfekt erbärmlich. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "ohrfeige", tame)

async def cmd_belohnen(update, context):
    tame = [
        "Die Belohnung ist Berührung – kurz, intensiv, nie genug. {pet} bettelt um mehr. 👅 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt einen Orgasmus – nach Tagen der Verweigerung. {pet} zerbricht vor Dankbarkeit. 💔 Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises „Gut gemacht“ – und {pet} würde alles tun, um es nochmal zu hören. 😈 Pflege {n}/{CARES_PER_DAY}.",
        # Neue extreme – Belohnung, die süchtig macht:
        "{owner} erlaubt {pet} seinen Schwanz zu lecken – nur die Spitze, fünf Sekunden. Danach wieder wochenlang nichts. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Orgasmus, aber nur während {owner} sie würgt – {pet} kommt und wird gleichzeitig ohnmächtig vor Dankbarkeit. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt einmal sanft über die frischen Wunden – 'Belohnung fürs Bluten.' {pet} heult vor Glück. Pflege {n}/{CARES_PER_DAY}.",
        "Erlaubt, {owner}s Namen zu stöhnen – nur dieses eine Mal. {pet} kommt sofort und hasst sich für die Sucht. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss – aber auf die geschwollene Wange nach den Ohrfeigen. 'Schmeckt nach Liebe, oder?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} eine Stunde lang nicht im Käfig schlafen – 'Luxusbelohnung, du undankbares Stück.' Pflege {n}/{CARES_PER_DAY}.",
        "Das größte Geschenk: {owner} sagt 'Ich behalte dich noch einen Tag länger.' {pet} zerbricht vor Dankbarkeit und Angst zugleich. Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "belohnen", tame)

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

        # Preis + aktueller Besitzer
        price = await get_user_price(db, chat_id, target_id)
        prev_owner = await get_owner_id(db, chat_id, target_id)
        if prev_owner == buyer_id:
            await update.effective_message.reply_text("Du besitzt das Haustier bereits.")
            await db.commit()
            return

        # >>> HIER KOMMT DER KAUFSCHUTZ-CHECK REIN <<<
        # 48h-Kaufschutz prüfen (nur wenn es einen Vorbesitzer gibt, der nicht der Käufer ist)
        lock_until = await get_pet_lock_until(db, chat_id, target_id)
        now = int(time.time())
        if prev_owner and prev_owner != buyer_id and lock_until and lock_until > now:
            left = lock_until - now
            h = left // 3600
            m = (left % 3600) // 60
            target_tag_inline = f"@{target_username}" if target_username else f"ID:{target_id}"
            await update.effective_message.reply_text(
                f"{escape(target_tag_inline, False)} ist noch {h}h {m}m geschützt. Kauf erst danach möglich."
            )
            await db.commit()
            return
        # <<< ENDE KAUFSCHUTZ-CHECK <<<

        # Coins prüfen
        async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, buyer_id)) as cur:
            row = await cur.fetchone()
        buyer_coins = row[0] if row else 0
        if buyer_coins < price:
            await update.effective_message.reply_text(f"Zu teuer. Preis: {price} Coins. Dein Guthaben: {buyer_coins}.")
            await db.commit()
            return

        # Coins abziehen
        await db.execute(
            "UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?",
            (price, chat_id, buyer_id)
        )

        # Owner setzen + neuen 48h-Kaufschutz starten
        now = int(time.time())
        lock_until_new = now + LOCK_SECONDS  # LOCK_SECONDS = 48*3600 (global)
        await db.execute("""
            INSERT INTO pets(chat_id, pet_id, owner_id, purchase_lock_until)
            VALUES(?,?,?,?)
            ON CONFLICT(chat_id, pet_id) DO UPDATE SET
                owner_id=excluded.owner_id,
                purchase_lock_until=excluded.purchase_lock_until
        """, (chat_id, target_id, buyer_id, lock_until_new))

        # Preis erhöhen
        new_price = price + USER_PRICE_STEP
        await set_user_price(db, chat_id, target_id, new_price)

        await db.commit()

    target_tag = f"@{target_username}" if target_username else f"ID:{target_id}"
    await update.effective_message.reply_text(
        f"{nice_name_html(buyer)} hat {escape(target_tag, False)} für {price} Coins gekauft. Neuer Preis: {new_price}."
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

        # --- HIER: Lock-Info laden & Text bauen ---
        lock_until = await get_pet_lock_until(db, chat_id, target_id)
        lock_txt = ""
        now = int(time.time())
        if lock_until and lock_until > now:
            left = lock_until - now
            h = left // 3600
            m = (left % 3600) // 60
            lock_txt = f" 🔒{h}h{m:02d}m"
        # --- ENDE Lock-Block ---

    if owner_id:
        tag = f"@{owner_uname}" if owner_uname else f"[ID:{owner_id}](tg://user?id={owner_id})"
        await update.effective_message.reply_text(
            f"Besitzer: {tag}. Aktueller Preis: {price}.{lock_txt}",
            parse_mode="Markdown"
        )
    else:
        await update.effective_message.reply_text(
            f"Kein Besitzer. Aktueller Preis: {price}.{lock_txt}"
        )


async def cmd_ownerlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt alle Besitzverhältnisse gruppiert nach Besitzer (mit Lockzeit und Wert)."""
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
                    COALESCE(p.purchase_lock_until, 0)          AS locked_until
                FROM pets p
                LEFT JOIN players ou ON ou.chat_id=p.chat_id AND ou.user_id=p.owner_id
                LEFT JOIN players pu ON pu.chat_id=p.chat_id AND pu.user_id=p.pet_id
                LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
                WHERE p.chat_id=?
                ORDER BY p.owner_id ASC, current_price DESC, p.pet_id ASC
            """, (chat_id,)) as cur:
                rows = await cur.fetchall()
    except Exception as e:
        return await update.effective_message.reply_text(
            f"⚠️ Konnte Ownerliste nicht laden: <code>{type(e).__name__}</code> – {escape(str(e), False)}"
        )

    if not rows:
        return await update.effective_message.reply_text("Noch keine Besitzverhältnisse. Kauf dir erstmal jemanden. 🐾")

    # Gruppieren nach Owner
    by_owner = {}
    for owner_id, owner_uname, pet_id, pet_uname, price, locked_until in rows:
        by_owner.setdefault((owner_id, owner_uname), []).append(
            (pet_id, pet_uname, int(price or 0), int(locked_until or 0))
        )

    def tag(uid: int | None, uname: str | None) -> str:
        if uid is None:
            return "—"
        return f"@{uname}" if uname else f"<a href='tg://user?id={uid}'>ID:{uid}</a>"

    out = ["📜 <b>Ownerliste</b> — gruppiert nach Besitzer:\n"]
    owners_sorted = sorted(by_owner.keys(), key=lambda k: (k[0] is None, k[0] or 0))
    for (owner_id, owner_uname) in owners_sorted:
        pets = by_owner[(owner_id, owner_uname)]
        total_value = sum(p[2] for p in pets)

        out.append(f"<b>{tag(owner_id, owner_uname)}</b>  <i>({len(pets)} Pet(s), Gesamtwert: {total_value})</i>")
        for pet_id, pet_uname, price, locked_until in pets:
            pet_tag = tag(pet_id, pet_uname)
            lock_txt = ""
            if locked_until > now:
                mins_total = (locked_until - now) // 60
                hrs, mins = divmod(mins_total, 60)
                lock_txt = f" 🔒{hrs}h{mins:02d}m"
            out.append(f" ├─ {pet_tag}  (<b>{price}</b>){lock_txt}")
        out.append("")

    text = "\n".join(out).strip()
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
    
    #Auto Bot commands (falls mal ein User das machen darf)
    # app.add_handler(CommandHandler("verfluchen",  cmd_verfluchen,  filters=CHAT_FILTER))
    # app.add_handler(CommandHandler("brandmarken", cmd_brandmarken, filters=CHAT_FILTER))

    # hass und selbst
    app.add_handler(CommandHandler("hass",   cmd_hass,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("selbst", cmd_selbst, filters=CHAT_FILTER))



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
    app.job_queue.run_repeating(hass_watchdog_job, interval=60, first=30, name="hass_watchdog")

    log.info("Bot startet, warte auf Updates...")
    app.run_polling()

if __name__ == "__main__":
    main()
