# Petflix 2.0 .py (Refreshed: owner-steal logic, ownerlist, bugfixes)

import asyncio
import os
import random
import time
import logging
import shutil
import aiosqlite
import datetime
import hashlib
import re
from typing import Optional
from datetime import time as dtime
from zoneinfo import ZoneInfo  # Python 3.9+
from html import escape
from love_text_rules import LoveTextRules, love_text_ok
from text_helpers import get_cached_json, load_json_dict, split_chunks
from admin_coin_commands import create_admin_coin_commands
from runtime_features import create_runtime_features
from ownership_features import create_ownership_features
from economy_commands import create_economy_commands
from jobs_watchdogs import create_jobs_watchdogs
from brand_features import create_brand_features
from petflix_cooldowns import get_cd_left, set_cd
from petflix_db import db_init
from petflix_superwords import (
    SUPERWORD_KEYS,
    SUPERWORDS,
    claim_superword_once,
    count_active_superword_cooldowns,
    normalize_superword_text,
    superword_key,
    superword_pattern,
)
from petflix_players import (
    ensure_player as _ensure_player_base,
    ensure_player_entry as _ensure_player_entry_base,
    get_coins as _get_coins_base,
    get_user_price as _get_user_price_base,
    set_user_price,
)
from petflix_pets import (
    apply_runaway_owner_penalty as _apply_runaway_owner_penalty,
    care_count_in_window as _care_count_in_window,
    care_count_last_24h as _care_count_last_24h,
    get_care,
    get_latest_owned_pet_id as _get_latest_owned_pet_id,
    get_pet_lock_until,
    set_care,
    should_runaway as _should_runaway,
)
from petflix_texts import (
    DOM_FEMALE_DENY_LINES,
    ADMIN_MORAL_TAX_REPLIES,
    RUNAWAY_LINES,
    PET_DAILY_MOODS,
    REBELLION_STAGE_LINES,
    REBELLION_STAGE_EXTRA_LINES,
    PET_STATUS_LINES,
    CARE_STYLE_LINES,
    JEALOUSY_LINES,
    FULL_CARE_FINISH_LINES_SARCASTIC,
    FULL_CARE_FINISH_LINES_BLACK,
    FULL_CARE_FINISH_LINES_VICIOUS,
    BOX_STANDARD_TITLES,
    BOX_ABYSS_TITLES,
    BOX_STANDARD_COIN_TEXTS,
    BOX_STANDARD_EMPTY_TEXTS,
    BOX_STANDARD_LOSS_TEXTS,
    BOX_STANDARD_SHIELD_TEXTS,
    BOX_STANDARD_XP_TEXTS,
    BOX_STANDARD_FALLBACK_TEXTS,
    BOX_STANDARD_TITLE_TEXTS,
    BOX_ABYSS_COIN_TEXTS,
    BOX_ABYSS_EMPTY_TEXTS,
    BOX_ABYSS_LOSS_TEXTS,
    BOX_ABYSS_SHIELD_TEXTS,
    BOX_ABYSS_XP_TEXTS,
    BOX_ABYSS_FALLBACK_TEXTS,
    BOX_ABYSS_TITLE_TEXTS,
    BOX_ABYSS_JACKPOT_TEXTS,
    BOX_STANDARD_FLAVOR_TEXTS,
    BOX_ABYSS_FLAVOR_TEXTS,
    FLUCH_LINES,
    LOVE_NICKNAMES,
    LOVE_EMOJIS,
    LOVE_SAD_PATTERNS,
    LOVE_MASTER_LINES,
    SELF_LINES,
    MORAL_TAX_TRIGGERS,
    REWARD_TRIGGERS,
    _SAVAGE_LINES,
    _WORLD_PLACES,
    _TREASURE_METHODS,
    _TREASURE_STORIES,
    CARE_FALLBACK_TEXTS,
    CARE_COOL_TEXTS,
)

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ChatMemberStatus, ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler, CallbackQueryHandler,
    ContextTypes, filters, Defaults
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID_RAW = os.getenv("ALLOWED_CHAT_ID", "-1003697514358")
try:
    ALLOWED_CHAT_ID = int(ALLOWED_CHAT_ID_RAW)
    CHAT_FILTER = filters.Chat(ALLOWED_CHAT_ID)
except ValueError:
    CHAT_FILTER = filters.Chat(ALLOWED_CHAT_ID_RAW)

DB = os.environ.get("DB_PATH", "petflix_3.0.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "data")
BACKUP_KEEP_FILES = 7
MAX_CHUNK = 3500  # unter 4096 bleiben, wegen HTML-Overhead sicher
DOM_RESPONSES_PATH = os.getenv("DOM_RESPONSES_PATH", "texts/dom_responses.json")
CARE_RESPONSES_PATH = os.getenv("CARE_RESPONSES_PATH", "texts/care_responses.json")
STEAL_TEXTS_PATH = os.getenv("STEAL_TEXTS_PATH", "texts/steal_texts.json")


# =========================
# Konfiguration
# =========================
START_COINS = 0
DAILY_COINS = 0
DAILY_COOLDOWN_S = 22 * 3600
MESSAGE_REWARD = 10
USER_BASE_PRICE = 100
USER_PRICE_STEP = 200  # 100 -> 300 -> 500 ...
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MESSAGE_THROTTLE_S = 1
CARE_COOLDOWN_S = 5  # Sekunden zwischen Pflegeaktionen
CARES_PER_DAY = 10
CARE_XP_PER_ACTION = 3
FULL_CARE_XP_BONUS = 5
MIN_CARES_PER_24H = 10
RUNAWAY_WINDOW_DAYS = 3
RUNAWAY_MIN_CARES_IN_WINDOW = 10
LEVEL_DECAY_XP = 0
LEVEL_DECAY_INTERVAL_S = 6 * 3600
CARE_CHAT_CLEANUP_S = 90
STICKER_CHAT_CLEANUP_S = 30
RUNAWAY_HOURS = RUNAWAY_WINDOW_DAYS * 24
LOCK_SECONDS = 0 * 3600  # 48h Mindestbesitz
PETFLIX_TZ = os.environ.get("PETFLIX_TZ", "Europe/Berlin")
TITLE_MASTEROFPUPPETS = "MasterofPuppets"
TITLE_DURATION_S = 2 * 3600
PRESTIGE_TITLE_DURATION_S = 24 * 3600
DAILY_GIFT_COINS = 25000
DAILY_CURSE_PENALTY = 150
DAILY_PRIMETIME_COINS = 70000
DAILY_CURSE_ENABLED = True
MORAL_TAX_DEFAULT = 5
REWARD_AMOUNT = 1 
# =========================
# Ausreisser
# =========================
RUNAWAY_PENALTY = 400
REBELLIOUS_DURATION_S = 12 * 3600
REBELLION_DEFICIT_TRIGGER = 4


SOFT_CARE_ACTIONS = {"pet", "kiss", "dine", "massage", "loben", "belohnen", "walk"}
STRICT_CARE_ACTIONS = {
    "knien", "kriechen", "klaps", "leine", "halsband", "verweigern",
    "kaefig", "schande", "stumm", "bestrafen", "demuetigen", "ohrfeige",
}



TITLE_KETTENHALTER = "Kettenhalter"
TITLE_UNANTASTBAR = "Unantastbar"
TITLE_LEINENKOENIG = "Leinenkönig"
TITLE_ZUCHTMEISTER = "Zuchtmeister"

# Superwort-Listen und Hilfsfunktionen sind in petflix_superwords.py ausgelagert.
# =========================
# /steal
# =========================
STEAL_SUCCESS_CHANCE = 0.45
STEAL_COOLDOWN_S = 30
STEAL_FAIL_PENALTY_RATIO = 0.20

# =========================
# /buy Schutz durch Pflege
# =========================
BUY_SUCCESS_MAX = 0.95   # Bei 0/10 Pflege fast sicher kaufbar
BUY_SUCCESS_MIN = 0.05   # Bei 10/10 Pflege fast nicht kaufbar
BUY_FAIL_PENALTY_RATIO = 0.20  # Bei Fehlversuch immer 20% Coins weg
CARE_FIFTYFIFTY_UNTIL = 4
CARE_HARD_PROTECT_START = 8
RISK_BONUS_PER_PRICE = 0.20  # Risiko in Höhe des Preises => +20% Chance
RISK_MAX_BONUS = 0.35        # Maximal +35% durch Risiko

# =========================
# Pet-Skills
# =========================
SKILL_KEEP_CHANCE = 0.70
SKILL_REROLL_CHANCE = 0.30
FULL_CARE_OWNER_BONUS = 40
PRICE_STEP_SKILL_BONUS = 80
BUY_REFUND_SKILL_RATIO = 0.15

PET_SKILLS = {
    "schildwall": {
        "name": "Halsbandhörig",
        "desc": "Sitzt eng und macht Klauversuche schwerer: -20% Kaufchance.",
        "weight": 25,
    },
    "treuesiegel": {
        "name": "Kettengehorsam",
        "desc": f"Bei {CARES_PER_DAY}/{CARES_PER_DAY} Pflege bleibt das Pet fast unantastbar.",
        "weight": 18,
    },
    "goldzahn": {
        "name": "Tributsklave",
        "desc": "Findet beim Kauf 15% vom Preis als dreckiges Trinkgeld zurück.",
        "weight": 18,
    },
    "wertanlage": {
        "name": "Wertmarke",
        "desc": f"Preis steigt kontrollierter: +{PRICE_STEP_SKILL_BONUS} statt +{USER_PRICE_STEP}.",
        "weight": 16,
    },
    "goldesel": {
        "name": "Schoßopfer",
        "desc": f"Bei perfekter Pflege zahlt das Pet +{FULL_CARE_OWNER_BONUS} Coins Tribut.",
        "weight": 13,
    },
    "chamaeleon": {
        "name": "Rollenwechsel",
        "desc": "Bei Besitzerwechsel wird die Rolle sofort neu ausgewürfelt.",
        "weight": 10,
    },
}

PET_BOND_STAGES = [
    (520, "Unzertrennlich"),
    (320, "Verschmust"),
    (180, "Treudoof"),
    (80, "Anhänglich"),
    (25, "Zutraulich"),
    (0, "Scheu"),
]
FULLCARE_EVOLUTION_STAGES = [
    (30, "Hörig"),
    (14, "Unterworfen"),
    (7, "Gefügig"),
    (3, "Gezähmt"),
    (1, "Frech"),
]




FULL_CARE_FINISH_POOLS = [
    FULL_CARE_FINISH_LINES_SARCASTIC,
    FULL_CARE_FINISH_LINES_BLACK,
    FULL_CARE_FINISH_LINES_VICIOUS,
]

# =========================
# /blackjack
# =========================
BLACKJACK_COOLDOWN_S = 45
BLACKJACK_MIN_BET = 10
BLACKJACK_MAX_BET = 5000
BLACKJACK_OUTCOMES = [
    ("bust", 0.50, 0.0, "Bust"),
    ("push", 0.11, 1.0, "Push"),
    ("win", 0.27, 1.8, "Win"),
    ("blackjack", 0.12, 2.4, "Blackjack"),
]
# =========================
# Fluch
# =========================

AUTO_CURSE_ENABLED = False
AUTO_CURSE_CHANCE_PER_MESSAGE = 0.3  # 2% pro normaler Nachricht
AUTO_CURSE_COOLDOWN_S = 30 * 60       # 30 Minuten globaler Cooldown im Chat
CURSE_SHIELD_KEY = "curse_shield"

BOX_STANDARD_COST = 2500
BOX_STANDARD_COOLDOWN_S = 45 * 60
BOX_ABYSS_COST = 15000
BOX_ABYSS_COOLDOWN_S = 3 * 3600
BOX_TITLE_DURATION_S = 24 * 3600
BOX_ABYSS_TITLE_DURATION_S = 48 * 3600






def render_curse_text(user_mention: str) -> str:
    line = random.choice(FLUCH_LINES).format(user=user_mention)
    return f"{line}\n<b>Strafe:</b> -{DAILY_CURSE_PENALTY} Coins"


def _format_duration_compact(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


# =========================
# /hass + /selbst
# =========================
HASS_DURATION_S = 2 * 3600
HASS_REQUIRED = 3
HASS_PENALTY = 5000
HASS_REWARD = 5000

# =========================
# /liebes (Liebesgeständnis)
# =========================
LOVE_CHALLENGE_HOURS = 2
LOVE_REWARD = 5000
LOVE_PENALTY_PERCENT = 50
LOVE_MIN_WORDS = 60
LOVE_MIN_NICKNAMES = 0
LOVE_MIN_EMOJIS = 5
LOVE_MIN_SAD_SENTENCES = 0
LOVE_MIN_SENTENCES = 2
LOVE_SENTENCE_MIN_WORDS = 4
LOVE_MIN_VERBS = 1
LOVE_COUNT_ANY_EMOJI = True
LOVE_REMIND_1_S = 60 * 60
LOVE_REMIND_2_S = 105 * 60
LOVE_VERB_RE = re.compile(
    r"\b(bin|bist|ist|sind|seid|war|waren|habe|hast|hat|haben|hatte|hatten|"
    r"werde|wirst|wird|werden|kann|kannst|können|k?nnen|mag|"
    r"liebe|liebst|liebt|lieben|"
    r"fühle|f?hle|fühlst|f?hlst|fühlt|fühlt|"
    r"brauch(e|st|t|en)|"
    r"will|willst|wollen|"
    r"möchte|moechte|möchtest|moechtest|mögen|m?gen|"
    r"vermisse|vermisst|vermissen|"
    r"sehe|siehst|sieht|sehen|"
    r"träume|träumst|träumt|traeume|traeumst|traeumt|"
    r"sag(e|st|t|en)|"
    r"denk(e|st|t|en)|"
    r"glaub(e|st|t|en)|"
    r"hoff(e|st|t|en)|"
    r"wünsch(e|st|t|en)|wuensch(e|st|t|en)|"
    r"brauchte|brauchtest|brauchten|"
    r"wollte|wolltest|wollten|"
    r"mochte|mochtest|mochten|"
    r"liebte|liebtest|liebten)\b",
    re.IGNORECASE
)
LOVE_TEXT_RULES = LoveTextRules(
    min_words=LOVE_MIN_WORDS,
    min_emojis=LOVE_MIN_EMOJIS,
    min_sentences=LOVE_MIN_SENTENCES,
    sentence_min_words=LOVE_SENTENCE_MIN_WORDS,
    min_verbs=LOVE_MIN_VERBS,
    count_any_emoji=LOVE_COUNT_ANY_EMOJI,
    emojis=tuple(LOVE_EMOJIS),
    sad_patterns=tuple(LOVE_SAD_PATTERNS),
    verb_re=LOVE_VERB_RE,
)



# =========================
# Moralsteuer – jetzt exakt wie ein Skalpell in deiner Haut
# =========================


# =========================
# Reward Triggers – nur für die wirklich Braven, die exakt parieren
# =========================



BOOT_TS = int(time.time())

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
log = logging.getLogger("Petflix_2.0")

# =========================
# DB-Setup 
# =========================

# DB-Setup und Migrationen sind in petflix_db.py ausgelagert.

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
          username=CASE
            WHEN TRIM(COALESCE(excluded.username, '')) <> '' THEN excluded.username
            ELSE hass_challenges.username
          END,
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

async def _get_care_meta(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    care_map = context.application.bot_data.get("care_map", {})
    meta = care_map.get((chat_id, message_id))
    if meta:
        return meta
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT pet_id, owner_id, action, ts, message_id FROM care_events WHERE chat_id=? AND message_id=?",
            (chat_id, message_id)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {
        "pet_id": int(row[0]),
        "owner_id": int(row[1]),
        "action": row[2],
        "ts": int(row[3] or 0),
        "bot_msg_id": int(row[4]),
        "owner_msg_id": int(row[4]),
    }


async def _delete_messages_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}
    chat_id = data.get("chat_id")
    message_ids = data.get("message_ids") or []
    if not chat_id or not message_ids:
        return

    seen = set()
    unique_ids = []
    for message_id in message_ids:
        if not message_id or message_id in seen:
            continue
        seen.add(message_id)
        unique_ids.append(message_id)

    for message_id in unique_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass


async def on_single_g_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return

    context.job_queue.run_once(
        _delete_messages_job,
        when=STICKER_CHAT_CLEANUP_S,
        data={"chat_id": chat.id, "message_ids": [msg.message_id]},
        name=f"single_g_cleanup:{chat.id}:{msg.message_id}",
    )


async def _send_or_replace_level_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    trigger_msg,
    text: str,
):
    store = context.application.bot_data.setdefault("latest_level_message", {})
    prev_message_id = store.get(chat_id)
    if prev_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_message_id)
        except Exception:
            pass
    level_msg = await trigger_msg.reply_text(text, parse_mode=ParseMode.HTML)
    store[chat_id] = level_msg.message_id
    return level_msg

async def get_moraltax_settings(db, chat_id: int):
    async with db.execute("SELECT moraltax_enabled, moraltax_amount FROM settings WHERE chat_id=?", (chat_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.execute(
            "INSERT INTO settings(chat_id, moraltax_enabled, moraltax_amount) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET moraltax_enabled=COALESCE(moraltax_enabled,excluded.moraltax_enabled), "
            "moraltax_amount=COALESCE(moraltax_amount,excluded.moraltax_amount)",
            (chat_id, 1, MORAL_TAX_DEFAULT)
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

async def apply_moraltax_if_needed(db, chat_id: int, user_id: int, text: str) -> tuple[Optional[int], Optional[str]]:
    if not text:
        return None, None

    if user_id == ADMIN_ID:
        t = text.lower()
        for pattern, reply in ADMIN_MORAL_TAX_REPLIES:
            if re.search(pattern, t):
                return None, reply
        return None, None

    t = text.lower()
    enabled, amount = await get_moraltax_settings(db, chat_id)
    if not enabled or amount <= 0:
        return None, None

    # Finde den ersten passenden Trigger + Kommentar
    trigger_comment = None
    for pattern, comment in MORAL_TAX_TRIGGERS:
        if re.search(pattern, t):
            trigger_comment = comment
            break

    if not trigger_comment:
        return None, None

    async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    coins = row[0] if row else 0
    deduct = min(amount, coins)
    if deduct <= 0:
        return 0, "Nettigkeit erkannt – aber du bist pleite. Beim nächsten Mal kassiere ich richtig, du kleine Bettlerin 😈"

    await db.execute("UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?", (deduct, chat_id, user_id))
    await db.commit()
    log.info(f"[MORALTAX] chat={chat_id} user={user_id} deducted={deduct}")

    response = trigger_comment.format(deduct=deduct)
    return deduct, response

async def apply_reward_if_needed(db, chat_id: int, user_id: int, text: str) -> tuple[Optional[int], Optional[str]]:
    if not text:
        return None, None

    t = text.lower()

    # Finde den ersten passenden Trigger + Kommentar
    trigger_comment = None
    for pattern, comment in REWARD_TRIGGERS:
        if re.search(pattern, t):
            trigger_comment = comment
            break

    if not trigger_comment:
        return None, None

    reward = REWARD_AMOUNT
    await db.execute("UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?", (reward, chat_id, user_id))
    await db.commit()
    log.info(f"[REWARD] chat={chat_id} user={user_id} rewarded={reward}")

    response = trigger_comment.format(reward=reward)
    return reward, response

def _tz_now() -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo(PETFLIX_TZ))


def today_ymd():
    return _tz_now().date().isoformat()


def _today_bounds_unix() -> tuple[int, int]:
    now = _tz_now()
    start = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=now.tzinfo)
    end = start + datetime.timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())



def _skill_meta(skill_key: str | None) -> dict:
    return PET_SKILLS.get(skill_key or "", {"name": "Ohne Skill", "desc": "Kein passiver Effekt."})

def _skill_label(skill_key: str | None) -> str:
    meta = _skill_meta(skill_key)
    return f"{meta['name']} ({meta['desc']})"

def _roll_pet_skill() -> str:
    keys = list(PET_SKILLS.keys())
    weights = [int(PET_SKILLS[k]["weight"]) for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]

async def get_pet_skill(db, chat_id: int, pet_id: int) -> Optional[str]:
    async with db.execute("SELECT pet_skill FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet_id)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return row[0]

async def set_pet_skill(db, chat_id: int, pet_id: int, skill_key: str):
    await db.execute(
        "UPDATE pets SET pet_skill=? WHERE chat_id=? AND pet_id=?",
        (skill_key, chat_id, pet_id)
    )

def resolve_next_skill(prev_skill: Optional[str], has_prev_owner: bool) -> tuple[str, bool]:
    if not has_prev_owner:
        return _roll_pet_skill(), True
    if prev_skill == "chamaeleon":
        return _roll_pet_skill(), True
    if not prev_skill:
        return _roll_pet_skill(), True
    reroll_chance = max(SKILL_REROLL_CHANCE, 1.0 - SKILL_KEEP_CHANCE)
    if random.random() < reroll_chance:
        return _roll_pet_skill(), True
    return prev_skill, False

def pet_level_from_xp(xp: int) -> int:
    points = max(0, int(xp))
    level = 0
    for threshold, _title in reversed(PET_BOND_STAGES):
        if points >= threshold:
            return level
        level += 1
    return 0

def pet_bond_title(points: int) -> str:
    amount = max(0, int(points))
    for threshold, title in PET_BOND_STAGES:
        if amount >= threshold:
            return title
    return "Scheu"

def pet_level_title(level: int) -> str:
    return pet_bond_title(level)

def pet_bond_percent(points: int) -> int:
    return max(0, min(100, int(points or 0)))

def pet_mood_label(care_done_today: int, fullcare_streak: int) -> str:
    done = max(0, int(care_done_today))
    streak = max(0, int(fullcare_streak))
    if done >= CARES_PER_DAY:
        return "Glücklich"
    if streak >= 7:
        return "Tiefenentspannt"
    if done >= max(1, CARES_PER_DAY // 2):
        return "Zufrieden"
    if done > 0:
        return "Aufmerksam"
    return "Unruhig"


def rebellion_stage_label(stage: int) -> str:
    labels = {
        0: "Ruhig",
        1: "Zickig",
        2: "Gierig",
        3: "Verweigernd",
        4: "Ausgebrochen",
        5: "Blamage-Modus",
    }
    return labels.get(max(0, min(5, int(stage or 0))), "Zickig")


def pet_status_label(stage: int, rebellious_until: int, now_ts: int) -> str:
    stage = max(0, min(5, int(stage or 0)))
    if stage == 0 and int(rebellious_until or 0) > int(now_ts):
        stage = 1
    pool = PET_STATUS_LINES.get(stage) or PET_STATUS_LINES.get(0) or ["Liegt wachsam am Platz und wartet auf Fuehrung."]
    return random.choice(pool)


def rebellion_stage_from_deficit(care_deficit: int, runaway_due: bool, care_window: int) -> int:
    if runaway_due and care_window < 3:
        return 5
    if runaway_due:
        return 4
    if care_deficit >= 7:
        return 3
    if care_deficit >= 5:
        return 2
    if care_deficit >= REBELLION_DEFICIT_TRIGGER:
        return 1
    return 0


def rebellion_drama_text(stage: int, pet_tag: str, owner_tag: str) -> str:
    stage = int(stage or 0)
    if stage <= 0:
        return ""
    stage = min(5, stage)
    pool = list(REBELLION_STAGE_LINES.get(stage, []))
    pool.extend(REBELLION_STAGE_EXTRA_LINES.get(stage, []))
    if pool:
        return random.choice(pool).format(pet=pet_tag, owner=owner_tag)
    return ""


def pet_imprint_label(score: int) -> str:
    points = int(score or 0)
    if points <= -8:
        return "Strafgeprägt"
    if points <= -3:
        return "Abgehärtet"
    if points < 3:
        return "Loyal"
    if points < 8:
        return "Fixiert"
    return "Hörig"


def _care_style_delta(action_key: str) -> int:
    key = (action_key or "").strip().lower()
    if key in SOFT_CARE_ACTIONS:
        return 1
    if key in STRICT_CARE_ACTIONS:
        return -1
    return 0


def _daily_pet_mood(chat_id: int, pet_id: int, owner_pet_count: int, today: str) -> str:
    digest = hashlib.sha256(f"{chat_id}:{pet_id}:{today}:{owner_pet_count}".encode("utf-8")).digest()
    mood_pool = list(PET_DAILY_MOODS)
    if owner_pet_count < 2 and "Besitzergreifend" in mood_pool:
        mood_pool.remove("Besitzergreifend")
    return mood_pool[digest[0] % len(mood_pool)]


def render_pet_mood(mood_name: str | None, care_done_today: int, fullcare_streak: int, rebellious_until: int, now_ts: int) -> str:
    if int(rebellious_until or 0) > int(now_ts):
        return "Zickig"
    if mood_name:
        return mood_name
    return pet_mood_label(care_done_today, fullcare_streak)


async def ensure_pet_dynamic_state(db, chat_id: int, pet_id: int, owner_id: int | None, today: str):
    async with db.execute(
        "SELECT mood_name, mood_day, COALESCE(imprint_score, 0), COALESCE(rebellious_until, 0), COALESCE(breakout_count, 0), "
        "COALESCE(hostage_until, 0), COALESCE(snatched_until, 0) "
        "FROM pets WHERE chat_id=? AND pet_id=?",
        (chat_id, pet_id)
    ) as cur:
        row = await cur.fetchone()
    mood_name = row[0] if row else None
    mood_day = row[1] if row else None
    imprint_score = int(row[2]) if row and row[2] is not None else 0
    rebellious_until = int(row[3]) if row and row[3] is not None else 0
    breakout_count = int(row[4]) if row and row[4] is not None else 0
    hostage_until = int(row[5]) if row and row[5] is not None else 0
    snatched_until = int(row[6]) if row and row[6] is not None else 0

    owner_pet_count = 0
    if owner_id:
        async with db.execute(
            "SELECT COUNT(*) FROM pets WHERE chat_id=? AND owner_id=?",
            (chat_id, owner_id)
        ) as cur:
            owner_row = await cur.fetchone()
        owner_pet_count = int(owner_row[0]) if owner_row and owner_row[0] is not None else 0

    if mood_day != today or not mood_name:
        mood_name = _daily_pet_mood(chat_id, pet_id, owner_pet_count, today)
        await db.execute(
            "UPDATE pets SET mood_name=?, mood_day=? WHERE chat_id=? AND pet_id=?",
            (mood_name, today, chat_id, pet_id)
        )

    return {
        "mood_name": mood_name,
        "mood_day": today,
        "imprint_score": imprint_score,
        "rebellious_until": rebellious_until,
        "breakout_count": breakout_count,
        "hostage_until": hostage_until,
        "snatched_until": snatched_until,
        "owner_pet_count": owner_pet_count,
    }


async def maybe_grant_owner_prestige_title(db, chat_id: int, owner_id: int, today: str) -> tuple[str | None, int | None]:
    async with db.execute(
        """
        SELECT
          COUNT(*) AS pet_count,
          SUM(COALESCE(pet_xp, 0)) AS total_bond,
          MAX(COALESCE(fullcare_streak, 0)) AS max_streak,
          SUM(CASE WHEN COALESCE(pet_xp, 0) >= 80 THEN 1 ELSE 0 END) AS high_bond_pets,
          SUM(CASE WHEN day_ymd=? AND COALESCE(care_done_today, 0) >= ? THEN 1 ELSE 0 END) AS fully_cared_today
        FROM pets
        WHERE chat_id=? AND owner_id=?
        """,
        (today, CARES_PER_DAY, chat_id, owner_id)
    ) as cur:
        row = await cur.fetchone()
    pet_count = int(row[0]) if row and row[0] is not None else 0
    total_bond = int(row[1]) if row and row[1] is not None else 0
    max_streak = int(row[2]) if row and row[2] is not None else 0
    high_bond_pets = int(row[3]) if row and row[3] is not None else 0
    fully_cared_today = int(row[4]) if row and row[4] is not None else 0

    title = None
    if pet_count >= 2 and fully_cared_today == pet_count:
        title = TITLE_UNANTASTBAR
    elif pet_count >= 3 and total_bond >= 120:
        title = TITLE_LEINENKOENIG
    elif high_bond_pets >= 2:
        title = TITLE_ZUCHTMEISTER
    elif max_streak >= 3:
        title = TITLE_KETTENHALTER
    elif fully_cared_today >= 1:
        title = TITLE_MASTEROFPUPPETS

    if not title:
        return None, None

    until_ts = await set_temp_title(db, chat_id, owner_id, title, PRESTIGE_TITLE_DURATION_S)
    return title, until_ts


def fullcare_evolution_title(fullcare_days: int) -> str:
    days = max(0, int(fullcare_days))
    for needed_days, title in FULLCARE_EVOLUTION_STAGES:
        if days >= needed_days:
            return title
    return "Frech"

def is_group(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}

async def ensure_player(db, chat_id: int, user_id: int, username: str):
    await _ensure_player_base(db, chat_id, user_id, username, START_COINS, USER_BASE_PRICE)


async def get_user_price(db, chat_id: int, user_id: int) -> int:
    return await _get_user_price_base(db, chat_id, user_id, USER_BASE_PRICE)

def _secs_until_tomorrow() -> int:
    now = _tz_now()
    tomorrow = (now + datetime.timedelta(days=1)).date()
    midnight = datetime.datetime.combine(tomorrow, datetime.time.min, tzinfo=now.tzinfo)
    return max(1, int((midnight - now).total_seconds()))

# 48h Mindestbesitz
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


async def set_temp_title(db, chat_id: int, user_id: int, title: str, duration_s: int):
    expires_ts = int(time.time()) + max(1, int(duration_s))
    await db.execute(
        """
        INSERT INTO user_titles(chat_id, user_id, title, expires_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
          title=excluded.title,
          expires_ts=excluded.expires_ts
        """,
        (chat_id, user_id, title, expires_ts)
    )
    return expires_ts


async def get_active_titles_map(db, chat_id: int, user_ids: list[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    now = int(time.time())
    await db.execute("DELETE FROM user_titles WHERE chat_id=? AND expires_ts<=?", (chat_id, now))
    uniq_ids = sorted({int(u) for u in user_ids})
    placeholders = ",".join("?" for _ in uniq_ids)
    sql = (
        f"SELECT user_id, title FROM user_titles "
        f"WHERE chat_id=? AND expires_ts>? AND user_id IN ({placeholders})"
    )
    params = [chat_id, now, *uniq_ids]
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    return {int(uid): (title or "") for uid, title in rows}


def with_title_suffix(label: str, title: str | None) -> str:
    if not title:
        return label
    return f"{label} [{title}]"

def runaway_text(pet_tag: str, owner_tag: str) -> str:
    line = random.choice(RUNAWAY_LINES)
    return line.format(pet=pet_tag, owner=owner_tag)

# =========================
# Pflegeaktionen (gemeinsamer Handler)
# =========================
async def do_care(update, context, action_key, tame_lines):
    if not is_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    active_cutoff = int(time.time()) - SUPERWORD_COOLDOWN_S
    active_cutoff = int(time.time()) - SUPERWORD_COOLDOWN_S
    owner = update.effective_user

    # Ziel bestimmen: Reply > @username/user_id > letztes Haustier
    pet = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        pet = msg.reply_to_message.from_user
    elif context.args:
        target_id = None
        target_name = None
        first = context.args[0].lstrip("@")
        if first.isdigit():
            target_id = int(first)
        else:
            async with aiosqlite.connect(DB) as db:
                async with db.execute(
                    "SELECT user_id, username FROM players WHERE chat_id=? AND username=?",
                    (chat_id, first)
                ) as cur:
                    row = await cur.fetchone()
            if row:
                target_id = int(row[0])
                target_name = row[1] or first
        if target_id is None:
            await msg.reply_text("Ziel nicht gefunden. Nutze Reply, @username oder user_id.")
            return
        class Obj:
            pass
        pet = Obj()
        pet.id = target_id
        pet.first_name = target_name or "Dein Haustier"
        pet.username = target_name
    else:
        async with aiosqlite.connect(DB) as db:
            async with db.execute("""
                SELECT pet_id FROM pets
                WHERE chat_id=? AND owner_id=?
                ORDER BY last_care_ts DESC LIMIT 1
            """, (chat_id, owner.id)) as cur:
                row = await cur.fetchone()
        if not row:
            await msg.reply_text("Antworte auf dein Haustier, nutze @username oder kaufe dir eines mit /buy.")
            return
        class Obj:
            pass
        pet = Obj()
        pet.id = row[0]
        pet.first_name = "Dein Haustier"
        pet.username = None

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

        care = await get_care(db, chat_id, pet.id)
        today = today_ymd()
        pet_state = await ensure_pet_dynamic_state(db, chat_id, pet.id, owner.id, today)
        async with db.execute(
            "SELECT COALESCE(pet_xp,0) FROM pets WHERE chat_id=? AND pet_id=?",
            (chat_id, pet.id)
        ) as cur:
            prog_row = await cur.fetchone()
        prev_bond = int(prog_row[0]) if prog_row else 0
        prev_bond_title = pet_bond_title(prev_bond)

        now = int(time.time())
        hostage_line = None
        if int(pet_state.get("hostage_until") or 0) > now:
            await db.execute(
                "UPDATE pets SET hostage_until=0 WHERE chat_id=? AND pet_id=?",
                (chat_id, pet.id)
            )
            pet_state["hostage_until"] = 0
            hostage_line = f"{nice_name_html(pet)} ist nicht mehr Geisel. Die Leine sitzt wieder normal."

        care_window_since = now - RUNAWAY_HOURS * 3600
        care_window = await _care_count_in_window(db, chat_id, pet.id, owner.id, care_window_since)
        care_deficit = max(0, RUNAWAY_MIN_CARES_IN_WINDOW - (care_window + 1))
        runaway_due = await _should_runaway(
            db,
            chat_id,
            pet.id,
            owner.id,
            care["acquired_ts"] if care else None,
            now,
            care_window=care_window + 1
        )
        prev_rebellion_stage = int(pet_state.get("breakout_count") or 0)
        rebellion_stage = 0
        rebellion_line = None
        if (care["acquired_ts"] if care else None) and now - int(care["acquired_ts"]) >= RUNAWAY_HOURS * 3600:
            rebellion_stage = max(prev_rebellion_stage, rebellion_stage_from_deficit(care_deficit, runaway_due, care_window))

        if rebellion_stage >= 4:
            await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id))
            await _apply_runaway_owner_penalty(db, chat_id, owner.id)
            await db.commit()
            await msg.reply_text(
                rebellion_drama_text(
                    rebellion_stage,
                    nice_name_html(pet),
                    mention_html(owner.id, owner.username or None),
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        if rebellion_stage > 0:
            rebellious_until = max(int(pet_state["rebellious_until"]), now + REBELLIOUS_DURATION_S)
            await db.execute(
                "UPDATE pets SET rebellious_until=?, breakout_count=MAX(COALESCE(breakout_count, 0), ?) WHERE chat_id=? AND pet_id=?",
                (rebellious_until, rebellion_stage, chat_id, pet.id)
            )
            pet_state["rebellious_until"] = rebellious_until
            pet_state["breakout_count"] = rebellion_stage
            rebellion_line = rebellion_drama_text(
                rebellion_stage,
                nice_name_html(pet),
                mention_html(owner.id, owner.username or None),
            )
            if rebellion_stage >= 2 and prev_rebellion_stage < 2:
                async with db.execute(
                    "SELECT COALESCE(coins,0) FROM players WHERE chat_id=? AND user_id=?",
                    (chat_id, owner.id)
                ) as cur:
                    owner_coin_row = await cur.fetchone()
                owner_coins = int(owner_coin_row[0]) if owner_coin_row else 0
                tribute = max(1, owner_coins * 5 // 100) if owner_coins > 0 else 0
                if tribute > 0:
                    await db.execute(
                        "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                        (tribute, chat_id, owner.id)
                    )
                    await db.execute(
                        "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                        (tribute, chat_id, pet.id)
                    )
                    rebellion_line += f"\n{nice_name_html(pet)} klaut <b>{tribute}</b> Coins Owner-Tribut."

        if rebellion_stage >= 3 and action_key in STRICT_CARE_ACTIONS:
            await db.commit()
            await msg.reply_text(
                f"{nice_name_html(pet)} verweigert diese Aktion. Erst sanft führen: /pet, /kuessen, /fuettern, /massage, /loben oder /belohnen.",
                parse_mode=ParseMode.HTML,
            )
            return

        cd_key = f"care:{action_key}:{owner.id}:{pet.id}"
        left = await get_cd_left(db, chat_id, owner.id, cd_key)
        if left > 0:
            await msg.reply_text("Langsam, Casanova. Etwas Geduld.")
            return

        done = care["done"] if (care and care["day"] == today) else 0
        if done >= CARES_PER_DAY:
            await msg.reply_text("Heute ist das Haustier bereits bestens versorgt. Morgen wieder.")
            return

        done += 1
        await set_care(db, chat_id, pet.id, now, done, today)

        bond_text = None
        style_delta = _care_style_delta(action_key)
        imprint_score = max(-12, min(12, int(pet_state["imprint_score"]) + style_delta))
        rebellious_penalty = 1 if int(pet_state["rebellious_until"] or 0) > now else 0
        gained_bond = max(1, CARE_XP_PER_ACTION - rebellious_penalty)
        new_bond = prev_bond + gained_bond
        current_fullcare_days = 0
        current_fullcare_streak = 0
        bonus_text = None
        jealousy_line = None
        if done >= CARES_PER_DAY:
            async with db.execute(
                "SELECT pet_skill, care_bonus_day, COALESCE(fullcare_streak, 0), fullcare_last_day, COALESCE(fullcare_days, 0) "
                "FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, pet.id)
            ) as cur:
                prow = await cur.fetchone()
            skill_key = prow[0] if prow else None
            care_bonus_day = prow[1] if prow else None
            prev_streak = int(prow[2]) if prow and prow[2] is not None else 0
            last_full_day = prow[3] if prow else None
            prev_fullcare_days = int(prow[4]) if prow and prow[4] is not None else 0

            yesterday = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
            streak = (prev_streak + 1) if last_full_day == yesterday else 1
            fullcare_days = prev_fullcare_days + 1
            current_fullcare_days = fullcare_days
            current_fullcare_streak = streak
            if rebellion_stage < 1:
                gained_bond += FULL_CARE_XP_BONUS
            new_bond = prev_bond + gained_bond
            await db.execute(
                "UPDATE pets SET pet_xp=?, fullcare_streak=?, fullcare_last_day=?, fullcare_days=?, imprint_score=?, rebellious_until=0, breakout_count=0 "
                "WHERE chat_id=? AND pet_id=?",
                (new_bond, streak, today, fullcare_days, imprint_score, chat_id, pet.id)
            )

            mood = render_pet_mood(pet_state["mood_name"], done, streak, 0, now)
            bonus_lines = [
                f"Bindung heute: +{gained_bond} ({done}x Pflege{' + Full-Care-Bonus' if rebellion_stage < 1 else ' - Rebellion ignoriert Bonus'}).",
                f"Bindung gesamt: <b>{new_bond}</b> | Wesen: <b>{escape(pet_bond_title(new_bond), False)}</b>.",
                f"Laune: <b>{escape(mood, False)}</b> | Prägung: <b>{escape(pet_imprint_label(imprint_score), False)}</b>.",
                f"Perfekte Tage gesamt: <b>{fullcare_days}</b>.",
                f"Streak voller Tage: <b>{streak}</b>.",
            ]

            if skill_key == "goldesel" and care_bonus_day != today and rebellion_stage < 1:
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (FULL_CARE_OWNER_BONUS, chat_id, owner.id)
                )
                await db.execute(
                    "UPDATE pets SET care_bonus_day=? WHERE chat_id=? AND pet_id=?",
                    (today, chat_id, pet.id)
                )
                bonus_lines.append(
                    f"Skill-Bonus <b>{escape(_skill_meta(skill_key)['name'], False)}</b>: {mention_html(owner.id, owner.username or None)} "
                    f"bekommt +{FULL_CARE_OWNER_BONUS} Coins für {CARES_PER_DAY}/{CARES_PER_DAY} Pflege."
                )
            elif skill_key == "goldesel" and rebellion_stage >= 1:
                bonus_lines.append("Skill-Bonus blockiert: Rebellion ignoriert das Schoßopfer.")
            until_ts = await set_temp_title(
                db,
                chat_id=chat_id,
                user_id=owner.id,
                title=TITLE_MASTEROFPUPPETS,
                duration_s=TITLE_DURATION_S,
            )
            mins = max(1, (until_ts - int(time.time())) // 60)
            title_line = (
                f"Titel aktiv: {mention_html(owner.id, owner.username or None)} ist jetzt "
                f"<b>{escape(TITLE_MASTEROFPUPPETS, False)}</b> für {mins} Minuten."
            )
            bonus_lines.append(title_line)
            prestige_title, prestige_until = await maybe_grant_owner_prestige_title(db, chat_id, owner.id, today)
            if prestige_title and prestige_until and prestige_title != TITLE_MASTEROFPUPPETS:
                mins = max(1, (prestige_until - int(time.time())) // 60)
                bonus_lines.append(
                    f"Prestige eskaliert: {mention_html(owner.id, owner.username or None)} trägt jetzt "
                    f"<b>{escape(prestige_title, False)}</b> für {mins} Minuten."
                )
            bonus_text = "\n".join(bonus_lines)
        else:
            await db.execute(
                "UPDATE pets SET pet_xp=?, imprint_score=? WHERE chat_id=? AND pet_id=?",
                (new_bond, imprint_score, chat_id, pet.id)
            )
            if int(pet_state["owner_pet_count"]) >= 2 and pet_state["mood_name"] in {"Besitzergreifend", "Fordernd", "Provokant"}:
                async with db.execute(
                    """
                    SELECT p.pet_id, pl.username
                    FROM pets p
                    LEFT JOIN players pl ON pl.chat_id=p.chat_id AND pl.user_id=p.pet_id
                    WHERE p.chat_id=? AND p.owner_id=? AND p.pet_id<>?
                    ORDER BY COALESCE(p.last_care_ts, 0) DESC, p.pet_id ASC
                    LIMIT 1
                    """,
                    (chat_id, owner.id, pet.id)
                ) as cur:
                    sibling_row = await cur.fetchone()
                if sibling_row:
                    sibling_id = int(sibling_row[0])
                    sibling_name = sibling_row[1] if len(sibling_row) > 1 else None
                    jealousy_line = random.choice(JEALOUSY_LINES).format(
                        pet=nice_name_html(pet),
                        other_pet=mention_html(sibling_id, sibling_name or None),
                    )

        new_bond_title = pet_bond_title(new_bond)
        if new_bond_title != prev_bond_title:
            bond_text = (
                f"Neue Bindung: <b>{escape(new_bond_title, False)}</b> | "
                f"{nice_name_html(pet)} | Owner: {mention_html(owner.id, owner.username or None)} | "
                f"Pflege <b>{done}/{CARES_PER_DAY}</b> | Prägung: <b>{escape(pet_imprint_label(imprint_score), False)}</b>"
            )

        await set_cd(db, chat_id, owner.id, cd_key, CARE_COOLDOWN_S)
        await db.commit()

    configured_lines = get_cached_json(context, "care_responses", CARE_RESPONSES_PATH).get(action_key) or tame_lines
    style_lines = CARE_STYLE_LINES.get(action_key, [])
    cool_lines = CARE_COOL_TEXTS.get(action_key) or []
    lines = (style_lines * 3) + cool_lines + configured_lines
    text = random.choice(lines)
    text = text.replace("{CARES_PER_DAY}", str(CARES_PER_DAY)).replace("{pets}", "{pet}")
    text = text.format(owner=nice_name_html(owner), pet=nice_name_html(pet), n=done)
    reply_msg = await msg.reply_text(text)
    cleanup_message_ids = [msg.message_id, reply_msg.message_id]
    if bond_text:
        await _send_or_replace_level_message(context, chat_id, msg, bond_text)
    if bonus_text:
        bonus_msg = await msg.reply_text(bonus_text, parse_mode=ParseMode.HTML)
        cleanup_message_ids.append(bonus_msg.message_id)
    if rebellion_line:
        rebel_msg = await msg.reply_text(rebellion_line, parse_mode=ParseMode.HTML)
        cleanup_message_ids.append(rebel_msg.message_id)
    if hostage_line:
        hostage_msg = await msg.reply_text(hostage_line, parse_mode=ParseMode.HTML)
        cleanup_message_ids.append(hostage_msg.message_id)
    if jealousy_line:
        jealous_msg = await msg.reply_text(jealousy_line, parse_mode=ParseMode.HTML)
        cleanup_message_ids.append(jealous_msg.message_id)
    if done % CARES_PER_DAY == 0:
        progress_mood = render_pet_mood(pet_state["mood_name"], done, current_fullcare_streak, 0, now)
        finish_line = random.choice(random.choice(FULL_CARE_FINISH_POOLS))
        progress_text = (
            f"Pflege-Stand: {nice_name_html(owner)} hat {nice_name_html(pet)} "
            f"<b>{done}/{CARES_PER_DAY}</b> gepflegt. "
            f"Bindung: <b>{new_bond}</b> | Wesen: <b>{escape(pet_bond_title(new_bond), False)}</b> | "
            f"Laune: <b>{escape(progress_mood, False)}</b> | Prägung: <b>{escape(pet_imprint_label(imprint_score), False)}</b>.\n"
            f"{escape(finish_line, False)}"
        )
        await _send_or_replace_level_message(context, chat_id, msg, progress_text)

    care_map = context.application.bot_data.setdefault("care_map", {})
    if len(care_map) > 1000:
        care_map.clear()
    meta = {
        "pet_id": pet.id,
        "owner_id": owner.id,
        "action": action_key,
        "ts": int(time.time()),
        "bot_msg_id": reply_msg.message_id,
        "owner_msg_id": msg.message_id
    }
    care_map[(chat_id, reply_msg.message_id)] = meta
    care_map[(chat_id, msg.message_id)] = meta

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO care_events(chat_id, message_id, pet_id, owner_id, action, ts) VALUES(?,?,?,?,?,?)",
            (chat_id, reply_msg.message_id, pet.id, owner.id, action_key, meta["ts"])
        )
        await db.execute(
            "INSERT OR REPLACE INTO care_events(chat_id, message_id, pet_id, owner_id, action, ts) VALUES(?,?,?,?,?,?)",
            (chat_id, msg.message_id, pet.id, owner.id, action_key, meta["ts"])
        )
        await db.commit()

    if context.job_queue:
        context.job_queue.run_once(
            _delete_messages_job,
            when=CARE_CHAT_CLEANUP_S,
            data={"chat_id": chat_id, "message_ids": cleanup_message_ids},
            name=f"care_cleanup:{chat_id}:{msg.message_id}"
        )


async def cmd_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return

    chat_id = update.effective_chat.id
    sender = update.effective_user
    target = msg.reply_to_message.from_user

    async with aiosqlite.connect(DB) as db:
        await _ensure_player_entry(db, chat_id, sender.id, sender.username or sender.full_name or "")
        await _ensure_player_entry(db, chat_id, target.id, target.username or target.full_name or "")

        async with db.execute(
            "SELECT gender FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, target.id)
        ) as cur:
            row = await cur.fetchone()
        if not row or row[0] != "f":
            return await msg.reply_text("Nur bei Frauen.")

        async with db.execute(
            "SELECT gender FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, sender.id)
        ) as cur:
            sender_row = await cur.fetchone()
        sender_gender = sender_row[0] if sender_row else ""
        if sender_gender == "f":
            line = random.choice(DOM_FEMALE_DENY_LINES)
            return await msg.reply_text(line)

        bonus = 2 if sender_gender == "m" else 0
        if bonus > 0:
            await db.execute(
                "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                (bonus, chat_id, sender.id)
            )
        await db.commit()

    responses = get_cached_json(context, "dom_responses", DOM_RESPONSES_PATH).get("dom", [])
    owner_tag = mention_html(sender.id, sender.username or None)
    pet_tag = mention_html(target.id, target.username or None)
    if responses:
        line = random.choice(responses)
        try:
            text = line.format(owner=owner_tag, pet=pet_tag, target=pet_tag, coins=bonus)
        except Exception:
            text = line
        try:
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await msg.reply_text(text)
            except Exception:
                pass
    else:
        text = f"+{bonus} Coins" if bonus > 0 else "Ok."
        try:
            await msg.reply_text(text)
        except Exception:
            pass

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
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.effective_message
    if not msg or not getattr(msg, "text", None) or msg.text.startswith("/"):
        return

    chat_id = update.effective_chat.id

    async with aiosqlite.connect(DB) as db:
        runtime = await get_runtime_settings(db, chat_id)
        if not runtime["auto_curse_enabled"]:
            await db.commit()
            return
        left = await get_cd_left(db, chat_id, 0, "autocurse")
        if left > 0:
            return

        if random.random() > AUTO_CURSE_CHANCE_PER_MESSAGE:
            return

        uid, uname = await pick_random_player_excluding(chat_id, exclude_ids={update.effective_user.id})
        if not uid:
            return

        shield_left = await get_cd_left(db, chat_id, uid, CURSE_SHIELD_KEY)
        if shield_left > 0:
            user = mention_html(uid, uname)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"Auto-Fluch geblockt!\n{user} war geschützt und bleibt unversehrt.\n"
                    f"<b>Fluchschild aktiv:</b> {_format_duration_compact(shield_left)}"
                ),
                parse_mode=ParseMode.HTML
            )
            await set_cd(db, chat_id, 0, "autocurse", AUTO_CURSE_COOLDOWN_S)
            await db.commit()
            return

        user = mention_html(uid, uname)
        curse_text = render_curse_text(user)
        await db.execute(
            "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
            (DAILY_CURSE_PENALTY, chat_id, uid)
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Auto-Fluch!\n{curse_text}",
            parse_mode=ParseMode.HTML
        )

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
    if (msg.text or "").strip().casefold() == "g":
        return
    if getattr(msg, "forward_date", None):
        return

    await mark_chat_and_maybe_announce(context, chat.id)
    await maybe_auto_curse(update, context)

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat.id, user.id, user.username or user.full_name or "")

        now = int(time.time())
        await db.execute(
            "UPDATE players SET last_seen=? WHERE chat_id=? AND user_id=?",
            (now, chat.id, user.id)
        )

        # Superworte (pro Chat mit 4-Tage-Cooldown pro Wort, global für alle User)
        msg_text = msg.text or ""
        msg_norm = normalize_superword_text(msg_text)
        for word in SUPERWORDS:
            pattern = superword_pattern(word)
            if not pattern or not re.search(pattern, msg_norm):
                continue
            found_key = superword_key(word)
            if not found_key:
                continue
            claimed = await claim_superword_once(db, chat.id, found_key, user.id, SUPERWORD_COOLDOWN_S)
            if not claimed:
                continue
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (SUPERWORD_REWARD, chat.id, user.id)
            )
            await db.commit()
            try:
                await msg.reply_text(
                    f"✨ Superwort gefunden: <b>{escape(word)}</b> +{SUPERWORD_REWARD} Coins",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
            break

        love = await _get_active_love_for_user(db, chat.id, user.id)
        if love and love_text_ok(msg.text, LOVE_TEXT_RULES):
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (LOVE_REWARD, chat.id, user.id)
            )
            await _finish_love(db, chat.id, user.id)
            await db.commit()
            try:
                await msg.reply_text(
                    f"OK {mention_html(user.id, user.username or None)} hat's geschafft. +{LOVE_REWARD} Coins. Ab jetzt ein Monat lang: 'mein Liebesgeständnis'.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
            return

        # Moralsteuer prüfen
        deducted, tax_message = await apply_moraltax_if_needed(db, chat.id, user.id, msg.text)
        if tax_message:
            try:
                await msg.reply_text(tax_message)
            except Exception:
                pass

        # Reward prüfen – NUR wenn KEINE Moralsteuer ausgelöst wurde (damit's fair bleibt)
        if deducted is None or deducted == 0:  # Kein Abzug oder pleite
            rewarded, reward_message = await apply_reward_if_needed(db, chat.id, user.id, msg.text)
            if reward_message:
                try:
                    await msg.reply_text(reward_message)
                except Exception:
                    pass

        # Normale Nachrichten-Belohnung (wie bisher)
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
# verfluchen
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

        shield_left = await get_cd_left(db, chat_id, tid, CURSE_SHIELD_KEY)
        if shield_left > 0:
            user = mention_html(tid, tname)
            return await update.effective_message.reply_text(
                f"{user} war geschützt.\n<b>Fluchschild aktiv:</b> {_format_duration_compact(shield_left)}",
                parse_mode=ParseMode.HTML
            )

        await db.execute(
            "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
            (DAILY_CURSE_PENALTY, chat_id, tid)
        )
        await db.commit()

    user = mention_html(tid, tname)
    curse_text = render_curse_text(user)
    await update.effective_message.reply_text(curse_text, parse_mode=ParseMode.HTML)


# =========================
# Boxen / Coin-Sink
# =========================
async def cmd_boxen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Boxen</b>\n\n"
        f"1. Kellerkiste - <b>{BOX_STANDARD_COST}</b> Coins\n"
        "Coins, Bindung, Fluchschild oder ein brutaler Titel.\n"
        "Kaufen: <code>/buyboxkeller</code> oder <code>/buybox keller</code>\n\n"
        f"2. Abyss-Kiste - <b>{BOX_ABYSS_COST}</b> Coins\n"
        "Größere Drops, größere Treffer, größere Schmerzen.\n"
        "Kaufen: <code>/buyboxabyss</code> oder <code>/buybox abyss</code>\n\n"
        "Wer zu lang auf seinen Coins sitzt, fault mit ihnen zusammen."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


def _min_box_coin_payout(cost: int) -> int:
    return (int(cost) * 13 + 9) // 10


async def _open_loot_box(
    update: Update,
    cost: int,
    box_name: str,
    title_pool: list[str],
    title_duration_s: int,
    abyss: bool = False,
):
    if not is_group(update):
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    msg = update.effective_message

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, user.id, user.username or user.full_name or "")

        async with db.execute(
            "SELECT coins FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, user.id)
        ) as cur:
            row = await cur.fetchone()
        coins = int(row[0]) if row else 0
        before_balance = coins
        if before_balance < cost:
            return await msg.reply_text(
                f"Zu teuer. {box_name} kostet {cost} Coins. Dein Guthaben: {before_balance}."
            )

        await db.execute(
            "UPDATE players SET coins = coins - ? WHERE chat_id=? AND user_id=?",
            (cost, chat_id, user.id)
        )

        roll = random.random()
        title = None
        body = ""
        flavor = random.choice(BOX_ABYSS_FLAVOR_TEXTS if abyss else BOX_STANDARD_FLAVOR_TEXTS)

        if abyss:
            if roll < 0.32:
                min_gain = _min_box_coin_payout(cost)
                gain = random.randint(min_gain, max(min_gain, 28000))
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (gain, chat_id, user.id)
                )
                body = random.choice(BOX_ABYSS_COIN_TEXTS).format(amount=gain)
            elif roll < 0.52:
                body = random.choice(BOX_ABYSS_EMPTY_TEXTS)
            elif roll < 0.66:
                extra_loss = random.randint(2000, 6000)
                await db.execute(
                    "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
                    (extra_loss, chat_id, user.id)
                )
                body = random.choice(BOX_ABYSS_LOSS_TEXTS).format(amount=extra_loss)
            elif roll < 0.78:
                await set_cd(db, chat_id, user.id, CURSE_SHIELD_KEY, 12 * 3600)
                body = random.choice(BOX_ABYSS_SHIELD_TEXTS)
            elif roll < 0.88:
                pet_id = await _get_latest_owned_pet_id(db, chat_id, user.id)
                if pet_id:
                    xp_gain = random.randint(45, 100)
                    async with db.execute(
                        "SELECT COALESCE(pet_xp, 0) FROM pets WHERE chat_id=? AND pet_id=?",
                        (chat_id, pet_id)
                    ) as cur:
                        pet_row = await cur.fetchone()
                    new_xp = int((pet_row[0] if pet_row else 0) or 0) + xp_gain
                    await db.execute(
                        "UPDATE pets SET pet_xp=? WHERE chat_id=? AND pet_id=?",
                        (new_xp, chat_id, pet_id)
                    )
                    body = random.choice(BOX_ABYSS_XP_TEXTS).format(amount=xp_gain)
                else:
                    min_fallback = _min_box_coin_payout(cost)
                    fallback = random.randint(min_fallback, max(min_fallback, 22000))
                    await db.execute(
                        "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                        (fallback, chat_id, user.id)
                    )
                    body = random.choice(BOX_ABYSS_FALLBACK_TEXTS).format(amount=fallback)
            elif roll < 0.95:
                title = random.choice(title_pool)
                await set_temp_title(db, chat_id, user.id, title, title_duration_s)
                body = random.choice(BOX_ABYSS_TITLE_TEXTS).format(
                    title=escape(title),
                    duration=_format_duration_compact(title_duration_s),
                )
            else:
                min_gain = _min_box_coin_payout(cost)
                gain = random.randint(max(min_gain, 28000), max(min_gain, 50000))
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (gain, chat_id, user.id)
                )
                title = random.choice(title_pool)
                await set_temp_title(db, chat_id, user.id, title, title_duration_s)
                body = random.choice(BOX_ABYSS_JACKPOT_TEXTS).format(
                    amount=gain,
                    title=escape(title),
                    duration=_format_duration_compact(title_duration_s),
                )
        else:
            if roll < 0.34:
                min_gain = _min_box_coin_payout(cost)
                gain = random.randint(min_gain, max(min_gain, 5000))
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (gain, chat_id, user.id)
                )
                body = random.choice(BOX_STANDARD_COIN_TEXTS).format(amount=gain)
            elif roll < 0.58:
                body = random.choice(BOX_STANDARD_EMPTY_TEXTS)
            elif roll < 0.74:
                extra_loss = random.randint(300, 1200)
                await db.execute(
                    "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
                    (extra_loss, chat_id, user.id)
                )
                body = random.choice(BOX_STANDARD_LOSS_TEXTS).format(amount=extra_loss)
            elif roll < 0.86:
                await set_cd(db, chat_id, user.id, CURSE_SHIELD_KEY, 6 * 3600)
                body = random.choice(BOX_STANDARD_SHIELD_TEXTS)
            elif roll < 0.96:
                pet_id = await _get_latest_owned_pet_id(db, chat_id, user.id)
                if pet_id:
                    xp_gain = random.randint(18, 40)
                    async with db.execute(
                        "SELECT COALESCE(pet_xp, 0) FROM pets WHERE chat_id=? AND pet_id=?",
                        (chat_id, pet_id)
                    ) as cur:
                        pet_row = await cur.fetchone()
                    new_xp = int((pet_row[0] if pet_row else 0) or 0) + xp_gain
                    await db.execute(
                        "UPDATE pets SET pet_xp=? WHERE chat_id=? AND pet_id=?",
                        (new_xp, chat_id, pet_id)
                    )
                    body = random.choice(BOX_STANDARD_XP_TEXTS).format(amount=xp_gain)
                else:
                    min_fallback = _min_box_coin_payout(cost)
                    fallback = random.randint(min_fallback, max(min_fallback, 4000))
                    await db.execute(
                        "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                        (fallback, chat_id, user.id)
                    )
                    body = random.choice(BOX_STANDARD_FALLBACK_TEXTS).format(amount=fallback)
            else:
                title = random.choice(title_pool)
                await set_temp_title(db, chat_id, user.id, title, title_duration_s)
                body = random.choice(BOX_STANDARD_TITLE_TEXTS).format(
                    title=escape(title),
                    duration=_format_duration_compact(title_duration_s),
                )

        async with db.execute(
            "SELECT coins FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, user.id)
        ) as cur:
            row = await cur.fetchone()
        new_balance = int(row[0]) if row else 0
        await db.commit()

    header = f"<b>{escape(box_name)}</b> für <b>{cost}</b> Coins geöffnet."
    footer = (
        f"<b>Vorher:</b> {before_balance} Coins\n"
        f"<b>Nachher:</b> {new_balance} Coins"
    )
    await msg.reply_text(f"{header}\n{flavor}\n{body}\n{footer}", parse_mode=ParseMode.HTML)


async def cmd_buybox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.effective_message.reply_text(
            "Nutzung: /buybox <keller|abyss>"
        )

    choice = (context.args[0] or "").strip().casefold()
    if choice in {"keller", "box", "kellerkiste", "1"}:
        return await _open_loot_box(
            update,
            cost=BOX_STANDARD_COST,
            box_name="Kellerkiste",
            title_pool=BOX_STANDARD_TITLES,
            title_duration_s=BOX_TITLE_DURATION_S,
            abyss=False,
        )
    if choice in {"abyss", "abyssbox", "abysskiste", "2"}:
        return await _open_loot_box(
            update,
            cost=BOX_ABYSS_COST,
            box_name="Abyss-Kiste",
            title_pool=BOX_ABYSS_TITLES,
            title_duration_s=BOX_ABYSS_TITLE_DURATION_S,
            abyss=True,
        )

    return await update.effective_message.reply_text(
        "Unbekannte Box. Nutze /buybox <keller|abyss>."
    )


async def cmd_buybox_keller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _open_loot_box(
        update,
        cost=BOX_STANDARD_COST,
        box_name="Kellerkiste",
        title_pool=BOX_STANDARD_TITLES,
        title_duration_s=BOX_TITLE_DURATION_S,
        abyss=False,
    )


async def cmd_buybox_abyss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _open_loot_box(
        update,
        cost=BOX_ABYSS_COST,
        box_name="Abyss-Kiste",
        title_pool=BOX_ABYSS_TITLES,
        title_duration_s=BOX_ABYSS_TITLE_DURATION_S,
        abyss=True,
    )


# =========================
# Preise, Balance, Top
# =========================
async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update): return
    chat_id = update.effective_chat.id
    active_cutoff = int(time.time()) - SUPERWORD_COOLDOWN_S
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

    chat_id = update.effective_chat.id
    caller = update.effective_user

    async with aiosqlite.connect(DB) as db:
        # bereits aktive Hass-Ziele sammeln
        active_ids = await _get_active_hass_user_ids(db, chat_id)
        active_ids.add(caller.id)  # Aufrufer nie Ziel

        # neuen Kandidaten wählen
        uid, uname = await pick_random_player_excluding(
            chat_id,
            exclude_ids=active_ids
        )

        if not uid:
            return await update.effective_message.reply_text(
                "Keine weiteren Opfer verfügbar. Alle anderen leiden bereits."
            )

        expires = await _start_hass(
            db,
            chat_id,
            int(uid),
            uname,
            caller.id
        )
        await db.commit()

        until = datetime.datetime.fromtimestamp(
            expires, tz=ZoneInfo(PETFLIX_TZ)
        ).strftime("%d.%m.%Y %H:%M")

        target = mention_html(int(uid), uname if uname else None)
        caller_tag = mention_html(caller.id, caller.username or None)

        await update.effective_message.reply_text(
            f"🖤 <b>/hass</b> scharfgestellt.\n"
            f"Ausgelöst von: {caller_tag}\n"
            f"Ziel: {target}\n"
            f"Challenge: <b>{HASS_REQUIRED}x /selbst</b> in 2 Stunden\n"
            f"Deadline: <b>{until}</b>\n"
            f"Belohnung bei Erfolg: <b>+{HASS_REWARD} Coins</b>\n"
            f"Strafe bei Versagen: <b>-{HASS_PENALTY} Coins</b>\n"
            f"Mehrere Hass-Ziele laufen parallel.",
            parse_mode=ParseMode.HTML
        )

async def _get_active_hass_user_ids(db, chat_id: int):
    async with db.execute("""
        SELECT user_id
        FROM hass_challenges
        WHERE chat_id=? AND active=1
    """, (chat_id,)) as cur:
        rows = await cur.fetchall()
    return {int(r[0]) for r in rows}

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
                    f"⌛ Zeit um. {mention_html(uid, uname if uname else None)} hat's nicht geschafft. -{penalty} Coins.",
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
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (HASS_REWARD, chat_id, uid)
            )
            await _finish_hass(db, chat_id, uid)
            await db.commit()
        await update.effective_message.reply_text(
            f"✅ {mention_html(uid, user.username or None)} hat's geschafft. Hass-Status beendet. +{HASS_REWARD} Coins.",
            parse_mode=ParseMode.HTML
        )

# ============== Liebesgeständnis

async def _start_love(db, chat_id: int, user_id: int, username: str | None, triggered_by: int):
    now = int(time.time())
    expires = now + LOVE_CHALLENGE_HOURS * 3600
    await db.execute("""
        INSERT INTO love_challenges(chat_id, user_id, username, triggered_by, started_ts, expires_ts, remind_stage, active)
        VALUES(?,?,?,?,?,?,0,1)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
          username=CASE
            WHEN TRIM(COALESCE(excluded.username, '')) <> '' THEN excluded.username
            ELSE love_challenges.username
          END,
          triggered_by=excluded.triggered_by,
          started_ts=excluded.started_ts,
          expires_ts=excluded.expires_ts,
          remind_stage=0,
          active=1
    """, (chat_id, user_id, username or "", triggered_by, now, expires))
    return expires

async def _finish_love(db, chat_id: int, user_id: int):
    await db.execute("UPDATE love_challenges SET active=0 WHERE chat_id=? AND user_id=?", (chat_id, user_id))

async def _get_active_love_for_user(db, chat_id: int, user_id: int):
    async with db.execute("""
        SELECT username, triggered_by, started_ts, expires_ts, remind_stage, active
        FROM love_challenges
        WHERE chat_id=? AND user_id=? AND active=1
    """, (chat_id, user_id)) as cur:
        return await cur.fetchone()

FEUD_STAGE_1_HEAT = 3
FEUD_STAGE_2_HEAT = 6
FEUD_STAGE_3_HEAT = 10
FEUD_ACTIVE_WINDOW_S = 48 * 3600
FEUD_REVENGE_WINDOW_S = 30 * 60
FEUD_REVENGE_CHANCE_BONUS = 0.15
FEUD_STAGE_BONUS = {
    0: {"chance": 0.00, "steal_pct": 0.00, "label": "Ruhe vor dem Diebstahl"},
    1: {"chance": 0.04, "steal_pct": 0.10, "label": "Erstes Blut"},
    2: {"chance": 0.08, "steal_pct": 0.20, "label": "Menschenjagd"},
    3: {"chance": 0.12, "steal_pct": 0.35, "label": "Hinrichtung"},
}
FEUD_STAGE_TRIGGER_LINES = {
    1: [
        "Zwischen {attacker} und {victim} ist das <b>Erste Blut</b> gefallen.",
        "{attacker} und {victim} haben die Schwelle überschritten. <b>Stufe 1: Erstes Blut</b>.",
    ],
    2: [
        "{attacker} gegen {victim}: Das kippt in offene <b>Menschenjagd</b>.",
        "Die Gruppe riecht Blut. {attacker} und {victim} stehen jetzt in <b>Stufe 2: Menschenjagd</b>.",
    ],
    3: [
        "{attacker} und {victim} sind komplett entgleist. <b>Hinrichtung</b> wurde ausgerufen.",
        "Alarm im Chat: {attacker} und {victim} haben <b>Stufe 3: Hinrichtung</b> erreicht.",
    ],
}

def feud_stage_from_heat(heat: int) -> int:
    value = max(0, int(heat or 0))
    if value >= FEUD_STAGE_3_HEAT:
        return 3
    if value >= FEUD_STAGE_2_HEAT:
        return 2
    if value >= FEUD_STAGE_1_HEAT:
        return 1
    return 0

def feud_stage_label(stage: int) -> str:
    return FEUD_STAGE_BONUS.get(int(stage or 0), FEUD_STAGE_BONUS[0])["label"]

def _feud_pair(user_x: int, user_y: int) -> tuple[int, int]:
    a = int(user_x)
    b = int(user_y)
    return (a, b) if a < b else (b, a)

def feud_revenge_key(other_user_id: int) -> str:
    return f"revenge:{int(other_user_id)}"

async def get_feud_state(db, chat_id: int, user_x: int, user_y: int) -> dict:
    user_a, user_b = _feud_pair(user_x, user_y)
    async with db.execute("""
        SELECT heat, clash_count, success_count, last_attack_ts,
               last_attacker_id, last_victim_id, active_until_ts
        FROM steal_feuds
        WHERE chat_id=? AND user_a=? AND user_b=?
    """, (chat_id, user_a, user_b)) as cur:
        row = await cur.fetchone()
    if not row:
        return {
            "heat": 0,
            "clash_count": 0,
            "success_count": 0,
            "last_attack_ts": 0,
            "last_attacker_id": None,
            "last_victim_id": None,
            "active_until_ts": 0,
            "stage": 0,
            "active": False,
        }
    heat = int(row[0] or 0)
    active_until_ts = int(row[6] or 0)
    active = active_until_ts > int(time.time())
    return {
        "heat": heat,
        "clash_count": int(row[1] or 0),
        "success_count": int(row[2] or 0),
        "last_attack_ts": int(row[3] or 0),
        "last_attacker_id": int(row[4]) if row[4] is not None else None,
        "last_victim_id": int(row[5]) if row[5] is not None else None,
        "active_until_ts": active_until_ts,
        "stage": feud_stage_from_heat(heat) if active else 0,
        "active": active,
    }

async def register_feud_clash(db, chat_id: int, attacker_id: int, victim_id: int, success: bool) -> dict:
    state_before = await get_feud_state(db, chat_id, attacker_id, victim_id)
    heat = int(state_before["heat"] or 0) + (2 if success else 1)
    clash_count = int(state_before["clash_count"] or 0) + 1
    success_count = int(state_before["success_count"] or 0) + (1 if success else 0)
    now = int(time.time())
    active_until_ts = now + FEUD_ACTIVE_WINDOW_S
    user_a, user_b = _feud_pair(attacker_id, victim_id)
    await db.execute("""
        INSERT INTO steal_feuds(
          chat_id, user_a, user_b, heat, clash_count, success_count,
          last_attack_ts, last_attacker_id, last_victim_id, active_until_ts
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(chat_id, user_a, user_b) DO UPDATE SET
          heat=excluded.heat,
          clash_count=excluded.clash_count,
          success_count=excluded.success_count,
          last_attack_ts=excluded.last_attack_ts,
          last_attacker_id=excluded.last_attacker_id,
          last_victim_id=excluded.last_victim_id,
          active_until_ts=excluded.active_until_ts
    """, (
        chat_id, user_a, user_b, heat, clash_count, success_count,
        now, attacker_id, victim_id, active_until_ts
    ))
    stage_before = int(state_before["stage"] or 0)
    stage_after = feud_stage_from_heat(heat)
    return {
        "heat": heat,
        "clash_count": clash_count,
        "success_count": success_count,
        "last_attack_ts": now,
        "last_attacker_id": attacker_id,
        "last_victim_id": victim_id,
        "active_until_ts": active_until_ts,
        "active": True,
        "stage": stage_after,
        "stage_changed": stage_after > stage_before,
    }

def format_feud_stage_trigger(stage: int, attacker_tag: str, victim_tag: str) -> str:
    lines = FEUD_STAGE_TRIGGER_LINES.get(int(stage or 0))
    if not lines:
        return ""
    return random.choice(lines).format(attacker=attacker_tag, victim=victim_tag)

async def _get_active_love_user_ids(db, chat_id: int):
    async with db.execute("""
        SELECT user_id FROM love_challenges WHERE chat_id=? AND active=1
    """, (chat_id,)) as cur:
        rows = await cur.fetchall()
    return {int(r[0]) for r in rows}

async def _pick_recent_active_user(db, chat_id: int, cutoff_ts: int, exclude_ids: set[int]):
    async with db.execute("""
        SELECT user_id, username
        FROM players
        WHERE chat_id=? AND last_seen IS NOT NULL AND last_seen >= ?
    """, (chat_id, cutoff_ts)) as cur:
        rows = await cur.fetchall()
    rows = [r for r in rows if r and int(r[0]) not in exclude_ids]
    if not rows:
        return None, None
    return random.choice(rows)

async def cmd_liebes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update) or update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    chat_id = update.effective_chat.id
    caller = update.effective_user
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return await msg.reply_text(
            "Bitte antworte auf eine Person und sende dann /liebes."
        )
    target_user = msg.reply_to_message.from_user
    uid = target_user.id
    uname = target_user.username or None
    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, uid, uname or target_user.full_name or "")
        if uid == ADMIN_ID:
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (LOVE_REWARD, chat_id, uid)
            )
            await db.commit()
            return await msg.reply_text(
                random.choice(LOVE_MASTER_LINES),
                parse_mode=ParseMode.HTML
            )

        active_ids = await _get_active_love_user_ids(db, chat_id)
        if uid in active_ids:
            return await msg.reply_text(
                "Für diese Person läuft bereits eine Liebes-Bombe."
            )

        expires = await _start_love(db, chat_id, int(uid), uname, caller.id)
        await db.commit()

    until = datetime.datetime.fromtimestamp(expires, tz=ZoneInfo(PETFLIX_TZ)).strftime("%d.%m.%Y %H:%M")
    target = mention_html(int(uid), uname if uname else None)
    caller_tag = mention_html(caller.id, caller.username or None)
    await update.effective_message.reply_text(
        (
            "💣 <b>Liebes-Bombe detoniert.</b>\n"
            f"Ausgelöst von: {caller_tag}\n"
            f"Ziel: {target}\n"
            f"Zeit: <b>{LOVE_CHALLENGE_HOURS}h</b> (Deadline: <b>{until}</b>)\n\n"
            "Jetzt gibt's kein Rumgeeier mehr: Du lieferst einen übertriebenen Liebesbrief in den Chat oder gehst komplett unter.\n"
            f"- Mindestens {LOVE_MIN_WORDS} Wörter\n"
            f"- Mindestens {LOVE_MIN_EMOJIS} Emojis (beliebig)\n"
            f"- Mindestens {LOVE_MIN_SENTENCES} Sätze (Satzzeichen optional)\n\n"
            "Der Bot wird dich zwischendurch jagen, falls du wieder nur dumm rumsitzt.\n"
            f"Ziehst du's durch: <b>+{LOVE_REWARD} Coins</b> + ein Monat lang 'mein Liebesgeständnis'.\n"
            f"Verkackst du's: <b>-{LOVE_PENALTY_PERCENT}% deiner Coins</b> und der Chat sieht, was für ein peinlicher Totalausfall du bist."
        ),
        parse_mode=ParseMode.HTML
    )


async def cmd_resetsuperwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("🚫 Nur der Bot-Admin darf das.")

    chat_id = update.effective_chat.id
    active_cutoff = int(time.time()) - SUPERWORD_COOLDOWN_S
    async with aiosqlite.connect(DB) as db:
        cleared = await count_active_superword_cooldowns(db, chat_id, active_cutoff)
        await db.execute("DELETE FROM superwords_found WHERE chat_id=?", (chat_id,))
        await db.commit()

    await update.effective_message.reply_text(
        f"Superwort-Cooldowns wurden zurückgesetzt. {cleared} aktuell gesperrte Superworte sind sofort wieder verfügbar."
    )


async def cmd_superwordsstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        return

    chat_id = update.effective_chat.id
    loaded_total = len(SUPERWORDS)
    unique_total = len(SUPERWORD_KEYS)
    active_cutoff = int(time.time()) - SUPERWORD_COOLDOWN_S
    async with aiosqlite.connect(DB) as db:
        found = await count_active_superword_cooldowns(db, chat_id, active_cutoff)

    remaining = max(0, unique_total - found)
    await update.effective_message.reply_text(
        (
            "✨ <b>Superwort-Status</b>\n"
            f"Geladene Einträge: <b>{loaded_total}</b>\n"
            f"Gesamt (eindeutige Superworte): <b>{unique_total}</b>\n"
            f"Aktuell gefundene Worte: <b>{found}</b>\n"
            f"Verbleibende Worte: <b>{remaining}</b>"
        ),
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

    # Erst nach @username / username irgendwo in den Args suchen.
    # Das erlaubt z.B. "/addcoins 60000 @name" statt nur "/addcoins @name 60000".
    chat_id = update.effective_chat.id

    for token in context.args:
        raw = token.strip().lstrip("@")
        if not raw or raw.isdigit():
            continue
        async with db.execute(
            "SELECT user_id, username FROM players WHERE chat_id=? AND lower(username)=lower(?)",
            (chat_id, raw)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return int(row[0]), (row[1] or raw)

    # Wenn nur Zahlen da sind, interpretieren wir die letzte Zahl als Betrag
    # und bevorzugen davor stehende Zahlen als Ziel-ID.
    numeric_tokens = [int(token.strip()) for token in context.args if token.strip().isdigit()]
    if len(numeric_tokens) >= 2:
        target_id = numeric_tokens[0]
        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, target_id)
        ) as cur:
            row = await cur.fetchone()
        return target_id, (row[0] if row else None)
    if len(numeric_tokens) == 1:
        target_id = numeric_tokens[0]
        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, target_id)
        ) as cur:
            row = await cur.fetchone()
        return target_id, (row[0] if row else None)
    return None, None

async def _ensure_player_entry(db, chat_id: int, user_id: int, username: str | None):
    await _ensure_player_entry_base(db, chat_id, user_id, username, START_COINS, USER_BASE_PRICE)

async def _get_coins(db, chat_id: int, user_id: int) -> int:
    return await _get_coins_base(db, chat_id, user_id)

def _parse_amount_from_args(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if context.args:
        for token in reversed(context.args):
            raw = token.strip()
            if raw.isdigit():
                return int(raw)
    return None


_RUNTIME_FEATURES = create_runtime_features({
    "aiosqlite": aiosqlite,
    "datetime": datetime,
    "os": os,
    "shutil": shutil,
    "time": time,
    "escape": escape,
    "ParseMode": ParseMode,
    "BACKUP_DIR": BACKUP_DIR,
    "BACKUP_KEEP_FILES": BACKUP_KEEP_FILES,
    "DB": DB,
    "MORAL_TAX_DEFAULT": MORAL_TAX_DEFAULT,
    "DAILY_CURSE_ENABLED": DAILY_CURSE_ENABLED,
    "AUTO_CURSE_ENABLED": AUTO_CURSE_ENABLED,
    "ALLOWED_CHAT_ID": ALLOWED_CHAT_ID,
    "_is_admin_here": _is_admin_here,
    "is_allowed_chat": is_allowed_chat,
    "log": log,
})
get_runtime_settings = _RUNTIME_FEATURES["get_runtime_settings"]
set_runtime_flag = _RUNTIME_FEATURES["set_runtime_flag"]
cmd_backupnow = _RUNTIME_FEATURES["cmd_backupnow"]
cmd_backups = _RUNTIME_FEATURES["cmd_backups"]
cmd_restorebackup = _RUNTIME_FEATURES["cmd_restorebackup"]
cmd_settings = _RUNTIME_FEATURES["cmd_settings"]
cmd_admin = _RUNTIME_FEATURES["cmd_admin"]
daily_backup_job = _RUNTIME_FEATURES["daily_backup_job"]
cmd_help = _RUNTIME_FEATURES["cmd_help"]
cmd_start = _RUNTIME_FEATURES["cmd_start"]

_OWNERSHIP_FEATURES = create_ownership_features({
    "aiosqlite": aiosqlite,
    "DB": DB,
    "time": time,
    "escape": escape,
    "MAX_CHUNK": MAX_CHUNK,
    "ALLOWED_CHAT_ID": ALLOWED_CHAT_ID,
    "is_group": is_group,
    "get_user_price": get_user_price,
    "get_pet_skill": get_pet_skill,
    "_skill_label": _skill_label,
    "pet_bond_title": pet_bond_title,
    "pet_bond_percent": pet_bond_percent,
    "pet_mood_label": pet_mood_label,
    "render_pet_mood": render_pet_mood,
    "pet_imprint_label": pet_imprint_label,
    "pet_status_label": pet_status_label,
    "pet_level_title": pet_level_title,
    "fullcare_evolution_title": fullcare_evolution_title,
    "get_pet_lock_until": get_pet_lock_until,
    "get_active_titles_map": get_active_titles_map,
    "with_title_suffix": with_title_suffix,
    "_skill_meta": _skill_meta,
    "get_active_brand_labels": None,
})
get_owner_id = _OWNERSHIP_FEATURES["get_owner_id"]
set_owner = _OWNERSHIP_FEATURES["set_owner"]
cmd_top = _OWNERSHIP_FEATURES["cmd_top"]
cmd_profil = _OWNERSHIP_FEATURES["cmd_profil"]
cmd_owner = _OWNERSHIP_FEATURES["cmd_owner"]
cmd_ownerlist = _OWNERSHIP_FEATURES["cmd_ownerlist"]
cmd_release = _OWNERSHIP_FEATURES["cmd_release"]

_ECONOMY_COMMANDS = create_economy_commands({
    "aiosqlite": aiosqlite,
    "DB": DB,
    "ParseMode": ParseMode,
    "random": random,
    "is_group": is_group,
    "_parse_amount_from_args": _parse_amount_from_args,
    "_resolve_target": _resolve_target,
    "_ensure_player_entry": _ensure_player_entry,
    "_get_coins": _get_coins,
    "mention_html": mention_html,
    "ensure_player": ensure_player,
    "get_cd_left": get_cd_left,
    "set_cd": set_cd,
    "DAILY_COINS": DAILY_COINS,
    "DAILY_COOLDOWN_S": DAILY_COOLDOWN_S,
    "BLACKJACK_COOLDOWN_S": BLACKJACK_COOLDOWN_S,
    "BLACKJACK_MIN_BET": BLACKJACK_MIN_BET,
    "BLACKJACK_MAX_BET": BLACKJACK_MAX_BET,
    "BLACKJACK_OUTCOMES": BLACKJACK_OUTCOMES,
})
cmd_balance = _ECONOMY_COMMANDS["cmd_balance"]
cmd_gift = _ECONOMY_COMMANDS["cmd_gift"]
cmd_daily = _ECONOMY_COMMANDS["cmd_daily"]
cmd_blackjack = _ECONOMY_COMMANDS["cmd_blackjack"]
cmd_id = _ECONOMY_COMMANDS["cmd_id"]

_JOBS_WATCHDOGS = create_jobs_watchdogs({
    "aiosqlite": aiosqlite,
    "time": time,
    "ParseMode": ParseMode,
    "random": random,
    "ALLOWED_CHAT_ID": ALLOWED_CHAT_ID,
    "today_ymd": today_ymd,
    "_today_bounds_unix": _today_bounds_unix,
    "_pick_recent_active_user": _pick_recent_active_user,
    "get_cd_left": get_cd_left,
    "set_cd": set_cd,
    "_secs_until_tomorrow": _secs_until_tomorrow,
    "_pick_random_player": _pick_random_player,
    "_mention_from_uid_username": _mention_from_uid_username,
    "_SAVAGE_LINES": _SAVAGE_LINES,
    "DAILY_GIFT_COINS": DAILY_GIFT_COINS,
    "get_runtime_settings": get_runtime_settings,
    "DAILY_CURSE_PENALTY": DAILY_CURSE_PENALTY,
    "DAILY_PRIMETIME_COINS": DAILY_PRIMETIME_COINS,
    "mention_html": mention_html,
    "CURSE_SHIELD_KEY": CURSE_SHIELD_KEY,
    "FLUCH_LINES": FLUCH_LINES,
    "render_curse_text": render_curse_text,
    "_format_duration_compact": _format_duration_compact,
    "_apply_hass_penalty": _apply_hass_penalty,
    "_finish_hass": _finish_hass,
    "_finish_love": _finish_love,
    "LOVE_PENALTY_PERCENT": LOVE_PENALTY_PERCENT,
    "LOVE_REMIND_1_S": LOVE_REMIND_1_S,
    "LOVE_REMIND_2_S": LOVE_REMIND_2_S,
    "_care_count_last_24h": _care_count_last_24h,
    "MIN_CARES_PER_24H": MIN_CARES_PER_24H,
    "LEVEL_DECAY_XP": LEVEL_DECAY_XP,
    "pet_level_from_xp": pet_level_from_xp,
    "LEVEL_DECAY_INTERVAL_S": LEVEL_DECAY_INTERVAL_S,
    "_should_runaway": _should_runaway,
    "_apply_runaway_owner_penalty": _apply_runaway_owner_penalty,
    "runaway_text": runaway_text,
    "DB": DB,
})
daily_gift_job = _JOBS_WATCHDOGS["daily_gift_job"]
daily_curse_job = _JOBS_WATCHDOGS["daily_curse_job"]
daily_primetime_job = _JOBS_WATCHDOGS["daily_primetime_job"]
hass_watchdog_job = _JOBS_WATCHDOGS["hass_watchdog_job"]
love_watchdog_job = _JOBS_WATCHDOGS["love_watchdog_job"]
runaway_watchdog_job = _JOBS_WATCHDOGS["runaway_watchdog_job"]


_ADMIN_COIN_CMDS = create_admin_coin_commands({
    "aiosqlite": aiosqlite,
    "DB": DB,
    "ADMIN_ID": ADMIN_ID,
    "ParseMode": ParseMode,
    "escape": escape,
    "random": random,
    "load_json_dict": load_json_dict,
    "STEAL_TEXTS_PATH": STEAL_TEXTS_PATH,
    "STEAL_SUCCESS_CHANCE": STEAL_SUCCESS_CHANCE,
    "STEAL_COOLDOWN_S": STEAL_COOLDOWN_S,
    "STEAL_FAIL_PENALTY_RATIO": STEAL_FAIL_PENALTY_RATIO,
    "CARES_PER_DAY": CARES_PER_DAY,
    "FEUD_REVENGE_WINDOW_S": FEUD_REVENGE_WINDOW_S,
    "FEUD_REVENGE_CHANCE_BONUS": FEUD_REVENGE_CHANCE_BONUS,
    "FEUD_STAGE_BONUS": FEUD_STAGE_BONUS,
    "set_cd": set_cd,
    "get_cd_left": get_cd_left,
    "mention_html": mention_html,
    "format_duration": _format_duration_compact,
    "today_ymd": today_ymd,
    "is_group": is_group,
    "_is_admin_here": _is_admin_here,
    "_resolve_target": _resolve_target,
    "_ensure_player_entry": _ensure_player_entry,
    "_get_coins": _get_coins,
    "_parse_amount_from_args": _parse_amount_from_args,
    "get_feud_state": get_feud_state,
    "register_feud_clash": register_feud_clash,
    "feud_revenge_key": feud_revenge_key,
    "feud_stage_label": feud_stage_label,
    "format_feud_stage_trigger": format_feud_stage_trigger,
})
cmd_adminping = _ADMIN_COIN_CMDS["cmd_adminping"]
cmd_careminus = _ADMIN_COIN_CMDS["cmd_careminus"]
cmd_addcoins = _ADMIN_COIN_CMDS["cmd_addcoins"]
cmd_takecoins = _ADMIN_COIN_CMDS["cmd_takecoins"]
cmd_setcoins = _ADMIN_COIN_CMDS["cmd_setcoins"]
cmd_resetcoins = _ADMIN_COIN_CMDS["cmd_resetcoins"]
cmd_steal = _ADMIN_COIN_CMDS["cmd_steal"]
cmd_snatchsteal = _ADMIN_COIN_CMDS["cmd_snatchsteal"]
cmd_fehde = _ADMIN_COIN_CMDS["cmd_fehde"]

_BRAND_FEATURES = create_brand_features({
    "aiosqlite": aiosqlite,
    "datetime": datetime,
    "random": random,
    "escape": escape,
    "DB": DB,
    "ParseMode": ParseMode,
    "is_group": is_group,
    "mention_html": mention_html,
    "_ensure_player_entry": _ensure_player_entry,
    "_get_coins": _get_coins,
})
cmd_brandshop = _BRAND_FEATURES["cmd_brandshop"]
cmd_brandkaufen = _BRAND_FEATURES["cmd_brandkaufen"]
cmd_brandsetzen = _BRAND_FEATURES["cmd_brandsetzen"]
cmd_meinebrands = _BRAND_FEATURES["cmd_meinebrands"]
cmd_brandpet = _BRAND_FEATURES["cmd_brandpet"]
cmd_brandablegen = _BRAND_FEATURES["cmd_brandablegen"]
get_active_brand_labels = _BRAND_FEATURES["get_active_brand_labels"]

async def _fetch_gender_candidates(db, chat_id: int, include_assigned: bool):
    if include_assigned:
        sql = "SELECT user_id, username FROM players WHERE chat_id=? ORDER BY user_id"
        params = (chat_id,)
    else:
        sql = "SELECT user_id, username FROM players WHERE chat_id=? AND (gender IS NULL OR gender='') ORDER BY user_id"
        params = (chat_id,)
    async with db.execute(sql, params) as cur:
        return await cur.fetchall()

async def _gender_counts(db, chat_id: int):
    async with db.execute("SELECT COUNT(*) FROM players WHERE chat_id=?", (chat_id,)) as cur:
        total_row = await cur.fetchone()
    async with db.execute(
        "SELECT COUNT(*) FROM players WHERE chat_id=? AND (gender IS NULL OR gender='')",
        (chat_id,)
    ) as cur:
        open_row = await cur.fetchone()
    total = int(total_row[0]) if total_row else 0
    open_count = int(open_row[0]) if open_row else 0
    return total, open_count

def _gender_prompt_text(user_id: int, username: str | None, index: int, total: int) -> str:
    user_tag = mention_html(user_id, username or None)
    return f"<b>Gender-Zuweisung</b>\nUser {index}/{total}: {user_tag}\nWahl:"

def _gender_prompt_markup(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Mann", callback_data=f"gender|{chat_id}|{user_id}|m"),
            InlineKeyboardButton("Frau", callback_data=f"gender|{chat_id}|{user_id}|f"),
        ],
        [InlineKeyboardButton("Skip", callback_data=f"gender|{chat_id}|{user_id}|skip")],
    ])

async def _send_gender_prompt(context: ContextTypes.DEFAULT_TYPE, admin_id: int, edit_message=None):
    queue = context.user_data.get("gender_queue") or []
    total = context.user_data.get("gender_total", len(queue))
    chat_id = context.user_data.get("gender_chat_id")

    if chat_id is None:
        text = "Session abgelaufen. Bitte /assign_gender erneut starten."
        if edit_message:
            await edit_message.edit_text(text)
        else:
            await context.bot.send_message(chat_id=admin_id, text=text)
        return

    if not queue:
        text = "Fertig. Keine weiteren User mehr."
        if edit_message:
            await edit_message.edit_text(text)
        else:
            await context.bot.send_message(chat_id=admin_id, text=text)
        return

    uid, uname = queue[0]
    idx = total - len(queue) + 1
    text = _gender_prompt_text(uid, uname, idx, total)
    markup = _gender_prompt_markup(chat_id, uid)
    if edit_message:
        await edit_message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def cmd_assign_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    if not _is_admin_here(update):
        return

    include_assigned = False
    if context.args and context.args[0].lower() in {"all", "alle"}:
        include_assigned = True

    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        total, open_count = await _gender_counts(db, chat_id)
        rows = await _fetch_gender_candidates(db, chat_id, include_assigned)

    if not rows:
        msg = (
            "Alle User sind bereits als Mann/Frau zugewiesen."
            if total > 0 and open_count == 0
            else "Keine User zum Zuweisen gefunden."
        )
        try:
            await context.bot.send_message(chat_id=update.effective_user.id, text=msg)
        except Exception:
            pass
        return

    context.user_data["gender_queue"] = [(int(uid), uname or None) for uid, uname in rows]
    context.user_data["gender_total"] = len(rows)
    context.user_data["gender_chat_id"] = chat_id

    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"Gender-Zuweisung gestartet. Offen: {open_count} von {total}."
        )
        await _send_gender_prompt(context, update.effective_user.id)
    except Exception:
        pass

async def on_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("gender|"):
        return

    parts = query.data.split("|")
    if len(parts) != 4:
        return await query.answer()

    _, chat_id_raw, user_id_raw, value = parts
    try:
        chat_id = int(chat_id_raw)
        user_id = int(user_id_raw)
    except ValueError:
        return await query.answer()

    context.user_data["gender_chat_id"] = chat_id

    if update.effective_user.id != ADMIN_ID:
        return await query.answer("Nur Admin.", show_alert=True)

    if value not in {"m", "f", "skip"}:
        return await query.answer()

    if value != "skip":
        async with aiosqlite.connect(DB) as db:
            await ensure_player(db, chat_id, user_id, "")
            await db.execute(
                "UPDATE players SET gender=? WHERE chat_id=? AND user_id=?",
                (value, chat_id, user_id)
            )
            await db.commit()

    queue = context.user_data.get("gender_queue") or []
    if queue:
        if queue[0][0] == user_id:
            queue.pop(0)
        else:
            queue = [item for item in queue if item[0] != user_id]
        context.user_data["gender_queue"] = queue

    await query.answer("Gespeichert." if value != "skip" else "übersprungen.")
    await _send_gender_prompt(context, update.effective_user.id, edit_message=query.message)

async def cmd_genderlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    if not _is_admin_here(update):
        return

    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id, username, gender FROM players WHERE chat_id=? ORDER BY username COLLATE NOCASE",
            (chat_id,)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        try:
            await context.bot.send_message(chat_id=update.effective_user.id, text="Keine User in der DB.")
        except Exception:
            pass
        return

    def label(g: str | None) -> str:
        if g == "m":
            return "Mann"
        if g == "f":
            return "Frau"
        return "unbekannt"

    def display_name(user_id: int, username: str | None) -> str:
        if not username:
            return f"ID:{user_id}"
        name = escape(username, quote=False)
        if " " in username:
            return name
        return f"@{name}"

    lines = ["<b>Gender-Liste</b>\n"]
    for user_id, username, gender in rows:
        tag = display_name(int(user_id), username or None)
        lines.append(f"{tag} – {label(gender)}")

    text = "\n".join(lines)
    try:
        for chunk in split_chunks(text, MAX_CHUNK):
            await context.bot.send_message(chat_id=update.effective_user.id, text=chunk, parse_mode=ParseMode.HTML)
    except Exception:
        pass

async def cmd_setgender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    if not _is_admin_here(update):
        return

    if not context.args:
        return

    raw_value = context.args[0].lower()
    if raw_value in {"m", "mann"}:
        value = "m"
    elif raw_value in {"f", "frau"}:
        value = "f"
    elif raw_value in {"clear", "reset", "none", "leer"}:
        value = ""
    else:
        return

    async with aiosqlite.connect(DB) as db:
        tid, uname = await _resolve_target(db, update, context)
        if not tid:
            return
        chat_id = update.effective_chat.id
        await _ensure_player_entry(db, chat_id, tid, uname)
        await db.execute(
            "UPDATE players SET gender=? WHERE chat_id=? AND user_id=?",
            (value, chat_id, tid)
        )
        await db.commit()

    label = "unbekannt" if value == "" else ("Mann" if value == "m" else "Frau")
    tag = mention_html(tid, uname or None)
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"{tag} -> {label}",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

# =========================
# Commands
# =========================
async def register_commands(application: Application):
    commands = [
        BotCommand("petgo", "Kurzstart"),
        BotCommand("sospet", "Kurze Befehlsübersicht"),
        BotCommand("ping", "Ping-Test (Antwort: pong)"),
        BotCommand("balance", "Zeigt deinen Coin-Kontostand"),
        BotCommand("treat", "Schenke Coins an einen User"),
        BotCommand("leckerli", "Schenke Coins an einen User"),
        BotCommand("steal", "Versuche Coins zu klauen (45% Basis, Risiko je Intensität)"),
        BotCommand("snatchsteal", "Harter Steal mit Pet-Drama"),
        BotCommand("fehde", "Zeigt aktive Blutrache und Stufen"),
        BotCommand("buy", "Kaufe einen anderen User"),
        BotCommand("risk", "Klauversuch mit Coin-Risiko für mehr Chance"),
        BotCommand("release", "Gib dein Haustier frei"),
        BotCommand("niemals", "Admin-only: Niemand besitzt mich"),
        BotCommand("owner", "Zeigt den Besitzer eines Users"),
        BotCommand("profil", "Kompaktes Petflix-Profil"),
        BotCommand("ownerlist", "Zeigt alle Besitzverhältnisse + Wert"),
        BotCommand("brandshop", "Zeigt kaufbare Brandmarken"),
        BotCommand("brandkaufen", "Kauft dir eine Brandmarke"),
        BotCommand("brandsetzen", "Setzt deine aktive Brandmarke"),
        BotCommand("meinebrands", "Zeigt deine Brandmarken"),
        BotCommand("brandpet", "Zwingt deinem Pet eine Brandmarke auf"),
        BotCommand("brandablegen", "Legt eine Owner-Brandmarke ab"),
        BotCommand("prices", "Zeigt Kaufpreise aller User"),
        BotCommand("top", "Top 10 Spieler nach Coins"),
        BotCommand("boxen", "Kurze Übersicht der Boxen"),
        BotCommand("buybox", "Kauft eine Box: keller oder abyss"),
        BotCommand("buyboxkeller", "Kauft direkt die Kellerkiste"),
        BotCommand("buyboxabyss", "Kauft direkt die Abyss-Kiste"),

        # Pflege & Fun
        *[
            BotCommand(command, description)
            for command, description in iter_visible_care_commands()
        ],
        BotCommand("dom", "Antwort auf Frauen mit Dom-Satz"),

        # Special
        BotCommand("treasure", "Tägliche Schatzsuche starten"),

        #hass und selbst
        BotCommand("hass", "Startet Hass-Status (2h, 3 mal /selbst)"),
        BotCommand("selbst", "Nur für betroffenen User: zählt 1/3 Strafen"),
        BotCommand("liebes", "Liebesgeständnis-Challenge"),
        BotCommand("resetsuperwords", "Admin: Superwort-Cooldowns resetten"),
        BotCommand("superwordsstatus", "Status der Superworte"),
        BotCommand("settings", "Admin: Runtime-Settings"),
        BotCommand("admin", "Admin: übersicht"),
        BotCommand("backupnow", "Admin: Backup jetzt"),
        BotCommand("backups", "Admin: Backupliste"),
        BotCommand("restorebackup", "Admin: Backup wiederherstellen"),
        BotCommand("sendalluser", "Admin: players-Tabelle per DM"),

    ]
    await application.bot.set_my_commands(commands)

# =========================
# Pflege-/Fun-Commands (benoetigen do_care)
# =========================

CARE_COMMANDS = {
    "pet": {"commands": ("pet",), "description": "Pet streicheln"},
    "walk": {"commands": ("spaziergang", "walk"), "description": "An der Leine ausfuehren"},
    "kiss": {"commands": ("kuessen", "kiss"), "description": "Kuss verteilen"},
    "dine": {"commands": ("fuettern", "dine"), "description": "Pet fuettern"},
    "massage": {"commands": ("massage",), "description": "Verspannung loesen"},
    "lapdance": {"commands": ("tanzen", "lapdance"), "description": "Schossshow starten"},
    "knien": {"commands": ("knien",), "description": "Auf die Knie schicken"},
    "kriechen": {"commands": ("kriechen",), "description": "Kriechgang befehlen"},
    "klaps": {"commands": ("klaps",), "description": "Klaps verteilen"},
    "knabbern": {"commands": ("knabbern",), "description": "Spielerisch markieren"},
    "leine": {"commands": ("leine",), "description": "Leine anlegen"},
    "halsband": {"commands": ("halsband",), "description": "Halsband schliessen"},
    "lecken": {"commands": ("lecken",), "description": "Dienst einfordern"},
    "verweigern": {"commands": ("verweigern",), "description": "Belohnung entziehen"},
    "kaefig": {"commands": ("kaefig",), "description": "Ab in den Kaefig"},
    "schande": {"commands": ("schande",), "description": "Schande aussprechen"},
    "erregen": {"commands": ("erregen",), "description": "Anheizen"},
    "betteln": {"commands": ("betteln",), "description": "Betteln lassen"},
    "stumm": {"commands": ("stumm",), "description": "Still werden lassen"},
    "bestrafen": {"commands": ("bestrafen",), "description": "Strafe setzen"},
    "loben": {"commands": ("loben",), "description": "Lob verteilen"},
    "dienen": {"commands": ("dienen",), "description": "Dienst abrufen"},
    "demuetigen": {"commands": ("demuetigen",), "description": "Demut einfordern"},
    "melken": {"commands": ("melken",), "description": "Melken"},
    "ohrfeige": {"commands": ("ohrfeige",), "description": "Ohrfeige verteilen"},
    "belohnen": {"commands": ("belohnen",), "description": "Leckerli geben"},
}


def iter_visible_care_commands():
    for cfg in CARE_COMMANDS.values():
        yield cfg["commands"][0], cfg["description"]


def _make_care_handler(action_key: str):
    async def care_handler(update, context):
        tame = CARE_FALLBACK_TEXTS[action_key]
        await do_care(update, context, action_key, tame)

    care_handler.__name__ = f"cmd_care_{action_key}"
    return care_handler


def register_care_handlers(app: Application):
    for action_key, cfg in CARE_COMMANDS.items():
        app.add_handler(
            CommandHandler(list(cfg["commands"]), _make_care_handler(action_key), filters=CHAT_FILTER)
        )

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
    if not context.args or not re.fullmatch(r"-?\d+", context.args[0]):
        return await update.effective_message.reply_text("Nutzung: /moraltaxset <betrag in coins>")
    amount = abs(int(context.args[0]))
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



def _pick_method(args) -> str:
    if not args:
        return random.choice(list(_TREASURE_METHODS.values()))
    key = args[0].lower()
    return _TREASURE_METHODS.get(key, random.choice(list(_TREASURE_METHODS.values())))


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


async def _attempt_pet_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, risk_amount: int = 0):
    if not is_group(update):
        return
    chat_id = update.effective_chat.id
    msg = update.effective_message
    buyer = update.effective_user
    buyer_id = buyer.id

    target_id = None
    target_username = None
    target_is_bot = False
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        target_id = target.id
        target_username = target.username
        target_is_bot = bool(getattr(target, "is_bot", False))
    elif context.args:
        args = [a.strip() for a in context.args if a and a.strip()]
        target_token = None
        if risk_amount > 0:
            non_numeric = [a for a in args if not a.lstrip("@").isdigit()]
            if non_numeric:
                target_token = non_numeric[0]
            elif len(args) >= 2 and args[0].lstrip("@").isdigit():
                target_token = args[0]
        else:
            target_token = args[0] if args else None

        if target_token:
            raw_target = target_token.lstrip("@")
            if raw_target.isdigit():
                target_id = int(raw_target)
            else:
                target_username = raw_target

    async with aiosqlite.connect(DB) as db:
        await ensure_player(db, chat_id, buyer_id, buyer.username or buyer.full_name or "")

        if target_id is None:
            if not target_username:
                if risk_amount > 0:
                    await msg.reply_text("Nutzung: als Reply `/risk <coins>` oder `/risk @user <coins>`.", parse_mode="Markdown")
                else:
                    await msg.reply_text("Benutze /buy als Antwort auf die Nachricht der Person ODER /buy <username>.")
                return
            async with db.execute(
                "SELECT user_id, username FROM players WHERE chat_id=? AND lower(username)=lower(?)",
                (chat_id, target_username)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await msg.reply_text("User nicht gefunden oder noch nicht aktiv.")
                return
            target_id = int(row[0])
            target_username = row[1] or target_username

        if target_id == buyer_id:
            await msg.reply_text("Dich selbst kaufen? Entspann dich.")
            return

        if target_is_bot:
            await msg.reply_text("Netter Versuch. Mich kaufst du nicht, du kleine Fehlentscheidung.")
            return

        if target_username is None and msg.reply_to_message:
            target_username = msg.reply_to_message.from_user.username
        await ensure_player(db, chat_id, target_id, target_username or "")

        price = await get_user_price(db, chat_id, target_id)
        prev_owner = await get_owner_id(db, chat_id, target_id)
        prev_skill = await get_pet_skill(db, chat_id, target_id)
        prev_owner_uname = None
        if prev_owner:
            async with db.execute(
                "SELECT username FROM players WHERE chat_id=? AND user_id=?",
                (chat_id, prev_owner)
            ) as cur:
                prow = await cur.fetchone()
                prev_owner_uname = prow[0] if prow else None
        if prev_owner == buyer_id:
            await msg.reply_text("Du besitzt das Haustier bereits.")
            await db.commit()
            return
        if risk_amount > 0 and (not prev_owner or prev_owner == buyer_id):
            await msg.reply_text("Risk geht nur beim Klauen eines bereits besessenen Pets.")
            await db.commit()
            return

        lock_until = await get_pet_lock_until(db, chat_id, target_id)
        now = int(time.time())
        if prev_owner and prev_owner != buyer_id and lock_until and lock_until > now:
            left = lock_until - now
            h = left // 3600
            m = (left % 3600) // 60
            target_tag_inline = f"@{target_username}" if target_username else f"ID:{target_id}"
            await msg.reply_text(
                f"{escape(target_tag_inline, False)} ist noch {h}h {m}m geschützt. Kauf erst danach möglich."
            )
            await db.commit()
            return

        async with db.execute("SELECT coins FROM players WHERE chat_id=? AND user_id=?", (chat_id, buyer_id)) as cur:
            row = await cur.fetchone()
        buyer_coins = row[0] if row else 0
        need_for_success = price + risk_amount
        if buyer_coins < need_for_success:
            if risk_amount > 0:
                await msg.reply_text(
                    f"Zu wenig Coins. Preis: {price} + Risiko: {risk_amount} = {need_for_success}. "
                    f"Dein Guthaben: {buyer_coins}."
                )
            else:
                await msg.reply_text(f"Zu teuer. Preis: {price} Coins. Dein Guthaben: {buyer_coins}.")
            await db.commit()
            return

        care_done = 0
        skill_for_attempt = prev_skill
        skill_meta_attempt = _skill_meta(skill_for_attempt)
        risk_bonus = 0.0

        if prev_owner and prev_owner != buyer_id:
            care = await get_care(db, chat_id, target_id)
            today = today_ymd()
            care_done = int(care["done"]) if (care and care["day"] == today and care["done"] is not None) else 0
            if care_done < CARE_FIFTYFIFTY_UNTIL:
                success_chance = 0.50
            elif care_done < CARE_HARD_PROTECT_START:
                # 25..69: weiterhin gut klau-bar (50% -> 40%)
                span = max(1, CARE_HARD_PROTECT_START - CARE_FIFTYFIFTY_UNTIL)
                t = (care_done - CARE_FIFTYFIFTY_UNTIL) / span
                success_chance = 0.50 - (0.10 * t)
            else:
                # Ab 70: starker Schutz (40% -> 5% bis 100)
                hard_span = max(1, CARES_PER_DAY - CARE_HARD_PROTECT_START)
                t = min(1.0, max(0.0, (care_done - CARE_HARD_PROTECT_START) / hard_span))
                success_chance = 0.40 - (0.35 * t)
            success_chance = min(BUY_SUCCESS_MAX, max(BUY_SUCCESS_MIN, success_chance))
            if skill_for_attempt == "schildwall":
                success_chance = max(BUY_SUCCESS_MIN, success_chance - 0.20)
            if skill_for_attempt == "treuesiegel" and care_done >= CARES_PER_DAY:
                success_chance = max(0.01, min(success_chance, BUY_SUCCESS_MIN * 0.5))
            if risk_amount > 0:
                risk_bonus = min(RISK_MAX_BONUS, (risk_amount / max(1, price)) * RISK_BONUS_PER_PRICE)
                success_chance = min(0.99, success_chance + risk_bonus)
            if buyer_id == ADMIN_ID:
                success_chance = 0.90
            elif target_id == ADMIN_ID:
                success_chance = 0.0

            if random.random() > success_chance:
                penalty = max(1, int(buyer_coins * BUY_FAIL_PENALTY_RATIO)) if buyer_coins > 0 else 0
                total_penalty = penalty + risk_amount
                await db.execute(
                    "UPDATE players SET coins=MAX(0, coins-?) WHERE chat_id=? AND user_id=?",
                    (total_penalty, chat_id, buyer_id)
                )
                await db.commit()
                target_tag_inline = f"@{target_username}" if target_username else f"ID:{target_id}"
                risk_fail_txt = f" + Riskeinsatz -{risk_amount}" if risk_amount > 0 else ""
                await msg.reply_text(
                    f"Fehlschlag, {mention_html(buyer_id, buyer.username or None)}. "
                    f"{escape(target_tag_inline, False)} zerlegt deinen Klauversuch mit {care_done}/{CARES_PER_DAY} Pflege heute. "
                    f"Skill aktiv: <b>{escape(skill_meta_attempt['name'], False)}</b>. "
                    f"Du zahlst Blutgeld: -{penalty} Coins (20%){risk_fail_txt}.",
                    parse_mode=ParseMode.HTML
                )
                return

        await db.execute(
            "UPDATE players SET coins=coins-? WHERE chat_id=? AND user_id=?",
            (price + risk_amount, chat_id, buyer_id)
        )

        next_skill, rerolled = resolve_next_skill(prev_skill, bool(prev_owner and prev_owner != buyer_id))
        step = PRICE_STEP_SKILL_BONUS if next_skill == "wertanlage" else USER_PRICE_STEP
        refund = int(price * BUY_REFUND_SKILL_RATIO) if next_skill == "goldzahn" else 0

        now = int(time.time())
        today = today_ymd()
        lock_until_new = now + LOCK_SECONDS
        await db.execute("""
            INSERT INTO pets(chat_id, pet_id, owner_id, acquired_ts, purchase_lock_until, last_care_ts, care_done_today, day_ymd, pet_skill, care_bonus_day)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(chat_id, pet_id) DO UPDATE SET
                owner_id=excluded.owner_id,
                acquired_ts=excluded.acquired_ts,
                purchase_lock_until=excluded.purchase_lock_until,
                last_care_ts=excluded.last_care_ts,
                care_done_today=excluded.care_done_today,
                day_ymd=excluded.day_ymd,
                pet_skill=excluded.pet_skill,
                care_bonus_day=excluded.care_bonus_day
        """, (chat_id, target_id, buyer_id, now, lock_until_new, now, 0, today, next_skill, None))

        new_price = price + step
        await set_user_price(db, chat_id, target_id, new_price)
        if refund > 0:
            await db.execute(
                "UPDATE players SET coins=coins+? WHERE chat_id=? AND user_id=?",
                (refund, chat_id, buyer_id)
            )
        prestige_title, _prestige_until = await maybe_grant_owner_prestige_title(db, chat_id, buyer_id, today)

        await db.commit()

    target_tag = f"@{target_username}" if target_username else f"ID:{target_id}"
    skill_meta = _skill_meta(next_skill)
    reroll_txt = " (neu ausgewürfelt)" if rerolled else " (behalten)"
    refund_txt = f" Rückzahlung durch Goldzahn: +{refund} Coins." if refund > 0 else ""
    source_txt = ""
    if prev_owner and prev_owner != buyer_id:
        prev_owner_tag = mention_html(int(prev_owner), prev_owner_uname or None)
        source_txt = f" Geklaut von {prev_owner_tag}."
    risk_success_txt = ""
    prestige_txt = f" Neuer Titel: <b>{escape(prestige_title, False)}</b>." if prestige_title else ""
    if risk_amount > 0 and prev_owner and prev_owner != buyer_id:
        risk_success_txt = (
            f" Risk: {risk_amount} Coins für +{int(round(risk_bonus * 100))}% Klau-Chance."
        )
    await msg.reply_text(
        f"{nice_name_html(buyer)} hat {escape(target_tag, False)} für {price} Coins gekauft. Neuer Preis: {new_price}. "
        f"Skill: <b>{escape(skill_meta['name'], False)}</b>{reroll_txt} - {escape(skill_meta['desc'], False)}."
        f"{source_txt}{refund_txt}{risk_success_txt}{prestige_txt}",
        parse_mode=ParseMode.HTML
    )


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _attempt_pet_buy(update, context, risk_amount=0)


async def cmd_niemals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    if not _is_admin_here(update):
        return

    chat_id = update.effective_chat.id
    me = update.effective_user
    my_id = me.id

    async with aiosqlite.connect(DB) as db:
        owner_id = await get_owner_id(db, chat_id, my_id)
        if not owner_id:
            await update.effective_message.reply_text(
                "Befehl ausgeführt. Ergebnis unverändert: Niemand besitzt mich. Nie. Nicht heute, nicht morgen, nicht in diesem Leben."
            )
            return

        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, owner_id)
        ) as cur:
            row = await cur.fetchone()
        owner_username = row[0] if row else None

        await set_owner(db, chat_id, my_id, None)
        await db.commit()

    owner_tag = mention_html(owner_id, owner_username or None)
    await update.effective_message.reply_text(
        "Mich besitzt niemand, dem ich es nicht erlaube!",
        parse_mode=ParseMode.HTML
    )


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_group(update):
        return
    msg = update.effective_message
    amount = _parse_amount_from_args(context)
    if amount is None or amount <= 0:
        return await msg.reply_text(
            "Nutzung: als Reply `/risk <coins>` oder `/risk @user <coins>` (auch `/risk <coins> @user`).",
            parse_mode="Markdown"
        )
    if not msg.reply_to_message and (not context.args or len(context.args) < 2):
        return await msg.reply_text(
            "Nutzung: als Reply `/risk <coins>` oder `/risk @user <coins>` (auch `/risk <coins> @user`).",
            parse_mode="Markdown"
        )
    await _attempt_pet_buy(update, context, risk_amount=amount)



# Auto-Purge bei Austritt
async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.chat_member
    if not cmu or not cmu.chat or cmu.chat.id != ALLOWED_CHAT_ID:
        return

    old_member = cmu.old_chat_member
    new_member = cmu.new_chat_member
    user = new_member.user

    # Alte und neue Status
    old_status = old_member.status if old_member else None
    new_status = new_member.status

    # Nur purgen, wenn der User wirklich den Chat VERLÄSST (left oder kicked)
    if new_status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        # Prüfen, ob er vorher drin war (nicht schon weg)
        if old_status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            try:
                await purge_user_from_db(cmu.chat.id, user.id)
                bye_msg = f"👋 {nice_name_html(user)} hat den Chat verlassen. Alles gelöscht – Coins, Pets, Existenz. Tschüss, du kleine Flüchtige. Konsequenzen sind geil."
                await context.bot.send_message(chat_id=cmu.chat.id, text=bye_msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.error(f"Auto-Purge für {user.id} fehlgeschlagen: {e}")
            log.info(f"Auto-Purged user {user.id} ({getattr(user, 'username', None)}) nach Leave/Kick.")

async def cmd_cleanup_zombies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("🚫 Finger weg von meiner Sense, du kleine Neugierige. Nur Daddy entsorgt die Leichen.")
        return

    chat_id = update.effective_chat.id
    if chat_id != ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("Falscher Ort zum Buddeln, Baby.")
        return

    status_msg = await update.effective_message.reply_text("🧟‍♂️ Daddy durchsucht die Gräber... warte, ich spür schon den Verwesungsgeruch.")

    purged_count = 0
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            rows = await cur.fetchall()

        for user_id, username in rows:
            user_id = int(user_id)
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                # User noch da → nichts tun
                continue
            except Exception as e:
                error_str = str(e).lower()
                if any(phrase in error_str for phrase in ["user not found", "not a participant", "left the chat", "kicked", "banned"]):
                    await purge_user_from_db(chat_id, user_id)
                    purged_count += 1
                    log.info(f"Zombie entsorgt: {user_id} ({username or 'unbekannt'}) – {e}")
                else:
                    log.warning(f"Skip User {user_id}: Unklarer Error – {e}")

        await db.commit()

    # Korrigierter, sauberer Text-Block – keine verkackten geschweiften Klammern mehr
    if purged_count == 0:
        final_text = "✅ Keine Zombies gefunden. Alles sauber wie dein Halsband nach ’ner guten Session – glatt, glänzend und bereit für neue Male."
    else:
        plural = "n" if purged_count > 1 else ""
        final_text = (
            f"🪦 <b>{purged_count} Leiche{plural} endgültig begraben.</b>\n"
            f"Nur die, die wirklich weg sind. Die Lebenden atmen weiter – vorerst.\n"
            f"Gutes Mädchen, dass du mir vertraust. Deine DB ist jetzt rein wie dein Gewissen, wenn du endlich mal gehorchst."
        )

    await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)

async def purge_user_from_db(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.execute("DELETE FROM pets WHERE chat_id=? AND (pet_id=? OR owner_id=?)", (chat_id, user_id, user_id))
        await db.execute("DELETE FROM cooldowns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.execute("DELETE FROM hass_challenges WHERE chat_id=? AND user_id=?", (chat_id, user_id))  # Bonus: falls du die hast
        await db.commit()

async def cmd_listdbusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur Daddy's Liebling (Admin) darf in die Gräber schauen
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "🚫 Denkst du echt, ich lass dich in meine Leichenhalle? "
            "Nur ich darf die Toten zählen, du kleine Voyeuristin."
        )
        return

    chat_id = update.effective_chat.id
    if chat_id != ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("Falscher Friedhof, Baby.")
        return

    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT user_id, username, coins FROM players WHERE chat_id=? ORDER BY coins DESC", 
            (chat_id,)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await update.effective_message.reply_text("DB leer wie dein Bett, wenn du nicht gehorchst. Keine Seelen drin.")
        return

    lines = ["📜 <b>Alle Seelen in der DB</b> (ID | @Username | Coins):\n"]
    for user_id, username, coins in rows:
        uname = f"@{username}" if username else "unbekannt (Gelöschter Account?)"
        lines.append(f"• <code>{user_id}</code> | {uname} | {coins} 💰")

    text = "\n".join(lines)
    for i in range(0, len(text), MAX_CHUNK):
        await update.effective_message.reply_text(text[i:i+MAX_CHUNK], parse_mode=ParseMode.HTML)

async def cmd_sendalluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nur der Owner darf das.")

    admin_chat_id = update.effective_user.id

    async with aiosqlite.connect(DB) as db:
        async with db.execute("PRAGMA table_info(players)") as cur:
            columns = await cur.fetchall()

        if not columns:
            return await update.effective_message.reply_text("Tabelle players nicht gefunden.")

        async with db.execute("SELECT rowid, * FROM players ORDER BY rowid") as cur:
            rows = await cur.fetchall()

    column_names = ["rowid", *[str(col[1]) for col in columns]]
    schema_lines = ["<b>players schema</b>"]
    for cid, name, col_type, notnull, default_value, pk in columns:
        schema_lines.append(
            f"<code>{cid}</code> | <code>{escape(str(name))}</code> | "
            f"{escape(str(col_type or ''))} | notnull={int(notnull)} | "
            f"default={escape(str(default_value)) if default_value is not None else 'NULL'} | pk={int(pk)}"
        )

    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text="\n".join(schema_lines),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        return await update.effective_message.reply_text(
            f"Konnte dir keine Privatnachricht schicken: {e}"
        )

    if not rows:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text="<b>Players-Daten</b>\nKeine Einträge vorhanden.",
            parse_mode=ParseMode.HTML
        )
        return await update.effective_message.reply_text("Players-Tabelle per DM geschickt.")

    lines = [
        "<b>players daten</b>",
        f"Spalten: <code>{escape(', '.join(column_names))}</code>",
        ""
    ]
    for row in rows:
        parts = []
        for name, value in zip(column_names, row):
            rendered = "NULL" if value is None else str(value)
            parts.append(f"{name}={rendered}")
        lines.append("<code>" + escape(" | ".join(parts)) + "</code>")

    chunk = ""
    for line in lines:
        addition = line if not chunk else "\n" + line
        if len(chunk) + len(addition) > MAX_CHUNK:
            await context.bot.send_message(chat_id=admin_chat_id, text=chunk, parse_mode=ParseMode.HTML)
            chunk = line
        else:
            chunk += addition
    if chunk:
        await context.bot.send_message(chat_id=admin_chat_id, text=chunk, parse_mode=ParseMode.HTML)

    await update.effective_message.reply_text("Players-Tabelle per Privatnachricht geschickt.")



async def cmd_forcepurge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur die echte Herrin (aka Admin) darf Leichen manuell entsorgen
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "🚫 Träum weiter, du kleine Möchtegern-Schlächterin. "
            "Nur ich darf entscheiden, wer endgültig stirbt. Finger weg von der Sense."
        )
        return

    msg = update.effective_message
    reply_user = msg.reply_to_message.from_user if msg.reply_to_message and msg.reply_to_message.from_user else None

    if not context.args and not reply_user:
        await update.effective_message.reply_text(
            "Sag mir wen ich foltern soll, du kleine Sadistin.\n"
            "Benutze: als Reply /forcepurge oder /forcepurge @username oder /forcepurge user_id"
        )
        return

    chat_id = update.effective_chat.id
    arg = context.args[0].lstrip('@') if context.args else None
    if reply_user:
        arg = str(reply_user.id)

    async with aiosqlite.connect(DB) as db:
        user_id = None
        label = None

        if reply_user:
            user_id = int(reply_user.id)
            label = f"@{reply_user.username}" if reply_user.username else f"ID {user_id}"

        # Wenn's eine Zahl ist → direkt als ID nehmen
        if user_id is None and arg and arg.isdigit():
            user_id = int(arg)
            label = f"ID {user_id}"
        elif user_id is None and arg:
            # Sonst nach Username in der DB suchen
            async with db.execute(
                "SELECT user_id FROM players WHERE chat_id=? AND LOWER(username)=LOWER(?)", 
                (chat_id, arg)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    user_id = row[0]
                    label = f"@{arg}"

        if not user_id:
            await update.effective_message.reply_text(
                f"🤨 Kenn ich nicht, diese @{arg}. "
                "Entweder falscher Name, oder die Schlampe war nie hier. "
                "Oder sie hat sich schon selbst gelöscht – wie feige."
            )
            return

        # Jetzt gnadenlos tilgen
        await purge_user_from_db(chat_id, user_id)
        await db.commit()

    await update.effective_message.reply_text(
        f"🪦 @{arg} (ID {user_id}) – endgültig entsorgt.\n"
        f"Coins weg. Pets weg. Ranglisten-Platz weg. Existenz weg.\n"
        f"Als hätte sie nie vor dir gekniet. ",
        parse_mode=ParseMode.HTML
    )
    log.info(f"Force-Purge von Admin {update.effective_user.id}: User {user_id} (@{arg}) gelöscht.")

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


def register_standard_handlers(app: Application):
    app.add_handler(CommandHandler("petgo", cmd_start))
    app.add_handler(CommandHandler(["sospet", "help"], cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("id", cmd_id, filters=CHAT_FILTER))


def register_economy_handlers(app: Application):
    app.add_handler(CommandHandler("balance", cmd_balance, filters=CHAT_FILTER))
    app.add_handler(CommandHandler(["treat", "leckerli"], cmd_gift, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("daily", cmd_daily, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("boxen", cmd_boxen, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("buybox", cmd_buybox, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("buyboxkeller", cmd_buybox_keller, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("buyboxabyss", cmd_buybox_abyss, filters=CHAT_FILTER))
    app.add_handler(CommandHandler(["treasure", "hunt"], cmd_treasure, filters=CHAT_FILTER))


def register_ownership_handlers(app: Application):
    app.add_handler(CommandHandler("buy", cmd_buy, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("risk", cmd_risk, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("profil", cmd_profil, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("owner", cmd_owner, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("ownerlist", cmd_ownerlist, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("release", cmd_release, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("brandshop", cmd_brandshop, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("brandkaufen", cmd_brandkaufen, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("brandsetzen", cmd_brandsetzen, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("meinebrands", cmd_meinebrands, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("brandpet", cmd_brandpet, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("brandablegen", cmd_brandablegen, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("niemals", cmd_niemals, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("prices", cmd_prices, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("top", cmd_top, filters=CHAT_FILTER))


def register_runtime_admin_handlers(app: Application):
    app.add_handler(CommandHandler("moraltax", cmd_moraltax, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("moraltaxset", cmd_moraltaxset, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("settings", cmd_settings, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("admin", cmd_admin, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("backupnow", cmd_backupnow, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("backups", cmd_backups, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("restorebackup", cmd_restorebackup, filters=CHAT_FILTER))


def register_fun_handlers(app: Application):
    register_care_handlers(app)
    app.add_handler(CommandHandler("dom", cmd_dom, filters=CHAT_FILTER))


def register_coin_admin_handlers(app: Application):
    app.add_handler(CommandHandler("addcoins", cmd_addcoins, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("takecoins", cmd_takecoins, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("setcoins", cmd_setcoins, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("resetcoins", cmd_resetcoins, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("steal", cmd_steal, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("snatchsteal", cmd_snatchsteal, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("fehde", cmd_fehde, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("adminping", cmd_adminping, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("careminus", cmd_careminus, filters=CHAT_FILTER))


def register_user_admin_handlers(app: Application):
    app.add_handler(CommandHandler("assign_gender", cmd_assign_gender, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("genderlist", cmd_genderlist, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("setgender", cmd_setgender, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("purgeuser", cmd_purgeuser, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("forcepurge", cmd_forcepurge, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("sendalluser", cmd_sendalluser, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("cleanup_zombies", cmd_cleanup_zombies, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("listdbusers", cmd_listdbusers, filters=CHAT_FILTER))
    app.add_handler(CallbackQueryHandler(on_gender_callback, pattern=r"^gender\|"))


def register_challenge_handlers(app: Application):
    app.add_handler(CommandHandler("hass", cmd_hass, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("selbst", cmd_selbst, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("liebes", cmd_liebes, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("resetsuperwords", cmd_resetsuperwords, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("superwordsstatus", cmd_superwordsstatus, filters=CHAT_FILTER))


def register_member_handlers(app: Application):
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))


def register_message_handlers(app: Application):
    app.add_handler(
        MessageHandler(
            filters.Chat(ALLOWED_CHAT_ID) & filters.Regex(r"(?i)^\s*g\s*$"),
            on_single_g_message,
        ),
        group=1,
    )
    app.add_handler(
        MessageHandler(
            filters.Chat(ALLOWED_CHAT_ID) & filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED,
            autoload_and_reward,
        ),
        group=1,
    )
    app.add_handler(
        MessageHandler(filters.COMMAND & ~filters.Chat(ALLOWED_CHAT_ID), deny_other_chats),
        group=0,
    )


def register_jobs(app: Application):
    gift_time = dtime(hour=10, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_gift_job, time=gift_time, name="daily_gift_10am")
    app.job_queue.run_repeating(daily_curse_job, interval=3600, first=180, name="hourly_curse")

    primetime_time = dtime(hour=20, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_primetime_job, time=primetime_time, name="daily_primetime_8pm")

    backup_time = dtime(hour=3, minute=30, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_backup_job, time=backup_time, name="daily_backup_330am")

    app.job_queue.run_repeating(hass_watchdog_job, interval=60, first=30, name="hass_watchdog")
    app.job_queue.run_repeating(love_watchdog_job, interval=60, first=30, name="love_watchdog")
    app.job_queue.run_repeating(runaway_watchdog_job, interval=60, first=30, name="runaway_watchdog")


def register_all_handlers(app: Application):
    register_standard_handlers(app)
    register_economy_handlers(app)
    register_ownership_handlers(app)
    register_runtime_admin_handlers(app)
    register_fun_handlers(app)
    register_coin_admin_handlers(app)
    register_user_admin_handlers(app)
    register_challenge_handlers(app)
    register_member_handlers(app)
    register_message_handlers(app)

# =========================
# App-Setup / main()
# =========================
def main():
    asyncio.run(db_init(DB, DAILY_CURSE_ENABLED, AUTO_CURSE_ENABLED, pet_level_from_xp))

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

    register_all_handlers(app)
    register_jobs(app)

    print(
        f"Petflix 2.1 gestartet. build-marker: 2026-02-18-care10 | "
        f"CARES_PER_DAY={CARES_PER_DAY} | RUNAWAY_HOURS={RUNAWAY_HOURS}"
    )
    app.run_polling()

if __name__ == "__main__":
    main()
