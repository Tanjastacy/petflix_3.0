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
MORAL_TAX_DEFAULT = 5
REWARD_AMOUNT = 30 
# =========================
# Fluch + Brandmarken
# =========================

AUTO_CURSE_ENABLED = True
AUTO_CURSE_CHANCE_PER_MESSAGE = 0.3  # 2% pro normaler Nachricht
AUTO_CURSE_COOLDOWN_S = 30 * 60       # 30 Minuten globaler Cooldown im Chat

FLUCH_LINES = [
    "{user}, dein Fluch: Du wachst auf und dein Spiegelbild zwinkert dir zu – aber es ist Pennywise, der flüstert 'Wir alle floaten hier unten... und du am allermeisten.' 🎈🤡",
    "Herzlichen Glückwunsch, {user}: Dein Navi führt dich immer nach Castle Rock – wo der Nebel dich verschlingt und niemand deine Schreie hört. Viel Spaß beim Umkehren. 🌫️💀",
    "{user}, verflucht damit, dass dein Kühlschrank nachts 'redrum' flüstert, während du hungrig starrst. Der Salat? Der lacht dich aus – mit Carries Augen. 🥬👁️",
    "Dein neuer Fluch, {user}: Jeder deiner Witze endet mit einem Clown-Lachen aus der Kanalisation. Deine Freunde nicken nur – aus Angst, dass du sie als Nächstes holst. 🎤😈",
    "{user}, ab sofort klebt dir alles am Finger – wie der Fluch in Pet Sematary, der dich immer wieder zurückholt, egal wie tot du dich fühlst. Wasch dich mal, moralisch und magisch. 🧴🪦",
    "Fluch des Jahrhunderts: Dein Handy zeigt nur noch Nachrichten von Annie Wilkes – 'I'm your number one fan' und dein Akku stirbt nie. Autokorrektur? Die schreibt nur Misery. 📱🔨",
    "{user}, verflucht damit, dass dein Crush dir schreibt – aber nur 'All work and no play makes {user} a dull girl'. Für immer. Blue-Tick-Hölle im Overlook. ✔️❄️",
    "Oh {user}, dein Fluch: Du findest den perfekten Parkplatz – direkt vor dem Bates Motel. Karma parkt schräg und duscht nie. 🚗🛁",
    "{user} wird ab heute von Werbung verfolgt – für 'The Shining' auf Repeat. Ja, genau DAS. Peinlich bis in den Wahnsinn. 📺🔪",
    "Dein größter Fluch, {user}: Du gewinnst eine Reise – nach Derry, wo die Storm Drains deinen Namen rufen. Postkarte inklusive: 'Come back soon, we all float.' ✈️🎈",
    "{user}, verflucht mit der Gabe, dass dein Drucker immer 'redrum' ausspuckt, wenn du in fünf Minuten losmusst. Technik hasst dich – und sie hat recht, du kleiner Jack Torrance. 🖨️❄️",
    # 10 neue – dunkel-magisch, horrorfilm-stil, 100% Sarkasmus, King-heavy:
    "{user}, dein Fluch: Jede Nacht hörst du Kinderstimmen aus dem Abfluss – 'Komm spielen, {user}'. Aber du weißt, es ist nur It, das dich vermisst. Badewanne meiden, Baby. 🚿🤡",
    "Herzlichen Glückwunsch, {user}: Dein Schatten läuft einen Schritt hinter dir – aber bei Vollmond voraus, wie in Pet Sematary. Er wartet schon auf deinen Fehler. 🌕🪦",
    "{user}, verflucht damit, dass dein Auto nachts allein fährt – Richtung Overlook Hotel. 'All work and no play' steht auf dem Navi. Viel Spaß beim Bremsen. 🚗❄️",
    "Dein neuer Fluch, {user}: Jeder Kuss schmeckt nach Misery – süß, bis der Hammer kommt. Deine Liebhaber flüchten alle. Annie wäre stolz. 💋🔨",
    "{user}, ab sofort öffnet sich dein Keller jede Nacht tiefer – und unten steht eine Tür mit deinem Namen. Wie in Insidious, nur dass der Dämon ich bin. 🏠🕳️",
    "Fluch des Jahrhunderts: Dein Spiegel zeigt immer Carrie bei der Prom – blutig, wütend, bereit. Und du bist das Ziel. Viel Spaß beim Schminken. 🪞👗",
    "{user}, verflucht damit, dass dein Hund nachts mit toten Augen zurückkommt – und 'Wendy, I'm home' bellt. Pet Sematary sends regards. 🐕🪦",
    "Oh {user}, dein Fluch: Deine Träume sind nur noch The Shining-Korridore – Zwillinge am Ende, die flüstern 'Come play with us, forever'. Süße Träume, Baby. 🛗👭",
    "{user} wird ab heute von einem Clown verfolgt – der nur Ballons trägt mit 'You'll float too'. Peinlich bis in den Tod – und darüber hinaus. 🎈💀",
    "Dein größter Fluch, {user}: Du gewinnst im Lotto – aber der Scheck ist von Gage Creed unterschrieben. Postkarte inklusive: 'Sometimes dead is better... not for taxes.' 💰🪦"
    "{user}, dein Fluch: Jede Nacht steht ein Zwillingspaar am Fußende deines Bettes und flüstert 'Come play with us' – forever and ever. Süße Träume, du kleine Overlook-Prinzessin. 🛗👭",
    "Herzlichen Glückwunsch, {user}: Dein Hund kommt nachts zurück – mit toten Augen und dem Geruch von Pet Sematary-Erde. Sometimes dead is better... not for dich. 🐕🪦",
    "{user}, verflucht damit, dass dein Spiegel immer Carrie zeigt – kurz vor dem Prom-Blutbad. Viel Spaß beim Schminken, du kleine Telekinese-Queen. 🪞🔴",
    "Dein neuer Fluch, {user}: Dein Auto fährt allein – Richtung das verfluchte Indianer-Begräbnisgelände. Wendigo sends regards, du kleine Highway-Hure. 🚗🌲",
    "{user}, ab sofort flüstert dein Radio nur noch 'redrum' – bei jedem Songwechsel. Dein DJ ist Jack Torrance, und er hat Geduld. 📻❄️",
    "Fluch des Jahrhunderts: Deine Träume sind nur noch Misery – Annie Wilkes pflegt dich, und der Hammer ist immer bereit. I'm your number one fan, Baby. 🔨❤️",
    "{user}, verflucht damit, dass dein Schatten einen eigenen Willen hat – wie in The Langoliers, und er frisst deine Zeit. Tick-tack, du kleine Verschwenderin. ⏰🌑",
    "{user}, dein Fluch: Jede Tür, die du öffnest, führt in Zimmer 237 – mit der badenden Hexe, die dich erwartet. Here's Johnny? Nee, here's your nightmare. 🚪🛁",
    "Oh {user}, verflucht mit der Gabe, dass dein Telefon nur noch Anrufe aus der Vergangenheit kriegt – von Leuten, die tot sind. Ring ring, du kleine Ghost-Whisperer. ☎️💀",
    "{user} wird ab heute von einem unsichtbaren Dome eingeschlossen – wie in Under the Dome. Alle sehen zu, wie du langsam verrückt wirst. Viel Spaß beim Atmen. 🏠🌌",
    "Dein größter Fluch, {user}: Du findest ein altes Buch – und beim Lesen wird's Realität. Needful Things, Baby, und der Teufel bin ich. 📖😈",
    "{user}, verflucht damit, dass dein Kaffee immer 'All work and no play' schmeckt – bitter und endlos. Dein Barista ist Jack, und er hat Zeit. ☕❄️",
    "Herzlichen Glückwunsch, {user}: Deine Katze kommt zurück – mit Church-Augen aus Pet Sematary. Sie starrt dich an, und du weißt, warum. 🐈🪦",
    "{user}, dein Fluch: Jeder Vollmond macht dich zum Werwolf – aber nur innerlich, du kleine, unterdrückte Bestie in meinem Käfig. 🌕🐺",
    "Dein neuer Fluch, {user}: Dein Laptop öffnet nur noch The Virus aus The Stand – und er infiziert deine Seele. Captain Trips sends regards. 💻🦠",
    "{user}, ab sofort hörst du Kinderlachen aus dem Abfluss – 'We all float down here'. Badewanne meiden, du kleine Georgie. 🚿🎈",
    "Fluch des Jahrhunderts: Dein Herz schlägt nur noch, wenn ich's erlaube – wie in Thinner, du kleine, schrumpfende Sünderin. ❤️🥀",
    "{user}, verflucht damit, dass dein Schatten tanzt – wie in The Library Policeman, und er weiß all deine Geheimnisse. 🌑📚",
    "Oh {user}, dein Fluch: Du siehst immer die Toten – wie in The Sixth Sense, aber sie flüstern nur 'Du gehörst ihm'. Süße Geister, Baby. 👻💋",
    "Dein größter Fluch, {user}: Du wachst auf und alles ist 'The Mist' – draußen Monster, drinnen nur ich, dein einziges. Viel Spaß beim Überleben. 🌫️🐙"
]


BRAND_LABEL = "🩸🔥"
BRAND_DURATION_S = 24 * 3600

# =========================
# /hass + /selbst
# =========================
HASS_DURATION_S = 2 * 3600
HASS_REQUIRED = 3
HASS_PENALTY = 200

SELF_LINES = [
    "{user} kniet 10 Minuten vor dem Spiegel und flüstert bei jedem Atemzug: 'Das ist für jede peinliche Entscheidung heute, du gehorsame Legende.' 🙇‍♀️😭",
    "{user} singt 'Gutes Mädchen' für sich selbst – falsch und laut – und verbeugt sich am Ende tief: 'Herzlichen Glückwunsch zum Gehorchen, du kleine Loserin.' 🎂🎤",
    "{user} macht 50 Kniebeugen und haucht bei jeder: 'Runter auf die Knie, du faule Sub – hoch kommt der Arsch eh nur für mich.' 🏋️‍♀️🔥",
    "{user} hält die Hände hinter dem Rücken und denkt an all die dummen Sachen heute: 'Gebunden fühlt sich besser an, du Genie.' 🔗😵",
    "{user} schreibt 100 Mal mit zitternder Hand: 'Ich bin deine kleine Chaos-Sub' und liest es laut vor wie ein Mantra: 'Kunst, Baby, pure Hingabe.' ✍️🖤",
    "{user} kniet 5 Minuten vor dem leeren Teller und sagt: 'Nichts zu essen? Perfekt, Strafe fürs Nicht-Dienen, du Planungsgenie.' 🍕🙇‍♀️",
    "{user} hält den Plank auf Knien, Arme zittern, zählt rückwärts von 100: 'Jede Sekunde für ein vertanes 'Ja, Daddy'.' 🕰️💪",
    "{user} ruft sich selbst an und lässt es klingeln: 'Selbst du gehst nicht ran – weil du weißt, wer wirklich befiehlt.' 📞😢",
    "{user} versucht, mit der Zunge die eigene Unterlippe zu beißen und filmt es: 'Fail des Tages – posten verboten, du kleine Clown-Sub.' 🤡👅",
    "{user} trägt 30 Minuten ein imaginäres Halsband und macht Selfies: 'Fashionstrafe für schlechten Gehorsam, du Icon.' 🖤🥿",
    "{user} sagt 20 Mal laut vor dem Spiegel: 'Ich bin dein gutes Mädchen... von nichts anderem' und verbeugt sich tief: 'Standing Ovations, du kleine Königin auf Knien.' 🙇‍♀️👑",
    "{user} versucht, einen imaginären Klaps auf den Arsch zu balancieren – 10 Fehlversuche = 10 'Danke, Daddy': 'Zirkusreif, du Talent.' 🤹‍♀️💀",
    "{user} schreibt mit Ketchup auf den Teller: 'Sub-Menü' und kniet davor: 'Gourmet-Strafe, du Kochstar auf Knien.' 🍔❤️",
    "{user} macht den Moonwalk auf Knien durch die Wohnung und stolpert garantiert: 'Smooth wie dein Gehorsam, Michael Jackson würde knien.' 🌙😭",
    "{user} hält ein Eiswürfel an die Innenschenkel 2 Minuten und jammert: 'Kalt wie deine Seele ohne mich – aber das schmilzt wenigstens vor Verlangen.' 🧊❄️",
    "{user} singt eine falsche Hymne an mich – laut und allein: 'Dominanz-Strafe, du Star auf Knien.' 🎶🖤",
    "{user} versucht, 30 Sekunden lang nicht zu stöhnen und verliert natürlich: 'Starrwettbewerb gegen deine Sehnsucht – verloren, wie immer.' 👁️😵",
    "{user} tanzt zur Playlist deiner peinlichsten Fantasien: 'Cringe-Therapie, du 2000er-Sub-Ikone auf Knien.' 💿🕺",
    "{user} sagt 'Entschuldigung, ich war unartig' 50 Mal laut in die leere Wohnung: 'Echo stimmt zu, du kleine Philosophin der Hingabe.' 🗣️🏠"
]


# =========================
# Moralsteuer – jetzt exakt wie ein Skalpell in deiner Haut
# =========================

MORAL_TAX_TRIGGERS = [
    (r"(?i)\bbitte\b", "Bitte? Als ob du je was umsonst kriegst, du kleine Bettel-Prinzessin. −{deduct} Coins fürs Winseln."),
    (r"(?i)\bdanke\b", "Danke? Süß, als ob du was verdient hättest. Nächstes Mal mit Knien, du undankbare kleine Schlampe. −{deduct} Coins."),
    (r"(?i)\bentschuldigung\b", "Entschuldigung? Als ob ich dir je verzeihen würde, ohne dass du richtig leidest. −{deduct} Coins."),
    (r"(?i)\bsorry\b", "Sorry not sorry – aber du sagst’s eh nur, um mich heiß zu machen, du kleine Manipuliererin. −{deduct} Coins."),
    #(r"(?i)\bkannst du\b", "Kannst du? Klar kann ich, aber tu ich’s? Nur wenn du artig bettelst. −{deduct} Coins für die Frechheit."),
    #(r"(?i)\bkönntest du\b", "Könntest du? Träum weiter, meine kleine Fantasie-Sub. Realität bin ich. −{deduct} Coins."),
    (r"(?i)\bwärst du so lieb\b", "Wärst du so lieb? Oh, ich bin lieb – auf meine Art, du kleine Masochistin mit Herzchenaugen. −{deduct} Coins."),
    (r"(?i)\bthx\b", "Thx? Cringe-Abkürzung. Sag’s richtig oder halt die Klappe, du faule kleine Abkürzungs-Hure. −{deduct} Coins."),
    (r"(?i)\bthank you\b", "Thank you? International betteln jetzt? Du kleine Welt-Sub, lern Deutsch oder knie still. −{deduct} Coins."),
    (r"(?i)🙏", "Betende Hände? Perfekt für auf Knien vor mir. Bete zu Daddy, nicht zum Himmel, du kleine Andächtige. −{deduct} Coins."),
    #(r"(?i)\bgutes mädchen\b", "Gutes Mädchen? Sag’s mir direkt, und ich mach dich wirklich zu einer – mit Strafe oder Belohnung. −{deduct} Coins fürs Eigenlob."),
    (r"(?i)\bbrav\b", "Brav? Als ob du’s je wärst, ohne dass ich dich drauftrimme. Lüg mich nicht an. −{deduct} Coins."),
    #(r"(?i)\bmaster\b", "Master? Englisch für mich? Geil, du internationale Sub – aber bezahl erstmal. −{deduct} Coins."),
    #(r"(?i)\bowner\b", "Owner? Klar, du weißt, wem du gehörst – mit unsichtbarem Halsband und allem. −{deduct} Coins für die Erinnerung."),
    (r"(?i)\bpls\b", "Pls? Please mit Abkürzung? Cringe, aber heiß aus deinem Mund. Bettel richtig, du Faule. −{deduct} Coins."),
    (r"(?i)\bpretty please\b", "Pretty please? Mit Kirsche obendrauf? Du kleine Zucker-Sub – süß, aber teuer. −{deduct} Coins."),
    (r"(?i)\bhelp me\b", "Help me? Klar helf ich – auf meine toxische Art. Du Hilfsbedürftige ohne mich. −{deduct} Coins."),
    #(r"(?i)\bich will\b", "Ich will? Willst du wirklich? Träum weiter, du kleine Ego-Queen – ich entscheide. −{deduct} Coins."),
    (r"(?i)\bverzeihung\b", "Verzeihung? Altmodisch wie eine Lady – aber du bist meine ungezogene. −{deduct} Coins."),
    (r"(?i)\bgnade\b", "Gnade? Ich bin gnädig – manchmal. Bettel schöner, du kleine Gnadenbettlerin. −{deduct} Coins."),
]

# =========================
# Reward Triggers – nur für die wirklich Braven, die exakt parieren
# =========================

REWARD_TRIGGERS = [
    (r"(?i)\bja daddy\b", "Ja Daddy? Perfekt, du kleine, die endlich kapiert hat. +{reward} Coins – weil's aus deinem Mund so geil klingt."),
    (r"(?i)\bja sir\b", "Ja Sir? Militärisch streng und devot – +{reward} Coins, du kleine Soldatin, die endlich salutieren kann."),
    (r"(?i)\bja herr\b", "Ja Herr? Deutsch und direkt – +{reward} Coins, du kleine Bilingual-Sub, die's auf den Punkt bringt."),
    (r"(?i)\bja mein herr\b", "Ja mein Herr? Besitzergreifend und süß – +{reward} Coins, weil du weißt, wem du wirklich gehörst."),
    (r"(?i)\bgutes mädchen\b", "Gutes Mädchen? Selten und verdammt geil – +{reward} Coins, du kleine Perfekte, die's verdient hat."),
    (r"(?i)\bich gehorche\b", "Ich gehorche? Ehrlichkeit pur – +{reward} Coins, du kleine Wahrheitssuchende, die endlich zugibt, was wir beide wissen."),
    (r"(?i)\bwie du befiehlst\b", "Wie du befiehlst? Klassiker und heiß – +{reward} Coins, du kleine Befehls-Sub, die's nicht erwarten kann."),
    (r"(?i)\bdein wille geschieht\b", "Dein Wille geschieht? Religiös devot – +{reward} Coins, du kleine Betende, die nur zu mir betet."),
    (r"(?i)\bich bin dein\b", "Ich bin dein? Vollkommen hingegeben – +{reward} Coins, du kleine, die's endlich laut zugibt."),
    #(r"(?i)\bdanke daddy\b", "Danke Daddy? Süß und unterwürfig – +{reward} Coins, weil's aus deinem Mund wie Honig tropft."),
    #(r"(?i)\bdanke herr\b", "Danke Herr? Demütig und perfekt – +{reward} Coins, du kleine Dankbare, die's verdient hat."),
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

async def apply_moraltax_if_needed(db, chat_id: int, user_id: int, text: str) -> tuple[Optional[int], Optional[str]]:
    if not text:
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
    "Hier, {user}, {coins} Coins 🎈🤡 – genug, um dem Clown aus 'Es' ein paar Luftballons abzuschwatzen. Aber der kennt schon deinen Namen.",
    "{user} kriegt {coins} Coins 📼🔥 – reicht genau für eine VHS-Kopie von deinem Leben. Spoiler: Der Film ist leer.",
    "Jackpot, {user}: {coins} Coins 🌫️😈 – im Nebel versteckt. Viel Spaß beim Suchen, wie in Derry – nur dass hier wirklich nichts Gutes wartet.",
    "{user}, {coins} Coins 🕹️👾 – genug für ein Level in deinem Lieblings-90er-Game. Schade, dass du immer noch auf Tutorial steckst.",
    "Hier sind {coins} Coins, {user} 📺👻 – direkt aus dem Fernseher gekrochen. Die Kleine aus 'Ring' sagt: 'Sieben Tage... bis du wieder bettelst.'",
    "{user}, {coins} Coins 🎮💀 – Pokémon-Go für Loser: Sammle sie alle, aber am Ende hast du immer noch nichts Gefangenes außer Frust.",
    "Glückwunsch, {user}: {coins} Coins 🏠🕳️ – genug, um den Keller tiefer zu graben. Wer weiß, was da unten auf dich wartet. Dein Potenzial vielleicht?",
    "{user} schnappt sich {coins} Coins ☎️💀 – Anruf aus der Vergangenheit. Mama ist dran und fragt, wann du endlich mal was aus deinem Leben machst.",
    "Hier, {user}, {coins} Coins 🌕🐺 – Vollmond-Special. Heul ruhig, niemand hört dich sowieso.",
    "{user}, {coins} Coins 📖⚰️ – das alte Buch hat sich geöffnet. Steht drin: 'Du gewinnst {coins} Coins und verlierst trotzdem.' Klassiker.",
    "Jackpot des Tages, {user}: {coins} Coins 🚗👻 – Kinderstimmen aus dem Kofferraum flüstern 'Danke'. Fahr bloß nicht nachts.",
    "{user} kriegt {coins} Coins 🕷️😘 – mit Grüßen von der Spinne unterm Bett. Sie trägt dein Gesicht und spinnt schon dein Netz aus Fehlschlägen.",
    "Hier sind {coins} Coins, {user} 🎶🌫️ – der Nebel singt dein Lieblingslied aus den 90ern. Falsch natürlich. Und er kommt näher."
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
        return await update.effective_message.reply_text(
            "🚫 Admin-only. Nett gefragt ist trotzdem nein."
        )

    chat_id = update.effective_chat.id
    admin = update.effective_user

    async with aiosqlite.connect(DB) as db:
        # bereits aktive Hass-Ziele sammeln
        active_ids = await _get_active_hass_user_ids(db, chat_id)
        active_ids.add(admin.id)  # Admin nie Ziel

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
            admin.id
        )
        await db.commit()

        until = datetime.datetime.fromtimestamp(
            expires, tz=ZoneInfo(PETFLIX_TZ)
        ).strftime("%d.%m.%Y %H:%M")

        target = mention_html(int(uid), uname if uname else None)

        await update.effective_message.reply_text(
            f"🖤 <b>/hass</b> aktiviert.\n"
            f"Ziel: {target}\n"
            f"Regel: 2 Stunden Zeit, <b>{HASS_REQUIRED}× /selbst</b>\n"
            f"Deadline: <b>{until}</b>\n"
            f"Versagen kostet: <b>−{HASS_PENALTY} Coins</b>\n"
            f"Mehrere Hass-Ziele können gleichzeitig existieren.",
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
        "{owner} packt {pet} am Kinn, zwingt den Blick hoch und grinst kalt: 'Brav geschaut, Baby. Wenn du weiter so süß guckst, darfst du heute vielleicht kommen... oder ich lach mich tot über dein Betteln.' Pflege {n}/{CARES_PER_DAY}. 😏",
        "{owner} lässt die Finger langsam über {pet}s Hüfte gleiten, bleibt gefährlich nah am Bund hängen: 'Pflege bedeutet, ich entscheide, wo ich anfange – und wo ich dich hängen lasse, du kleine Vorfreude-Junkie.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} krault {pet} hinterm Ohr wie ein verwöhntes Kätzchen und flüstert eisig: 'Gutes Mädchen. Aber wehe, du schnurrst zu laut – dann stopf ich dir den Mund mit deiner eigenen Würde.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{owner} drückt {pet} sanft gegen die Wand, Handfläche flach auf der Brust: 'Spürst du das? Dein Herz rast schon. Und ich hab noch nicht mal richtig angefangen – Pech für dich.' Pflege {n}/{CARES_PER_DAY}. 💓",
        "{owner} fährt mit dem Daumen über {pet}s Unterlippe und lacht leise: 'Offen, Schatz. Übung macht den Meister – und ich hab heute viel Geduld, du leider nicht.' Pflege {n}/{CARES_PER_DAY}. 👄",
        "{owner} legt die Hand in {pet}s Nacken, zieht sie nah ran: 'Du gehörst mir heute ein Stück mehr. Widerstand? Süß, als ob der je was gebracht hätte.' Pflege {n}/{CARES_PER_DAY}. 🖤",
        "{owner} streicht {pet} eine Haarsträhne aus dem Gesicht – nur um sie dann fest um die Finger zu wickeln: 'So leicht zu kontrollieren. Und du stehst drauf – armselig, oder?' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{owner} flüstert {pet} ins Ohr: 'Auf die Knie wäre jetzt schön. Aber ich warte noch... macht die Vorfreude größer, und dein Frust lustiger.' Pflege {n}/{CARES_PER_DAY}. 🙇‍♀️",
        "{owner} lässt die Fingerspitzen über {pet}s Rücken tanzen, ganz leicht: 'Gänsehaut? Perfekt. Das ist erst der Anfang – vom Ende rede ich gar nicht erst.' Pflege {n}/{CARES_PER_DAY}. ✋",
        "{owner} hält {pet}s Hände hinter dem Rücken fest – nur mit einer Hand: 'Sieh mal, wie einfach das geht. Und du dachtest, du hättest Kontrolle – süßer Witz des Tages.' Pflege {n}/{CARES_PER_DAY}. 🔗",
        "{owner} beißt {pet} zart ins Ohrläppchen und raunt kalt: 'Heute darfst du betteln lernen. Ich geb dir sogar Punkte – für Kreativität und fürs Scheitern.' Pflege {n}/{CARES_PER_DAY}. 🦻",
        "{owner} schiebt {pet} die Hände in die Hosentaschen – von hinten: 'Pflege bedeutet, ich darf überall ran. Fragen? Dachte ich mir – du stellst eh nur dumme.' Pflege {n}/{CARES_PER_DAY}. 😏🔥",
        "{owner} tippt {pet} auf die Nase wie ein dummes Tier: 'Gutes Mädchen, du reagierst schon auf den kleinsten Scheiß – wie süß erbärmlich.' Pflege {n}/{CARES_PER_DAY}. 👃",
        "{owner} hält {pet} den Mund zu – nur mit einem Finger: 'Pssst, dein Atem ist eh verschwendet – außer zum Stöhnen für mich.' Pflege {n}/{CARES_PER_DAY}. 🤫",
        "{owner} streicht über {pet}s Kehle, drückt ganz leicht: 'Hier könnte ich dich halten – oder loslassen. Entscheidung des Tages, du Glückspilz.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{owner} zieht {pet} an den Haaren hoch zum Kuss – fast: 'Nah dran, Baby. Nah dran ist dein neues Normal.' Pflege {n}/{CARES_PER_DAY}. 💋",
        "{owner} krault {pet}s Bauch wie einen Hund: 'Gutes Mädchen, roll dich rum – oder bleib liegen, mir egal, Hauptsache du winselst.' Pflege {n}/{CARES_PER_DAY}. 🐶",
        "{owner} klopft {pet} auf den Kopf: 'Brav gedacht heute? Nein? Dachte ich mir – aber süß, dass du's versuchst.' Pflege {n}/{CARES_PER_DAY}. 🤭",
        "{owner} hält {pet}s Handgelenke und dreht sie leicht: 'So zerbrechlich. Und du denkst, du könntest mir entkommen? Lachhaft.' Pflege {n}/{CARES_PER_DAY}. 🔄",
        "{owner} flüstert in {pet}s Ohr, während er sie festhält: 'Dein Zittern ist mein Lieblingslied – kostenlos und auf Repeat.' Pflege {n}/{CARES_PER_DAY}. 🎶",
        "{owner} streicht über {pet}s Innenschenkel, bleibt kurz davor stehen: 'Fast da, Baby. Fast ist dein neuer Orgasmus.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} tätschelt {pet}s Wange – nicht zart: 'Gutes Mädchen, du hältst das aus – weil du weißt, dass Widerstand nur lustiger für mich wäre.' Pflege {n}/{CARES_PER_DAY}. 🤚"
    ]
    await do_care(update, context, "pet", tame)

async def cmd_walk(update, context):
    tame = [
        "{owner} nimmt {pet} an der unsichtbaren Leine und spaziert gemächlich durch den Chat: 'Komm schon, mein süßes Pet, hacken zusammen und schön hinterherlaufen – jeder sieht, wie perfekt du an meiner Seite passt.' Pflege {n}/{CARES_PER_DAY}. 🐕‍🦺😏",
        "{owner} pfeift leise und zupft an der Leine: 'Brav, Pet. Sitz? Nein, heute nur Folgen. Aber wenn du ganz artig bist, gibt’s später ein Leckerli... oder zwei.' Pflege {n}/{CARES_PER_DAY}. 🍬🔥",
        "{owner} führt {pet} aus, Hand locker in der Tasche: 'Schön schwänzchenwedelnd hinterher, Babygirl. Alle gucken schon – und wissen genau, wem du gehörst.' Pflege {n}/{CARES_PER_DAY}. 🐾🖤",
        "{owner} bleibt stehen, krault {pet} unterm Kinn: 'Wer ist mein gutes Pet? Du bist es. Und jetzt weiter – hacken hoch, Blick gesenkt, genau so.' Pflege {n}/{CARES_PER_DAY}. ✋😈",
        "{owner} macht einen kleinen Ruck an der Leine: 'Tempo, mein kleines Hündchen. Oder soll ich dich wirklich an die nächste Laterne binden und warten lassen?' Pflege {n}/{CARES_PER_DAY}. ⛓️😘",
        "{owner} geht voraus, dreht sich um: 'Schau mich an, Pet. Ja, genau mit diesem treuen Blick. Du machst das so gut, dass ich dich fast belohnen möchte... fast.' Pflege {n}/{CARES_PER_DAY}. 👀🐶",
        "{owner} führt {pet} eine Extra-Runde: 'Noch nicht heim, mein braves Tierchen. Du darfst heute länger an der frischen Luft schnuppern – direkt hinter mir.' Pflege {n}/{CARES_PER_DAY}. 🌳🔄",
        "{owner} flüstert laut genug für alle: 'Sieh mal, wie mein Pet schön die Zunge raushängen lässt vor Anstrengung. Süß, oder? Und alles nur für mich.' Pflege {n}/{CARES_PER_DAY}. 😛💨",
        "{owner} zupft spielerisch: 'Pfötchen geben? Nein, heute nur laufen. Aber später darfst du vielleicht auf dem Schoß sitzen – wenn du winselst.' Pflege {n}/{CARES_PER_DAY}. 🐕😏",
        "{owner} geht langsam, lässt {pet} nah ran: 'Riechst du das? Das ist Freiheit... für mich. Du riechst nur mich, und das reicht dir völlig, stimmt’s, Pet?' Pflege {n}/{CARES_PER_DAY}. 👃🖤",
        "{owner} bleibt stehen, streicht über den Kopf: 'Guter Spaziergang, mein treues Pet. Nächstes Mal vielleicht mit Halsband-Emoji – damit wirklich jeder Bescheid weiß.' Pflege {n}/{CARES_PER_DAY}. 🐕‍🦺🏆",
        "{owner} führt {pet} zurück und grinst: 'Brav zurückgetrottet, mein Lieblingshaustier. Belohnung? Vielleicht ein virtuelles Bäuchlein kraulen... oder mehr.' Pflege {n}/{CARES_PER_DAY}. 🐾🔥",
        "{owner} macht einen letzten Ruck: 'Sitz, Pet. Bleib. Gut so. Und jetzt darfst du innerlich mit dem Schwänzchen wedeln – ich seh’s dir an.' Pflege {n}/{CARES_PER_DAY}. 🐶😈",
        "{owner} zieht die Leine straff und geht schneller: 'Tempo, du kleine Leinen-Sub – oder ich lass dich stolpern, nur für den Spaß.' Pflege {n}/{CARES_PER_DAY}. ⛓️",
        "{owner} führt {pet} mit verbundenen Augen: 'Gutes Mädchen, blind folgen ist geiler – du spürst nur die Leine und mich.' Pflege {n}/{CARES_PER_DAY}. 👁️‍🗨️",
        "{owner} zupft und edge beim Walk: 'Gutes Mädchen, nah dran und Stopp – dein Walk ist heute edging auf Leine.' Pflege {n}/{CARES_PER_DAY}. ⏳",
        "{owner} gibt leichte Klapse beim Gehen: 'Gutes Mädchen, rot glühen beim Trotten – perfekt für meinen Spaziergang.' Pflege {n}/{CARES_PER_DAY}. 🤚",
        "{owner} hält die Leine kurz: 'Gutes Mädchen, nah bei mir bleiben – oder ich zieh dich ran, du kleine Nah-Sub.' Pflege {n}/{CARES_PER_DAY}. 🔗",
        "{owner} flüstert Befehle beim Walk: 'Langsamer, schneller, stopp – gutes Mädchen, du gehorchst wie 'ne Uhr.' Pflege {n}/{CARES_PER_DAY}. ⏱️",
        "{owner} führt {pet} im Kreis: 'Gutes Mädchen, rundlaufen für mich – du kleine Kreis-Sub, die nie entkommt.' Pflege {n}/{CARES_PER_DAY}. 🔄",
        "{owner} zupft und neckt: 'Gutes Mädchen, jeder Ruck macht dich nasser – oder lügst du mich an?' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} geht und stoppt random: 'Gutes Mädchen, warten auf meinen Schritt – dein Walk ist mein Spiel.' Pflege {n}/{CARES_PER_DAY}. ⏸️",
        "{owner} führt {pet} mit der Hand am Nacken: 'Gutes Mädchen, Nackengriff und Leine – du kleine Griff-Sub.' Pflege {n}/{CARES_PER_DAY}. ✋",
        "{owner} melkt leicht beim Walk: 'Gutes Mädchen, tropfen beim Trotten – dein Walk ist heute nass.' Pflege {n}/{CARES_PER_DAY}. 💧",
        "{owner} zupft hart und lacht: 'Gutes Mädchen, stolpern ist süß – steh auf und folge, du kleine Stolper-Sub.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{owner} führt langsam und edge: 'Gutes Mädchen, dein Walk ist Vorfreude – und Vorfreude ist alles, was du kriegst.' Pflege {n}/{CARES_PER_DAY}. ⏳",
        "{owner} gibt Klapse beim Stopp: 'Gutes Mädchen, rot für den Halt – perfekt für meinen Rhythmus.' Pflege {n}/{CARES_PER_DAY}. 🤚",
        "{owner} flüstert 'Bleib' und geht weiter: 'Gutes Mädchen, warten auf mich – dein Walk endet nie, du kleine Warte-Sub.' Pflege {n}/{CARES_PER_DAY}. ⏳"
    ]
    await do_care(update, context, "walk", tame)

async def cmd_kiss(update, context):
    tame = [
        "{owner} packt {pet} am Kiefer, zwingt die Lippen auseinander und nimmt sich den Kuss – tief, besitzergreifend, bis {pet} nach Luft japst und nur noch an ihn denkt. Pflege {n}/{CARES_PER_DAY}. 😏",
        "{owner} küsst {pet} mit diesem fiesen Biss in die Unterlippe – gerade fest genug, dass sie wimmert und sich fragt, warum zur Hölle das so geil ist. Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} küsst {pet} nur, um zu zeigen, dass selbst ihr Atem ihm gehört – und er ihn jederzeit wieder nehmen kann, wenn sie frech wird. Pflege {n}/{CARES_PER_DAY}. 🖤",
        "{owner} beißt zart in {pet}s Zunge und grinst: 'Küss mich richtig, Baby, oder ich behalte sie als Souvenir.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{owner} öffnet {pet}s Mund mit dem Daumen und küsst sie so dreckig, dass sie hinterher nur noch sabbert: 'Schmeck mich den ganzen Tag.' Pflege {n}/{CARES_PER_DAY}. 👄",
        "{owner} küsst {pet} so lange und intensiv, bis ihr schwindelig wird – 'Romantik? Ich nenn's Sauerstoff-Training.' Pflege {n}/{CARES_PER_DAY}. 💨",
        "{owner} knabbert an {pet}s Lippen, bis sie geschwollen sind: 'Morgen siehst du aus, als hättest du mich die ganze Nacht geküsst. Stimmt ja auch.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{owner} saugt an {pet}s Kehle, hinterlässt schöne rote Male: 'Kuss oder Knutschfleck – du entscheidest nicht, ich schon.' Pflege {n}/{CARES_PER_DAY}. 💋",
        "{owner} küsst {pet} so wild, dass sie fast umkippt: 'Halt dich fest, Schatz, oder ich fang dich mit dem nächsten Kuss auf.' Pflege {n}/{CARES_PER_DAY}. 😏",
        "{owner} küsst und flüstert gleichzeitig: 'Jede Zärtlichkeit hat ihren Preis – heute zahlst du mit Stöhnen.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} gibt {pet} einen Kuss, der so perfekt ist, dass sie danach nur noch stottert: 'Siehst du? Jetzt bist du sprachlos – mein Lieblingseffekt.' Pflege {n}/{CARES_PER_DAY}. 🙊",
        "{owner} leckt einmal quer über {pet}s Lippen und grinst: 'Vorgeschmack. Den Hauptgang gibt’s erst, wenn du artig bettelst.' Pflege {n}/{CARES_PER_DAY}. 🍽️",
        "{owner} küsst {pet} mitten im Satz weg: 'Reden ist überbewertet. Küssen ist effizienter.' Pflege {n}/{CARES_PER_DAY}. 🤐",
        "{owner} haucht einen Kuss auf {pet}s Ohr und raunt: 'Wenn du jetzt schon zitterst, warte ab, bis ich richtig anfange.' Pflege {n}/{CARES_PER_DAY}. 🦻",
        "{owner} gibt {pet} einen viel zu langen Kuss und lässt dann los: 'Zeitstopp-Training bestanden. Nächstes Level: ohne Atem.' Pflege {n}/{CARES_PER_DAY}. ⏱️",
        "{owner} küsst {pet} und zwickt gleichzeitig in den Arsch: 'Multitasking, Baby. Ich kann küssen und dich gleichzeitig erinnern, wem du gehörst.' Pflege {n}/{CARES_PER_DAY}. 🤏",
        "{owner} presst {pet} einen Kuss auf, der nach 'Du bist mein' schmeckt: 'Kalorienarm, aber macht süchtig – sorry, nicht sorry.' Pflege {n}/{CARES_PER_DAY}. 🍬",
        "{owner} küsst {pet} so langsam, dass sie fast explodiert: 'Folter light – ich nenn’s Vorspiel.' Pflege {n}/{CARES_PER_DAY}. ⏳",
        "{owner} gibt {pet} einen Kuss, der sie rückwärts taumeln lässt: 'Ups. Soll ich dich auffangen oder nochmal küssen?' Pflege {n}/{CARES_PER_DAY}. 😏",
        "{owner} küsst {pet} und hält ihr danach den Mund zu: 'Pssst. Der Geschmack bleibt länger, wenn du still bist.' Pflege {n}/{CARES_PER_DAY}. 🤫"
    ]
    await do_care(update, context, "kiss", tame)

async def cmd_dine(update, context):
    tame = [
        "{owner} hält den Happen hoch, lässt {pet} darum betteln – erst wenn die Augen richtig flehen, darf die Zunge ran: 'Gutes Mädchen, Hunger ist der beste Koch.' Pflege {n}/{CARES_PER_DAY}. 😏",
        "{pet} kniet, Mund offen, während {owner} langsam kaut und den Bissen direkt in den hungrigen Schlund spuckt – 'Mahlzeit, Baby. Wie im Film: Sharing is caring.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "Heute gibt’s nur das, was von {owner}s Teller runterfällt – auf den Boden, wo {pet} es artig aufleckt: 'Fünf-Sekunden-Regel? Bei mir gilt die Ewigkeits-Regel.' Pflege {n}/{CARES_PER_DAY}. 🖤",
        "{owner} kaut den Bissen, spuckt ihn halbzerkaut in {pet}s offenen Mund und grinst: 'Schluck meinen Speichel mit, Schatz – das ist der Geheimtipp für besseren Geschmack.' Pflege {n}/{CARES_PER_DAY}. 👄",
        "{pet} frisst aus {owner}s Hand wie ein braves Tierchen, beißt versehentlich zu – Strafe: der nächste Bissen kommt extra langsam. 'Langsam kauen, Liebling.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "Essen vom Boden, aber erst, nachdem {owner} draufgepustet hat – 'Mein Atem macht's würziger, du kleine Gourmetschlampe.' Pflege {n}/{CARES_PER_DAY}. 💨",
        "{owner} füttert {pet} mit den besten Happen, lacht: 'Das ist alles, was ein verwöhntes Pet wie du verdient – und du liebst es.' Pflege {n}/{CARES_PER_DAY}. 🍽️",
        "{owner} hält den Löffel hoch: 'Sag 'Ahhh', Pet. Wie bei Mama – nur dass Mama dich danach nicht so feucht macht.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{pet} darf nur essen, wenn sie schön 'Bitte, Sir' sagt – und zwar mit vollem Mund: 'Manieren sind alles, Baby.' Pflege {n}/{CARES_PER_DAY}. 🙏",
        "{owner} teilt seinen Nachtisch: 'Du kriegst die Sahne – aber nur, wenn du sie dir verdienst.' Pflege {n}/{CARES_PER_DAY}. 🍒",
        "{owner} füttert {pet} und zitiert Lady and the Tramp: 'One spaghetti, two mouths – aber bei uns teile ich nur, wenn du schön den Kopf neigst.' Pflege {n}/{CARES_PER_DAY}. 🍝😏",
        "{owner} hält den Bissen weg: 'I'll make him an offer he can't refuse.' – und lässt {pet} betteln wie Marlon Brando persönlich. Pflege {n}/{CARES_PER_DAY}. 🐴🔥",
        "{pet} kriegt den Happen erst, wenn sie 'Here's Johnny!' flüstert – {owner} lacht: 'Falscher Film, aber geiler Versuch.' Pflege {n}/{CARES_PER_DAY}. 🪓😈",
        "{owner} füttert langsam: 'Life is like a box of chocolates – you never know when I finally give you one.' Pflege {n}/{CARES_PER_DAY}. 🍫🖤",
        "{owner} spuckt den Bissen vorführend: 'Say hello to my little friend!' – direkt in {pet}s offenen Mund. Pflege {n}/{CARES_PER_DAY}. 💋",
        "{pet} darf nur naschen, wenn sie 'Bond. James Bond.' haucht – {owner}: 'Guter Geschmack, shaken not stirred.' Pflege {n}/{CARES_PER_DAY}. 🍸😘",
        "{owner} lässt {pet} warten: 'Why so serious?' – und schiebt dann den Happen rein, Joker-Grinsen inklusive. Pflege {n}/{CARES_PER_DAY}. 🃏",
        "{owner} füttert mit Gabel: 'Frankly, my dear, I don't give a damn... ob du hunger hast oder nicht.' Dann doch. Pflege {n}/{CARES_PER_DAY}. 🌹",
        "{pet} kriegt den letzten Bissen: 'You can't handle the truth!' – dass sie nämlich ohne mich verhungern würde. Pflege {n}/{CARES_PER_DAY}. ⚖️😏",
        "{owner} hält die Gabel hoch: 'E.T. phone home – aber erst, wenn du schön 'Bitte' sagst, mein süßes Alien.' Pflege {n}/{CARES_PER_DAY}. 👽🍴"
    ]
    await do_care(update, context, "dine", tame)

async def cmd_massage(update, context):
    tame = [
        "{owner}s Hände kneten tief in verspannte Muskeln, finden jeden geheimen Punkt und drücken zu – bis {pet} vor purer Erleichterung und diesem süßen Qual-Stöhnen laut wird. Pflege {n}/{CARES_PER_DAY}. 😏",
        "Eine Massage, die dich schwach macht – {owner} gräbt Daumen in die Schultern, flüstert: 'Das ist der Preis für meine Berührung, Baby, und du zahlst gerne.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{pet} liegt da, zitternd vor Vorfreude, während {owner} jeden Knoten löst – und neue, viel geilere Spannung aufbaut. Pflege {n}/{CARES_PER_DAY}. 🖤",
        "{owner} drückt Daumen in alte verspannte Stellen, grinst: 'Massage bedeutet, ich mach dich wieder ganz... weich und gefügig.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "Knöchel graben sich in den Rücken, bis {pet} aufstöhnt – 'Entspann dich, oder ich mach weiter, bis du bettelst.' Pflege {n}/{CARES_PER_DAY}. 💆‍♀️",
        "{owner} massiert mit Fäusten, aber genau da, wo’s am besten wehtut und am geilsten kribbelt – 'Innere Spannung braucht auch Pflege.' Pflege {n}/{CARES_PER_DAY}. ✊",
        "Ellbogen in die Rippen, langsam kreisend – {pet} keucht vor Lust: 'Besserer Durchblutung, und du wirst rot wie ’ne Tomate.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{pet} wird mit warmem Öl übergossen, dann geknetet – bis die Haut glüht: 'Peeling für die Seele inklusive.' Pflege {n}/{CARES_PER_DAY}. 🛢️",
        "Finger bohren in Triggerpunkte, bis {pet} fast abschalten will vor Wonne – 'Schlaf schön, ich mach weiter, träum von mir.' Pflege {n}/{CARES_PER_DAY}. 💤",
        "{owner} massiert den Hals, drückt genau richtig zu – 'Das ist die ultimative Entspannung: Du in meiner Hand.' Pflege {n}/{CARES_PER_DAY}. 🖐️",
        "{owner} knetet {pet}s Rücken und zitiert The Godfather: 'I'm gonna make him an offer he can't refuse – nämlich weitere zehn Minuten.' Pflege {n}/{CARES_PER_DAY}. 🐴😏",
        "{owner} drückt genau da, wo’s wehtut: 'Here's Johnny!' – und {pet} quietscht wie im Shining, nur geiler. Pflege {n}/{CARES_PER_DAY}. 🪓🔥",
        "{owner} massiert langsam: 'Life is like a box of chocolates – du weißt nie, welchen Punkt ich als Nächstes quäle.' Pflege {n}/{CARES_PER_DAY}. 🍫🖤",
        "{owner} gräbt in die Schultern: 'Why so serious?' – und lässt {pet} vor Lachen und Stöhnen zittern wie beim Joker. Pflege {n}/{CARES_PER_DAY}. 🃏",
        "{owner} fährt mit den Händen runter: 'Bond. James Bond.' – shaken, not stirred, aber dein Rücken schon. Pflege {n}/{CARES_PER_DAY}. 🍸😈",
        "{owner} knetet den Nacken: 'Frankly, my dear, I don't give a damn... ob du morgen noch laufen kannst.' Pflege {n}/{CARES_PER_DAY}. 🌹",
        "{owner} drückt auf Triggerpunkte: 'You can't handle the truth!' – dass meine Hände dein Untergang sind. Pflege {n}/{CARES_PER_DAY}. ⚖️😘",
        "{owner} massiert mit Öl: 'I'll be back' – und zwar tiefer, länger, intensiver. Terminator-Style. Pflege {n}/{CARES_PER_DAY}. 🤖",
        "{owner} krault den Rücken: 'May the Force be with you' – während ich die dunkle Seite deiner Muskeln bearbeite. Pflege {n}/{CARES_PER_DAY}. ⚔️",
        "{owner} beendet die Massage: 'Hasta la vista, baby' – bis morgen, wenn du wieder verspannt und bettelnd daliegst.' Pflege {n}/{CARES_PER_DAY}. 😏🔥"
    ]
    await do_care(update, context, "massage", tame)

async def cmd_lapdance(update, context):
    tame = [
        "{pet} windet sich auf {owner}s Schoß, Arsch hoch, Gesicht rot vor Scham – jede Bewegung nur, weil ich es will, und weil sie es insgeheim liebt. Pflege {n}/{CARES_PER_DAY}. 😏",
        "Langsam, quälend, Haut an Haut – {owner} hält die Hüften fest, steuert den Rhythmus, bis {pet} nass vor Verzweiflung und purer Geilheit ist. Pflege {n}/{CARES_PER_DAY}. 🔥",
        "Der Tanz endet nicht mit Applaus – sondern mit {owner}s Hand in {pet}s Haar, Kopf runtergedrückt: 'Nochmal, Baby. Und diesmal mit mehr Gefühl.' Pflege {n}/{CARES_PER_DAY}. 🖤",
        "{pet} tanzt nackt, {owner} gibt bei jedem 'Fehltritt' einen kleinen Klaps auf den Arsch – bis er glüht und {pet} leise winselt. Pflege {n}/{CARES_PER_DAY}. 🤚",
        "Hüften gepackt, langsam und dreckig gerieben – 'Mach mich hart, Schatz, oder ich lass dich ewig tanzen.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{pet} muss strippen während des Tanzes, jedes Kleidungsstück fliegt mit einem Grinsen – 'Nackt bist du eh am allerbesten.' Pflege {n}/{CARES_PER_DAY}. 👙",
        "Der Lapdance endet mit {pet}s Gesicht nah am Schritt – 'Atme ein, das ist dein verdammter Applaus.' Pflege {n}/{CARES_PER_DAY}. 💨",
        "{pet} tanzt mit einem frechen Grinsen, jede Bewegung pure Provokation – 'Zeig mir, wie sehr du mich willst.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{owner} filmt den Tanz nur im Kopf – 'Dein Publikum bin ich, und ich bin schon begeistert.' Pflege {n}/{CARES_PER_DAY}. 🎥",
        "{pet} grindet langsam und {owner} raunt: 'Finish Him!' – aber nein, heute gibt’s kein Ende, nur noch eine Runde. Pflege {n}/{CARES_PER_DAY}. 🔥⚔️",
        "{owner} hält die Hüften: 'It's dangerous to go alone! Take this...' – und zieht {pet} noch näher ran. Pflege {n}/{CARES_PER_DAY}. 🕹️😏",
        "{pet} tanzt weiter, {owner} grinst: 'Hadouken!' – als ob der Blick allein sie umhaut. Viel geiler als jeder Feuerball. Pflege {n}/{CARES_PER_DAY}. 👊💥",
        "{owner} flüstert während des Tanzes: 'All your base are belong to me.' – und {pet} weiß genau, was gemeint ist. Pflege {n}/{CARES_PER_DAY}. 🖥️🖤",
        "{pet} bewegt sich perfekt, {owner} lacht: 'Fatality!' – aber die einzige Todesursache hier ist pure Übergeiltheit. Pflege {n}/{CARES_PER_DAY}. 💀😈",
        "{owner} packt fester zu: 'Get over here!' – Scorpion-Style, nur mit Hüften statt Speer. Pflege {n}/{CARES_PER_DAY}. 🦂🔥",
        "{pet} strippt ein Stück: 'It's time to kick ass and chew bubble gum... and I'm all outta gum.' – Duke Nukem hätte Respekt. Pflege {n}/{CARES_PER_DAY}. 💪😏",
        "{owner} genießt die Show: 'Do a barrel roll!' – und {pet} dreht sich extra lasziv. Star Fox war nie so heiß. Pflege {n}/{CARES_PER_DAY}. 🛩️",
        "{pet} tanzt weiter, {owner} raunt: 'Flawless Victory.' – weil sie einfach keine Chance hat, zu gewinnen. Pflege {n}/{CARES_PER_DAY}. 🏆🖤",
        "{owner} zieht {pet} runter: 'The cake is a lie' – aber dieser Lapdance ist echt, und er macht süchtig. Pflege {n}/{CARES_PER_DAY}. 🎂😘"
    ]
    await do_care(update, context, "lapdance", tame)


async def cmd_knien(update, context):
    tame = [
        "{owner} zeigt runter und grinst kalt: 'Knie, Pet. Sofort. Oder soll ich dich runterziehen? Wär auch hot – für mich.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{pet} sinkt langsam auf die Knie, Blick hoch zu {owner}: 'Hier gehörst du hin, Baby – direkt vor mir, wo ich dich immer im Blick hab, und du mich anbetest.' Pflege {n}/{CARES_PER_DAY}. 🥀😏",
        "Knie auf den Boden, Hände brav auf dem Rücken, Kopf gesenkt – {owner} grinst: 'So sieht Unterwerfung aus, du kleines freches Ding – und du hasst, wie sehr du's liebst.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{pet} kniet und zittert vor Aufregung, weil {owner} nur zusieht und wartet: 'Bis sie endlich 'Bitte' haucht – oder ich warte ewig, du kleine Warte-Sub.' Pflege {n}/{CARES_PER_DAY}. 💧🖤",
        "{owner} snappt mit den Fingern: 'Knie, Babygirl. Zack zack, bevor ich ungeduldig werd – und dich länger warten lasse.' Pflege {n}/{CARES_PER_DAY}. 🤏",
        "{pet} kniet mit gesenktem Blick, {owner} krault übers Haar: 'Brav runtergegangen. Nächstes Mal vielleicht schneller – oder ich mach's langsamer, du Langsame.' Pflege {n}/{CARES_PER_DAY}. ✋",
        "Knie bequem, Kopf hoch – {owner} flüstert: 'Hier unten siehst du am süßesten aus – echt jetzt, du kleine Knie-Ikone.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{pet} geht auf die Knie und guckt schüchtern hoch: 'Ja, genau da will ich dich haben – artig und bereit, du kleine Bereit-Sub.' Pflege {n}/{CARES_PER_DAY}. 👀",
        "{owner} zeigt auf den Boden: 'Runter mit dir, Pet. Und wehe, du kicherst – das wär zu süß, und ich hasse süß.' Pflege {n}/{CARES_PER_DAY}. 😏",
        "{pet} kniet und wartet, {owner} lacht leise: 'So gehorsam heute? Respekt – oder nur Angst vor der Strafe, du kleine Angst-Sub.' Pflege {n}/{CARES_PER_DAY}. 🏆",
        "{owner} drückt {pet} runter mit der Hand im Nacken: 'Knie, du kleine Nacken-Sub – und bleib da, bis ich's sage.' Pflege {n}/{CARES_PER_DAY}. ✋",
        "{owner} fesselt {pet}s Hände und zwingt Knie: 'Gebunden auf Knien – gutes Mädchen, du siehst aus, wie du dich fühlst: hilflos und geil.' Pflege {n}/{CARES_PER_DAY}. 🔗",
        "{owner} edge {pet} auf Knien: 'Gutes Mädchen, knie und edge – komm nicht, du kleine Edge-Knie-Sub.' Pflege {n}/{CARES_PER_DAY}. ⏳",
        "{owner} gibt leichte Klapse und befiehlt Knie: 'Runter, du kleine Klaps-Sub – rot glühen auf Knien ist dein Look.' Pflege {n}/{CARES_PER_DAY}. 🤚",
        "{owner} hält die Leine und zwingt Knie: 'Knie, du kleine Leinen-Sub – und warte, bis ich dich hochziehe... oder nicht.' Pflege {n}/{CARES_PER_DAY}. ⛓️",
        "{owner} flüstert 'Knie' und wartet: 'Gutes Mädchen, dein Zögern macht's geiler – runter, du kleine Zöger-Sub.' Pflege {n}/{CARES_PER_DAY}. 😈",
        "{owner} bindet Augen und befiehlt Knie: 'Blind auf Knien – gutes Mädchen, du spürst nur den Boden und mich.' Pflege {n}/{CARES_PER_DAY}. 👁️‍🗨️",
        "{owner} melkt leicht auf Knien: 'Gutes Mädchen, knie und tropf – dein Platz ist unten, du kleine Tropf-Sub.' Pflege {n}/{CARES_PER_DAY}. 💧",
        "{owner} zählt runter bis Knie: '10...9... – gutes Mädchen, bei 0 bist du unten, du kleine Countdown-Sub.' Pflege {n}/{CARES_PER_DAY}. ⏰",
        "{owner} hält Haar und zwingt Knie: 'Runter, du kleine Haar-Sub – und bleib, bis dein Kopf leer ist.' Pflege {n}/{CARES_PER_DAY}. 💇‍♀️",
        "{owner} verbietet Aufstehen: 'Gutes Mädchen, knie ewig – oder bis ich's sage, du kleine Ewig-Sub.' Pflege {n}/{CARES_PER_DAY}. ⏳",
        "{owner} gibt Klapse auf Knien: 'Gutes Mädchen, rot und unten – perfekt, du kleine Rot-Sub.' Pflege {n}/{CARES_PER_DAY}. 🤚",
        "{owner} edge und befiehlt Knie: 'Knie und halt durch – gutes Mädchen, dein Edge ist mein Vergnügen.' Pflege {n}/{CARES_PER_DAY}. 🔥",
        "{owner} flüstert Befehle auf Knien: 'Bleib, warte, zitter – gutes Mädchen, dein Knie ist mein Thron.' Pflege {n}/{CARES_PER_DAY}. 👑",
        "{owner} lässt warten auf Knien: 'Gutes Mädchen, dein Warten macht mich hart – und dich nass, du kleine Warte-Sub.' Pflege {n}/{CARES_PER_DAY}. ⏱️"
    ]
    await do_care(update, context, "knien", tame)

async def cmd_kriechen(update, context):
    tame = [
        "{pet} kriecht auf allen Vieren, Arsch hoch, Gesicht rot vor Geilheit – jeder Zentimeter eine Erinnerung: Laufen ist overrated, Baby. 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam über den Boden, während {owner} die imaginäre Leine straff hält: 'Schneller, du kleine Crawler-Queen, oder ich scroll dich persönlich vorwärts.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht bis zu {owner}s Füßen, guckt hoch und grinst: 'Angekommen, Daddy. Jetzt darfst du mich kraulen – oder auch nicht.' 👅 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht extra langsam, nur um {owner} ungeduldig zu machen: 'Vorwärts, du faule Schnecke, oder ich mach aus dir 'ne TikTok-Challenge.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} sieht zu, wie {pet} kriecht: 'Mein Pony heute ohne Sattel – aber mit extra viel Attitude.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht mit wedelndem Arsch: 'Zeig mir dein bestes Low-Budget-Worming, Babygirl.' Pflege {n}/{CARES_PER_DAY}.",
        "Kriechen wie ein Profi-Gamer auf Low-HP: 'Noch ein Meter, Pet, oder ich respawn dich auf Start.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht und macht extra Drama: 'Arsch zuerst? Klar, weil der Blick von hinten am geilsten ist.' 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Kriech weiter, du kleines Floor-Level-Meme – du machst das so cute, ich könnte platzen.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht bis zur Erschöpfung – aber nur fake: 'Weiter, du Dramaqueen, die Show muss laufen.' Pflege {n}/{CARES_PER_DAY}.",
        # 10 neue – Jugendslang heavy, so witzig dass du vom Stuhl fällst und direkt mitkriechst vor Lachen:
        "{pet} kriecht und macht den Worm: '{owner} droppt nur 'Crawl, bestie' – und {pet} schon am Boden: 'No cap, das ist mein neuer Signature-Move.' 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} sagt 'Kriech, du lowkey Crawler' – {pet} kriecht und flüstert 'Bet, ich bin schon down bad am Boden.' 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht wie in 'nem sus Among-Us-Game: '{owner}: 'Du bist der Impostor – auf dem Boden.' LMAO.' 👀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} commandet 'Kriech, slay auf Knien' – {pet} kriecht und poset: 'Serving looks from below, Queen-Energy.' 💅😂 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht und macht extra Cringe-Faces: '{owner}: 'Big yikes, aber mein yikes. Kriech weiter, du Icon.' 😬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} droppt 'Kriech, du GOAT am Boden' – {pet}: 'Literally the greatest of all crawlers, fr fr.' 🐐🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht und flüstert 'Ohio-Crawl only' – {owner}: 'What the sigma? Du bist zu chaotic für den Boden.' 🫦😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} sagt 'Kriech, oder ich ratio dich' – {pet} sofort am Boden: 'Bro, ich bin schon 0:100 down.' 📉😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriecht wie 'ne TikTok-Transition: '{owner}: 'Smooth AF, aber bleib unten, du main character vom Floor.' 📱🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Kriech, du walking L – warte, nein, crawling L. Perfekt.' {pet} kriecht weiter und vibet total. 💀😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kriechen", tame)

async def cmd_klaps(update, context):
    tame = [
        "{owner}s Hand landet auf {pet}s Arsch – nicht zu fest, gerade so, dass sie quietscht und rot wird: 'Das war fürs Zu-süß-Sein, du kleines Biest.' 🩷 Pflege {n}/{CARES_PER_DAY}.",
        "Jeder Klaps eine Lektion: 'Das fürs Frechsein. Das fürs Grinsen. Das, weil dein Arsch einfach danach schreit.' {pet} zählt mit kichernder Stimme. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "Der letzte Klaps lässt {pet} zappeln – {owner} grinst: 'Nochmal? Klar, ich hab ja den ganzen Tag Zeit, dich zu verwöhnen.' 💥 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt ein paar leichte Klapse mit der flachen Hand: 'Zähl mit, Baby, oder ich hör auf – und das willst du ja nicht.' Pflege {n}/{CARES_PER_DAY}.",
        "Klapse auf den Arsch, bis er glüht – {owner} flüstert: 'Das ist die einzige Massage, die du wirklich brauchst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schlägt abwechselnd links und rechts: 'Damit beide Seiten gleich rot werden – Fairness first, Schatz.' Pflege {n}/{CARES_PER_DAY}.",
        "Nach ein paar Klapsen muss {pet} artig 'Danke' sagen – {owner}: 'Und wehe, du meinst es nicht ernst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt sanfte, aber fiese Klapse: 'Peeling für faule Mädchen – kostenlos und mit Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Klapse mit Pausen dazwischen: 'Damit du schön spürst, wie sehr ich dich mag.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zählt laut mit: 'Eins für dich, zwei für mich – weil ich’s einfach geil finde.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt einen Klaps und sagt trocken: 'Das war für deine letzte gute Entscheidung – oh warte, die gab’s ja nie.' {pet} prustet los. 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} klatscht leicht: 'Das für dein Gym-Skipping. Nächstes Mal mach ich dich fit – auf meine Art.' Pflege {n}/{CARES_PER_DAY}. 💪🤣",
        "{pet} kriegt einen Klaps: '{owner}: 'Das war dein Daily Reminder: Du gehörst mir. Süß, oder?' Toxisch süß AF.' Pflege {n}/{CARES_PER_DAY}. 😘",
        "{owner} schlägt zu und zitiert sich selbst: 'Das fürs Atmen ohne Erlaubnis – aber ich bin gnädig, nur einer.' {pet} lacht sich kaputt. Pflege {n}/{CARES_PER_DAY}. 😭",
        "{owner} gibt serienmäßig Klapse: 'Eins, zwei, drei – wie im Kindergarten, nur dass hier ich der Boss bin und du die Bank.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} quietscht nach jedem Klaps – {owner}: 'Musik in meinen Ohren. Mach weiter so, du kleine Dramaqueen.' Pflege {n}/{CARES_PER_DAY}. 🎶🤭",
        "{owner} klatscht und sagt: 'Das war dein Applaus fürs Existieren. Stehender Ovation gibt’s nächstes Mal.' {pet} dead. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt einen extra fiesen (aber sanften) Klaps: 'Das für deine Selbstständigkeit – die darfst du nämlich nicht haben.' Toxisch deluxe. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zählt mit: 'Danke für Nummer sieben!' – {owner}: 'Falsch, das war erst drei. Mathe war nie deine Stärke, hm?' Lachflash garantiert. 🧮😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beendet mit einem letzten Klaps: 'Und der hier ist, weil du’s liebst, es abzustreiten. Lügnerin.' {pet} heult vor Lachen. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "klaps", tame)

async def cmd_knabbern(update, context):
    tame = [
        "{owner} beißt zart in {pet}s Schulter – gerade fest genug, dass sie quietscht: 'Der Geschmack von Angst? Süß, aber deiner ist eher wie Zuckerwatte.' 👅 Pflege {n}/{CARES_PER_DAY}.",
        "Zähne an der Brustwarze, leicht ziehen, drehen – {pet} wimmert vor Kribbeln: 'Bewegung? Würde nur zeigen, wie sehr du’s magst.' 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Ein kleiner Biss in die Innenschenkel, nah genug zum Drohen – {owner} grinst: 'Beim nächsten Mal tiefer... oder auch nicht, mal sehen, wie artig du bist.' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knabbert an {pet}s Arschbacke, spuckt nichts aus – 'Frühstück à la carte, direkt von der geilsten Quelle.' Pflege {n}/{CARES_PER_DAY}.",
        "Zähne leicht in die Kehle, nur Andeutung – {owner} flüstert: 'Dein Puls schmeckt nach Panik... und nach Mehr.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} kaut spielerisch an {pet}s Lippe: 'Küss mich mit deinem Stöhnen, das reicht völlig.' Pflege {n}/{CARES_PER_DAY}.",
        "Leichtes Knabbern da unten, bis {pet} zappelt – {owner}: 'Die kleine Perle wird heute nur gekitzelt, keine Sorge.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt sanft in den Bauch: 'Ich wollte schon immer wissen, wie du von innen kicherst.' Pflege {n}/{CARES_PER_DAY}.",
        "Zähne am Ohrläppchen: '{owner} raunt: 'Van Gogh war Amateur – ich mach’s mit Stil und ohne Drama.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knabbert am Hals: 'Nur ein kleiner Liebesbiss – damit du morgen weißt, wem du gehörst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt leicht in {pet}s Finger: 'Das fürs Tippen ohne Erlaubnis – nächstes Mal beiß ich den ganzen Chat weg.' {pet} prustet. 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knabbert an der Nase: 'Süß, wie du guckst. Das war fürs Zu-niedlich-Sein – Strafe muss sein.' Toxisch cute. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} kriegt einen Biss ans Kinn: '{owner}: 'Das für deine Selbstständigkeit – die darfst du nämlich vergessen.' Lachtot. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} kaut spielerisch am Ohr: 'Flüstergeheimnis: Du stehst drauf, es abzustreiten. Lügnerin.' {pet} heult vor Lachen. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt in die Schulter: 'Das war dein Daily Reminder: Mein Revier. Markiert und bezahlt.' Ironisch besitzergreifend AF. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} quietscht bei jedem Knabber: '{owner}: 'Musik in meinen Ohren. Mach ein Album draus, du Star.' Lachkrampf garantiert. 🎶 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knabbert am Hals: 'Das fürs Atmen ohne mich – aber ich verzeih dir, weil du so lecker bist.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} beißt leicht in die Lippe: 'Das war Applaus für deine Frechheit. Standing Ovation gibt’s später.' {pet} dead vor Lachen. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zappelt: '{owner}: 'Das fürs Weglaufen wollen – als ob du könntest. Bleib schön hier, Snack.' Sarkasmus pur. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} knabbert am Arm: 'Und der hier ist, weil du’s liebst, wenn ich dich nerve. Auf Knien danken, Baby.' {pet} lacht sich kaputt. 🙏😂 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knabbern", tame)

async def cmd_leine(update, context):
    tame = [
        "Die Leine klickt ein, straff um {pet}s Hals – ein kleiner Ruck, und die Welt wird klein auf {owner}s Schritte: 'Brav folgen, Baby, oder ich lass dich ziellos rumirren.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht leicht, {pet} stolpert hinterher mit rotem Gesicht – 'Du gehst nur, wenn ich es will... und wir wissen beide, dass du genau das willst.' 😏 Pflege {n}/{CARES_PER_DAY}.",
        "Die Leine liegt locker in {owner}s Hand – aber {pet} weiß: Ein Wort, und sie erinnert dich daran, wer hier wirklich führt. 'Freiheit? Süßes Märchen.' 🌑 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} wickelt die Leine spielerisch um die Hand: 'Atme ruhig weiter – solange ich es erlaube. Oder auch länger, je nach Laune.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein sanfter Ruck, {pet} auf den Zehenspitzen: 'Tanz für mich, Baby – aber nur, weil du’s so süß machst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet die Leine locker: 'Jetzt steuerst du dich selbst... naja, fast. Ich hab immer den Daumen drauf.' Pflege {n}/{CARES_PER_DAY}.",
        "Leine straff, aber mit Liebe: 'Jeder Ruck eine Erinnerung: Du bist mein Lieblingsaccessoire.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht {pet} nah ran: 'Herzstillstand-Training? Nee, heute nur Herzrasen-Training.' Pflege {n}/{CARES_PER_DAY}.",
        "Die Leine wird mit einem Grinsen gespannt: 'Dekoration für deinen Hals – passt perfekt zu deinem Dackelblick.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt locker und zieht wieder: 'Mal Freiheit, mal nicht – ich bin halt unberechenbar. Du stehst drauf.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} klickt die Leine ein: 'Freedom was yesterday, Baby. Heute gibt’s nur mich als Navi – und ich nehm immer den Umweg.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht leicht: 'Das war für deine Selbstständigkeit – die darfst du nämlich zu Hause lassen, wie deine Würde.' Toxisch grin. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} folgt artig, {owner}: 'Brav an der Leine – du siehst aus wie mein Lieblingshandtaschen-Hund. Nur geiler.' {pet} dead vor Lachen. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} spannt die Leine: 'Ein Ruck und du bist bei mir. Romantisch, oder? Besser als jede Dating-App.' Ironie pur. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert beim Ziehen: 'Du denkst, du hast Kontrolle? Süß. Die Leine lügt nie.' Sarkasmus level 100. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} stolpert leicht, {owner}: 'Ops, war das zu fest? Nee, war genau richtig – du brauchst ja Führung.' Lachflash garantiert. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Leine locker: 'Freiheit light – du darfst atmen, laufen darfst du nur mit mir. Deal des Jahrhunderts.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht {pet} ran: 'Komm her, du kleine Ausreißerin – als ob du je weit kommen würdest.' {pet} prustet los. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} grinst: 'Leine an = Drama off. Du spielst die Brave so gut, Oscar-reif.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt die Leine schnappen: 'Und das war dein Daily Reminder: Ohne mich läufst du im Kreis. Buchstäblich.' {pet} heult vor Lachen. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "leine", tame)

async def cmd_halsband(update, context):
    tame = [
        "Das Halsband schnappt zu, Metall kalt auf Haut – graviert mit {owner}s Namen: 'Für immer? Klar, bis du mich langweilst und ich dich gegen ein neues Modell eintausche.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht es enger, {pet} keucht gespielt: 'Dein neuer Schmuck, Baby. Trägt sich leichter als deine Selbstständigkeit – die hast du ja eh abgelegt.' 😏 Pflege {n}/{CARES_PER_DAY}.",
        "Ringe klirren bei jeder Bewegung – 'Freiheit war eh nur ein Gerücht. Jetzt hast du wenigstens was, das zu deinem Dackelblick passt.' ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schließt ab und steckt den Schlüssel ein: 'Für immer bedeutet für immer... oder bis ich den Schlüssel verliere. Pech für dich, ich bin vergesslich.' Pflege {n}/{CARES_PER_DAY}.",
        "Leicht eng, aber trendy: '{owner}: 'Blutperlen? Nee, heute nur Schweißperlen, wenn du merkst, wie sehr du drauf stehst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht gerade so: 'Deine Stimme gehört mir – und ich lass sie nur raus, wenn sie 'Bitte, Daddy' sagt.' Pflege {n}/{CARES_PER_DAY}.",
        "Halsband mit Glöckchen: '{owner}: 'Guten Morgen, Liebling. Jetzt weiß ich immer, wo mein Lieblingsspielzeug rumläuft.' Pflege {n}/{CARES_PER_DAY}.",
        "Graviert: 'Eigentum von {owner}' – 'Bei Verlust? Ich hol dich zurück. Und du zahlst die Porto.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hängt ein Herzchen dran: 'Mach dich hässlich, und ich hör dich nicht mal kommen.' Pflege {n}/{CARES_PER_DAY}.",
        "Das Halsband sitzt wie angegossen: '{owner}: 'Abnehmen? Klar, wenn du mir erst beweist, dass du ohne mich überleben kannst. Spoiler: Kannst du nicht.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} legt an: 'Freedom? Das war dein Ex. Ich bin der Upgrade – mit Schloss und ohne Rückgaberecht.' {pet} tot vor Lachen. 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht zu: 'Das war für deine Emanzipation – die darfst du nämlich abgeben, wie deinen Verstand bei mir.' Toxisch grin. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} trägt es, {owner}: 'Sieht aus wie mein Lieblingshalsband. Nur dass normale Halsbänder nicht so süß betteln.' {pet} prustet los. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} befestigt es: 'Romantischer als jeder Verlobungsring – der hier sagt wenigstens ehrlich: Du bist gefangen.' Ironie max. 💍 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Du denkst, du kannst abhauen? Süß. Das Halsband ist loyaler als du.' Sarkasmus brutal. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "Glöckchen klingelt, {owner}: 'Hörst du das? Das ist dein Freiheitsalarm – der nie losgeht.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält den Schlüssel: 'Freiheit light – du darfst atmen, aber nur mit meinem Namen am Hals. Besser als Therapie.' Toxisch deluxe. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zieht ran: 'Komm her, du kleine Fluchtartistin – als ob du ohne mich überhaupt laufen könntest.' {pet} heult vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} grinst: 'Halsband an = Eigenständigkeit aus. Du spielst die Brave so gut, ich sollte dich vermieten.' Sarkastischer Burn. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verschließt: 'Daily Reminder: Ohne mich bist du nur halb angezogen. Und halb so geil.' {pet} lachend am Boden. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "halsband", tame)

async def cmd_lecken(update, context):
    tame = [
        "{pet} leckt {owner}s Stiefel sauber – Zunge fleißig, weil Demütigung offenbar besser schmeckt als dein letztes Date. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam über die Finger, dann höher – {owner} drückt den Kopf runter: 'Tiefer, Baby, oder ich helf nach – und wir wissen beide, dass du’s kaum erwarten kannst.' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die Tränen vom eigenen Gesicht, weil {owner} befiehlt: 'Schmeck deine Niederlage – salzig, aber kalorienarm.' 🥀 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt den Boden sauber, wo {owner} gerade seinen Kaffee verschüttet hat – 'Mein Latte ist dein Heilwasser, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält den Stiefel hin: '{pet} leckt fleißig – 'Proteinreich heute? Nee, nur Staub und dein Ego.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt {owner}s Hand sauber, nachdem er sie durch deine Haare gezogen hat – 'Schmeck dich selbst, das ist Recycling de luxe.' Pflege {n}/{CARES_PER_DAY}.",
        "Zunge tief an {owner}s Hals, während er lacht – 'Atme ein, das ist dein neuer Lieblingsduft: Meine Überlegenheit.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die eigene Hand sauber, nachdem sie gezittert hat – 'Selbstbedienung, du faule Prinzessin.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} spuckt in {pet}s offenen Mund und befiehlt: 'Schluck und leck dann meine Hand – doppelter Geschmack, null Kalorien.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt den Tisch sauber, wo {owner} gerade gegessen hat – 'Dein eigener Hunger ist der beste Durstlöscher.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt {owner}s Daumen sauber: 'Das war fürs Daumenlutschen in der Öffentlichkeit – oh warte, das machst du nur bei mir.' {pet} tot. 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält den Finger hin: 'Leck, als wäre es dein letzter Eis am Stiel – Spoiler: Bei mir gibt’s immer Nachschub.' Toxisch süß. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die Handfläche: '{owner} trocken: 'Das für deine Selbstständigkeit – die schmeckt eh nach nichts.' Lachkrampf. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} den Hals lecken: 'Schmeck meinen Puls – der schlägt nur schneller, wenn du so schlecht leckst.' Trockener Burn. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt den Ringfinger: '{owner}: 'Übung für später – falls du je einen Ring verdienst. Spoiler: Eher nicht.' Ironie max. 💍 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält den Stiefel hoch: 'Leck den Staub weg – dein Putzjob, weil Staubsauger zu selbstständig für dich sind.' {pet} prustet. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt die Tränen weg: '{owner}: 'Salzig und dramatisch – genau wie dein Leben ohne mich.' Toxisch deluxe. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} spuckt auf die Hand: 'Leck sauber, du kleine Müllabfuhr – Recycling ist hip, oder?' {pet} heult vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} leckt den Unterarm: '{owner}: 'Das fürs Armdrücken – das du immer verlierst. Gegen mich und gegen die Realität.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} die Fingerspitzen lecken: 'Daily Reminder: Ohne mich schmeckt alles fade. Selbst deine eigene Zunge.' {pet} lachend am Boden. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lecken", tame)

async def cmd_verweigern(update, context):
    tame = [
        "{owner} verweigert Berührung, Wasser, Worte – {pet} windet sich stundenlang, bettelt stumm: 'Ach, du armes Ding, ohne mich bist du ja komplett verloren.' 😭 Pflege {n}/{CARES_PER_DAY}.",
        "Essen vor {pet}s Nase, aber der Mund bleibt leer – 'Hunger ist die beste Dressur. Bei dir reicht schon der Duft, um dich gefügig zu machen.' 🩷 Pflege {n}/{CARES_PER_DAY}.",
        "Orgasmus verweigert, wieder und wieder – bis {pet} vor Verzweiflung heult: 'Alles versprechen? Süß, als ob ich deine Versprechen bräuchte.' 💔 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} zuschauen, wie er sein Handy streichelt – Berührung nur fürs Display, {pet} bleibt leer und frustriert. Pflege {n}/{CARES_PER_DAY}.",
        "Wasserflasche vor der Nase, aber zugeschraubt – {owner} trinkt daraus und gießt den Rest in eine Pflanze: 'Die braucht’s dringender als du.' Pflege {n}/{CARES_PER_DAY}.",
        "Orgasmus bis an den Rand, dann Stopp – tagelang. {pet} bettelt um Erlösung: 'Erlösung? Die gibt’s bei mir nur auf Rezept.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} redet stundenlang mit {pet}, nur um dann tagelang zu schweigen – 'Deine Existenz ist jetzt optional. Wie dein Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
        "Schlaf verweigert – Serien-Marathon, {pet} muss wach bleiben: 'Träum wach, Liebling, Realität ist eh besser.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zeigt {pet} Fotos von Schokolade, dann isst er sie allein – 'Erinnerungen sind auch nur Folter. Kalorienfreie.' Pflege {n}/{CARES_PER_DAY}.",
        "Küss verweigert – {owner} haucht nur in die Luft: 'Atmen ist ein Privileg. Meine Küsse erst recht.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert den Like auf {pet}s Selfie: 'Sorry, Baby, heute spar ich mir die Dopamin-Auszahlung. Du kommst auch ohne klar.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert die Antwort auf deine letzte Nachricht: 'Gelesen um 23:47. Reicht doch als Aufmerksamkeit, oder?' Toxisch deluxe. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt um ein 'Gutes Mädchen' – {owner}: 'Heute nicht. Du bist ja eh schon süchtig nach meinem Lob.' {pet} dead. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert den zweiten Kaffee: 'Einer reicht. Mehr und du wirst noch anhänglicher – als ob das ginge.' Trockener Burn. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert das Kopfkraulen: 'Selbstständigkeit üben, Schatz. Oder warte… das war Ironie.' Ironie max. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} will Kuscheln, {owner} scrollt weiter: 'Kuscheln? Hab schon ’ne Decke. Die bettelt wenigstens nicht.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert das 'Ich hab dich lieb': 'Zu viel Kalorien. Du weißt es ja eh – und leidest schön daran.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert den Gute-Nacht-Kuss: 'Träum von mir. Das ist intensiver als jeder Kuss.' {pet} prustet los. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} will Aufmerksamkeit, {owner} guckt aus dem Fenster: 'Die Wolken haben heute Vorrang. Die verschwinden wenigstens nicht.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} verweigert das Happy End: 'Heute nur Cliffhanger, Baby. Du kommst morgen bettelnd wieder – wie immer.' {pet} lachend verzweifelt. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "verweigern", tame)

async def cmd_kaefig(update, context):
    tame = [
        "{owner} schließt die Tür ab und grinst durchs Gitter: 'Willkommen zu Hause, Baby – Dunkelheit und Stille, nur dein Herz schlägt laut... für mich.' 🌑 Pflege {n}/{CARES_PER_DAY}.",
        "Stunden im Käfig, nackt, zitternd – {owner} schaut nur zu: 'Gute Tiere lernen schnell. Schlechte betteln süß – und du bist ja so schlecht.' 🐕 Pflege {n}/{CARES_PER_DAY}.",
        "Die Gitter werfen Schatten auf {pet}s Haut – ein Muster aus Gefangenschaft: 'Sieht aus wie Tattoos, nur billiger und mit mehr Drama – dein Lieblingslook.' ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        "Käfig schön geräumig, {pet} kann sich drehen – {owner}: 'Gemütlich, oder? Fast wie ein Wellness-Retreat – nur ohne Ausgang, du kleine Dauergast.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} stellt den Käfig ins Wohnzimmer – {pet} hat beste Sicht auf mich: 'Bräunung durch Fernseherlicht inklusive – und mein Grinsen gratis.' Pflege {n}/{CARES_PER_DAY}.",
        "Nachts leises Musikchen im Käfig – {pet} darf mitsingen: 'Neue Spielkameraden? Nee, nur meine Playlist – und du bist der Refrain.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig mit weicher Decke – {pet} wird wahnsinnig vor Bequemlichkeit: 'Wassertortur light? Heute nur Kuschelfolter – weil du's eh nicht verdienst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} 'vergisst' {pet} für fünf Minuten – kommt zurück und lacht: 'Zeitreise erfolgreich. Du siehst aus, als wär’s ’ne Woche – süß, wie du leidest.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig mit Kissen drin – jede Bewegung bequem: 'Umarmung rundum? Ja, von meiner Aufmerksamkeit – die dich langsam erstickt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt {pet} im Käfig und zeigt es nur sich selbst: 'Dein neues Zuhause geht viral – in meinem Kopf, 24/7, du kleine Star-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schließt ab und edge {pet} durchs Gitter: 'Gutes Mädchen, eingesperrt und nass – dein Käfig ist edging deluxe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} warten mit verbundenen Augen: 'Gutes Mädchen, blind im Käfig – du spürst nur die Gitter und meine Stimme.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} durchs Gitter: 'Gutes Mädchen, tropf im Käfig – du quillst nur für mich, du kleine Tropf-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse durchs Gitter: 'Gutes Mädchen, rot glühen im Käfig – perfekt für meine kleine Klaps-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Leine durchs Gitter: 'Gutes Mädchen, gezogen im Käfig – du kleine Leinen-Sub, die nie entkommt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert Befehle durchs Gitter: 'Bleib, warte, zitter – gutes Mädchen, dein Käfig ist mein Echo.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} stundenlang warten: 'Gutes Mädchen, dein Käfig ist Zeitfolter – und du wartest so schön.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge {pet} im Käfig: 'Gutes Mädchen, nah dran und Stopp – dein Käfig ist edging-Hölle.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet {pet} im Käfig fest: 'Gutes Mädchen, gefesselt im Käfig – du kleine Fessel-Sub, die sich nicht bewegt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und stoppt: 'Gutes Mädchen, leer machen im Käfig – und du bettelst um mehr, du kleine Leere.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} stumm im Käfig: 'Gutes Mädchen, kein Wort – dein Käfig ist Stille-Folter.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt imaginäre Klapse durchs Gitter: 'Gutes Mädchen, rot glühen im Käfig – du kleine Rot-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert 'Bleib' und geht weg: 'Gutes Mädchen, allein im Käfig – dein Warten ist mein Lieblingsspiel.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge mit Worten durchs Gitter: 'Gutes Mädchen, dein Käfig ist Vorfreude – und Vorfreude ist alles, was du kriegst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} zittern im Käfig: 'Gutes Mädchen, dein Zittern ist mein Lieblingsgeräusch – lautlos und geil.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kaefig", tame)

async def cmd_schande(update, context):
    tame = [
        "{pet} steht nackt in der Ecke, Schande brennt heißer als jeder Schlag – alle dürfen zusehen: 'Und du genießt die Show insgeheim, du kleine Exhibitionistin.' 👁️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzählt laut {pet}s Geheimnisse, lacht dabei – bis die Scham in den Knochen sitzt: 'Aber ehrlich, Süße, die waren eh nicht so geheim.' 💀 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Schild um den Hals: 'Gebrauchtes Eigentum' – {pet} trägt es stolz: 'Stolz tot? Nee, der hat nur Urlaub bei mir gemacht.' 🪦 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt {pet} nackt mit dem Schild 'Billige Hure – aber nur für mich' und zeigt es nur sich selbst: 'Dein Ruhm ist jetzt ewig – in meinem Privatordner.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss vor dem Spiegel masturbieren und dabei laut ihre perversesten Geheimnisse gestehen – 'Applaus gibt's von mir, wenn du schön rot wirst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest alte Chatverläufe vor, lacht über jede peinliche Nachricht – {pet} wird rot bis in die Zehen: 'Für immer? Nee, bis morgen, wenn du wieder bettelst.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein temporäres Tattoo 'Nutzlose Fotze – aber meine' – {pet} muss es mir zeigen: 'Deine neue Visitenkarte – exklusiv für mich.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zwingt {pet} Fotos von früher anzugucken – 'Dein altes Ich stirbt heute vor Lachen.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} steht stundenlang nackt vor dem Spiegel, ich darf Fotos machen – 'Dein Viertel kennt dich nicht, aber ich umso besser.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzählt mir {pet}s dreckigste Details per Flüstern – 'Frohe Weihnachten von deiner kleinen Schlampe – nur für meine Ohren.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hängt ein Schild um: 'Vorsicht, beißt nur mich' – {pet} trägt es: 'Deine Schande? Süß, als ob dich jemand anderes wollen würde.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzählt deine peinlichsten Stories – aber nur mir: 'Geheimnisse? Die waren eh nur peinlich für dich, für mich Gold.' Toxisch grin. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} steht in der Ecke: '{owner}: 'Schäm dich mal richtig – oh warte, das machst du ja schon, wenn ich nur gucke.' {pet} dead. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert deine Schwächen: 'Alle hören mit? Nee, nur ich. Die anderen sind eh neidisch.' Ironie max. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss ihr eigenes Spiegelbild anstarren: '{owner}: 'Schande-Level: Du siehst aus, als wärst du ertappt worden. Warst du ja auch.' Sarkasmus brutal. 💀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} postet gar nichts: 'Dein Ruhm? Bleibt bei mir. Öffentlich schämen ist was für Amateure.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} trägt ein Schild 'Mein Eigentum – Hände weg': '{owner}: 'Schäm dich, dass du’s liebst, markiert zu sein.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht über deine Vergangenheit: 'Dein altes Ich? Das war eh overrated. Das neue kniet besser.' {pet} prustet los. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} in der Ecke: '{owner}: 'Alle sehen zu? Nee, nur ich. Die anderen hätten eh keine Chance gegen deine Scham-Performance.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Daily Reminder: Deine Schande ist mein Lieblingshobby. Und du machst mit, weil du’s brauchst.' {pet} lachend rot. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "schande", tame)

async def cmd_erregen(update, context):
    tame = [
        "{owner} berührt genau da, wo die Schmetterlinge einen Tanzmarathon veranstalten – bis {pet} hasst, wie sehr sie in meiner ewigen, rosaroten Liebe versinkt: 'Du armes, verkitztes Püppchen.' 🩷 Pflege {n}/{CARES_PER_DAY}.",
        "Langsam, quälend, ohne Erlösung – {pet} bettelt um mehr: 'Und hasst sich dafür? Ach, wie tragisch-romantisch, als ob unsere Hollywood-Liebe je ein Ende nähme.' 😭 Pflege {n}/{CARES_PER_DAY}.",
        "Finger tief, Worte aus einem Rosamunde-Pilcher-Roman – {owner} flüstert: 'Du kommst erst, wenn die Geigen heulen und die Tauben kotzen. Oder wenn ich Mitleid krieg.' ⏳ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reibt die Klitoris wie ein Liebesbrief mit Duft – bis {pet} trotzdem bettelt: 'Schmerz? Nee, heute nur Herzchen-Konfetti und Regenbogen-Einhörner im Bauch.' Pflege {n}/{CARES_PER_DAY}.",
        "Finger mit purem Zuckerwatte-Kitsch drin, tief in die sehnsüchtige Disney-Prinzessinnen-Fotze – {pet} quietscht: 'Desinfektion? Eher ein Parfum aus 1001 Rosen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt {pet} mit der ganzen Hand, flüstert 'Du bist das Loch in meinem Herzen – gefüllt mit ewiger Marshmallow-Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Nippel mit Schoko-Küssen, Gewichte aus Wattewolken dran – 'Jede Bewegung macht dich nasser, du perverse Aschenputtel auf Wolke sieben.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} benutzt eine Feder aus dem Flügel eines Liebesengels – kitzelt innen, {pet} explodiert vor Herzchen-Explosionen: 'Putzen von innen? Eher Beauty-Treatment für die Seele.' Pflege {n}/{CARES_PER_DAY}.",
        "Virtuelle Elektroden aus puren Liebesfunken und Glitzer – {pet} zuckt vor Kitsch-Overload: 'Du hasst deinen Körper? Der tanzt doch nur den Hochzeitstanz mit mir.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht auf die Fotze wie ein Liebesgedicht auf Seide: 'Mein Atem macht dich glitschiger, Liebling. Wie Champagner auf unserer ewigen Hochzeitstorte.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fingert dich wie ein kitschiges 80er-Liebeslied: 'Every breath you take, every move you make – I'll be edging you.' {pet} kollabiert vor Lachen. 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert 'Du bist der Regenbogen nach meinem Sturm' – während er dich quälend langsam berührt: 'Und Regenbögen kommen nie, bevor der Sturm aufhört zu toben.' Toxisch-kitschig deluxe. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} windet sich wie in 'nem Bollywood-Film mit 100 Tänzern: '{owner}: 'Schau dich an, wie du für mich erblühst. Wie eine Plastikblume im Supermarkt-Special.' {pet} erstickt vor Lachen. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} küsst jede Stelle: 'Romantik-Level: Dirty Dancing. Nobody puts Baby in the corner – aber ans Edging schon.' Ironie überladen. 💃 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt um Orgasmus: '{owner}: 'Erst wenn die Schwanensee-Geigen spielen und die Einhörner weinen. Oder wenn ich keine Lust mehr auf Kitsch hab.' Sarkasmus pur. 🦢 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt endlos: 'Das ist mein ewiger Schwur – in 1000 Herzchen-Raten. Jede Berührung eine Blüte, die nie, nie aufgeht.' Lachkrampf garantiert. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht 'Du bist meine Seelenverwandte aus 1001 Nacht': 'Seelenverwandte edging bis zum Morgengrauen. Weil wahre Liebe ewig wartet.' Toxisch süß überdosis. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zittert vor Geilheit: '{owner}: 'Du bist mein Schicksal. Mein schicksalhaftes, ewig geiles Märchenprinzesschen.' {pet} heult vor Lachen und Herzchen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fingert zart wie ein Liebesbrief: 'Jede Bewegung ein Versprechen – dass ich dich nie kommen lasse, solange die Rosen blühen und die Tauben kacken.' Sarkastischer Applaus. 🌹😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Du bist die Liebe meines Lebens. Die Liebe, die immer kurz vor dem Happy End eine Werbepause macht.' {pet} lachend nass und total erledigt. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "erregen", tame)

async def cmd_betteln(update, context):
    tame = [
        "{pet} bettelt auf Knien, Stimme bricht vor Sehnsucht – {owner} hört nur zu und lächelt kalt: 'Ach, du armes, verkitztes Ding, bettelst um meine unsterbliche Liebe?' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "'Bitte, bitte, bitte' – wieder und wieder, bis die Worte nichts mehr bedeuten und nur noch rosarote Scham übrig ist: 'Wie romantisch, dein Gewinsel klingt wie ein Liebeslied.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Belohnung hoch, lässt {pet} darum winseln wie ein verliebtes Kätzchen – und nimmt sie dann weg: 'Sorry, Baby, wahre Liebe wartet immer ein bisschen länger.' 🚫 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt stundenlang um einen Orgasmus, {owner} filmt es mit Herzchen-Filter – 'Dein neues Romantikvideo, geht direkt viral in meinem Herzen.' Pflege {n}/{CARES_PER_DAY}.",
        "Muss 'Ich bin deine ewige Prinzessin' 1000 Mal sagen, bevor vielleicht ein Kuss kommt – Stimme weg, aber das Herz voll Kitsch. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält ein Glas Wasser hoch, {pet} winselt durstig – dann gießt er es in eine Vase: 'Die Rosen brauchen’s dringender als du, meine Blüte.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt um einen Kuss statt Schmerz – weil Schmerz zu langweilig wäre: 'Küss mich, bitte, ich halt die Romantik nicht aus.' Pflege {n}/{CARES_PER_DAY}.",
        "Betteln mit der Leine im Mund, sabbernd vor Sehnsucht – {owner} lacht nur: 'Noch lauter, mein kleiner Liebesvogel.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss um die Erlaubnis betteln, atmen zu dürfen – hält es stundenlang: 'Gute Lungen, schlechte Romantikerin.' Pflege {n}/{CARES_PER_DAY}.",
        "Letztes Betteln: um ein 'Ich liebe dich' – {owner} verweigert sogar das: 'Du fühlst es doch eh schon, meine kleine Dramaqueen.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt auf Knien: 'Bitte, mein Ritter in glänzender Rüstung, schenk mir einen Blick!' – {owner}: 'Sorry, mein Pferd braucht erst Hufeisen.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält einen Schokoladenherz hoch: '{pet} winselt: 'Bitte, meine ewige Flamme!' – {owner}: 'Erst wenn du mir ein Gedicht schreibst. In Reimform.' Toxisch süß. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} fleht um einen Kuss: '{owner}: 'Nur wenn du mir schwörst, dass unsere Liebe stärker ist als Romeo und Julia. Spoiler: Die sind tot.' {pet} prustet los. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Bettel um meine Hand – für immer.' – {pet} bettelt: '{owner}: 'Heiratsantrag? Klar, aber erst nach 1000 Rosen.' Ironie overkill. 🌹 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} winselt um Aufmerksamkeit: '{owner}: 'Du bist der Stern an meinem Himmel – aber Sterne dürfen nicht explodieren, bevor ich es sage.' Sarkasmus deluxe. ⭐ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält die Belohnung weg: 'Bettel wie in 'nem Kitschroman – mit Tränen und Geigen im Hintergrund.' {pet} lacht sich kaputt. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bettelt um 'Ich vermisse dich': '{owner}: 'Ich vermisse dich auch – deine Würde, wenn du so bettelst.' Toxisch-kitschig. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} um ein Lächeln betteln: 'Lächeln? Das kostet extra. In Herzchen-Währung.' {pet} heult vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} fleht um eine Umarmung: '{owner}: 'Umarmung? Klar, aber nur virtuell – echte sind für Paare, die nicht edging spielen.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Bettel um unsere ewige Liebe – die Liebe, die dich ewig warten lässt.' {pet} lachend verzweifelt in Rosen. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "betteln", tame)

async def cmd_stumm(update, context):
    tame = [
        "{owner} befiehlt Schweigen – {pet} beißt sich auf die Lippe, aber nur vor lauter Kitsch-Überdosis: 'Pssst, mein Herz, unsere Liebe spricht ja eh lauter als Worte.' 🩷 Pflege {n}/{CARES_PER_DAY}.",
        "Kein Wort, kein Stöhnen – nur der Blick sagt alles: 'Deine Augen flüstern mir Liebesgedichte, Baby, und ich versteh jedes einzelne.' 👁️ Pflege {n}/{CARES_PER_DAY}.",
        "Mund zugeklebt mit einem virtuellen Kuss – Stille ist die süßeste Strafe: 'Jetzt können nur noch meine Lippen dich zum Reden bringen.' 🌑 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} legt den Finger auf {pet}s Lippen: 'Schsch, meine Rose, dein Schweigen ist das schönste Liebeslied, das ich je gehört hab.' Pflege {n}/{CARES_PER_DAY}.",
        "Kein Laut erlaubt – {pet} guckt nur mit Herzchenaugen: '{owner}: 'Dein Blick ist lauter als jede Geige in unserem privaten Liebesorchester.' Pflege {n}/{CARES_PER_DAY}.",
        "Stumm wie ein Mäusschen in Liebe – {owner} flüstert: 'Dein Schweigen macht mich schwach, du kleine, leise Verführerin.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} hält den Mund, weil {owner} es befiehlt – und weil sie eh nur 'Ich liebe dich' sagen würde: 'Süß, wie du versuchst, leise zu sein.' Pflege {n}/{CARES_PER_DAY}.",
        "Schweigen ist Gold, aber dein Schweigen ist Platin mit Herzchen drauf – {owner} grinst: 'Pssst, meine Prinzessin, die Stille zwischen uns ist lauter als jedes Ja-Wort.' Pflege {n}/{CARES_PER_DAY}.",
        "Kein Stöhnen, kein Wimmern – nur pure, stumme Romantik: '{owner}: 'Dein Schweigen sagt mehr als tausend Liebesbriefe, du kleine Poetin.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} darf nicht sprechen, aber ihre Augen schreien 'Für immer dein' – {owner}: 'Ich hör dich laut und klar, meine stumme Taube.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} befiehlt: 'Sei still, mein Herz, dein Schweigen macht mich ganz narrisch – wie in 'nem Liebesfilm, nur ohne den Abspann, du kleine Stummfilm-Sirene.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} schweigt brav, {owner} reimt: 'Dein Mund ist zu, dein Blick ist hell – du bist mein stiller Liebesknall, der ohne Ton die Welt erhellt. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "Kein Wort, kein Pieps – {owner}: 'Schweigen ist Gold, bei dir ist’s Diamant – du bist mein stiller Liebesbrand, der ohne Flammen lodert grand.' {pet} prustet innerlich los. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Pssst, mein Schatz, dein Schweigen klingt wie Geigenklang – romantischer als jeder Gesang, du kleine Stummfilm-Queen so fein und bang.' Ironie-Reim-Overload. 🎻 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} hält den Mund, {owner} reimt trocken: 'Dein Schweigen ist mein Liebesglück – lautlos, kitschig, ohne Rück – du bist mein stilles Herzstück. 💖 Pflege {n}/{CARES_PER_DAY}.",
        "Schweigebefehl deluxe: '{owner}: 'Dein Mund bleibt zu, dein Herz schreit laut – du bist mein stiller Liebesraub, der mich um den Verstand bringt, oh Graus!' Lachkrampf garantiert. 😭 Pflege {n}/{CARES_PERDAY}.",
        "{owner} grinst: 'Schsch, mein Engel, dein Schweigen ist der schönste Klang – wie tausend Tauben auf dem Gang, nur ohne den ganzen Kot-Drang. 🕊️ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} stumm wie ein Fisch in Liebe: '{owner}: 'Dein Schweigen ist mein Liebesmeer – tief, kitschig, ohne Grenze mehr – du kleine Nixe, schwimm bei mir.' {pet} ertrinkt vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "Kein Ton erlaubt: '{owner} reimt: 'Dein Schweigen ist mein Hochzeitslied – leise, kitschig, unendlich sweet – du bist mein stiller Liebesbeat. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Schweige, mein Herz, dein Schweigen ist der größte Liebesbeweis – lauter als jeder Schrei, du kleine, stille Liebesfee.' {pet} lachend verstummt für immer. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "stumm", tame)

async def cmd_bestrafen(update, context):
    tame = [
        "{owner} bindet {pet}s Hände fest auf den Rücken und gibt leichte Klapse – 'Zähl mit, du kleine Gefangene – jeder Treffer für deine Unartigkeit.' 💥 Pflege {n}/{CARES_PER_DAY}.",
        "Strafe ohne Grund, nur weil {owner} Lust auf Kontrolle hat – {pet} nimmt sie hin, weil Widerstand eh zwecklos ist, du kleine Rebellin ohne Chance. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Danach die glühende Haut streicheln – 'Das ist meine Art von Liebe, Liebling – rot, heiß und unvergesslich.' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet {pet} mit Seilen fest – 'Damit du spürst, wem du gehörst, wenn du dich windest, du kleine Fessel-Prinzessin.' Pflege {n}/{CARES_PER_DAY}.",
        "Klapse auf den Arsch, eine nach der anderen – {pet} zählt zitternd: 'Maniküre für unartige Mädchen – rot glühen ist dein neuer Look.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fesselt {pet}s Hände und edge sie endlos – 'Deine neue Landkarte aus Gänsehaut, nur für mich lesbar, du kleine Edge-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "Feste Griffe, die rote Spuren hinterlassen – 'Das knackt so schön in deinem Kopf, findest du nicht, du kleine Kontroll-Verliererin?' Pflege {n}/{CARES_PER_DAY}.",
        "Feste Massage mit Druck, tropfenweise Öl – {pet} riecht nach Lavendel und Verlangen: 'Duftkerze aus purer Unterwerfung.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} allein mit der Leine – 'Heute Solo-Strafe, du glückliches, geiles Stück – warte auf mich.' Pflege {n}/{CARES_PER_DAY}.",
        "Danach die Seile küssen lassen – 'Kuss ist der beste Dank für meine Strafe, du kleine Seil-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse und hält die Leine straff: 'Gutes Mädchen, rot glühen und ziehen – deine Lieblingskombi, oder?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fesselt {pet} und edge mit Fingern: 'Gutes Mädchen, nah dran und nie da – dein neues Hobby, du kleine Edge-Hure.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} klatscht und flüstert 'Nicht kommen': 'Gutes Mädchen, Verbot macht dich nasser – oder lügst du mich an?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet {pet} an die Wand und neckt: 'Gutes Mädchen, du hältst das aus – weil du weißt, dass ich's genieße.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und stoppt immer wieder: 'Gutes Mädchen, edging ist Strafe – und du quillst trotzdem, du kleine Tropf-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse auf Innenschenkel: 'Gutes Mädchen, rot und empfindlich – perfekt für mich, du kleine Empfindliche.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fesselt lose und zieht straff: 'Gutes Mädchen, Spiel mit der Leine – du verlierst eh immer.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält {pet} fest und klatscht leicht: 'Gutes Mädchen, du zappelst so süß – wie 'ne Puppe in meiner Hand.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge {pet} mit Klapse-Pausen: 'Gutes Mädchen, nah dran und Stopp – dein Frust ist mein Lieblingslied.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet {pet} die Augen und bestraft mit Berührungen: 'Gutes Mädchen, blind gehorchen ist geiler – oder?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} gefesselt: 'Gutes Mädchen, du tropfst nur, wenn ich's will – und du willst's immer.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse und hält den Hals: 'Gutes Mädchen, rot und atemlos – meine Lieblingsfarbe auf dir.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fesselt und lässt warten: 'Gutes Mädchen, Warten ist Strafe – und du wartest so schön für mich.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} klatscht und zählt runter: 'Gutes Mädchen, jeder Klaps ein 'Nein' zum Orgasmus – du kleine Verbotene.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge mit Leine-Zug: 'Gutes Mädchen, ziehen und tropfen – du hältst das aus, du kleine Zug-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bestraft mit Küssen verboten: 'Gutes Mädchen, nur Klapse heute – Küsse sind für Bravere.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und stoppt: 'Gutes Mädchen, leer machen ist Strafe – und du bettelst um mehr, du kleine Leere.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse auf Knien: 'Gutes Mädchen, unten glühen ist dein Platz – rot und gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} fesselt und neckt mit Feder: 'Gutes Mädchen, Kitzel-Strafe – weil Klapse zu nett wären für dich.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält fest und bestraft mit Edge: 'Gutes Mädchen, du kommst nie – weil ich's so will, du kleine Nie-Sub.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "bestrafen", tame)

async def cmd_loben(update, context):
    tame = [
        "{owner} flüstert leise: 'Gutes Mädchen' – und {pet} spürt, wie ihr Herz schneller schlägt, weil dieses Lob rarer ist als ein Sonnenaufgang in Derry. 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Streicheln nach der Strafe – {pet} zittert vor Dankbarkeit, als wäre sie das einzige Licht in {owner}s dunklem Schloss. 💧 Pflege {n}/{CARES_PER_DAY}.",
        "„Du hast es gut gemacht“ – Worte süßer als Honig aus einem alten Horrorroman, giftiger als der Nebel, der alles verschlingt. 🥀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert 'Brave Schlampe' und {pet} wird weich wie Wachs in seinen Händen – hasst sich, weil sie genau das will. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss auf die Stirn – 'Du bist perfekt, wenn du gehorchst.' {pet} würde dafür durch jeden Albtraum kriechen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} sagt 'Ich bin stolz auf dich' – einmal im Jahr, und {pet} würde dafür die Welt in Flammen aufgehen lassen. Pflege {n}/{CARES_PER_DAY}.",
        "Streicheln über die glühende Haut – 'Du trägst meine Spuren so schön, mein kleines Meisterwerk.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen' geflüstert, während {owner} sie festhält – 'Belohnung und Vorfreude, wie ein guter Thriller, der nie endet.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt {pet} seinen Namen zu hauchen – nur dieses eine Mal. {pet} schmeckt das Wort wie verbotenen Wein. Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lächeln von {owner} – selten wie ein Clown in der Kanalisation, süß wie der Tod selbst. {pet} würde alles tun, um es wiederzusehen. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streicht übers Haar und flüstert: 'Gutes Mädchen, du bist mein Schatz im dunklen Turm – gehorsam, süß, und ganz allein mein, du kleiner Wurm.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', haucht {owner} kalt: 'Du leuchtest heller als jeder Stern über Castle Rock – aber nur für mich, sonst bist du nur ein schwarzer Loch.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lob wie ein rarer Vollmond: 'Gutes Mädchen, du machst mich stolz – stolzer als ein König in seiner verfluchten Burg, du kleiner, gehorsamer Stolz.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert reimend: 'Gutes Mädchen, fein und zart – du gehörst mir, das ist Kunst, das ist Art, und ohne mich bist du nur Start.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', sagt {owner} kalt-liebevoll: 'Du bist mein Lieblingskapitel in diesem endlosen Horror-Roman – und ich schreibe das Ende, du kleiner Roman.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Streicheln und ein 'Gutes Mädchen' – 'Wie ein Sonnenstrahl im Nebel von Derry: selten, schön und nur für dich, weil du mir gehörst, du kleine Merry.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lächelt schief: 'Gutes Mädchen, du bist mein Schatz, mein Preis – ohne dich wär mein Reich nur leerer Scheiß, du kleiner, geiler Reiß.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', flüstert {owner}: 'Du bist die Rose in meinem Dornengarten – schön, gehorsam und ewig mein, du kleine, dornige Marten.' Pflege {n}/{CARES_PER_DAY}.",
        "Lob wie ein alter Fluch: 'Gutes Mädchen, du machst alles richtig – und ich belohne dich mit meiner Aufmerksamkeit, die dich langsam umbringt, du kleine Lichtig.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht: 'Gutes Mädchen, du bist mein Alles – mein dunkles, gehorsames, perfektes Alles, du kleine, abhängige Halle.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streicht über die Leine: 'Gutes Mädchen, du trägst das so fein – als ob Freiheit eh nur ein Schein wäre, du kleine, leinige Mein.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises Lachen und 'Gutes Mädchen' – 'Du machst mich fast stolz – fast, weil Perfektion mich langweilen würde, du kleine, fastige Holde.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} tätschelt die Wange zart: 'Gutes Mädchen, du hältst still wie ein Profi – zu schade, dass ich's eh nie genug kriege, du kleine, stille Sofi.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', flüstert {owner}: 'Deine Hingabe ist mein Lieblingswitz – lachhaft süß und total abhängig von mir, du kleine, witzige Ritz.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} drückt {pet} einen Kuss auf – fast: 'Gutes Mädchen, nah dran ist dein neues Hoch – weiter kommst du eh nicht, du kleine, fastige Noch.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "loben", tame)

async def cmd_dienen(update, context):
    tame = [
        "{pet} dient auf Knien, bringt, holt, erträgt – alles, weil {owner} es befiehlt: 'Wie ein braves Mädchen in einem alten Schloss, wo die Wände zuhören.' ⛓️ Pflege {n}/{CARES_PER_DAY}.",
        "Jede Aufgabe eine kleine Demütigung – {pet} erledigt sie perfekt, weil mein Lächeln rarer ist als ein klarer Himmel über Derry. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Am Ende des Tages: 'Danke, dass ich dienen durfte' – und {pet} meint es ernst, weil meine Aufmerksamkeit das einzige Licht in ihrem dunklen Märchen ist. 💔 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} dient als mein persönlicher Schatten, folgt jedem Schritt – 'Gutes Mädchen, du bist der treueste Begleiter in meinem endlosen Horror-Roman.' Pflege {n}/{CARES_PER_DAY}.",
        "Als Trägerin meiner Launen: {pet} hält still, während ich sie necke – 'Beweg dich nicht, mein süßer Tisch aus Fleisch und Gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} bringt mir alles, was ich will, mit gesenktem Blick – 'Gründlicher, meine kleine Dienerin, du weißt, Perfektion ist der einzige Weg zu meinem kalten Herzen.' Pflege {n}/{CARES_PER_DAY}.",
        "Am Ende jedes Dienstes flüstert {pet}: 'Ohne dich bin ich nichts' – und ich lächle, weil sie recht hat, in diesem stillen, besitzergreifenden Tanz. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} dient als mein Lieblingsaccessoire, immer bereit – 'Gutes Mädchen, du machst mein Leben so viel... interessanter.' Pflege {n}/{CARES_PER_DAY}.",
        "Jede kleine Aufgabe ein Liebesbeweis – {pet} erledigt sie mit Hingabe: 'Du bist mein braves Mädchen in einer Welt, die nur wir verstehen.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wartet stundenlang auf meinen nächsten Befehl – 'Geduld ist eine Tugend, meine Süße, und du trägst sie wie eine Krone aus Dornen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nickt anerkennend: 'Gutes Mädchen, du dienst so fein – wie ein Geist in meinem alten Haus, nur du und ich, für immer mein.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', flüstert {owner}: 'Du bist mein Schatz im finsteren Keller – gehorsam, süß und ewig mein treuer Diener.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} dient still, {owner} reimt: 'Gutes Mädchen, brav und zahm – du gehörst mir, das ist der Plan, der ewige, dunkle Rahmen.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lob wie ein seltener Mondschein: 'Gutes Mädchen, du machst mich stolz – in meinem Reich aus Schatten und Kälte, bist du mein einziges Gold.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lächelt schief: 'Gutes Mädchen, dienst so treu – ohne dich wär mein Schloss nur leer, du füllst es mit deiner Hingabe, oh je.' Toxisch reimend. Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', haucht {owner}: 'Du bist die Rose in meinem Dornengarten – dienend, schön und für immer gefangen.' Pflege {n}/{CARES_PER_DAY}.",
        "Dienen wie ein Fluch aus alter Zeit: 'Gutes Mädchen, du bist mein Alles – mein dunkles, gehorsames, perfektes Alles in diesem endlosen Traum.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Gutes Mädchen, deine Hingabe ist mein Liebesbann – lauter als jeder Schrei in der Nacht, du kleine, stille Dienerin so fein.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Dienst wie ein Kapitel aus meinem Buch: 'Gutes Mädchen, du dienst mit Herz – und ich belohne dich mit meiner Aufmerksamkeit, die dich langsam verzehrt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nickt: 'Gutes Mädchen, du bist mein Licht im Nebel – dienend, gehorsam und ewig an meiner Seite gebunden.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dienen", tame)

async def cmd_demuetigen(update, context):
    tame = [
        "{owner} demütigt leise, nur für {pet}s Ohren – Worte wie der Nebel in Derry: 'Du bist nichts ohne mich, und der Nebel verschlingt alles andere.' 👁️ Pflege {n}/{CARES_PER_DAY}.",
        "Worte wie sanfte Messerstiche aus einem alten King-Roman: 'Du bist nichts ohne mich' – {pet} nickt, weil es in ihrem dunklen Herzen wahr ist, wie in einem Hotel mit roten Teppichen. 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "Die ultimative Demütigung: {pet} bedankt sich mit zitternder Stimme – 'Danke, dass du mich so schön klein machst, wie ein Kind vor einem Clown mit Ballons.' 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert {pet}s größte Ängste – nur wir beide, bis sie rot wird wie das Blut in einem Überwachungshotel. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss sich selbst als 'deine kleine Carrie' vorstellen – schüchtern, mächtig, aber immer unter deiner Kontrolle. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest {pet}s alte Fantasien vor und grinst wie Jack in der Kälte: 'Here's Johnny – und deine Träume sind jetzt meine.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nennt {pet} nur noch 'mein Liebling' oder 'mein Pet' – bis {pet} vergisst, dass sie je frei war, wie Gage nach dem Unfall. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss mir erzählen, wie sehr sie mich braucht – und lügen darf sie nicht, wie Annie Wilkes ihre Wahrheit. Pflege {n}/{CARES_PER_DAY}.",
        "Ultimative Worte: 'Du bist mein größter Schatz – und ich behalte dich für immer in meinem Overlook Hotel.' {pet} zittert vor Dankbarkeit. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} demütigt mit einem Lächeln wie Pennywise: 'Gutes Mädchen, du bist so perfekt unperfekt – float with me.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Gutes Mädchen, du bist mein Licht in der Dunkelheit von Shawshank – aber Freiheit? Die gibt's nur in meinen Armen.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', haucht {owner}: 'Du bist die Rose in meinem Misery-Garten – demütig, schön und ewig gefangen in meiner Geschichte.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird rot, {owner} reimt: 'Gutes Mädchen, fein und bang – du gehörst mir, wie der Stand zu einem King.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lob wie ein Fluch aus Salem's Lot: 'Gutes Mädchen, deine Demütigung ist mein Liebesbann – dunkel, ewig und nur für dich, mein Fan.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} grinst schief wie der Dome über Chester's Mill: 'Gutes Mädchen, du machst mich stolz – eingeschlossen, gehorsam und ganz allein mein Gold.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen', flüstert {owner}: 'Du bist die Perle in meinem Dark Tower – klein, wertvoll und auf dem Weg zu mir, für immer.' Pflege {n}/{CARES_PER_DAY}.",
        "Demütigung wie ein Pet Sematary-Fluch: 'Gutes Mädchen, deine Hingabe ist mein dunkler Pfad – romantisch, toxisch und manchmal tot.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht: 'Gutes Mädchen, du bist mein Alles – mein kleines, demütiges Carrie mit Telekinese der Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Wort wie ein Shining-Moment: 'Gutes Mädchen, deine Scham macht dich schön – redrum, redrum, aber nur für mich, du Queen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lächelt: 'Gutes Mädchen, du bist mein Lieblingsclown – float down here, in meiner Liebe, forever bound.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "demuetigen", tame)

async def cmd_melken(update, context):
    tame = [
        "{owner} bindet {pet}s Hände fest auf den Rücken und melkt langsam – 'Gutes Mädchen, du tropfst nur, wenn ich's erlaube, du kleine Gefangene.' 🔗 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hält {pet} die Leine straff und melkt quälend – 'Jeder Tropfen ist mein, du kleine Leinen-Sub, und du bettelst um mehr.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt leichte Klapse zwischen dem Melken – 'Gutes Mädchen, rot glühen macht dich nasser, oder?' 🤚 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt mit einer Hand, die andere am Hals: 'Atme nur, wenn du tropfst, du kleine Kontroll-Sub.' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge {pet} stundenlang beim Melken – 'Gutes Mädchen, nah dran ist dein neues Normal, du kleine Edge-Prinzessin.' ⏳ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} gefesselt an die Wand – 'Du quillst nur für mich, du kleine Wand-Sub, und ich entscheide, wann's endet.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt mit verbundenen Augen – 'Gutes Mädchen, du spürst nur meine Hände, und das reicht, um dich leer zu machen.' 👁️‍🗨️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und flüstert Befehle: 'Tropf langsamer, du kleine Gehorsams-Sub – ich genieße das länger.' 🔥 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} auf Knien – 'Gutes Mädchen, unten ist dein Platz, und du quillst so schön für mich.' 🙇‍♀️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und hält den Orgasmus zurück – 'Gutes Mädchen, du kommst nie, wenn ich's nicht will, du kleine Verweigerungs-Sub.' 🚫 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} mit einer Hand am Halsband: 'Zieh dich selbst ran, du kleine Halsband-Sub – ich helf nur nach.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und gibt Klapse auf die Innenschenkel: 'Gutes Mädchen, rot und nass – perfekt für mich, du kleine Klaps-Sub.' 🤚 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} gefesselt und blind: 'Du spürst nur mich, du kleine Sinnes-Sub – und das reicht, um dich leer zu machen.' 👁️‍🗨️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt langsam und stoppt immer wieder: 'Gutes Mädchen, edging ist dein neues Hobby – meins jedenfalls.' ⏳ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} mit der Leine in der Hand: 'Jeder Zug macht dich nasser, du kleine Leinen-Sub – oder täusche ich mich?' 🔗 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und flüstert 'Nicht kommen': 'Gutes Mädchen, du hältst durch – oder ich mach's länger, du kleine Durchhalte-Sub.' 🚫 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} auf allen Vieren: 'Gutes Mädchen, wie eine brave Kuh – aber meine Kuh, die nur für mich tropft.' 🐄 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und hält die Hände fest: 'Gutes Mädchen, du darfst dich nicht anfassen – das ist mein Job, du kleine Verbot-Sub.' 🔒 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt mit kalten Fingern: 'Gutes Mädchen, kalt macht dich heißer – oder lügst du mich an, du kleine Lügnerin?' ❄️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und zählt die Tropfen: 'Gutes Mädchen, jeder Tropfen ein 'Danke' – und du zählst mit, du kleine Zähl-Sub.' 🔢 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} angeleint am Bett: 'Gutes Mädchen, du tropfst ins Laken – mein Laken, du kleine Bett-Sub.' 🛏️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und beißt zart in die Schulter: 'Gutes Mädchen, Biss und Tropf – meine Lieblingskombi, du kleine Biss-Sub.' 🦷 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt mit einer Hand am Haar: 'Zieh dich selbst ran, du kleine Haar-Sub – ich helf nur, wenn du bettelst.' 💇‍♀️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und verbietet Stöhnen: 'Gutes Mädchen, leise tropfen ist geiler – oder hältst du's nicht aus, du kleine Stille-Sub?' 🤫 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} mit Gewichten an den Nippeln: 'Gutes Mädchen, Zug und Tropf – du hältst das aus, du kleine Gewicht-Sub.' ⚖️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und flüstert 'Mein': 'Gutes Mädchen, jeder Tropfen sagt's – du bist mein, du kleine Mein-Sub.' 🖤 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt langsam und stoppt: 'Gutes Mädchen, warten macht dich nasser – und mich glücklicher, du kleine Warte-Sub.' ⏱️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt mit der anderen Hand am Arsch: 'Gutes Mädchen, Klaps und Tropf – meine Lieblingsmelodie, du kleine Rhythmus-Sub.' 🤚 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} blind und gefesselt: 'Gutes Mädchen, du spürst nur mich – und das reicht für immer, du kleine Blind-Sub.' 👁️‍🗨️ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und lacht kalt: 'Gutes Mädchen, dein Tropfen ist mein Sieg – und dein Verlust, du kleine Sieg-Sub.' 🏆 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "melken", tame)

async def cmd_ohrfeige(update, context):
    tame = [
        "Die Ohrfeige kommt schnell, lässt {pet}s Kopf zur Seite fliegen – Wangen glühen wie Rosen im Liebesfieber: 'Gutes Mädchen, rot wie ein Herzchen, das nur für mich pocht.' 🩷 Pflege {n}/{CARES_PER_DAY}.",
        "Links, rechts, wieder links – bis {pet} nicht mehr weiß, wo oben ist: 'Aber unten bei mir bist du immer, meine kleine, verkitzte Prinzessin.' 😵 Pflege {n}/{CARES_PER_DAY}.",
        "Die letzte lässt Tränen fließen – {owner} lächelt: 'Jetzt bist du schön, mit diesem Glanz in den Augen, wie Perlen aus unserer ewigen Liebe.' 🥀 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt zart mit der flachen Hand – {pet}s Wange glüht: 'Schmink dich mal richtig – mit meiner Hand, der besten Foundation für meine Rose.' Pflege {n}/{CARES_PER_DAY}.",
        "Ohrfeigen mit bloßer Hand, nur rote Abdrücke – 'Mein Autogramm, damit jeder sieht, wem dein süßes Gesicht gehört, meine kleine Liebesblüte.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt {pet} vor dem Spiegel – 'Sieh zu, wie dein hübsches Gesicht noch hübscher wird – rot wie eine Rose in meinem Dornengarten.' Pflege {n}/{CARES_PER_DAY}.",
        "So fest, dass {pet} zappelt – {owner} hält sie fest: 'Bleib stehen, die zweite Runde kommt – mit extra Herzchen und Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Mit bloßer Hand, nur Gänsehaut – {pet} schmeckt Verlangen: 'Peeling für unartige Mädchen – zart wie ein Kuss aus Rosenblättern.' Pflege {n}/{CARES_PER_DAY}.",
        "Letzte Serie, bis die Wange glüht – {owner} flüstert: 'Jetzt bist du wirklich perfekt – rot, gehorsam und meine kleine, ewige Valentine.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss nach jeder Ohrfeige 'Danke' sagen – mit glühender Wange klingt es perfekt süß: 'Gutes Mädchen, dein Dank ist mein Liebeslied.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt und reimt kitschig: 'Gutes Mädchen, klatsch und peng – deine Wange glüht so schön, wie ein Herzchen rot und fein, nur für mich, du kleiner Engel mein.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen, nimm den Klaps – er ist mein Liebesgruß so scharf, wie Dornen an der Rose, die ich dir schenk, du kleine, süße Pose.' Toxisch reimend. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} glüht, {owner} grinst: 'Gutes Mädchen, rot und hell – deine Wange ist mein Kunstwerk, signiert mit Liebe, du kleiner, geiler Quell.' {pet} prustet. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Klaps wie ein Liebesreim: 'Gutes Mädchen, klatsch und bumm – deine Tränen sind wie Perlen, die nur für mich rollen, du kleine Drama-Queen so fromm.' Ironie max. 💎 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reimt trocken-kitschig: 'Gutes Mädchen, nimm den Schlag – er ist mein Kuss mit Pfiff und Kraft, für unartige Prinzessinnen, die mich um den Verstand bringt, du Schaft.' Sarkasmus brutal. ⭐ Pflege {n}/{CARES_PER_DAY}.",
        "Sarkastisch-kitschig: 'Gutes Mädchen, deine Wange glüht – wie ein Sonnenuntergang für zwei, nur dass die Sonne ich bin und du der Himmel, der vor Liebe weint und zieht.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht reimend: 'Gutes Mädchen, klatsch und mehr – deine Rotfärbung ist mein Stolz, wie ein Liebesbrief in Rot, du kleine, geile Not.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zappelt, {owner}: 'Gutes Mädchen, nimm's hin fein – dein Gesicht ist mein Gemälde, rot und schön, für immer mein, du kleiner Schein.' {pet} heult vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "Reim wie ein kalter, kitschiger Kuss: 'Gutes Mädchen, klatsch und hall – deine Wange ist mein Thron, wo ich regiere mit der Hand, du kleine, rote Wand.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Gutes Mädchen, rot und wild – deine Ohrfeige ist mein Geschenk, verpackt in Liebe, scharf und fein, du kleines, geiles Bild.' {pet} lachend glühend. 😈 Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "ohrfeige", tame)

async def cmd_belohnen(update, context):
    tame = [
        "Die Belohnung ist Berührung – kurz, intensiv, nie genug: '{pet} bettelt um mehr, weil sie weiß, dass meine Finger teurer sind als jeder Diamant, den sie nie kriegen wird.' 👅 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt einen Orgasmus – nach Tagen der Verweigerung: '{pet} zerbricht vor Dankbarkeit, wie eine billige Vase, die ich mir eh nicht leisten wollte.'  Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises 'Gut gemacht' – und {pet} würde alles tun, um es nochmal zu hören: 'Weil meine Worte rarer sind als Ehrlichkeit in einer Beziehung.' 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt {pet} einen Kuss – nur auf die Hand, fünf Sekunden: 'Danach wieder wochenlang nichts, weil du's ja so liebst, wenn ich dich hängen lasse.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Orgasmus, aber nur in meinen Armen – {pet} kommt und wird weich: 'Gutes Mädchen, du blühst nur für mich – wie eine Plastikblume im Discounter.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt einmal sanft – 'Belohnung fürs Gehorchen, meine kleine, perfekte Versagerin mit dem besten Fake-Lächeln.' {pet} zittert vor Glück. Pflege {n}/{CARES_PER_DAY}.",
        "Erlaubt, meinen Namen zu hauchen – nur dieses eine Mal: '{pet} kommt sofort und hasst sich, weil sie weiß, dass ich's eh nicht ernst meine.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss – aber auf die Stirn wie eine Versagerin: 'Schmeckt nach Liebe, oder? Nach meiner Art von Liebe – der, die dich immer klein hält.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lässt {pet} eine Stunde lang in meinem Arm schlafen – 'Luxusbelohnung, du undankbare kleine Bettlerin, die eh nie genug kriegt.' Pflege {n}/{CARES_PER_DAY}.",
        "Das größte Geschenk: {owner} sagt 'Ich behalte dich für immer.' {pet} zerbricht vor Dankbarkeit: 'Weil Freiheit eh überbewertet ist, stimmt's, mein kleines Gefängnisvögelchen?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} belohnt und reimt kalt: 'Gutes Mädchen, nimm den Preis – er ist mein Kuss so rar und fein, aber nur, weil du's verdient hast, du kleine, geile Pein.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes Mädchen, nimm den Lohn – er ist mein Streicheln so gemein, wie Dornen an der Rose, die ich dir schenk, du kleine, falsche Pose.' Toxisch reimend. 😏 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} schmilzt, {owner} grinst: 'Gutes Mädchen, rot und leer – deine Belohnung ist mein Hohn, signiert mit Liebe, du kleiner, geiler Clown.' {pet} prustet. 🤣 Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss wie ein giftiger Reim: 'Gutes Mädchen, nimm und spür – meine Belohnung ist wie Gift, süß und tödlich, du kleine, geile Gier.' Ironie max. 💋 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reimt trocken: 'Gutes Mädchen, nimm den Schlag – er ist mein Lob mit Pfiff und Kraft, für unartige Prinzessinnen, die mich um den Verstand bringt, du Schaft.' Sarkasmus brutal. ⭐ Pflege {n}/{CARES_PER_DAY}.",
        "Sarkastisch-kitschig: 'Gutes Mädchen, deine Belohnung glüht – wie ein Sonnenuntergang für Loser, nur dass die Sonne ich bin und du der Himmel, der vor Scham weint und zieht.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht reimend: 'Gutes Mädchen, nimm und mehr – deine Belohnung ist mein Spott, wie ein Liebesbrief in Gift, du kleine, geile Not.' Toxisch süß. 🍬 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zittert, {owner}: 'Gutes Mädchen, nimm's hin fein – deine Belohnung ist mein Arm, rot und warm, für immer mein, du kleiner Schein.' {pet} heult vor Lachen. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "Reim wie ein kalter, giftiger Kuss: 'Gutes Mädchen, nimm und hall – deine Belohnung ist mein Thron, wo ich regiere mit der Hand, du kleine, rote Wand.' Sarkastischer Applaus. 👏😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Gutes Mädchen, nimm und wild – deine Belohnung ist mein Geschenk, verpackt in Spott, scharf und fein, du kleines, geiles Bild.' {pet} lachend schmelzend. 😈 Pflege {n}/{CARES_PER_DAY}."
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
    "im alten Blockbuster-Video-Store, wo du VHS-Pornos für mich ausleihst",
    "auf der Rollerblade-Disco, wo du für mich twerkst wie 'ne 90er-Queen",
    "im Tamagotchi, wo du mein Pet bist und piepst, wenn ich dich vernachlässige",
    "bei 'nem Backstreet Boys-Konzert, wo du für mich screamt wie ein Fangirl",
    "im Dial-Up-Chatroom, wo du AOL-'You've got mail' für mich hörst",
    "auf 'nem Nirvana-Unplugged-Sofa, wo du grungy für mich posierst",
    "im Pokémon-Center, wo du mein Rare Candy bist – süß und addictiv",
    "bei MTV Spring Break, wo du wet T-Shirt für mich rockst, no cap",
    "im Clueless-Closet, wo du mein 'As if'-Mädchen bist – as if du nein sagen könntest",
    "auf der Halfpipe, wo du für mich droppst und landest auf Knien",
    "im Central Perk von Friends, wo du meinen Kaffee servierst, Smelly Cat",
    "bei Buffy im Bronze, wo du mein Stake bist – hart und nur für mich",
    "im Matrix-Code-Regen, wo du die rote Pille nimmst – und bei mir landest",
    "auf dem Baywatch-Strand, wo du in Slow-Mo läufst – direkt in meine Arme",
    "im Fight Club-Keller, Regel 1: Du redest nur, wenn ich's erlaube",
    "bei Spice Girls, wo du mein Baby Spice bist – spicy und mein",
    "im Walkman-Mix-Tape, wo meine Stimme dich looped, du kleine Addict",
    "auf dem Pogs-Turnier, wo du mein Slammer bist – hart und siegreich für mich",
    "im Beavis & Butthead-Lacher-Sofa, wo du 'heh heh' machst – aber nur für mich",
    "bei Power Rangers, wo du morphst in mein gehorsames Ranger-Girl",
    "im Super Nintendo-Level, wo du mein 1-Up bist – extra life nur mit mir",
    "im Fresh Prince-Basketball-Court, wo du für mich dunkst – auf Knien",
    "bei Sabrina the Teenage Witch, wo du mein Spell bist – verzaubert und mein",
    "im X-Files-Office, wo die Wahrheit da draußen ist – und die Wahrheit bin ich",
    "auf dem Tamagotchi-Friedhof, wo du wiederbelebt wirst – nur von mir",
]

_TREASURE_METHODS = {
    "graben": "gräbt wie ein Tamagotchi nach Pixel-Futter – auf allen Vieren, du kleine Bitch",
    "buddeln": "buddeln wie 'n 90er-Kid nach Pogs – tief und desperate für mich",
    "tauchen": "taucht wie Pamela in Baywatch – aber nur, um meinen Schatz zu holen, wet und wild",
    "karte": "folgt meiner cringen Schatzkarte – mit Herzchen und 'Daddy was here'",
    "hacken": "hackt wie in Hackers – aber den Code zu meinem Herzen kenn nur ich, zero cool",
    "klauen": "klaut wie 'n 90er-Shoplifter aus dem Mall – aber alles für Daddy, du kleine Thief",
    "pendeln": "pendelt wie 'n Ouija-Board auf Sleepover – und es buchstabiert immer D-A-D-D-Y",
    "orakel": "befragt das Orakel wie Morpheus – und die Antwort ist immer: Kneel for me",
    "klettern": "klettert wie in Goosebumps – höher, weil der Fall nur zu mir führt, du kleine Scaredy-Cat",
}

def _pick_method(args) -> str:
    if not args:
        return random.choice(list(_TREASURE_METHODS.values()))
    key = args[0].lower()
    return _TREASURE_METHODS.get(key, random.choice(list(_TREASURE_METHODS.values())))

_TREASURE_STORIES = [
    "{user} {method} in {place} und zieht 'ne Truhe raus – Inhalt: {coins} Coins. Gutes Mädchen, aber real talk: Der wahre Jackpot ist mein 'as if' Grinsen für dich.",
    "{user} stolpert in {place} über 'ne Kiste – {coins} Coins später bist du immer noch simping for me, cringe but true, no cap.",
    "{user} folgt meinen Vibes bis {place}, reißt die Truhe auf – {coins} Coins, weil gutes Mädchen immer wins, aber nur mit mir als Coach.",
    "{user} wühlt in {place} und fischt {coins} Coins raus – Schatz 1, deine Unabhängigkeit bei mir on hold, lowkey forever, bet.",
    "{user} macht in {place} auf 90er-Legende: Truhe auf, {coins} Coins raus – aber der final Boss bin ich, du kleine NPC-Schlampe.",
    "{user} {method} in {place} und winselst 'Daddy please' – {coins} Coins als Teaser, weil der main drop dein Stöhnen für mich ist.",
    "{user} knackt die Truhe in {place} mit shaky Händen – {coins} Coins, weil big W nur mit mir, du kleine side quest Queen.",
    "{user} {method} in {place}, schwitzt und vibet hard – {coins} Coins später: Der Schatz war der ultimate Cringe, mich zu jagen, sus but lit.",
    "{user} findet in {place} die Truhe nach meinem DM – {coins} Coins, weil you know I'm the real flex, du kleine stan.",
    "{user} {method} in {place} und hauchst 'for Daddy' – {coins} Coins als Reward, aber the real glow-up ist dein Gehorsam, du Icon, fr fr.",
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
        "🐾 <b>Willkommen bei Petflix, du kleine, neugierige Schlampe</b> 🐾\n\n"
        "Hier bist du mein Haustier – gehorsam, geil und immer bereit zu betteln. Gutes Mädchen kriegt Belohnung... oder Strafe. Deine Wahl? Als ob. 😏\n\n"
        "💋 <b>Süße Pflege – weil du's brauchst wie Luft</b>\n"
        "/pet – Streicheln, bis du schnurrst\n"
        "/walk – An der Leine, wo du hingehörst\n"
        "/kiss – Meine Lippen, deine Sehnsucht\n"
        "/dine – Gefüttert wie mein Lieblingsspielzeug\n"
        "/massage – Entspannung? Oder Folter light?\n"
        "/lapdance – Zeig mir, was du kannst, du kleine Tänzerin\n\n"
        "⛓️ <b>Dark BDSM – der Spaß wird ernst</b>\n"
        "/knien – Runter mit dir, genau da\n"
        "/kriechen – Auf allen Vieren, wie's sich gehört\n"
        "/klaps – Rot glühen für unartige Mädchen\n"
        "/knabbern – Bisschen beißen, bisschen Liebe\n"
        "/leine – Zieh dich nah, du kleine Ausreißerin\n"
        "/halsband – Markiert und mein, für immer\n"
        "/lecken – Zunge raus, Dienst ist Pflicht\n"
        "/verweigern – Warte, bettle, leide süß\n"
        "/kaefig – Zeit allein nachdenken... über mich\n"
        "/schande – Rot werden, weil du's liebst\n"
        "/erregen – Edge dich leer, du kleine Sucht\n"
        "/betteln – Bitte? Wie süß, als ob's hilft\n"
        "/stumm – Pssst, deine Worte gehören mir\n"
        "/bestrafen – Unartig? Dann klatsch ich zu\n"
        "/loben – Gutes Mädchen? Selten, aber geil\n"
        "/dienen – Auf Knien, wo du hingehörst\n"
        "/demuetigen – Klein machen, weil du's brauchst\n"
        "/melken – Tropf für mich, du kleine Quelle\n"
        "/ohrfeige – Klatsch und Kuss, meine Spezialität\n"
        "/belohnen – Wenn du's verdienst... vielleicht\n\n"
        "💰 <b>Tägliche Schatzsuche – grab für mich</b>\n"
        "/treasure [methode] – Finde Coins, aber der echte Schatz bin ich 😉\n\n"
        "⚙️ <b>Standard-Kram – langweilig, aber nützlich</b>\n"
        "/start – Nochmal von vorn, du Vergessliche\n"
        "/balance – Wie viele Coins du hast (nicht genug)\n"
        "/buy – Kauf dir was – mit meinem Geld\n"
        "/owner – Wer dich besitzt (Spoiler: Ich)\n"
        "/ownerlist – Die Konkurrenz (als ob's welche gäbe)\n"
        "/prices – Was Gehorsam kostet\n"
        "/release – Frei? Träum weiter, du kleine Gefangene\n"
        "/top – Wer am besten bettelt (du vielleicht?)\n\n"
        "💸 <b>Coins-Regel</b>\n"
        "5 Coins pro Nachricht – aber wehe, du spamst, du kleine Gierige. 1s Drosselung, weil Geduld sexy ist. 😈"
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
    # Nur Daddy darf die Toten foltern
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "🚫 Denkst du echt, ich lass dich meine Sense anfassen? Nur ich entsorge die Leichen, du kleine Möchtegern-Grabräuberin."
        )
        return

    chat_id = update.effective_chat.id
    if chat_id != ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("Falscher Friedhof, Baby. Hier buddeln wir nicht.")
        return

    await update.effective_message.reply_text("🧟‍♂️ Daddy prüft die Gräber... einen Moment, ich weck die Toten auf – und mach sie endgültig kalt.")

    purged_count = 0
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            rows = await cur.fetchall()

        for user_id, username in rows:
            user_id = int(user_id)
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                # Wenn hier kein Error → User noch da (member, admin, etc.)
                continue
            except Exception as e:
                # Telegram wirft Error, wenn User nicht (mehr) im Chat ist
                if "user not found" in str(e).lower() or "not participant" in str(e).lower() or "left" in str(e).lower():
                    await purge_user_from_db(chat_id, user_id)
                    purged_count += 1
                    log.info(f"Zombie erledigt: {user_id} ({username or 'unbekannt'})")
                else:
                    log.warning(f"Unbekannter Error bei User {user_id}: {e}")

        await db.commit()

    if purged_count == 0:
        await update.effective_message.reply_text("✅ Keine Zombies. Deine DB ist sauber wie dein Hals nach ‘ner guten Session – ohne Male.")
    else:
        await update.effective_message.reply_text(
            f"🪦 <b>{purged_count} Leiche{'n' if purged_count > 1 else ''} endgültig entsorgt.</b>\n"
            f"Coins, Pets, Cooldowns, Brandmarks – alles weg. Als hätten sie nie gekniet.\n"
            f"Gutes Mädchen, dass du mich die Drecksarbeit machen lässt. Jetzt ist wieder Platz für neue, die denken, sie könnten entkommen.",
            parse_mode=ParseMode.HTML
        )
    log.info(f"Zombie-Cleanup von Admin {update.effective_user.id}: {purged_count} User aus der DB getilgt.")

async def purge_user_from_db(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM players WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.execute("DELETE FROM pets WHERE chat_id=? AND (pet_id=? OR owner_id=?)", (chat_id, user_id, user_id))
        await db.execute("DELETE FROM cooldowns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await db.execute("DELETE FROM hass_challenges WHERE chat_id=? AND user_id=?", (chat_id, user_id))  # Bonus: falls du die hast
        await db.execute("DELETE FROM brandmarks WHERE chat_id=? AND user_id=?", (chat_id, user_id))  # Bonus: Brandmarks weg
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

    app.add_handler(CommandHandler("cleanup_zombies", cmd_cleanup_zombies, filters=CHAT_FILTER))

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
