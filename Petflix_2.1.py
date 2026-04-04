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
from text_helpers import get_cached_json, split_chunks
from admin_coin_commands import create_admin_coin_commands
from runtime_features import create_runtime_features
from ownership_features import create_ownership_features
from economy_commands import create_economy_commands
from jobs_watchdogs import create_jobs_watchdogs

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

DB = os.environ.get("DB_PATH", "petflix_2.1.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "data")
BACKUP_KEEP_FILES = 7
MAX_CHUNK = 3500  # unter 4096 bleiben, wegen HTML-Overhead sicher
DOM_RESPONSES_PATH = os.getenv("DOM_RESPONSES_PATH", "texts/dom_responses.json")
CARE_RESPONSES_PATH = os.getenv("CARE_RESPONSES_PATH", "texts/care_responses.json")
DOM_FEMALE_DENY_LINES = [
    "Nein. Schau zu und lern.",
    "Schoener Versuch, aber nein.",
    "Netter Versuch. Heute nicht."
]

ADMIN_MORAL_TAX_REPLIES = [
    (r"(?i)\bbitte\b", "Sehr gerne, Master."),
    (r"(?i)\bdanke\b", "Immer, Master."),
]

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
TITLE_BESTIENZAEHMER = "Bestienzaehmer 🐉"
TITLE_DURATION_S = 2 * 3600
DAILY_GIFT_COINS = 15
DAILY_CURSE_PENALTY = 150
DAILY_PRIMETIME_COINS = 50000
DAILY_CURSE_ENABLED = True
MORAL_TAX_DEFAULT = 5
REWARD_AMOUNT = 1 
# =========================
# Ausreisser
# =========================
RUNAWAY_LINES = [
    "{pet} reisst aus und laeuft von {owner} weg. Eine Leine weniger.",
    "{pet} ist weg von {owner}. Keine Spuren, kein Mitleid.",
    "{pet} beisst sich frei und rennt von {owner} weg.",
    "{pet} verschwindet einfach so - weg von {owner}.",
    "{pet} zerreisst die Leine von {owner} und ist Staub."
]
RUNAWAY_PENALTY = 400

# =========================
# Superworte
# =========================
SUPERWORD_REWARD = 5000
SUPERWORDS = [
    "krieg der sterne",
    "stand by me",
    "teen wolf",
    "zurueck in die zukunft",
    "ghostbusters",
    "top gun",
    "stirb langsam",
    "blade runner",
    "breakfast club",
    "karate kid",
    "das ding",
    "predator",
    "robocop",
    "beetlejuice",
    "gremlins",
    "labyrinth",
    "flashdance",
    "dirty dancing",
    "rain man",
    "die goonies",
    "et",
    "jagd auf roter oktober",
    "risky business",
    "ferris macht blau",
    "zwei stahlharte profis",
    "big",
    "akira",
    "roger rabbit",
    "der prinz aus zamunda",
    "nummer 5 lebt",
    "die unendliche geschichte",
    "arielle",
    "die nackte kanone",
    "blues brothers",
    "poltergeist",
    "full metal jacket",
    "nightmare",
    "die unbestechlichen",
    "wall street",
    "scarface",
    "aliens",
    "rambo",
    "rambo 2",
    "rambo 3",
    "die hard 2",
    "die hard 3",
    "batman",
    "batman returns",
    "terminator",
    "terminator 2",
    "total recall",
    "the running man",
    "commando",
    "rocky 3",
    "rocky 4",
    "rocky 5",
    "bloodsport",
    "kickboxer",
    "highlander",
    "police academy",
    "the fly",
    "the thing",
    "shining",
    "platoon",
    "goodfellas",
    "world of warcraft",
    "wow classic",
    "the burning crusade",
    "wrath of the lich king",
    "cataclysm",
    "mists of pandaria",
    "warlords of draenor",
    "legion",
    "battle for azeroth",
    "shadowlands",
    "dragonflight",
    "the war within",
    "azeroth",
    "kalimdor",
    "eastern kingdoms",
    "northrend",
    "pandaria",
    "draenor",
    "broken isles",
    "the maw",
    "stormwind",
    "orgrimmar",
    "ironforge",
    "darnassus",
    "thunder bluff",
    "undercity",
    "silvermoon",
    "exodar",
    "dalaran",
    "booty bay",
    "stranglethorn vale",
    "elwynn forest",
    "durotar",
    "tirisfal glades",
    "the barrens",
    "tanaris",
    "ungoro crater",
    "silithus",
    "winterspring",
    "ashenvale",
    "darkshore",
    "deepholm",
    "bastion",
    "revendreth",
    "maldraxxus",
    "ardenweald",
    "oribos",
    "dragon isles",
    "valdrakken",
    "isle of queldanas",
    "argent tournament",
    "darkmoon faire",
    "auction house",
    "battleground",
    "arena skirmish",
    "mythic plus",
    "raid finder",
    "dungeon finder",
    "world quest",
    "garrison",
    "order hall",
    "artifact weapon",
    "heart of azeroth",
    "azerite armor",
    "covenant sanctum",
    "dragonriding",
    "warband bank",
    "horde",
    "alliance",
    "forsaken",
    "night elf",
    "blood elf",
    "tauren",
    "orc shaman",
    "human paladin",
    "dwarf hunter",
    "undead warlock",
    "troll priest",
    "draenei mage",
    "gnome rogue",
    "worgen druid",
    "pandaren monk",
    "death knight",
    "demon hunter",
    "evoker",
    "lich king",
    "arthas menethil",
    "sylvanas windrunner",
    "thrall",
    "jaina proudmoore",
    "anduin wrynn",
    "varian wrynn",
    "illidan stormrage",
    "malfurion stormrage",
    "tyrande whisperwind",
    "guldan",
    "kaelthas sunstrider",
    "ragnaros",
    "onyxia",
    "naxxramas",
    "molten core",
    "blackwing lair",
    "blackwing descent",
    "black temple",
    "sunwell plateau",
    "karazhan",
    "gruuls lair",
    "magtheridons lair",
    "serpentshrine cavern",
    "tempest keep",
    "hyjal summit",
    "icecrown citadel",
    "trial of the crusader",
    "ulduar",
    "ruby sanctum",
    "vault of archavon",
    "obsidian sanctum",
    "eye of eternity",
    "firelands",
    "dragon soul",
    "bastion of twilight",
    "throne of the four winds",
    "siege of orgrimmar",
    "throne of thunder",
    "heart of fear",
    "terrace of endless spring",
    "mogu shan vaults",
    "highmaul",
    "blackrock foundry",
    "hellfire citadel",
    "emerald nightmare",
    "trial of valor",
    "nighthold",
    "tomb of sargeras",
    "antorus the burning throne",
    "uldir",
    "battle of dazaralor",
    "eternal palace",
    "nyalotha",
    "castle nathria",
    "sanctum of domination",
    "sepulcher of the first ones",
    "vault of the incarnates",
    "aberrus the shadowed crucible",
    "amirdrassil the dreams hope",
    "deadmines",
    "shadowfang keep",
    "scarlet monastery",
    "scholomance",
    "stratholme",
    "zul farrak",
    "maraudon",
    "blackrock depths",
    "blackrock spire",
    "dire maul",
    "ragefire chasm",
    "wailing caverns",
    "razorfen downs",
    "razorfen kraul",
    "gnomeregan",
    "the stockade",
    "utgarde keep",
    "the nexus",
    "azjol nerub",
    "ahnkahet",
    "halls of lightning",
    "pit of saron",
    "the culling of stratholme",
    "grim batol",
    "the vortex pinnacle",
    "lost city of the tolvir",
    "well of eternity",
    "court of stars",
    "maw of souls",
    "neltharions lair",
    "freehold",
    "atal dazar",
    "waycrest manor",
    "tol dagor",
    "theater of pain",
    "mists of tirna scithe",
    "halls of atonement",
    "ruby life pools",
    "the nokhud offensive",
    "brackenhide hollow",
    "algethar academy",
    "azure vault",
    "dawn of the infinite",
    "scarlet halls",
    "temple of the jade serpent",
    "shadowmoon burial grounds",
    "skyreach",
    "operation mechagon",
    "return to karazhan",
    "mechagon",
    "nazjatar",
    "zuldazar",
    "kul tiras",
    "dragonblight",
    "howling fjord"
]

def _add_umlaut_variants(words: list[str]) -> list[str]:
    out = []
    for word in words:
        w = (word or "").strip()
        if not w:
            continue
        out.append(w)
        variant = (
            w.replace("ae", "ä")
             .replace("oe", "ö")
             .replace("ue", "ü")
             .replace("Ae", "Ä")
             .replace("Oe", "Ö")
             .replace("Ue", "Ü")
        )
        if variant != w:
            out.append(variant)
    return out


SUPERWORDS_FILES = [
    "texts/superwords_wow_1_de.txt",
    "texts/superwords_wow_2_de.txt",
    "texts/superwords_series_de.txt",
    "texts/superwords_series_en.txt",
]
SUPERWORDS_CLEAN_FILE = "texts/superwords_all_clean.txt"
if os.path.exists(SUPERWORDS_CLEAN_FILE):
    SUPERWORDS = []
    with open(SUPERWORDS_CLEAN_FILE, "r", encoding="utf-8-sig") as f:
        for line in f:
            word = line.strip()
            if word and not word.startswith("#"):
                SUPERWORDS.append(word)
else:
    for superwords_path in SUPERWORDS_FILES:
        if not os.path.exists(superwords_path):
            continue
        with open(superwords_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                word = line.strip()
                if word and not word.startswith("#"):
                    SUPERWORDS.append(word)
SUPERWORDS = list(dict.fromkeys(_add_umlaut_variants(SUPERWORDS)))
# =========================
# /steal
# =========================
STEAL_SUCCESS_CHANCE = 0.48
STEAL_COOLDOWN_S = 10 * 60
STEAL_FAIL_PENALTY_RATIO = 0.20

# =========================
# /buy Schutz durch Pflege
# =========================
BUY_SUCCESS_MAX = 0.95   # Bei 0/10 Pflege fast sicher kaufbar
BUY_SUCCESS_MIN = 0.05   # Bei 10/10 Pflege fast nicht kaufbar
BUY_FAIL_PENALTY_RATIO = 0.20  # Bei Fehlversuch immer 20% Coins weg
CARE_FIFTYFIFTY_UNTIL = 4
CARE_HARD_PROTECT_START = 8
RISK_BONUS_PER_PRICE = 0.20  # Risiko in Hoehe des Preises => +20% Chance
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
        "name": "Petflix Firewall",
        "desc": "Blockt Angreifer: -20% Kaufchance.",
        "weight": 25,
    },
    "treuesiegel": {
        "name": "Besitzvertrag X",
        "desc": f"Bei {CARES_PER_DAY}/{CARES_PER_DAY} Pflege ist Klauen nahezu unmoeglich.",
        "weight": 18,
    },
    "goldzahn": {
        "name": "Coin-Ruecklauf",
        "desc": "Bei erfolgreichem Kauf: 15% Cashback auf den Kaufpreis.",
        "weight": 18,
    },
    "wertanlage": {
        "name": "Hype-Maschine",
        "desc": f"Preis steigt nach Kauf um {PRICE_STEP_SKILL_BONUS} statt {USER_PRICE_STEP}.",
        "weight": 16,
    },
    "goldesel": {
        "name": "Petflix Prime",
        "desc": f"Bei {CARES_PER_DAY}/{CARES_PER_DAY} Pflege erhaelt der Owner +{FULL_CARE_OWNER_BONUS} Bonus/Tag.",
        "weight": 13,
    },
    "chamaeleon": {
        "name": "Patchnote",
        "desc": "Bei Besitzerwechsel wird der Skill sofort neu ausgewuerfelt.",
        "weight": 10,
    },
}

PET_LEVEL_TITLES = [
    "Pflegekueken",
    "Fellwaechter",
    "Bestienzaehmer",
    "Rudelfluesterer",
    "Instinktmeister",
    "Alpha-Dompteur",
    "Apex-Baendiger",
]
PET_LEVEL_THRESHOLDS = [
    0,
    30,
    60,
    100,
    150,
    210,
    280,
    360,
    450,
    550,
    660,
    780,
    910,
    1050,
    1200,
    1360,
    1530,
    1710,
    1900,
    2100,
]
FULLCARE_EVOLUTION_STAGES = [
    (30, "Legendaerer Baendiger"),
    (14, "Gold-Zaehmer"),
    (7, "Silber-Zaehmer"),
    (3, "Bronze-Zaehmer"),
    (1, "Bestienzaehmer"),
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

FLUCH_LINES = [
    "{user}, dein Fluch: Dein Spiegelbild bindet dich nachts ans Bett. Der DÃ¤mon flÃ¼stert 'Bleib liegen'.",
    "Herzlichen GlÃ¼ckwunsch {user}: Dein Schatten folgt dir â€“ bei Vollmond holt er dich ein und fesselt dich.",
    "{user}, verflucht: Dein KÃ¼hlschrank Ã¶ffnet sich allein. Der DÃ¤mon kocht dich langsam bei lebendigem Leib.",
    "Dein Fluch {user}: Jeder Witz endet mit deinem eigenen Schrei. Deine Freunde lachen â€“ aus Angst.",
    "{user}, klebrig wie ein DÃ¤mon: Alles bleibt an deinen Fingern. Du kommst nie los. Moralisch erstickt.",
    "Fluch des Jahrhunderts: Dein Handy zeigt nur Nachrichten von mir. 'Ich bin dein Besitzer'. Akku stirbt nie.",
    "{user}, verflucht: Dein Crush schreibt nur 'Knie fÃ¼r mich'. FÃ¼r immer. Du gehorchst.",
    "Oh {user}, dein Parkplatz ist vor meinem Keller. Karma parkt dich ein â€“ und lÃ¤sst dich nicht raus.",
    "{user} wird verfolgt: Werbung fÃ¼r Ketten und Peitschen. Peinlich bis zum Wahnsinn.",
    "Dein grÃ¶ÃŸter Fluch {user}: Du gewinnst 'ne Reise in meinen KÃ¤fig. Kein ZurÃ¼ck.",
    "{user}, verflucht: Dein Drucker spuckt nur Ketten. Du kommst zu spÃ¤t. Technik hasst dich.",
    "Jede Nacht Geisterstimmen aus dem Abfluss: 'Komm knien, {user}'. Badewanne meiden.",
    "Dein Schatten lÃ¤uft hinter dir â€“ bei Vollmond voraus. Er wartet auf deinen Fehler.",
    "{user}, dein Auto fÃ¤hrt allein in meinen Keller. 'All work and no play' auf dem Navi.",
    "Jeder Kuss schmeckt nach Fesseln. SÃ¼ÃŸ â€“ bis der Hammer kommt. Deine Liebhaber fliehen.",
    "Dein Keller Ã¶ffnet sich jede Nacht tiefer. Unten steht eine TÃ¼r mit deinem Namen. Der DÃ¤mon bin ich.",
    "Fluch des Jahrhunderts: Dein Spiegel zeigt dich gefesselt. Blutig. WÃ¼tend. Du bist das Ziel.",
    "{user}, dein Hund kommt nachts zurÃ¼ck â€“ tote Augen. Er bellt 'Knie'.",
    "Deine TrÃ¤ume sind nur noch Korridore. Geister flÃ¼stern 'Knie fÃ¼r mich'. FÃ¼r immer.",
    "{user} wird verfolgt von einem Schatten mit Ketten. 'Du gehÃ¶rst mir'. Peinlich bis in den Tod.",
    "Du gewinnst im Lotto â€“ Scheck von mir. Postkarte: 'Knie fÃ¼r den Preis'.",
    "Jede Nacht Geister am FuÃŸende. 'Knie fÃ¼r uns'. SÃ¼ÃŸe TrÃ¤ume, Prinzessin.",
    "Dein Hund kommt zurÃ¼ck â€“ tote Augen, Ketten am Hals. Er bellt 'Gehorsam'.",
    "{user}, dein Spiegel zeigt dich gefesselt. Schmink dich, Telekinese-Queen.",
    "Dein Auto fÃ¤hrt allein in den Keller. DÃ¤mon grÃ¼ÃŸt, du kleine Highway-Hure.",
    "Dein Radio flÃ¼stert nur 'Knie'. Der DÃ¤mon ist dein DJ. Er hat Geduld.",
    "Deine TrÃ¤ume sind Folter. Der DÃ¤mon pflegt dich. Der Hammer ist bereit.",
    "{user}, dein Schatten hat eigenen Willen. Er bindet dich. Tick-tack.",
    "Jede TÃ¼r fÃ¼hrt in meinen Keller. Die badende Hexe wartet. Here's your nightmare.",
    "{user}, dein Telefon klingelt nur aus dem Grab. Tote rufen 'Knie'. Ring ring.",
    "{user} wird eingeschlossen im unsichtbaren KÃ¤fig. Alle sehen zu, wie du brichst.",
    "Du findest ein altes Buch. Beim Lesen wird's real. Der DÃ¤mon bin ich.",
    "{user}, dein Kaffee schmeckt immer bitter. Der DÃ¤mon rÃ¼hrt um.",
    "Deine Katze kommt zurÃ¼ck â€“ tote Augen. Sie starrt. Du weiÃŸt warum.",
    "{user}, jeder Vollmond macht dich zur Bestie â€“ nur innerlich. Meine Bestie.",
    "Dein Laptop Ã¶ffnet nur den Virus. Er infiziert deine Seele.",
    "{user}, Kinderlachen aus dem Abfluss. 'Knie fÃ¼r uns'. Badewanne meiden.",
    "Dein Herz schlÃ¤gt nur noch, wenn ich's erlaube. Schrumpfende SÃ¼nderin.",
    "{user}, dein Schatten tanzt. Er kennt alle Geheimnisse.",
    "Du siehst immer die Toten. Sie flÃ¼stern 'Du gehÃ¶rst ihm'.",
    "Du wachst auf und alles ist Nebel. DrauÃŸen Monster, drinnen nur ich."
]

FLUCH_LINES.extend([
    "{user}, dein Fluch heute: Jede ruhige Minute klingt ploetzlich nach deinem eigenen Versagen. Laut. Nah. Ohne Pause.",
    "{user}, du ziehst heute Unglueck an wie andere Leute Parfum. Nur dass deins nach Keller und Panik riecht.",
    "{user}, jede Tuerspaltbreite heute ein Fehler. Dahinter wartet nichts Gutes und es kennt deinen Namen.",
    "{user}, dein Schatten geht heute nicht hinter dir. Er geht vor dir und lacht, wenn du stolperst.",
    "{user}, du hast heute das Charisma eines nassen Kellertuchs. Und selbst das waere noch schmeichelhaft.",
    "{user}, dein Spiegel zeigt dir heute exakt, was alle anderen schon laengst denken: peinlich, verflucht, verloren.",
    "{user}, heute findet dich jedes Pech. Schnell. Praezise. Mit Genuss.",
    "{user}, selbst deine Ausreden kriechen heute auf Knien vor mir an. Erbaermlicher wird's nicht.",
    "{user}, dein Tag fuehlt sich heute an wie ein Horrorfilm mit dir als billigster Nebenrolle.",
    "{user}, dein Fluch ist simpel: Egal was du anfasst, es wirkt danach noch trauriger als vorher.",
    "{user}, du bringst heute selbst Neonlicht dazu, muede auszusehen.",
    "{user}, irgendwo quietscht heute eine Tuer nur fuer dich. Dahinter steht dein schlechtester Tag in Reinform.",
    "{user}, jede Nachricht von dir klingt heute wie ein Hilferuf aus einem sehr kleinen, sehr kalten Raum.",
    "{user}, du bist heute offiziell das schlechteste Omen im ganzen Chat.",
    "{user}, dein Pech traegt heute Stiefel und tritt jede Hoffnung langsam tiefer in den Boden.",
    "{user}, heute reagiert sogar dein Glueck mit Abwesenheitsnotiz.",
    "{user}, du wirkst heute wie die Pointe eines besonders boesen Witzes.",
    "{user}, jede Lampe flackert heute kurz, nur um dir zu sagen: Nein, besser wird's nicht.",
    "{user}, dein Fluch heute ist Dauerblamage mit Premium-Abo.",
    "{user}, selbst der Nebel will heute Abstand von dir. So schlimm ist die Lage.",
    "{user}, heute fuehlt sich jeder Schritt an, als haette das Universum persoenlich was gegen dich.",
    "{user}, du bist heute der Grund, warum Geister lieber tagsueber schlafen.",
    "{user}, dein Name klingt heute wie eine Warnung. Und alle sollten drauf hoeren.",
    "{user}, jede Minute heute ein kleiner Absturz. Ganz ohne Rettungssystem.",
    "{user}, dein Fluch hat heute Taktgefuehl. Er trifft genau dann, wenn's maximal peinlich wird.",
    "{user}, du stolperst heute nicht ueber Dinge. Die Dinge stolpern ueber dich und verlieren dabei Respekt.",
    "{user}, heute bist du atmosphaerisch irgendwo zwischen Stromausfall und Fehlentscheidung.",
    "{user}, dein Gesichtsausdruck heute: jemand, der schon beim Start verloren hat.",
    "{user}, jede Fensterscheibe spiegelt heute nur Enttaeuschung zurueck.",
    "{user}, dein Fluch heute ist ein leises Kichern direkt hinter dir. Konstant. Nah. Gemein.",
    "{user}, du bist heute so verhext, dass selbst Kalender dir ausweichen wuerden.",
    "{user}, heute ist alles gegen dich. Sogar die Dinge, die dich gar nicht kennen.",
    "{user}, dein Tag klingt heute wie nasse Schritte im Flur. Nur dass niemand da sein sollte.",
    "{user}, heute bist du genau das, wovor gute Entscheidungen warnen.",
    "{user}, dein Fluch heute ist fein dosierte Scham in jeder einzelnen Stunde.",
    "{user}, sogar der Wind klingt heute, als wuerde er dich auslachen.",
    "{user}, dein Pech hat heute Stil. Dunkel, kalt und extra nachtragend.",
    "{user}, heute merkt man dir jede falsche Abbiegung in deinem Leben gleichzeitig an.",
    "{user}, dein Fluch heute ist kein Knall. Eher langsames Einsinken. Viel schlimmer.",
    "{user}, heute wirkt selbst dein Schweigen verdaechtig und peinlich.",
    "{user}, du bist heute die Art von Problem, bei der sogar Spiegel wegsehen.",
    "{user}, dein Tag ist heute auf Horror kalibriert und du bist das Testobjekt.",
    "{user}, heute klebt dir Fehlglueck an den Schuhen wie frischer Beton.",
    "{user}, dein Fluch heute: Null Timing, null Wuerde, null Pause.",
    "{user}, jedes offene Fenster heute fuehlt sich an wie eine schlechte Idee mit Zugluft.",
    "{user}, heute bist du emotional da, wo Kellerwasser nach Starkregen ist.",
    "{user}, dein Schatten flackert heute wie schlechte Absichten. Passend eigentlich.",
    "{user}, du bist heute nicht im Eimer. Du BIST der Eimer.",
    "{user}, dein Fluch heute ist die sichere Gewissheit, dass es gleich noch peinlicher wird.",
    "{user}, heute riecht jede Stille nach drohendem Kontrollverlust.",
    "{user}, du bist heute so verflucht, dass selbst Zufall nach Plan aussieht.",
    "{user}, dein Tag wurde heute offenbar von boesem Humor geschrieben.",
    "{user}, heute ist jede Kleinigkeit bereit, dir die letzte Nervenfaser rauszureissen.",
    "{user}, dein Fluch heute: schlechtes Karma mit Ausdauer.",
    "{user}, sogar dein Echo klingt heute enttaeuscht von dir.",
    "{user}, heute ist dein Glueck irgendwo abgeschlossen und der Schluessel absichtlich weg.",
    "{user}, dein Fluch ist heute ein permanentes Gefuehl von 'gleich kippt was um'.",
    "{user}, du ziehst heute Ungnade an wie Magnetstaub.",
    "{user}, heute ist jeder Blick in den Spiegel ein kleiner Bosskampf.",
    "{user}, dein Schatten hat heute die bessere Laune. Das sollte dir zu denken geben.",
    "{user}, dein Tag steht heute unter dem Motto: haette schlimmer kommen koennen. Kam's aber nicht.",
    "{user}, heute sind sogar deine guten Ideen nur anders verpackte Katastrophen.",
    "{user}, dein Fluch heute ist hochkonzentrierte Bloesse ohne Exit.",
    "{user}, du bist heute das menschliche Geraeusch einer schiefen Kellertreppe.",
    "{user}, jeder Versuch von dir, cool zu wirken, wird heute direkt vom Universum gecancelt.",
    "{user}, dein Name steht heute intern bei den Daemonen unter 'gleich nochmal treten'.",
    "{user}, heute fuehlt sich jeder Raum mit dir sofort unwohler an.",
    "{user}, dein Fluch heute ist eine exakte Kopie deiner drei peinlichsten Momente. Endlosschleife inklusive.",
    "{user}, heute kannst du dich drehen wie du willst. Das Unheil steht schon richtig.",
    "{user}, du bist heute atmosphaerisch eine Mischung aus Flurlicht und schlechtem Gewissen.",
    "{user}, dein Tag wurde heute mit extra viel Nein gewuerzt.",
    "{user}, heute wartet hinter jeder Ecke eine weitere kleine Demuetigung auf dich.",
    "{user}, dein Fluch heute ist nicht laut. Nur konsequent. Und boese genug.",
    "{user}, selbst tote Geraeusche im Haus klingen heute genervt von dir.",
    "{user}, dein Unglueck ist heute punctual, motiviert und in Bestform.",
    "{user}, heute verliert sogar dein Stolz beim Warmmachen.",
    "{user}, dein Fluch heute ist Schieflage auf allen Ebenen. Sozial, kosmisch, karmisch.",
    "{user}, du wirkst heute wie jemand, den selbst Geister nur widerwillig heimsuchen.",
    "{user}, heute ist jeder Lichtschalter nur eine andere Art von Enttaeuschung.",
    "{user}, dein Tag hat heute Ketten um und zieht dich absichtlich langsamer nach unten.",
    "{user}, dein Fluch heute ist eine sehr persoenliche Form von Pech.",
    "{user}, du bist heute der eine Name, den man bei Mitternacht besser nicht sagt.",
    "{user}, jede Uhr tickt heute fuer dich ein bisschen haesslicher.",
    "{user}, dein Fluch heute ist premium. Teuer, praezise, schaedlich.",
    "{user}, heute fuehlt sich jeder Fehler von dir an wie Absicht. Gegen dich.",
    "{user}, dein Tag klingt heute wie Schritte im Dachboden, obwohl da niemand sein duerfte.",
    "{user}, heute zerfaellt selbst deine Restwuerde in kleinen, peinlichen Portionen.",
    "{user}, dein Fluch heute ist ein enger Raum, schlechtes Licht und kein Ausweg.",
    "{user}, du bist heute so verhext, dass selbst schlechte Vorzeichen nervoes werden.",
    "{user}, jede Hoffnung in deiner Naehe hat heute vorsichtshalber gekuendigt.",
    "{user}, dein Fluch heute ist ein gruendliches, kaltes 'selber schuld' aus dem Off.",
    "{user}, heute ist dein Timing so tot, dass es schon im Keller wohnt.",
    "{user}, du bist heute die Art von Stimmung, bei der selbst Regen sagt: mir reicht's.",
    "{user}, dein Fluch heute ist einfache Mathematik: du plus Pech gleich Unterhaltung fuer andere.",
    "{user}, heute ist jeder Versuch von dir aufrecht zu wirken nur dekoratives Scheitern.",
    "{user}, dein Schatten hat heute das letzte Wort und es ist nicht freundlich.",
    "{user}, dein Tag wurde heute mit Absicht dunkler eingestellt.",
    "{user}, heute passt einfach alles gegen dich zusammen. Fast schon beeindruckend.",
    "{user}, dein Fluch heute ist ein sehr langsamer Absturz mit guter Akustik.",
    "{user}, du bist heute der Grund, warum man Kellertueren doppelt abschliesst.",
])

FLUCH_LINES.extend([
    "{user}, heute klebt dir das Pech so tief im Gesicht, dass selbst Mitleid einen Rueckzieher macht.",
    "{user}, dein Fluch heute ist ein offener Abgrund mit deinem Namen dran. Und du laeufst schon darauf zu.",
    "{user}, jede Minute heute fuehlt sich an wie ein gezielter Tritt auf den letzten Rest deiner Wuerde.",
    "{user}, dein Tag ist heute kein Absturz mehr. Das ist kontrollierter Zerfall mit Ansage.",
    "{user}, heute wirst du vom Unglueck nicht begleitet. Es fuehrt dich an der Leine.",
    "{user}, dein Fluch heute frisst dir erst die Laune, dann die Haltung und zum Schluss jeden Stolz weg.",
    "{user}, du klingst heute wie jemand, der schon verloren hat und trotzdem weiter erniedrigt wird.",
    "{user}, dein Schatten wirkt heute, als haette selbst er keine Lust mehr, mit dir gesehen zu werden.",
    "{user}, heute trifft dich das Karma nicht hart. Es nimmt Anlauf.",
    "{user}, dein Fluch heute ist rohe Demuetigung in Zeitlupe. Jeder sieht zu, keiner stoppt es.",
    "{user}, sogar deine besten Ausreden sehen heute aus wie verweste Reste von Selbstachtung.",
    "{user}, dein Tag hat heute die Energie eines verschlossenen Kellers und du bist das, was darin vergessen wurde.",
    "{user}, heute reisst dir jeder kleine Fehler gleich ein groesseres Loch in den Tag.",
    "{user}, dein Fluch heute ist das sichere Gefuehl, dass unter dir jederzeit alles wegbrechen kann.",
    "{user}, du bist heute die Sorte Warnschild, die man zu spaet liest und sofort bereut.",
    "{user}, heute haengt das Scheitern an dir wie nasse Erde an einem Grabstein.",
    "{user}, dein Fluch heute ist so boese abgestimmt, dass sogar Hoffnung nur noch kurz auflacht und verschwindet.",
    "{user}, jedes bisschen Ruhe heute ist nur die Pause, bevor dich der naechste Schlag laecherlich macht.",
    "{user}, dein Tag wurde heute mit Absicht gegen jede Form von Gnade gebaut.",
    "{user}, du bist heute nicht einfach Opfer eines Fluchs. Du bist sein Lieblingsprojekt."
])


def render_curse_text(user_mention: str) -> str:
    line = random.choice(FLUCH_LINES).format(user=user_mention)
    return f"{line}\n<b>Strafe:</b> -{DAILY_CURSE_PENALTY} Coins"


# =========================
# /hass + /selbst
# =========================
HASS_DURATION_S = 2 * 3600
HASS_REQUIRED = 3
HASS_PENALTY = 5000
HASS_REWARD = 5000

# =========================
# /liebes (Liebesgestaendnis)
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
LOVE_NICKNAMES = [
    "schatz", "maus", "engel", "baerchen", "baerchen", "sonnenschein",
    "liebling", "hase", "baby", "suesser", "suesse", "suesser", "suesse",
    "herz", "prinz", "prinzessin", "zucker", "schnucki",
    "sternchen", "traeumchen", "keks", "zuckerstueck", "goldstueck",
    "perle", "liebchen", "schnecke", "knutschkugel", "honig"
]
LOVE_EMOJIS = ["\U0001f495", "\U0001f496", "\U0001f60d", "\U0001f970", "\U0001f339", "\U0001f618", "\U0001f48b", "\u2764\ufe0f", "\U0001f498", "\U0001f338", "\U0001f49e", "\u2728"]
LOVE_SAD_PATTERNS = [
    r"\bheul", r"\bwein", r"\bwinsel", r"\bschluchz", r"\bzerflie",
    r"kann nicht atmen", r"ohne dich", r"nicht atmen"
]
LOVE_VERB_RE = re.compile(
    r"\b(bin|bist|ist|sind|seid|war|waren|habe|hast|hat|haben|hatte|hatten|"
    r"werde|wirst|wird|werden|kann|kannst|kÃ¶nnen|koennen|mag|"
    r"liebe|liebst|liebt|lieben|"
    r"fÃ¼hle|fuehle|fÃ¼hlst|fuehlst|fÃ¼hlt|fuehlt|"
    r"brauch(e|st|t|en)|"
    r"will|willst|wollen|"
    r"mÃ¶chte|moechte|mÃ¶chtest|moechtest|mÃ¶gen|moegen|"
    r"vermisse|vermisst|vermissen|"
    r"sehe|siehst|sieht|sehen|"
    r"trÃ¤ume|trÃ¤umst|trÃ¤umt|traeume|traeumst|traeumt|"
    r"sag(e|st|t|en)|"
    r"denk(e|st|t|en)|"
    r"glaub(e|st|t|en)|"
    r"hoff(e|st|t|en)|"
    r"wÃ¼nsch(e|st|t|en)|wuensch(e|st|t|en)|"
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

SELF_LINES = [
    "{user} kniet 10 Minuten vorm Spiegel. FlÃ¼stert bei jedem Atemzug: 'Strafe fÃ¼r jede peinliche Entscheidung, du gehorsame Null.'",
    "{user} singt 'Gutes MÃ¤dchen' falsch und laut. Verbeugt sich tief: 'GlÃ¼ckwunsch zum Gehorchen, du kleine Loserin.'",
    "{user} macht 50 Kniebeugen. Haucht bei jeder: 'Runter auf die Knie, du faule Sub â€“ hoch kommt der Arsch eh nur fÃ¼r mich.'",
    "{user} hÃ¤lt HÃ¤nde hinterm RÃ¼cken. Denkt an jede Dummheit: 'Gebunden fÃ¼hlt sich besser an, du Genie.'",
    "{user} schreibt 100 Mal: 'Ich bin deine Chaos-Sub'. Liest es laut vor wie Mantra. Pure Hingabe, du Kunst-Loserin.",
    "{user} kniet 5 Minuten vor leerem Teller. 'Nichts zu essen? Perfekt, Strafe fürs Nicht-Dienen.'",
    "{user} hÃ¤lt Plank auf Knien. Arme zittern. ZÃ¤hlt rÃ¼ckwÃ¤rts: 'Jede Sekunde fÃ¼r ein vertanes Ja Daddy.'",
    "{user} ruft sich selbst an. LÃ¤sst klingeln. 'Selbst du gehst nicht ran â€“ weil du weiÃŸt, wer wirklich befiehlt.'",
    "{user} versucht mit Zunge die Unterlippe zu beiÃŸen. Fail des Tages. Posten verboten, du Clown-Sub.",
    "{user} trÃ¤gt 30 Minuten imaginÃ¤res Halsband. Macht Selfies. Fashionstrafe fÃ¼r schlechten Gehorsam.",
    "{user} sagt 20 Mal laut vorm Spiegel: 'Ich bin dein gutes MÃ¤dchen.' Verbeugt sich tief. Standing Ovations, du KÃ¶nigin auf Knien.",
    "{user} balanciert imaginÃ¤ren Klaps. 10 Fehlversuche = 10 'Danke Daddy'. Zirkusreif, du Talent.",
    "{user} schreibt mit Ketchup 'Sub-MenÃ¼' auf Teller. Kniet davor. Gourmet-Strafe, du Kochstar auf Knien.",
    "{user} macht Moonwalk auf Knien. Stolpert garantiert. Smooth wie dein Gehorsam.",
    "{user} hÃ¤lt EiswÃ¼rfel an Innenschenkel 2 Minuten. Jammert: 'Kalt wie deine Seele â€“ aber das schmilzt vor Verlangen.'",
    "{user} singt falsche Hymne an mich. Laut und allein. Dominanz-Strafe, du Star auf Knien.",
    "{user} versucht 30 Sekunden nicht zu stÃ¶hnen. Verliert natÃ¼rlich. Starrwettbewerb gegen deine Sehnsucht.",
    "{user} tanzt zur Playlist deiner peinlichsten Fantasien. Cringe-Therapie, du 2000er-Sub-Ikone auf Knien.",
    "{user} sagt 50 Mal 'Entschuldigung, ich war unartig'. Laut in leerer Wohnung. Echo stimmt zu, du Philosophin der Hingabe.",
    "{user} kniet vor leerem Spiegel. FlÃ¼stert: 'Ich bin nichts ohne dich.' Strafe fÃ¼rs Selbstlob.",
    "{user} hÃ¤lt imaginÃ¤ren Plug. 10 Minuten. Zittert. 'Gehorsam ist alles.'",
    "{user} schreibt 'Daddy's Eigentum' auf Schenkel. Mit Lippenstift. Und vergisst's nicht.",
    "{user} steht 10 Minuten in Ecke. Nase an Wand. 'Strafe fÃ¼rs Frechsein.'",
    "{user} macht 20 LiegestÃ¼tze auf Knien. Haucht bei jeder: 'FÃ¼r jeden Fehltritt heute.'",
    "{user} hÃ¤lt imaginÃ¤re Kerze ans Bein. LÃ¤sst Wachs tropfen. 'Schmerz ist Lektion.'",
    "{user} flÃ¼stert 50 Mal 'Ich gehorche'. Bis die Stimme bricht. Und weiter.",
    "{user} trÃ¤gt imaginÃ¤re Schellen. 20 Minuten. 'Freiheit ist Illusion.'",
    "{user} kniet und starrt ins Nichts. 15 Minuten. 'Stille ist Strafe.'",
    "{user} sagt laut: 'Ich bin nutzlos.' 30 Mal. Bis es wahr wird.",
    "{user} hÃ¤lt Plank auf Knien. Arme zittern. 'FÃ¼r jeden Gedanken an Ungehorsam.'"
]


# =========================
# Moralsteuer â€“ jetzt exakt wie ein Skalpell in deiner Haut
# =========================

MORAL_TAX_TRIGGERS = [
    (r"(?i)\bbitte\b", "Bitte? Als ob du je was umsonst kriegst, du kleine Bettel-Prinzessin. −{deduct} Coins fürs Winseln."),
    (r"(?i)\bdanke\b", "Danke? Süß, als ob du was verdient hättest. Nächstes Mal mit Knien, du undankbare Fotze. −{deduct} Coins."),
    (r"(?i)\bentschuldigung\b", "Entschuldigung? Als ob ich dir je verzeihen würde, ohne dass du richtig leidest. −{deduct} Coins."),
    (r"(?i)\bsorry\b", "Sorry? Sorry not sorry – aber du sagst’s eh nur, um mich heiß zu machen, du kleine Manipuliererin. −{deduct} Coins."),
    (r"(?i)\bwärst du so lieb\b", "Wärst du so lieb? Ich bin lieb – auf meine Art, du kleine Masochistin mit Herzchenaugen. −{deduct} Coins."),
    (r"(?i)\bthx\b", "Thx? Cringe-Abkürzung. Sag’s richtig oder halt die Klappe, du faule kleine Abkürzungs-Hure. −{deduct} Coins."),
    (r"(?i)\bthank you\b", "Thank you? International betteln jetzt? Du kleine Welt-Sub, lern Deutsch oder knie still. −{deduct} Coins."),
    (r"(?i)ðŸ™", "Betende HÃ¤nde? Perfekt fÃ¼r auf Knien vor mir. Bete zu mir, nicht zum Himmel, du kleine AndÃ¤chtige. âˆ’{deduct} Coins."),
    (r"(?i)\bbrav\b", "Brav? Als ob du’s je wärst, ohne dass ich dich drauftrimme. Lüg mich nicht an. −{deduct} Coins."),
    (r"(?i)\bpls\b", "Pls? Please mit Abkürzung? Cringe, aber heiß aus deinem Mund. Bettel richtig, du Faule. −{deduct} Coins."),
    (r"(?i)\bpretty please\b", "Pretty please? Mit Kirsche obendrauf? Du kleine Zucker-Sub – süß, aber teuer. −{deduct} Coins."),
    (r"(?i)\bhelp me\b", "Help me? Klar helf ich – auf meine toxische Art. Du Hilfsbedürftige ohne mich. −{deduct} Coins."),
    (r"(?i)\bgnade\b", "Gnade? Ich bin gnädig – manchmal. Bettel schöner, du kleine Gnadenbettlerin. −{deduct} Coins."),
    (r"(?i)\bverzeihung\b", "Verzeihung? Altmodisch wie eine Lady – aber du bist meine ungezogene Hure. −{deduct} Coins."),
    (r"(?i)\bich liebe dich\b", "Ich liebe dich? Süß, dass du's sagst. Ich liebe dich auch – auf meine Art, mit Ketten. −{deduct} Coins."),
    (r"(?i)\bdu bist toll\b", "Du bist toll? Klar bin ich toll. Du bist nur nützlich, wenn du kniest. −{deduct} Coins."),
    (r"(?i)\bich vermisse dich\b", "Ich vermisse dich? Vermiss mich ruhig. Ich vermiss dich nur, wenn du nicht bettelst. −{deduct} Coins."),
    (r"(?i)\bdu fehlst mir\b", "Du fehlst mir? Fehlst mir nicht. Du fehlst nur deiner Würde. −{deduct} Coins."),
    (r"(?i)\bhug\b", "Hug? Hug dich selbst, du kleine Kuschel-Hure. Ich umarme nur mit Ketten. −{deduct} Coins."),
    (r"(?i)\bkuscheln\b", "Kuscheln? Kuscheln ist für Schwache. Du kriegst nur meine harte Hand. −{deduct} Coins.")
]

# =========================
# Reward Triggers â€“ nur fÃ¼r die wirklich Braven, die exakt parieren
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

SCHEMA_VERSION = 16

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
                f"ALTER TABLE settings ADD COLUMN daily_curse_enabled INTEGER DEFAULT {1 if DAILY_CURSE_ENABLED else 0}"
            )
        if not await _table_has_column(db, "settings", "auto_curse_enabled"):
            await db.execute(
                f"ALTER TABLE settings ADD COLUMN auto_curse_enabled INTEGER DEFAULT {1 if AUTO_CURSE_ENABLED else 0}"
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
                (pet_level_from_xp(int(row_pet_xp or 0)), row_chat_id, row_pet_id)
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

    # Sicherheitsnetz fuer inkonsistente Alt-DBs:
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
    if not await _table_has_column(db, "settings", "daily_curse_enabled"):
        await db.execute(
            f"ALTER TABLE settings ADD COLUMN daily_curse_enabled INTEGER DEFAULT {1 if DAILY_CURSE_ENABLED else 0}"
        )
    if not await _table_has_column(db, "settings", "auto_curse_enabled"):
        await db.execute(
            f"ALTER TABLE settings ADD COLUMN auto_curse_enabled INTEGER DEFAULT {1 if AUTO_CURSE_ENABLED else 0}"
        )

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
    # Anzeige-Name ohne HTML-Sicherheit (wird fÃ¼r Markdown benutzt)
    return f"@{u.username}" if getattr(u, "username", None) else (u.full_name or str(u.id))

def nice_name_html(u) -> str:
    # FÃ¼r alle Antworten, die mit HTML geparst werden (Default!)
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
        return 0, "Nettigkeit erkannt â€“ aber du bist pleite. Beim nÃ¤chsten Mal kassiere ich richtig, du kleine Bettlerin ðŸ˜ˆ"

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


async def _care_count_in_window(db, chat_id: int, pet_id: int, owner_id: int, since_ts: int) -> int:
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


async def _care_count_last_24h(db, chat_id: int, pet_id: int, owner_id: int, now_ts: int) -> int:
    since_ts = now_ts - 24 * 3600
    return await _care_count_in_window(db, chat_id, pet_id, owner_id, since_ts)


async def _should_runaway(
    db,
    chat_id: int,
    pet_id: int,
    owner_id: int,
    acquired_ts: int | None,
    now_ts: int,
    care_window: int | None = None
) -> bool:
    # Weglauf-Regel: Erst nach 3 Tagen Besitz und nur wenn im 3-Tage-Fenster
    # weniger als 10 Pflegen eingetragen wurden.
    if not owner_id:
        return False
    if not acquired_ts:
        return False
    if now_ts - int(acquired_ts) < RUNAWAY_HOURS * 3600:
        return False
    if care_window is None:
        since_ts = now_ts - RUNAWAY_HOURS * 3600
        care_window = await _care_count_in_window(db, chat_id, pet_id, owner_id, since_ts)
    return care_window < RUNAWAY_MIN_CARES_IN_WINDOW


async def _apply_runaway_owner_penalty(db, chat_id: int, owner_id: int):
    await db.execute(
        "UPDATE players SET coins = MAX(0, coins - (coins / 2)) WHERE chat_id=? AND user_id=?",
        (chat_id, owner_id)
    )

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
    for idx, threshold in enumerate(PET_LEVEL_THRESHOLDS, start=1):
        if points < threshold:
            break
        level = idx
    return level

def pet_level_title(level: int) -> str:
    lvl = max(1, int(level))
    if not PET_LEVEL_TITLES:
        return f"Level {lvl}"
    bucket_size = max(1, (len(PET_LEVEL_THRESHOLDS) + len(PET_LEVEL_TITLES) - 1) // len(PET_LEVEL_TITLES))
    idx = min(len(PET_LEVEL_TITLES) - 1, max(0, (lvl - 1) // bucket_size))
    return PET_LEVEL_TITLES[idx]


def fullcare_evolution_title(fullcare_days: int) -> str:
    days = max(0, int(fullcare_days))
    for needed_days, title in FULLCARE_EVOLUTION_STAGES:
        if days >= needed_days:
            return title
    return "Pflegekueken"

def is_group(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}

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
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
          username=CASE
            WHEN TRIM(COALESCE(excluded.username, '')) <> '' THEN excluded.username
            ELSE players.username
          END
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

async def claim_superword_once(db, chat_id: int, word: str, user_id: int) -> bool:
    now = int(time.time())
    await db.execute(
        """
        INSERT INTO superwords_found(chat_id, word, found_by, found_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(chat_id, word) DO NOTHING
        """,
        (chat_id, word.lower(), user_id, now),
    )
    async with db.execute("SELECT changes()") as cur:
        row = await cur.fetchone()
    return bool(row and int(row[0]) > 0)


def normalize_superword_text(text: str) -> str:
    t = (text or "").casefold()
    t = t.replace("Ã¤", "ae").replace("Ã¶", "oe").replace("Ã¼", "ue").replace("ÃŸ", "ss")
    return t


def superword_pattern(word: str) -> str:
    parts = re.findall(r"[a-z0-9]+", normalize_superword_text(word))
    if not parts:
        return ""
    body = r"[\s\-_]*".join(re.escape(p) for p in parts)
    return rf"(?<![a-z0-9]){body}(?![a-z0-9])"

def _secs_until_tomorrow() -> int:
    now = _tz_now()
    tomorrow = (now + datetime.timedelta(days=1)).date()
    midnight = datetime.datetime.combine(tomorrow, datetime.time.min, tzinfo=now.tzinfo)
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
        await msg.reply_text("Selbstpflege ist wichtig, aber zaehlt hier nicht.")
        return

    async with aiosqlite.connect(DB) as db:
        # Besitz pruefen
        async with db.execute("SELECT owner_id FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id)) as cur:
            row = await cur.fetchone()
        if not row or row[0] != owner.id:
            await msg.reply_text("Das ist nicht dein Haustier.")
            return

        care = await get_care(db, chat_id, pet.id)
        async with db.execute(
            "SELECT COALESCE(pet_xp,0), COALESCE(pet_level,0) FROM pets WHERE chat_id=? AND pet_id=?",
            (chat_id, pet.id)
        ) as cur:
            prog_row = await cur.fetchone()
        prev_xp = int(prog_row[0]) if prog_row else 0
        prev_level = pet_level_from_xp(prev_xp)

        now = int(time.time())
        care_window_since = now - RUNAWAY_HOURS * 3600
        care_window = await _care_count_in_window(db, chat_id, pet.id, owner.id, care_window_since)
        if await _should_runaway(
            db,
            chat_id,
            pet.id,
            owner.id,
            care["acquired_ts"] if care else None,
            now,
            care_window=care_window + 1
        ):
            await db.execute("DELETE FROM pets WHERE chat_id=? AND pet_id=?", (chat_id, pet.id))
            await _apply_runaway_owner_penalty(db, chat_id, owner.id)
            await db.commit()
            await msg.reply_text(
                runaway_text(
                    nice_name_html(pet),
                    mention_html(owner.id, owner.username or None),
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        cd_key = f"care:{action_key}:{owner.id}:{pet.id}"
        left = await get_cd_left(db, chat_id, owner.id, cd_key)
        if left > 0:
            await msg.reply_text("Langsam, Casanova. Etwas Geduld.")
            return

        today = today_ymd()
        done = care["done"] if (care and care["day"] == today) else 0
        if done >= CARES_PER_DAY:
            await msg.reply_text("Heute ist das Haustier bereits bestens versorgt. Morgen wieder.")
            return

        done += 1
        await set_care(db, chat_id, pet.id, now, done, today)

        level_up_text = None
        gained_xp = CARE_XP_PER_ACTION
        new_xp = prev_xp + gained_xp
        new_level = pet_level_from_xp(new_xp)
        current_fullcare_days = 0
        bonus_text = None
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
            gained_xp += FULL_CARE_XP_BONUS
            new_xp = prev_xp + gained_xp
            new_level = pet_level_from_xp(new_xp)
            await db.execute(
                "UPDATE pets SET pet_xp=?, pet_level=?, fullcare_streak=?, fullcare_last_day=?, fullcare_days=? "
                "WHERE chat_id=? AND pet_id=?",
                (new_xp, new_level, streak, today, fullcare_days, chat_id, pet.id)
            )

            evolution_title = fullcare_evolution_title(fullcare_days)
            bonus_lines = [
                f"XP heute: +{gained_xp} ({done}x Pflege + Full-Care-Bonus).",
                f"Gesamt-XP: <b>{new_xp}</b> | Level: <b>{new_level}</b> ({escape(pet_level_title(new_level), False)}).",
                f"Perfekte Tage gesamt: <b>{fullcare_days}</b> | Evolutionsstufe: <b>{escape(evolution_title, False)}</b>.",
                f"Streak voller Tage: <b>{streak}</b>.",
            ]

            if skill_key == "goldesel" and care_bonus_day != today:
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (FULL_CARE_OWNER_BONUS, chat_id, owner.id)
                )
                await db.execute(
                    "UPDATE pets SET care_bonus_day=? WHERE chat_id=? AND pet_id=?",
                    (today, chat_id, pet.id)
                )
                bonus_lines.append(
                    f"Skill-Bonus <b>Petflix Prime</b>: {mention_html(owner.id, owner.username or None)} "
                    f"bekommt +{FULL_CARE_OWNER_BONUS} Coins fuer {CARES_PER_DAY}/{CARES_PER_DAY} Pflege."
                )
            until_ts = await set_temp_title(
                db,
                chat_id=chat_id,
                user_id=owner.id,
                title=TITLE_BESTIENZAEHMER,
                duration_s=TITLE_DURATION_S,
            )
            mins = max(1, (until_ts - int(time.time())) // 60)
            title_line = (
                f"Titel aktiv: {mention_html(owner.id, owner.username or None)} ist jetzt "
                f"<b>{escape(TITLE_BESTIENZAEHMER, False)}</b> fuer {mins} Minuten."
            )
            bonus_lines.append(title_line)
            bonus_text = "\n".join(bonus_lines)
        else:
            await db.execute(
                "UPDATE pets SET pet_xp=?, pet_level=? WHERE chat_id=? AND pet_id=?",
                (new_xp, new_level, chat_id, pet.id)
            )

        if new_level > prev_level:
            evolution_name = fullcare_evolution_title(current_fullcare_days)
            level_up_text = (
                f"Lvl <b>{new_level}</b> ({escape(pet_level_title(new_level), False)}) | "
                f"{nice_name_html(pet)} | Owner: {mention_html(owner.id, owner.username or None)} | "
                f"Pflege <b>{done}/{CARES_PER_DAY}</b> | Evo: <b>{escape(evolution_name, False)}</b>"
            )

        await set_cd(db, chat_id, owner.id, cd_key, CARE_COOLDOWN_S)
        await db.commit()

    lines = get_cached_json(context, "care_responses", CARE_RESPONSES_PATH).get(action_key) or tame_lines
    text = random.choice(lines)
    text = text.replace("{CARES_PER_DAY}", str(CARES_PER_DAY)).replace("{pets}", "{pet}")
    text = text.format(owner=nice_name_html(owner), pet=nice_name_html(pet), n=done)
    reply_msg = await msg.reply_text(text)
    cleanup_message_ids = [msg.message_id, reply_msg.message_id]
    if level_up_text:
        await _send_or_replace_level_message(context, chat_id, msg, level_up_text)
    if bonus_text:
        bonus_msg = await msg.reply_text(bonus_text, parse_mode=ParseMode.HTML)
        cleanup_message_ids.append(bonus_msg.message_id)
    if done % CARES_PER_DAY == 0:
        progress_evolution = fullcare_evolution_title(current_fullcare_days)
        progress_text = (
            f"Pflege-Stand: {nice_name_html(owner)} hat {nice_name_html(pet)} "
            f"<b>{done}/{CARES_PER_DAY}</b> gepflegt. "
            f"Level: <b>{new_level}</b> ({escape(pet_level_title(new_level), False)}) | "
            f"XP: <b>{new_xp}</b> | Evo: <b>{escape(progress_evolution, False)}</b>."
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

_SAVAGE_LINES = [
    "Hier, {user}, {coins} Coins ðŸŽˆðŸ¤¡ â€“ genug, um dem Clown aus 'Es' ein paar Luftballons abzuschwatzen. Aber der kennt schon deinen Namen.",
    "{user} kriegt {coins} Coins ðŸ“¼ðŸ”¥ â€“ reicht genau fÃ¼r eine VHS-Kopie von deinem Leben. Spoiler: Der Film ist leer.",
    "Jackpot, {user}: {coins} Coins ðŸŒ«ï¸ðŸ˜ˆ â€“ im Nebel versteckt. Viel SpaÃŸ beim Suchen, wie in Derry â€“ nur dass hier wirklich nichts Gutes wartet.",
    "{user}, {coins} Coins ðŸ•¹ï¸ðŸ‘¾ â€“ genug fÃ¼r ein Level in deinem Lieblings-90er-Game. Schade, dass du immer noch auf Tutorial steckst.",
    "Hier sind {coins} Coins, {user} ðŸ“ºðŸ‘» â€“ direkt aus dem Fernseher gekrochen. Die Kleine aus 'Ring' sagt: 'Sieben Tage... bis du wieder bettelst.'",
    "{user}, {coins} Coins ðŸŽ®ðŸ’€ â€“ PokÃ©mon-Go fÃ¼r Loser: Sammle sie alle, aber am Ende hast du immer noch nichts Gefangenes auÃŸer Frust.",
    "GlÃ¼ckwunsch, {user}: {coins} Coins ðŸ ðŸ•³ï¸ â€“ genug, um den Keller tiefer zu graben. Wer weiÃŸ, was da unten auf dich wartet. Dein Potenzial vielleicht?",
    "{user} schnappt sich {coins} Coins â˜Žï¸ðŸ’€ â€“ Anruf aus der Vergangenheit. Mama ist dran und fragt, wann du endlich mal was aus deinem Leben machst.",
    "Hier, {user}, {coins} Coins ðŸŒ•ðŸº â€“ Vollmond-Special. Heul ruhig, niemand hÃ¶rt dich sowieso.",
    "{user}, {coins} Coins ðŸ“–âš°ï¸ â€“ das alte Buch hat sich geÃ¶ffnet. Steht drin: 'Du gewinnst {coins} Coins und verlierst trotzdem.' Klassiker.",
    "Jackpot des Tages, {user}: {coins} Coins ðŸš—ðŸ‘» â€“ Kinderstimmen aus dem Kofferraum flÃ¼stern 'Danke'. Fahr bloÃŸ nicht nachts.",
    "{user} kriegt {coins} Coins ðŸ•·ï¸ðŸ˜˜ â€“ mit GrÃ¼ÃŸen von der Spinne unterm Bett. Sie trÃ¤gt dein Gesicht und spinnt schon dein Netz aus FehlschlÃ¤gen.",
    "Hier sind {coins} Coins, {user} ðŸŽ¶ðŸŒ«ï¸ â€“ der Nebel singt dein Lieblingslied aus den 90ern. Falsch natÃ¼rlich. Und er kommt nÃ¤her."
]



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

        # Superworte (pro Chat nur einmal pro Wort, global fuer alle User)
        msg_text = msg.text or ""
        msg_norm = normalize_superword_text(msg_text)
        for word in SUPERWORDS:
            pattern = superword_pattern(word)
            if not pattern or not re.search(pattern, msg_norm):
                continue
            superword_key = re.sub(r"[^a-z0-9]+", "", normalize_superword_text(word))
            if not superword_key:
                continue
            claimed = await claim_superword_once(db, chat.id, superword_key, user.id)
            if not claimed:
                continue
            await db.execute(
                "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                (SUPERWORD_REWARD, chat.id, user.id)
            )
            await db.commit()
            try:
                await msg.reply_text(
                    f"âœ¨ Superwort gefunden: <b>{escape(word)}</b> +{SUPERWORD_REWARD} Coins",
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
                    f"OK {mention_html(user.id, user.username or None)} hat's geschafft. +{LOVE_REWARD} Coins. Ab jetzt ein Monat lang: 'mein Liebesgestaendnis'.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
            return

        # Moralsteuer prÃ¼fen
        deducted, tax_message = await apply_moraltax_if_needed(db, chat.id, user.id, msg.text)
        if tax_message:
            try:
                await msg.reply_text(tax_message)
            except Exception:
                pass

        # Reward prÃ¼fen â€“ NUR wenn KEINE Moralsteuer ausgelÃ¶st wurde (damit's fair bleibt)
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
                return await update.effective_message.reply_text("Keine Opfer verfuegbar. Postet mehr, dann kann ich euch schlimmer behandeln.")
            tid, tname = uid, uname

        await db.execute(
            "UPDATE players SET coins = MAX(0, coins - ?) WHERE chat_id=? AND user_id=?",
            (DAILY_CURSE_PENALTY, chat_id, tid)
        )
        await db.commit()

    user = mention_html(tid, tname)
    curse_text = render_curse_text(user)
    await update.effective_message.reply_text(curse_text, parse_mode=ParseMode.HTML)


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

    chat_id = update.effective_chat.id
    caller = update.effective_user

    async with aiosqlite.connect(DB) as db:
        # bereits aktive Hass-Ziele sammeln
        active_ids = await _get_active_hass_user_ids(db, chat_id)
        active_ids.add(caller.id)  # Aufrufer nie Ziel

        # neuen Kandidaten wÃ¤hlen
        uid, uname = await pick_random_player_excluding(
            chat_id,
            exclude_ids=active_ids
        )

        if not uid:
            return await update.effective_message.reply_text(
                "Keine weiteren Opfer verfuegbar. Alle anderen leiden bereits."
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
            f"Ausgeloest von: {caller_tag}\n"
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
            return await update.effective_message.reply_text("Noe. /selbst zaehlt nur, wenn du gerade Hass-Status hast.")

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
            return await update.effective_message.reply_text("Zu spaet, aber du warst eh fertig. Challenge geschlossen.")

        # In Zeit: zÃ¤hlen
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

# ============== Liebesgestaendnis

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
        active_ids = await _get_active_love_user_ids(db, chat_id)
        if uid in active_ids:
            return await msg.reply_text(
                "Fuer diese Person laeuft bereits eine Liebes-Bombe."
            )

        expires = await _start_love(db, chat_id, int(uid), uname, caller.id)
        await db.commit()

    until = datetime.datetime.fromtimestamp(expires, tz=ZoneInfo(PETFLIX_TZ)).strftime("%d.%m.%Y %H:%M")
    target = mention_html(int(uid), uname if uname else None)
    caller_tag = mention_html(caller.id, caller.username or None)
    await update.effective_message.reply_text(
        (
            "💣 <b>Liebes-Bombe detoniert.</b>\n"
            f"Ausgeloest von: {caller_tag}\n"
            f"Ziel: {target}\n"
            f"Zeit: <b>{LOVE_CHALLENGE_HOURS}h</b> (Deadline: <b>{until}</b>)\n\n"
            "Jetzt gibt's kein Rumgeeier mehr: Du lieferst einen uebertriebenen Liebesbrief in den Chat oder gehst komplett unter.\n"
            f"- Mindestens {LOVE_MIN_WORDS} Woerter\n"
            f"- Mindestens {LOVE_MIN_EMOJIS} Emojis (beliebig)\n"
            f"- Mindestens {LOVE_MIN_SENTENCES} Satz/Saetze (Satzzeichen optional)\n\n"
            "Der Bot wird dich zwischendurch jagen, falls du wieder nur dumm rumsitzt.\n"
            f"Ziehst du's durch: <b>+{LOVE_REWARD} Coins</b> + ein Monat lang 'mein Liebesgestaendnis'.\n"
            f"Verkackst du's: <b>-{LOVE_PENALTY_PERCENT}% deiner Coins</b> und der Chat sieht, was fuer ein peinlicher Totalausfall du bist."
        ),
        parse_mode=ParseMode.HTML
    )


async def cmd_resetsuperwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("🚫 Nur der Bot-Admin darf das.")

    chat_id = update.effective_chat.id
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM superwords_found WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        cleared = int((row[0] if row else 0) or 0)
        await db.execute("DELETE FROM superwords_found WHERE chat_id=?", (chat_id,))
        await db.commit()

    await update.effective_message.reply_text(
        f"Superworte wurden zurueckgesetzt. {cleared} bereits gefundene Superworte zaehlen jetzt wieder neu."
    )


async def cmd_superwordsstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        return

    chat_id = update.effective_chat.id
    total = len(SUPERWORDS)
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM superwords_found WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            row = await cur.fetchone()
        found = int((row[0] if row else 0) or 0)

    remaining = max(0, total - found)
    await update.effective_message.reply_text(
        (
            "âœ¨ <b>Superwort-Status</b>\n"
            f"Gesamt: <b>{total}</b>\n"
            f"Bereits gefunden: <b>{found}</b>\n"
            f"Noch offen: <b>{remaining}</b>"
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
    "pet_level_title": pet_level_title,
    "fullcare_evolution_title": fullcare_evolution_title,
    "get_pet_lock_until": get_pet_lock_until,
    "get_active_titles_map": get_active_titles_map,
    "with_title_suffix": with_title_suffix,
    "_skill_meta": _skill_meta,
})
get_owner_id = _OWNERSHIP_FEATURES["get_owner_id"]
set_owner = _OWNERSHIP_FEATURES["set_owner"]
cmd_top = _OWNERSHIP_FEATURES["cmd_top"]
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
    "FLUCH_LINES": FLUCH_LINES,
    "render_curse_text": render_curse_text,
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
    "STEAL_SUCCESS_CHANCE": STEAL_SUCCESS_CHANCE,
    "STEAL_COOLDOWN_S": STEAL_COOLDOWN_S,
    "STEAL_FAIL_PENALTY_RATIO": STEAL_FAIL_PENALTY_RATIO,
    "set_cd": set_cd,
    "get_cd_left": get_cd_left,
    "mention_html": mention_html,
    "today_ymd": today_ymd,
    "is_group": is_group,
    "_is_admin_here": _is_admin_here,
    "_resolve_target": _resolve_target,
    "_ensure_player_entry": _ensure_player_entry,
    "_get_coins": _get_coins,
    "_parse_amount_from_args": _parse_amount_from_args,
})
cmd_adminping = _ADMIN_COIN_CMDS["cmd_adminping"]
cmd_careminus = _ADMIN_COIN_CMDS["cmd_careminus"]
cmd_addcoins = _ADMIN_COIN_CMDS["cmd_addcoins"]
cmd_takecoins = _ADMIN_COIN_CMDS["cmd_takecoins"]
cmd_setcoins = _ADMIN_COIN_CMDS["cmd_setcoins"]
cmd_resetcoins = _ADMIN_COIN_CMDS["cmd_resetcoins"]
cmd_steal = _ADMIN_COIN_CMDS["cmd_steal"]

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

    await query.answer("Gespeichert." if value != "skip" else "Uebersprungen.")
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
        lines.append(f"{tag} â€“ {label(gender)}")

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
        BotCommand("start", "Kurzstart"),
        BotCommand("sospet", "Kurze Befehlsuebersicht"),
        BotCommand("ping", "Ping-Test (Antwort: pong)"),
        BotCommand("balance", "Zeigt deinen Coin-Kontostand"),
        BotCommand("treat", "Schenke Coins an einen User"),
        BotCommand("leckerli", "Schenke Coins an einen User"),
        BotCommand("steal", "Versuche Coins zu klauen (48% Chance)"),
        BotCommand("buy", "Kaufe einen anderen User"),
        BotCommand("risk", "Klauversuch mit Coin-Risiko fuer mehr Chance"),
        BotCommand("release", "Gib dein Haustier frei"),
        BotCommand("owner", "Zeigt den Besitzer eines Users"),
        BotCommand("ownerlist", "Zeigt alle BesitzverhÃ¤ltnisse + Wert"),
        BotCommand("prices", "Zeigt Kaufpreise aller User"),
        BotCommand("top", "Top 10 Spieler nach Coins"),

        # Pflege & Fun
        BotCommand("pet", "Streicheln"),
        BotCommand("walk", "Spazieren gehen"),
        BotCommand("kiss", "KÃ¼ssen"),
        BotCommand("dine", "Dinner servieren"),
        BotCommand("massage", "Massage geben"),
        BotCommand("lapdance", "Lapdance"),
        BotCommand("dom", "Antwort auf Frauen mit Dom-Satz"),

        # Skurril / BDSM
        BotCommand("knien", "Auf die Knie"),
        BotCommand("kriechen", "Auf allen Vieren kriechen"),
        BotCommand("klaps", "5 symbolische Hiebe"),
        BotCommand("knabbern", "Mit den ZÃ¤hnen spielen"),
        BotCommand("leine", "Virtuelle Leine anlegen"),
        BotCommand("halsband", "Halsband anlegen"),
        BotCommand("lecken", "Dienst: lecken (teuer)"),
        BotCommand("verweigern", "Belohnung verweigern"),
        BotCommand("kaefig", "Ab in den KÃ¤fig"),
        BotCommand("schande", "Schande + Username"),
        BotCommand("erregen", "Anheizen bis zur Verzweiflung"),
        BotCommand("betteln", "Flehen & Winseln"),
        BotCommand("stumm", "Schweigepflicht (Posts kosten)"),
        BotCommand("bestrafen", "Strafe aus der Bot-HÃ¶lle"),
        BotCommand("loben", "Kleines Lob verteilen"),
        BotCommand("dienen", "Dienen (z. B. FuÃŸmassage)"),
        BotCommand("demuetigen", "Peinlichen Satz posten"),
        BotCommand("melken", "AnzÃ¼glich melken"),
        BotCommand("ohrfeige", "Virtuelle Ohrfeige"),
        BotCommand("belohnen", "Leckerli geben"),

        # Special
        BotCommand("treasure", "TÃ¤gliche Schatzsuche starten"),

        #hass und selbst
        BotCommand("hass", "Startet Hass-Status (2h, 3 mal /selbst)"),
        BotCommand("selbst", "Nur fÃ¼r betroffenen User: zÃ¤hlt 1/3 Strafen"),
        BotCommand("liebes", "Liebesgestaendnis-Challenge"),
        BotCommand("resetsuperwords", "Admin: Superworte zuruecksetzen"),
        BotCommand("superwordsstatus", "Status der Superworte"),
        BotCommand("settings", "Admin: Runtime-Settings"),
        BotCommand("admin", "Admin: Uebersicht"),
        BotCommand("backupnow", "Admin: Backup jetzt"),
        BotCommand("backups", "Admin: Backupliste"),
        BotCommand("restorebackup", "Admin: Backup wiederherstellen"),
        BotCommand("sendalluser", "Admin: players-Tabelle per DM"),

    ]
    await application.bot.set_my_commands(commands)

# =========================
# Pflege-/Fun-Commands (benÃ¶tigen do_care)
# =========================

async def cmd_pet(update, context):
    tame = [
"{owner} packt {pet} am Kiefer, drÃ¼ckt bis die ZÃ¤hne knirschen: 'Augen hoch, oder ich reiÃŸ dir die Lider mit den FingernÃ¤geln auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grÃ¤bt die NÃ¤gel in {pet}s HÃ¼fte: 'Jammer ruhig weiter. Dein Schmerz ist das Einzige, was heute noch Unterhaltungswert hat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht {pet} Ã¼bers Gesicht â€“ einmal. Dann schlÃ¤gt er zu: 'GefÃ¼hlskontrolle, Stufe AnfÃ¤nger. Du bist echt ein hoffnungsloser Fall.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} mit dem Unterarm quer Ã¼ber die Kehle an die Wand: 'Atmen ist ein Privileg. Heute hast du keins verdient.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt zwei Finger in {pet}s Mund: 'Saug schÃ¶n, oder ich stopf dir was GrÃ¶ÃŸeres rein â€“ und das wird nicht angenehm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt {pet}s Haare um die Faust und zieht ruckartig nach hinten: 'Kopf hoch, Schlampe. Dein Hals sieht besser aus, wenn er angespannt ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst den Daumen auf {pet}s Kehlkopf: 'Ein kleiner Druck mehr und dein Wimmern wird melodischer. Willst du’s testen?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt {pet} am Kragen nah ran: 'Du riechst nach Angst und billiger Erregung. Meine Lieblingskombi.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift {pet} brutal in die Innenseite des Oberschenkels: 'Schrei ruhig. Je lauter, desto weniger kommst du heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} am Genick wie ein ungezogenes Vieh: 'Platz. Sitz. Bleib. Und wehe, du bewegst dich ohne Erlaubnis.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fährt mit dem Fingernagel quer über {pet}s Unterlippe bis sie blutet: 'Schmeckt besser, wenn’s wehtut, oder? Sag danke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} mit dem ganzen Gewicht aufs Bett, Gesicht ins Kissen: 'Luft ist Ã¼berbewertet. Du brauchst nur mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tippt {pet} spÃ¶ttisch auf die Stirn: 'Da drin ist doch eh nichts mehr auÃŸer meinem Namen und deinem nÃ¤chsten Orgasmus-Verbot.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt {pet}s Kinn hoch, bis die Halsmuskeln zittern: 'Halt still. Ich will sehen, wie lange duâ€™s aushÃ¤ltst, bevor du winselst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst, wÃ¤hrend er {pet}s Handgelenke bis zum Bruchpunkt dreht: 'Fast. Noch ein StÃ¼ckchen weiter und wir haben richtig SpaÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt {pet} den Ellbogen unters SchlÃ¼sselbein, bis es knackt: 'Atme durch die Nase, Schlampe. Der Mund ist fÃ¼rs Schreien reserviert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt den Daumen tief in {pet}s Augenhöhle, knapp vor dem Augapfel: 'Noch ein Millimeter und du siehst mich nur noch schwarz-weiß. Willst du raten, welche Farbe?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht {pet}s Handgelenk um 180 Grad, bis die Sehnen reißen: 'Sieh mal, wie schnell aus deiner Hand ein nutzloser Lappen wird. Und du wolltest mich schlagen? Süß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst glÃ¼hendes Metall gegen {pet}s Innenschenkel, langsam kreisend: 'Das ist keine Narbe mehr. Das ist mein Autogramm in deinem Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schiebt {pet} drei Finger in den Mund bis zum Rachen: 'WÃ¼rg schÃ¶n. Je mehr du kÃ¤mpfst, desto tiefer geh ich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt {pet} mit voller Wucht in die Magengrube: 'Luft? Brauchst du nicht. Ich entscheide, wann du wieder atmest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht {pet} an den Haaren Ã¼ber den Betonboden, Kopf schlÃ¤gt bei jedem Schritt auf: 'Teppich ist fÃ¼r Weicheier. Du verdienst SchÃ¼rfwunden bis auf den SchÃ¤del.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift {pet} in die Brustwarze und dreht, bis sie weiß wird: 'Noch ein Viertel Umdrehung und sie fällt ab. Willst du sie als Andenken?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet}s Gesicht in eine PfÃ¼tze aus ihrem eigenen Speichel und TrÃ¤nen: 'Trink. Das ist das Einzige, was du heute zu saufen kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt {pet} mit dem HandrÃ¼cken Ã¼ber den Mund, bis die Lippe aufplatzt: 'Blut steht dir. Macht dein Gesicht endlich interessant.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt {pet}s Beine auseinander, bis die HÃ¼ftgelenke schreien: 'Weiter. Ich will hÃ¶ren, wann was bricht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt {pet} den Knie in die Nieren, wieder und wieder: 'Jeder Tritt ein Kuss. Und ich bin gerade sehr liebevoll drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet}s Kopf unter Wasser, zählt laut bis 47: 'Du dachtest, 30 wär hart? Ich bin erst warm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt {pet} ein BÃ¼schel Haare aus, samt Kopfhaut: 'Souvenir. NÃ¤chstes Mal nehm ich ein StÃ¼ck Ohr mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt die FingernÃ¤gel unter {pet}s FingernÃ¤gel und hebt an: 'Das wÃ¤chst nach. Deine WÃ¼rde nicht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "pet", tame)

async def cmd_walk(update, context):
    tame = [
"{owner} reiÃŸt die Leine ruckartig hoch, bis {pet} auf die Zehenspitzen muss: 'Hoch mit dem Kinn, Pet. Dein Hals gehÃ¶rt mir â€“ und der sieht besser aus, wenn er blau anlÃ¤uft.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt die Leine dreimal um die Faust und zieht {pet} brutal zurÃ¼ck: 'RÃ¼ckwÃ¤rts stolpern ist dein neuer Gang. Ãœbung macht die Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst die Leine fallen und tritt drauf, wÃ¤hrend {pet} weiterzieht: 'Versuchâ€™s ruhig. Jeder Zentimeter mehr kostet dich Haut vom Hals.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt {pet} einmal hart um die eigene Achse: 'Dreh dich, du kleine Schraube. Ich will sehen, wie dir schwindelig wird.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt die Leine straff und geht schneller, bis {pet} rennt: 'Lauf, Pet. Oder ich schleif dich â€“ und Beton schmeckt scheiÃŸe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bleibt abrupt stehen, Leine schießt nach vorn: 'Halsbruch-Gefahr? Süß. Das ist der Moment, in dem du merkst, wer hier wirklich führt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht {pet} so nah ran, dass Nasen sich berÃ¼hren: 'Atme meinen Atem, kleine HÃ¼ndin. Deiner ist eh nur noch Winseln wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlingt die Leine um {pet}s Handgelenke und zieht sie hoch: 'Arme nach oben, Titten raus â€“ so lÃ¤ufst du jetzt. Deko fÃ¼r meinen Spaziergang.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} vor sich herkriechen, Leine am Halsband: 'Auf allen Vieren, Pet. Menschen gehen nicht â€“ die kriechen fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt den FuÃŸ in {pet}s Kniekehle beim nÃ¤chsten Schritt: 'Runter. Kriechen. Jetzt. Oder ich trete dir die Kniescheibe raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt die Leine um {pet}s Kehle und zieht zu: 'Jeder Atemzug ist ein Geschenk. Danke schÃ¶n sagen wÃ¤r jetzt angebracht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼hrt {pet} an der kurzen Leine direkt vor sich: 'RÃ¼ckwÃ¤rts, Blick zu mir. Ich will sehen, wie dir die TrÃ¤nen laufen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt einmal brutal und lÃ¤sst los: 'Fang dich, oder knall mit der Fresse auf. Deine Wahl, Pet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht die Leine seitlich, bis {pet} seitlich taumelt: 'SeitwÃ¤rts wie ein Krebs â€“ passend, weil du eh nur seitlich fickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt, wickelt die Leine um die eigene Hand und drÃ¼ckt {pet} gegen die nÃ¤chste Wand: 'Pause. Gesicht an Beton. Ich genieÃŸe den Ausblick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt Leine hoch: 'Hals oder Gehorsam. Schnell.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt brutal zurÃ¼ck: 'Kriech, du Wurm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'WÃ¼rg oder lauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt {pet} gegen Wand: 'Gesicht ans Beton.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt hart: 'Stolper. Blute schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle: 'Atmen? Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tempo hoch: 'Renn oder stirb.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt jäh: 'Halsbruch? Mein Favorit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'Krabbel wie Krebs.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt in Knie: 'Runter. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Blickkontakt rÃ¼ckwÃ¤rts: 'TrÃ¤nen zÃ¤hlen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Arme: 'Titten raus. Deko.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine drauftreten: 'Zieh. Verlier Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht hart: 'Schwindel? Gut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nase an Nase: 'SchnÃ¼ffel mich, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rÃ¼ckwÃ¤rts fÃ¼hren: 'Du folgst blind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} seitlicher Ruck: 'Insekt. Passt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'Renn oder erstick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht runter: 'Knie. Oder brech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nackengriff: 'Ein Fehler = Genickbruch.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "walk", tame)

async def cmd_kiss(update, context):
    tame = [
"{owner} packt {pet} am Kiefer, reiÃŸt den Mund auf: 'KÃ¼ss oder ich brech dir die ZÃ¤hne.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt tief in {pet}s Lippe bis Blut kommt: 'Schmeckt besser so.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt {pet}s Zunge raus: 'Die gehÃ¶rt jetzt mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} gegen die Wand, küsst bis sie würgt: 'Atmen? Nicht heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Ã¼ber {pet}s blutige Lippe: 'Mein Geschmack. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst brutal, ZÃ¤hne knirschen: 'Halt still oder verlier die Zunge.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Lippen so fest, dass {pet} blau anlÃ¤uft: 'Dein Blau ist hÃ¼bsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt ins OhrlÃ¤ppchen, dann auf den Mund: 'Beides meins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst und wÃ¼rgt gleichzeitig: 'Kuss mit Extra.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt {pet}s Kopf zurÃ¼ck, kÃ¼sst die Kehle: 'Hals zum BeiÃŸen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt an der Unterlippe bis sie reiÃŸt: 'Narben sind KÃ¼sse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst so hart, {pet} taumelt: 'Fallen oder folgen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt in die Zunge, zieht: 'Bleib dran oder verlier sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst und kneift in die Kehle: 'Atemzug? Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Mund auf Mund, Finger in Kehle: 'Tief. Tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst bis {pet} zittert: 'Zittern ist sÃ¼ÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt die Lippe auf, leckt Blut: 'Rot steht dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst und schlÃ¤gt gleichzeitig: 'Multitasking.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt {pet} am Haar zum Kuss: 'Kopf hoch, Mund auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst langsam, dann brutal: 'Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt {pet}s Mund auf: 'Zunge raus oder ich schneid sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt die Lippe durch: 'Blut schmeckt nach dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt die Zunge raus: 'Die bleibt bei mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst bis {pet} würgt: 'Luft? Vergiss es.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Ã¼ber frisches Blut: 'Mein Lippenstift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ZÃ¤hne in Lippe: 'Halt still oder verlier sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst bis blau: 'Dein neues Make-up.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Ohr, dann Mund: 'Beides markiert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss + WÃ¼rgegriff: 'Doppelt hÃ¤lt besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kehle kÃ¼ssen + beiÃŸen: 'Puls unter ZÃ¤hnen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Unterlippe reiÃŸen: 'Narben sind KÃ¼sse 2.0.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss so hart: 'Taumel oder brech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zunge ziehen: 'Bleib oder blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kehle kneifen + Kuss: 'Atem ist Luxus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Finger in Mund + Kuss: 'Tiefer gehtâ€™s.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kÃ¼sst bis Zittern: 'Zucken ist sÃ¼ÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Blut lecken: 'Rot ist deine Farbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss + Backpfeife: 'Gleichgewicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Haargriff + Kuss: 'Mund auf, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} langsam dann brutal: 'Folter im Doppelpack.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kiss", tame)

async def cmd_dine(update, context):
    tame = [
"{owner} hÃ¤lt den Bissen hoch: 'Bettel oder verhunger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt halbzerkaut rein: 'Schluck meinen Abfall.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst Essen auf Boden fallen: 'Leck. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt drauf, bevor {pet} darf: 'Dreck schmeckt besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert mit Fingern in Kehle: 'Tiefer. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Essen direkt rein: 'Mahlzeit aus meinem Mund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Bissen weg: 'Weine erst, dann darfst du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert, dann kneift Kehle zu: 'Kauen oder ersticken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} vom Schuh essen: 'Boden ist dein Teller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut langsam, spuckt aus: 'HeiÃŸer, weil ich dran war.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Bissen weg: 'Holen. Auf allen Vieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert mit Gabel in Mund: 'BeiÃŸ ab oder blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Essen ans Ohr: 'Hörst du’s knurren? Mein Magen lacht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Sahne rein: 'Trink meinen Rest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst warten, bis {pet} zittert: 'Hunger ist Gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert, dann schlÃ¤gt: 'Danke sagen oder nichts.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen rein bis WÃ¼rgen: 'Schluck oder kotz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Bissen über Klo: 'Willst du runterspülen?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} vom Boden fressen: 'Schweinchen kriegt KrÃ¼mel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt, wiederholt: 'Mein Speichel, dein Leben.' Pflege {n}/{CARES_PER_DAY}.", 
"{owner} spuckt den Bissen ins Klo: 'Fisch ihn raus. Mit den ZÃ¤hnen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} trampelt das Essen platt: 'Friss den Brei vom Schuh. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen rein bis zum Erbrechen: 'Kotz zurÃ¼ck in den Mund. Wiederverwertung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Bissen Ã¼ber offenes Klo: 'Sag danke, bevor ich spÃ¼le.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt auf Boden, tritt drauf: 'Leck meine Sohle sauber, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert mit der Faust: 'Schluck oder ich ramme tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst warten, bis {pet} heult: 'TrÃ¤nen sind die beste SoÃŸe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Essen in MÃ¼ll: 'Betteln. Dann darfst du im MÃ¼ll wÃ¼hlen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt rein, hÃ¤lt Kehle zu: 'Schluck meinen Abfall. Ganz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert vom Arsch: 'Mein SchweiÃŸ ist dein Dressing.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} hungern: 'Morgen vielleicht. Wenn du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen in Mund, schlÃ¤gt zu: 'Kauen mit gebrochener Lippe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Essen auf {pet}s Gesicht: 'Trag dein Abendessen den ganzen Tag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Bissen ans Messer: 'Iss oder ich schneid dir die Zunge raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fÃ¼ttert mit dem FuÃŸ: 'Leck zwischen den Zehen, du Wurm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut lange, spuckt aus: 'Kalter Brei. GenieÃŸ die Temperatur.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} vom Aschenbecher essen: 'Zigarettenkippen sind Beilage.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen bis zum WÃ¼rgen: 'Noch ein Bissen oder ich brech dir den Kiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Essen weg: 'Verhungern ist deine neue DiÃ¤t.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt den letzten Rest ins Gesicht: 'Das war's. Jetzt leck mich sauber.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dine", tame)

async def cmd_massage(update, context):
    tame = [
"{owner} grÃ¤bt Daumen in die Nieren: 'Entspann dich oder ich brech dir die Rippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Wirbelsäule: 'Knack. Nochmal?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Schultern bis Sehnen reiÃŸen: 'Lockerer wirdâ€™s nicht mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in Triggerpunkte: 'Schrei lauter, ich hÃ¶r schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Handballen in den Hals: 'Atemkontrolle deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit KnÃ¶cheln den RÃ¼cken runter: 'Haut abziehen inklusive.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Daumen tief in die Leiste: 'Innere Schenkel brauchen auch Pflege.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Brüste brutal: 'Muskeln? Oder nur Fett zum Quälen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grÃ¤bt NÃ¤gel in verspannte Stellen: 'Blut ist das beste Gleitmittel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert den Nacken, zieht Kopf zurÃ¼ck: 'Halsbruch-Massage, Stufe eins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Knie in den unteren RÃ¼cken: 'Atme durch die ZÃ¤hne, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Oberschenkel bis blaue Flecken: 'Morgen lÃ¤ufst du wie â€™ne KrÃ¼ppel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in die AchselhÃ¶hle: 'Tickle-Tortur, aber ohne Lachen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Ellbogen in die Leber: 'Innere Organe brauchen Entspannung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit der Faust den Bauch: 'Noch ein bisschen tiefer und du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet den Kiefer bis ZÃ¤hne klappern: 'Mund auf, oder ich brech ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt in die Waden: 'Krämpfe? Die kommen erst jetzt richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Daumen in die Schläfen: 'Kopfschmerzen? Mein Spezialgebiet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit vollem Gewicht drauf: 'Atemnot ist Teil der Therapie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beendet mit einem harten Schlag auf den RÃ¼cken: 'Fertig. Jetzt zitter schÃ¶n weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grÃ¤bt Daumen in die Nieren: 'Entspann dich oder ich brech dir die Rippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Wirbelsäule: 'Knack. Nochmal?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Schultern bis Sehnen reiÃŸen: 'Lockerer wirdâ€™s nicht mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in Triggerpunkte: 'Schrei lauter, ich hÃ¶r schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Handballen in den Hals: 'Atemkontrolle deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit KnÃ¶cheln den RÃ¼cken runter: 'Haut abziehen inklusive.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Daumen tief in die Leiste: 'Innere Schenkel brauchen auch Pflege.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Brüste brutal: 'Muskeln? Oder nur Fett zum Quälen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grÃ¤bt NÃ¤gel in verspannte Stellen: 'Blut ist das beste Gleitmittel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert den Nacken, zieht Kopf zurÃ¼ck: 'Halsbruch-Massage, Stufe eins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Knie in den unteren RÃ¼cken: 'Atme durch die ZÃ¤hne, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Oberschenkel bis blaue Flecken: 'Morgen lÃ¤ufst du wie â€™ne KrÃ¼ppel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in die AchselhÃ¶hle: 'Tickle-Tortur, aber ohne Lachen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Ellbogen in die Leber: 'Innere Organe brauchen Entspannung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit der Faust den Bauch: 'Noch ein bisschen tiefer und du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet den Kiefer bis ZÃ¤hne klappern: 'Mund auf, oder ich brech ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt in die Waden: 'Krämpfe? Die kommen erst jetzt richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Daumen in die Schläfen: 'Kopfschmerzen? Mein Spezialgebiet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit vollem Gewicht drauf: 'Atemnot ist Teil der Therapie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beendet mit einem harten Schlag auf den RÃ¼cken: 'Fertig. Jetzt zitter schÃ¶n weiter.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "massage", tame)

async def cmd_lapdance(update, context):
    tame = [
        "{pet} windet sich auf {owner}s SchoÃŸ, Arsch hoch, Gesicht rot vor Scham â€“ jede Bewegung nur, weil ich es will, und weil sie es insgeheim liebt. Pflege {n}/{CARES_PER_DAY}. ðŸ˜",
        "Langsam, quÃ¤lend, Haut an Haut â€“ {owner} hÃ¤lt die HÃ¼ften fest, steuert den Rhythmus, bis {pet} nass vor Verzweiflung und purer Geilheit ist. Pflege {n}/{CARES_PER_DAY}. ðŸ”¥",
        "Der Tanz endet nicht mit Applaus â€“ sondern mit {owner}s Hand in {pet}s Haar, Kopf runtergedrÃ¼ckt: 'Nochmal, Baby. Und diesmal mit mehr GefÃ¼hl.' Pflege {n}/{CARES_PER_DAY}. ðŸ–¤",
        "{pet} tanzt nackt, {owner} gibt bei jedem 'Fehltritt' einen kleinen Klaps auf den Arsch â€“ bis er glÃ¼ht und {pet} leise winselt. Pflege {n}/{CARES_PER_DAY}. ðŸ¤š",
        "HÃ¼ften gepackt, langsam und dreckig gerieben â€“ 'Mach mich hart, Schatz, oder ich lass dich ewig tanzen.' Pflege {n}/{CARES_PER_DAY}. ðŸ˜ˆ",
        "{pet} muss strippen wÃ¤hrend des Tanzes, jedes KleidungsstÃ¼ck fliegt mit einem Grinsen â€“ 'Nackt bist du eh am allerbesten.' Pflege {n}/{CARES_PER_DAY}. ðŸ‘™",
        "Der Lapdance endet mit {pet}s Gesicht nah am Schritt â€“ 'Atme ein, das ist dein verdammter Applaus.' Pflege {n}/{CARES_PER_DAY}. ðŸ’¨",
        "{pet} tanzt mit einem frechen Grinsen, jede Bewegung pure Provokation â€“ 'Zeig mir, wie sehr du mich willst.' Pflege {n}/{CARES_PER_DAY}. ðŸ˜˜",
        "{owner} filmt den Tanz nur im Kopf â€“ 'Dein Publikum bin ich, und ich bin schon begeistert.' Pflege {n}/{CARES_PER_DAY}. ðŸŽ¥",
        "{pet} grindet langsam und {owner} raunt: 'Finish Him!' â€“ aber nein, heute gibtâ€™s kein Ende, nur noch eine Runde. Pflege {n}/{CARES_PER_DAY}. ðŸ”¥âš”ï¸",
        "{owner} hÃ¤lt die HÃ¼ften: 'It's dangerous to go alone! Take this...' â€“ und zieht {pet} noch nÃ¤her ran. Pflege {n}/{CARES_PER_DAY}. ðŸ•¹ï¸ðŸ˜",
        "{pet} tanzt weiter, {owner} grinst: 'Hadouken!' â€“ als ob der Blick allein sie umhaut. Viel geiler als jeder Feuerball. Pflege {n}/{CARES_PER_DAY}. ðŸ‘ŠðŸ’¥",
        "{owner} flÃ¼stert wÃ¤hrend des Tanzes: 'All your base are belong to me.' â€“ und {pet} weiÃŸ genau, was gemeint ist. Pflege {n}/{CARES_PER_DAY}. ðŸ–¥ï¸ðŸ–¤",
        "{pet} bewegt sich perfekt, {owner} lacht: 'Fatality!' â€“ aber die einzige Todesursache hier ist pure Ãœbergeiltheit. Pflege {n}/{CARES_PER_DAY}. ðŸ’€ðŸ˜ˆ",
        "{owner} packt fester zu: 'Get over here!' â€“ Scorpion-Style, nur mit HÃ¼ften statt Speer. Pflege {n}/{CARES_PER_DAY}. ðŸ¦‚ðŸ”¥",
        "{pet} strippt ein StÃ¼ck: 'It's time to kick ass and chew bubble gum... and I'm all outta gum.' â€“ Duke Nukem hÃ¤tte Respekt. Pflege {n}/{CARES_PER_DAY}. ðŸ’ªðŸ˜",
        "{owner} genieÃŸt die Show: 'Do a barrel roll!' â€“ und {pet} dreht sich extra lasziv. Star Fox war nie so heiÃŸ. Pflege {n}/{CARES_PER_DAY}. ðŸ›©ï¸",
        "{pet} tanzt weiter, {owner} raunt: 'Flawless Victory.' â€“ weil sie einfach keine Chance hat, zu gewinnen. Pflege {n}/{CARES_PER_DAY}. ðŸ†ðŸ–¤",
        "{owner} zieht {pet} runter: 'The cake is a lie' â€“ aber dieser Lapdance ist echt, und er macht sÃ¼chtig. Pflege {n}/{CARES_PER_DAY}. ðŸŽ‚ðŸ˜˜"
    ]
    await do_care(update, context, "lapdance", tame)


async def cmd_knien(update, context):
    tame = [
"{owner} zeigt runter: 'Knie. Sofort. Oder ich trete dir die Beine weg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Nacken runter: 'Runter, Schlampe. Dein Platz ist immer unten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} packt Haare, reiÃŸt Kopf zurÃ¼ck: 'Knie, Augen hoch â€“ ich will die TrÃ¤nen sehen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt gegen Kniekehle: 'Fallen lassen. Hart. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine straff: 'Knie oder ich zieh dich runter â€“ bis der Hals reiÃŸt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt FuÃŸ auf RÃ¼cken: 'Runter mit dem Arsch. Bleib liegen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Knie auseinander: 'Breit. Wie die Hure, die du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet HÃ¤nde hinterm RÃ¼cken: 'Knie. Und wehe, du kippst um â€“ dann brech ich dir was.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst warten: 'Zitter ruhig. Knie sind zum Brechen da.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Daumen in Kehle: 'Knie, wÃ¤hrend du wÃ¼rgst. Perfekter Moment.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt auf Oberschenkel: 'Runter. Rot wird dein neuer Teppich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, Knie auf Beton: 'SpÃ¼r den Boden. Das ist dein neues Zuhause.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Kopf runter: 'Stirn am Boden. Wie beim Gebet â€“ nur an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt zwischen Beine: 'Knie breit. Oder ich trete rein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht an Haaren runter: 'Knie. Und halt die Fresse â€“ auÃŸer zum Betteln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst ewig warten: 'Knie. Bis die Knie kaputt sind. Dann erst hoch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Knie mit Stiefel runter: 'Bleib unten. Oder ich stampf drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Knie. Und denk dran: Stehen ist fÃ¼r Menschen. Du bist keins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Augen: 'Blind auf Knien. SpÃ¼r nur den Schmerz â€“ und mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, hÃ¤lt fest: 'Knie. Und bettel, dass ich dich nicht ewig so lasse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt dir die Knie weg: 'Runter, Fotze. Hart auf Beton â€“ bis die Kniescheiben splittern.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} packt Nacken, drÃ¼ckt runter bis Stirn am Boden klebt: 'Knie. Und leck den Dreck, wÃ¤hrend du betest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt Haare raus beim Runterzwingen: 'Knie. NÃ¤chstes Mal nehm ich die Kopfhaut mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt Stiefel in Kniekehle: 'Fallen. Und wehe, du heulst â€“ dann tret ich drauf, bis was bricht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Knie auseinander bis HÃ¼fte schreit: 'Breit wie â€™ne Nutte im Schlachthof. Halt durch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet HÃ¤nde hoch, Knie runter: 'Gebunden und gekniet â€“ jetzt bettel, dass ich dir nicht die Arme auskugle.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Daumen in Kehle beim RunterdrÃ¼cken: 'Knie. Und wÃ¼rg schÃ¶n â€“ macht den Anblick geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst dich ewig knien, bis Beine taub: 'Knie. Bis du nicht mehr aufstehen kannst â€“ dann schleif ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt mit GÃ¼rtel auf Oberschenkel: 'Runter. Jeder Schlag ein Grund mehr, unten zu bleiben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, presst Gesicht in Kotfladen: 'Knie. Und atme das ein â€“ dein neues ParfÃ¼m.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt zwischen Beine, drÃ¼ckt Knie auseinander: 'Weiter. Bis die Sehnen reiÃŸen â€“ oder du schreist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Kopf runter, Nase am Boden: 'Knie. Und schnÃ¼ffel wie das Vieh, das du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Leine kurz, zwingt runter: 'Knie. Und wehe, du hebst den Kopf â€“ dann strangulier ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt Knie auf Glas: 'Runter. SpÃ¼r die Scherben â€“ das ist dein neuer Teppich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt mit Stiefel auf RÃ¼cken: 'Knie. Und bleib liegen â€“ wie â€™ne tote Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt Kopf hoch, dann runter: 'Knie. Und lern, dass Hochkommen nie wieder kommt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, hÃ¤lt Kehle zu: 'Knie. Und stirb langsam â€“ sieht hÃ¼bsch aus von oben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst warten, bis Knie bluten: 'Knie. Blut ist der beste Beweis, dass du unten bleibst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt auf HÃ¤nde, zwingt Knie: 'Runter. Und wehe, du bewegst dich â€“ dann brech ich dir die Finger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst dich runter, Gewicht voll drauf: 'Knie. Und spÃ¼r, wie dein KÃ¶rper kaputtgeht â€“ fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knien", tame)

async def cmd_kriechen(update, context):
    tame = [
"{owner} tritt Arsch: 'Kriech, Wurm. Schneller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt Haare: 'Fresse runter. Kriech, Vieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'Kriech oder schleif ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Stiefel RÃ¼cken: 'Tiefer. Bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kalt: 'Kriech. Arsch wie tote Qualle.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter: 'Vierbeiner. Du kriechst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Knie: 'Weiter. Oder Beine brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Gesicht Dreck: 'SchnÃ¼ffel, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine wÃ¼rgen: 'Kriech. Keuch geil.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Boden: 'Leck. Kriechend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Kriech, Teppich. Bald platt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt HÃ¤nde: 'Ohne Finger. Mir egal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Arsch hoch: 'HÃ¶her. Zeig WÃ¼rdebruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ewig: 'Kriech. Kein RÃ¼ckgrat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kopf runter: 'Fresse Boden. Riech Tod.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreckig: 'Kriech, Insekt. Hammer nÃ¤chstes Mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} brutal: 'Schneller. Oder Haut reiÃŸen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt: 'Kriech. Jammerst? Zähne ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Gesicht: 'Kriech nass, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Kriech bis Sarg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt Rippen: 'Kriech, bevor ich dich zerquetsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Hals: 'Kriech oder strangulier ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt vor dich: 'Kriech durch meine Spucke, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nagel in RÃ¼cken: 'Kriech. Jeder Stich ein Schritt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Kriech, du nutzloser Wischlappen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Gesicht runter: 'Fresse am Boden. Kriech weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Ellbogen runter: 'Kriech flach. Wie â€™ne Leiche.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht an Ohren: 'Kriech. Oder ich reiÃŸ sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Glas auf Boden: 'Kriech Ã¼ber Scherben. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt inne: 'Kriech rÃ¼ckwÃ¤rts. Zeig mir dein Loch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Kehle zu: 'Kriech wÃ¼rgend. Geiler Sound.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Salz auf Wunden: 'Kriech. Brennt schön, oder?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kalt: 'Kriech, bis deine Knie Knochen sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Finger: 'Kriech ohne HÃ¤nde. Wurm pur.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Kriech in die HÃ¶lle. Ich komm mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine am Genick: 'Kriech oder Genickbruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt ins Haar: 'Kriech nass und stinkend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht dreckig: 'Kriech. Du bist schon tot â€“ nur noch Bewegung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nagel unter Nagel: 'Kriech. Jeder Finger ein Schrei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Arsch runter: 'Kriech platt. Wie â€™ne zerquetschte Ratte.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kriechen", tame)

async def cmd_klaps(update, context):
    tame = [
"{owner} knallt die Hand auf {pet}s Arsch: 'Das fÃ¼rs Atmen. NÃ¤chster fÃ¼rs Blinzeln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt hart: 'ZÃ¤hl falsch und ich fang von vorn an â€“ bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps so fest, dass es knallt: 'Dein Arsch schreit lauter als du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} abwechselnd links rechts: 'Symmetrie ist wichtig â€“ fÃ¼r blaue Flecken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haut zu: 'Das war fÃ¼r deine letzte LÃ¼ge. Die nÃ¤chste kommt gleich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit Ring: 'Spürst du den Stein? Der ist teurer als dein Stolz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt wiederholt: 'Musik fÃ¼r mich â€“ dein Heulen ist der Beat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} harter Klaps: 'Danke sagen oder ich mach weiter, bis duâ€™s vergisst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf Innenschenkel: 'Arsch ist voll? Dann wechsel ich die Seite.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Das fÃ¼rs Denken ohne Erlaubnis. Dummes MÃ¤dchen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps so laut, dass es hallt: 'Nachbarn wissen jetzt, wer hier die Hure ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt bis Schwellung: 'Morgen sitzt du nicht â€“ perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Kneifen: 'Rot und blau â€“ meine Lieblingsfarben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haut zu: 'Das war fÃ¼rs ZÃ¶gern. NÃ¤chster fÃ¼rs Zappeln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit der Faustkante: 'Weicher wirdâ€™s nicht. Nur roter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt in Serie: 'Zehn fÃ¼r jeden Atemzug ohne mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf SteiÃŸbein: 'Das sitzt tief â€“ genau wie du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart und trocken: 'Dein Arsch ist mein Schlaginstrument.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis TrÃ¤nen: 'Weinen machtâ€™s geiler. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt und lacht: 'Das war fÃ¼rs Existieren. Danke mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit GÃ¼rtel: 'Hand war zu nett. Jetzt wirdâ€™s ernst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Dein Hintern glÃ¼ht wie meine Laune.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Ziehen: 'Rot und gedehnt â€“ mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt bis Bluterguss: 'Morgen siehst du aus wie mein Eigentum.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf wunde Stelle: 'Frisch auf Alt â€“ doppelter SpaÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'ZÃ¤hl mit oder ich fang bei hundert an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit flacher Hand: 'Das ist Gnade. NÃ¤chster kommt mit Faust.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt rhythmisch: 'Dein Puls ist mein Metronom.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis Zucken: 'Zappel ruhig â€“ machtâ€™s nur hÃ¤rter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt zu: 'Das fÃ¼rs Betteln. Ohne zu kommen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf beide Backen: 'Gleichberechtigung â€“ fÃ¼r Schmerzen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis taub: 'Spürst du noch was? Gut. Dann weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Kratzen: 'Blut und Rot â€“ mein Farbschema.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'Das war fÃ¼r deine TrÃ¤nen. Die nÃ¤chsten fÃ¼rs LÃ¤cheln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt und flÃ¼stert: 'Dein Arsch gehÃ¶rt mir â€“ und der Schmerz auch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis Schreien: 'Lauter. Die Nachbarn sollen neidisch sein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Jeder Schlag ein Kuss â€“ nur ohne Lippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit Lederhandschuh: 'Weicher Stoff, hÃ¤rterer Schlag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt bis Schwellung platzt: 'Perfekt. Jetzt glÃ¤nztâ€™s.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + BeiÃŸen: 'Zuerst schlagen, dann markieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart und kalt: 'Das fÃ¼rs WÃ¼nschen. Du kriegst nur, was ich gebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt in Wellen: 'Leise â€“ laut â€“ leise â€“ bis du brichst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis der Arsch taub: 'Gefühllos? Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt zu: 'Das war fÃ¼rs Atmen. Danke, dass duâ€™s aushÃ¤ltst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt und zÃ¤hlt rÃ¼ckwÃ¤rts: 'FÃ¼nfzig bis eins â€“ dann fang ich neu an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf wunden Stellen: 'Alt und neu â€“ wie deine Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'Dein Arsch ist mein Punching-Bag. Schlag zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt bis du zitterst: 'Zittern ist sÃ¼ÃŸ. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} letzter Klaps brutal: 'Und der hier ist, weil duâ€™s verdienst â€“ einfach so.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "klaps", tame)

async def cmd_knabbern(update, context):
    tame = [
"{owner} beißt in Schulter, bis Blut kommt: 'Dein Geschmack? Nach Angst und Dummheit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt ZÃ¤hne in Brustwarze: 'Zieh dich zurÃ¼ck oder ich reiÃŸ sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Innenschenkel tief: 'Nah dran? Bald drin – und du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Arschbacke durch: 'FrÃ¼hstÃ¼ck. Direkt vom lebenden Buffet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ZÃ¤hne in Kehle: 'Puls schmeckt nach deinem baldigen Ende.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Lippe bis Riss: 'KÃ¼ss mich mit Blut â€“ romantischer gehtâ€™s nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Klit hart: 'Perle? Eher Perlenkette aus Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Bauch, zieht Haut: 'Von innen lachen? Bald von innen schreien.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Ohrläppchen: 'Van Gogh? Ich nehm mir alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Hals bis Markierung: 'Mein Revier. Und du bist der Zaun.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Tippen? Nächstes Mal ohne Finger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Nase: 'Zu niedlich? Dann beiß ich sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Kinn durch: 'Selbstständig? Vergiss es, du Stück Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Ohr bis Blut: 'Geheimnis: Du stirbst irgendwann – fang ich heute an?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Schulter tief: 'Daily Reminder: Du bist mein Snack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert bis Quietschen aufhört: 'Musik? Dein Schreien ist besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Hals: 'Atmen ohne mich? Strafe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Lippe auf: 'Applaus? Mit Blut applaudiert’s besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Arm bis Knochen: 'Weglaufen? Mit einem Arm?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Brust: 'Danke sagen oder ich nehm die ganze Titte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reiÃŸt Haut vom RÃ¼cken: 'HÃ¤utung deluxe â€“ fÃ¼r besseren Geschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Oberschenkel: 'Ader? Fast. Noch ein Biss.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Finger ab: 'NÃ¤chstes Mal die ganze Hand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Kehle bis Würgen: 'Puls? Bald keiner mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Innenschenkel: 'Nah dran? Bald drin – und leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ZÃ¤hne in Arsch: 'Markiert. FÃ¼r immer mein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Lippe durch: 'Blutkuss. Mein Lieblingsgeschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Klit: 'Perle? Bald nur noch Narbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut vom Bauch: 'Von innen? Bald von außen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Ohr: 'Hörst du? Das ist dein Tod.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Schulter bis Knochen: 'Fleisch ab. Knochen nÃ¤chstes Mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Hals: 'Narben? Meine Unterschrift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Tippen ohne Finger? Chat endet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Nase: 'Zu süß? Dann weg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Kinn: 'Kinn? Bald ohne.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Brustwarze ab: 'NÃ¤chstes Mal die ganze Brust.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Rücken: 'Rückgrat? Brauchst du eh nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Innenschenkel: 'Ader? Fast. Noch einer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Lippe: 'Blut? Mein Lippenstift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut vom Arm: 'Arm? Bald Stumpf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Kehle: 'Schlucken? Mit Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ZÃ¤hne in Arsch: 'FrÃ¼hstÃ¼ck. Mittag. Abend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt Schulter: 'Markiert. Und du heilst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Ohr: 'HÃ¶r gut zu â€“ das ist dein letztes.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Finger? Bald weniger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Hals: 'Puls? Mein Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Brust: 'Titze? Bald nur Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut: 'Haut? Überflüssig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ZÃ¤hne in Lippe: 'Blutkuss. Letzter Kuss.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert alles: 'Snack. Hauptgericht. Dessert â€“ du.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knabbern", tame)

async def cmd_leine(update, context):
    tame = [
"{owner} wickelt Leine um Kehle, zieht langsam zu: 'Atme nochmal. Das warâ€™s dann fÃ¼r heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt Leine brutal: 'WÃ¼rg. Dein neuer GruÃŸ an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff bis blau: 'Blau anlaufen? Mein Lieblings-Make-up.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert mit doppelter Wicklung: 'Zwei Schichten. Zwei Chancen zu sterben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch, bis Füße abheben: 'Schweben? Nur bis du schwarz wirst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Hals, drÃ¼ckt runter: 'Knie und wÃ¼rg. Perfekter Anblick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst locker, dann ruckartig: 'Atemzug-Geschenk. Danke schÃ¶n sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert bis Zittern: 'Zucken ist sÃ¼ÃŸ. Mach weiter, bevor du kippst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine um Kehle und zieht: 'Puls unter Leine. Mein neues Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält bis Ohnmacht nah: 'Schwarzwerden? Mein persönlicher Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt Leine in Serie: 'WÃ¼rg-WÃ¼rg-WÃ¼rg. Dein neuer Name.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'SeitwÃ¤rts wÃ¼rgen. Wie ein kranker Hund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Genick, zieht rÃ¼ckwÃ¤rts: 'Genickbruch oder Ersticken. Such dir was.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert langsam: 'Langsam sterben. GenieÃŸ die Vorfreude.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine straff bis TrÃ¤nen: 'Weinen und wÃ¼rgen. Doppelt hÃ¤lt besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine um Hals, knotet: 'Knoten. Jetzt atme, wenn du kannst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis BlutgefÃ¤ÃŸe platzen: 'Rot in den Augen. HÃ¼bsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert beim Gehen: 'Jeder Schritt ein WÃ¼rgen. Mein Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle, drÃ¼ckt gegen Wand: 'Wand und Leine. Dein neues Kreuz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst fallen, tritt drauf: 'Zieh selbst. Erstick dich, ich schau zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt bis Knie knicken: 'Runter. WÃ¼rg auf Knien.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert bis Keuchen: 'Keuchen ist geil. Mach lauter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine doppelt um Hals: 'Zwei Wicklungen. Zwei Leben zum Verlieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch zum Spiegel: 'Schau dir an, wie du erstickst. SchÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine straff bis Zunge raus: 'Zunge raus. Will ich lecken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert ruckartig: 'Kurz und hart. Wie dein letzter Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle, zieht langsam hoch: 'Hochziehen. Bis du schwebst â€“ oder fÃ¤llst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wÃ¼rgt mit Leine und Hand: 'Leine vorne, Hand hinten. Doppeltes GlÃ¼ck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt bis Bewusstlosigkeit: 'Schlaf schÃ¶n. Ich weck dich mit neuem Zug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert beim Strangulieren: 'Dein letzter Atemzug? Gehört mir.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "leine", tame)

async def cmd_halsband(update, context):
    tame = [
"{owner} schnappt das Halsband zu: 'Für immer? Bis ich dich zerlege und neu baue.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht es enger: 'Keuchen? Dein neuer Gruß an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlieÃŸt ab, SchlÃ¼ssel verschluckt: 'Such ihn. In meinem Magen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Fingernägel unter Rand: 'Blutperlen? Mein neues Dekor.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht zu bis blau: 'Blau steht dir. Wie dein letzter Atemzug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤ngt Gewicht dran: 'Schwerer Hals = schwereres Leben. GewÃ¶hn dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} graviert tief: 'Eigentum. Und du heilst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht zu: 'Stimme? Die gehört mir. Sprich nur, wenn ich zieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt Stachel rein: 'Jeder Schluck ein Stich. SchÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Zunge raus: 'Zunge raus. Will ich lecken â€“ oder abbeiÃŸen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Kette ans Bett: 'Schlaf damit. Oder stirb damit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch: 'Hoch mit dem Kinn. Oder ich reiÃŸ es hoch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt mit Vorhängeschloss: 'Schloss. Schlüssel? In meinem Arsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Metall in Haut: 'Narben? Meine Unterschrift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Ohnmacht: 'Schwarzwerden? Mein Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Dornen: 'Beweg dich. Und blute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'SeitwÃ¤rts wÃ¼rgen. Wie ein kranker Hund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt zu eng: 'Atem? Mein Geschenk. Danke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hängt Glöckchen dran: 'Klingelst du? Dann stirbst du lauter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Tränen: 'Weinen? Macht den Hals schöner.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Elektro: 'Zuck. Oder ich schalt ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt ab, Schlüssel weg: 'Verloren? Such ihn in deiner Leiche.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Genick knackt: 'Genickbruch? Romantisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Stacheldraht: 'Beweg dich. Und zerfleisch dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch zum Spiegel: 'Schau. So erstickst du schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt Stachel in Kehle: 'Schlucken? Mit Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband zu eng: 'Puls? Bald keiner mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Zittern: 'Zittern ist sÃ¼ÃŸ. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt mit Kleber: 'Abnehmen? Nur mit Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Messer: 'Beweg dich falsch. Und schneid dich.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "halsband", tame)

async def cmd_lecken(update, context):
    tame = [
"{owner} drÃ¼ckt {pet}s Gesicht in den Stiefel: 'Leck den Dreck ab, bevor ich dir die Zunge rausreiÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf den Boden: 'Leck meine Spucke auf. Langsam. Wie die Hure, die du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Stiefelsohle hin: 'Zunge rein in die Rillen. Schmeckt nach deinem Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Kopf runter: 'Leck meine Finger sauber â€“ oder ich stopf sie dir in den Hals.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} eigene Tränen lecken: 'Salzig? Das ist der Geschmack von Versagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt in offenen Mund: 'Leck meine Spucke runter. Und danke schÃ¶n sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Aschenbecher hin: 'Leck die Kippen sauber. Dein neues Dessert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Zunge in Klo: 'Leck den Rand. Das ist dein Heiligtum.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} den Boden lecken: 'Wo ich draufgetreten bin. Dein neuer Teller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Hand hin, dreckig: 'Leck den Dreck ab. Oder ich reib ihn dir ins Gesicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} an Arsch: 'Leck meine Ritze. Und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Stiefel: 'Leck. Und schmeck deine eigene Erniedrigung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Zeh hin: 'Leck zwischen den Zehen. Staub ist dein Protein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht in PfÃ¼tze: 'Leck den Dreck. Dein neues ParfÃ¼m.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} Blut lecken: 'Dein eigenes. Weil du zu langsam warst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Finger in Mund: 'Leck tief. Bis du wÃ¼rgst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Boden, tritt drauf: 'Leck meine Sohle sauber. Mit Dreck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} an Achsel: 'Leck den SchweiÃŸ. Dein neues GetrÃ¤nk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} Klo lecken: 'Ring um die SchÃ¼ssel. Dein neuer Thron.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Stiefel in Mund: 'Leck innen. Bis du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt ins Gesicht: 'Leck ab. Und weine dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Zunge an Kehle: 'Leck meinen Puls. Der schlÃ¤gt nur, wenn du leidest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} eigene Kotze lecken: 'Wiederverwertung. Mund auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Dreckhand hin: 'Leck. Und sag danke fÃ¼r den Geschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht in MÃ¼ll: 'Leck den Abfall. Passt zu dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Zunge: 'Leck meine Spucke. Dein neues Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Stiefel hoch: 'Leck die Sohle. Bis deine Zunge blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} an Arschloch: 'Leck. Und atme tief ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} TrÃ¤nen vom Boden lecken: 'Salzig und nutzlos. Genau wie du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Finger in Mund, tief: 'Leck bis zum WÃ¼rgen. Das ist dein Talent.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lecken", tame)

async def cmd_verweigern(update, context):
    tame = [
"{owner} hält Wasser vor Nase, trinkt selbst: 'Durst? Trink deine Tränen. Die schmecken besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert {pet} bis Rand, stoppt: 'Kommen? Nur in meinen Träumen. Und die träumst du heute Nacht allein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} isst vor {pet}, lÃ¤sst KrÃ¼mel fallen: 'Leck den Boden. Das ist dein Abendessen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt stundenlang: 'Deine Stimme? Überbewertet. Meine Stille ist Gold.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht sich weg beim Kuscheln: 'Decke reicht. Die bettelt wenigstens nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Kuss: 'Lippen? Die spar ich für jemanden, der’s verdient. Du nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Orgasmus-Foto: 'Das war gestern. Heute? Nur Erinnerung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} wach bleiben: 'Schlaf? Für Menschen. Du bist keins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Like: 'Dein Selfie? Zu hässlich für meinen Feed.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Essen hoch, wirft weg: 'Hunger? Gut. Der macht dich gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert bis Zucken, zieht raus: 'Fast. Aber fast ist dein neuer HÃ¶hepunkt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt auf Betteln: 'Betteln? Klingt wie ein sterbender Hund. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Berührung: 'Hautkontakt? Nur für Dinge, die nicht so erbärmlich sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} trinkt Kaffee, gießt Rest weg: 'Du? Nicht mal für die Pflanze wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Schokolade, isst allein: 'Süß? Nicht für dich. Du bleibst bitter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Gute-Nacht: 'TrÃ¤um von mir. Das ist die einzige BerÃ¼hrung, die du kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} zuschauen beim Wichsen: 'Schau zu. Aber komm nicht. Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt tagelang: 'Deine Nachrichten? Müll. Ich les sie nicht mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Lob: 'Gutes Mädchen? Du bist nicht mal ein guter Witz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Hand weg: 'Anfassen? Nur wenn du blutest. Und selbst dann vielleicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Antwort: 'Gelesen. Und gelÃ¶scht. Wie dein Wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} hungern: 'Mager werden? Passt zu deiner Persönlichkeit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht sich um beim Betteln: 'Bettel weiter. Ich hÃ¶r eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Schlaf: 'Wach bleiben. Deine AlbtrÃ¤ume sind besser als du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Video von Orgasmus: 'Das war nicht mit dir. Und wirdâ€™s nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Wasser: 'Trink deinen Speichel. Der ist eh nutzloser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst {pet} zuschauen beim Essen: 'Schau. Und stirb vor Hunger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert alles: 'Heute nichts. Morgen vielleicht. Oder nie. Dein Pech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Verweigern ist Liebe. Und ich liebe dich zu Tode.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "verweigern", tame)

async def cmd_kaefig(update, context):
    tame = [
        "{owner} schlieÃŸt die TÃ¼r ab und grinst durchs Gitter: 'Willkommen zu Hause, Baby â€“ Dunkelheit und Stille, nur dein Herz schlÃ¤gt laut... fÃ¼r mich.' ðŸŒ‘ Pflege {n}/{CARES_PER_DAY}.",
        "Stunden im KÃ¤fig, nackt, zitternd â€“ {owner} schaut nur zu: 'Gute Tiere lernen schnell. Schlechte betteln sÃ¼ÃŸ â€“ und du bist ja so schlecht.' ðŸ• Pflege {n}/{CARES_PER_DAY}.",
        "Die Gitter werfen Schatten auf {pet}s Haut â€“ ein Muster aus Gefangenschaft: 'Sieht aus wie Tattoos, nur billiger und mit mehr Drama â€“ dein Lieblingslook.' â›“ï¸ Pflege {n}/{CARES_PER_DAY}.",
        "Käfig schön geräumig, {pet} kann sich drehen – {owner}: 'Gemütlich, oder? Fast wie ein Wellness-Retreat – nur ohne Ausgang, du kleine Dauergast.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} stellt den KÃ¤fig ins Wohnzimmer â€“ {pet} hat beste Sicht auf mich: 'BrÃ¤unung durch Fernseherlicht inklusive â€“ und mein Grinsen gratis.' Pflege {n}/{CARES_PER_DAY}.",
        "Nachts leises Musikchen im Käfig – {pet} darf mitsingen: 'Neue Spielkameraden? Nee, nur meine Playlist – und du bist der Refrain.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig mit weicher Decke – {pet} wird wahnsinnig vor Bequemlichkeit: 'Wassertortur light? Heute nur Kuschelfolter – weil du's eh nicht verdienst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} 'vergisst' {pet} fÃ¼r fÃ¼nf Minuten â€“ kommt zurÃ¼ck und lacht: 'Zeitreise erfolgreich. Du siehst aus, als wÃ¤râ€™s â€™ne Woche â€“ sÃ¼ÃŸ, wie du leidest.' Pflege {n}/{CARES_PER_DAY}.",
        "Käfig mit Kissen drin – jede Bewegung bequem: 'Umarmung rundum? Ja, von meiner Aufmerksamkeit – die dich langsam erstickt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt {pet} im KÃ¤fig und zeigt es nur sich selbst: 'Dein neues Zuhause geht viral â€“ in meinem Kopf, 24/7, du kleine Star-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} schlieÃŸt ab und edge {pet} durchs Gitter: 'Gutes MÃ¤dchen, eingesperrt und nass â€“ dein KÃ¤fig ist edging deluxe.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤sst {pet} warten mit verbundenen Augen: 'Gutes MÃ¤dchen, blind im KÃ¤fig â€“ du spÃ¼rst nur die Gitter und meine Stimme.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt {pet} durchs Gitter: 'Gutes MÃ¤dchen, tropf im KÃ¤fig â€“ du quillst nur fÃ¼r mich, du kleine Tropf-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt Klapse durchs Gitter: 'Gutes MÃ¤dchen, rot glÃ¼hen im KÃ¤fig â€“ perfekt fÃ¼r meine kleine Klaps-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hÃ¤lt die Leine durchs Gitter: 'Gutes MÃ¤dchen, gezogen im KÃ¤fig â€“ du kleine Leinen-Sub, die nie entkommt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flÃ¼stert Befehle durchs Gitter: 'Bleib, warte, zitter â€“ gutes MÃ¤dchen, dein KÃ¤fig ist mein Echo.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤sst {pet} stundenlang warten: 'Gutes MÃ¤dchen, dein KÃ¤fig ist Zeitfolter â€“ und du wartest so schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge {pet} im KÃ¤fig: 'Gutes MÃ¤dchen, nah dran und Stopp â€“ dein KÃ¤fig ist edging-HÃ¶lle.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} bindet {pet} im KÃ¤fig fest: 'Gutes MÃ¤dchen, gefesselt im KÃ¤fig â€“ du kleine Fessel-Sub, die sich nicht bewegt.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} melkt und stoppt: 'Gutes MÃ¤dchen, leer machen im KÃ¤fig â€“ und du bettelst um mehr, du kleine Leere.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤sst {pet} stumm im KÃ¤fig: 'Gutes MÃ¤dchen, kein Wort â€“ dein KÃ¤fig ist Stille-Folter.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} gibt imaginÃ¤re Klapse durchs Gitter: 'Gutes MÃ¤dchen, rot glÃ¼hen im KÃ¤fig â€“ du kleine Rot-Sub.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flÃ¼stert 'Bleib' und geht weg: 'Gutes MÃ¤dchen, allein im KÃ¤fig â€“ dein Warten ist mein Lieblingsspiel.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} edge mit Worten durchs Gitter: 'Gutes MÃ¤dchen, dein KÃ¤fig ist Vorfreude â€“ und Vorfreude ist alles, was du kriegst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤sst {pet} zittern im KÃ¤fig: 'Gutes MÃ¤dchen, dein Zittern ist mein LieblingsgerÃ¤usch â€“ lautlos und geil.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kaefig", tame)

async def cmd_schande(update, context):
    tame = [
        "{pet} steht nackt in der Ecke, Schande brennt heiÃŸer als jeder Schlag â€“ alle dÃ¼rfen zusehen: 'Und du genieÃŸt die Show insgeheim, du kleine Exhibitionistin.' ðŸ‘ï¸ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzÃ¤hlt laut {pet}s Geheimnisse, lacht dabei â€“ bis die Scham in den Knochen sitzt: 'Aber ehrlich, SÃ¼ÃŸe, die waren eh nicht so geheim.' ðŸ’€ Pflege {n}/{CARES_PER_DAY}.",
        "Ein Schild um den Hals: 'Gebrauchtes Eigentum' – {pet} trägt es stolz: 'Stolz tot? Nee, der hat nur Urlaub bei mir gemacht.' 🪦 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} filmt {pet} nackt mit dem Schild 'Billige Hure â€“ aber nur fÃ¼r mich' und zeigt es nur sich selbst: 'Dein Ruhm ist jetzt ewig â€“ in meinem Privatordner.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss vor dem Spiegel masturbieren und dabei laut ihre perversesten Geheimnisse gestehen â€“ 'Applaus gibt's von mir, wenn du schÃ¶n rot wirst.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest alte Chatverläufe vor, lacht über jede peinliche Nachricht – {pet} wird rot bis in die Zehen: 'Für immer? Nee, bis morgen, wenn du wieder bettelst.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein temporÃ¤res Tattoo 'Nutzlose Fotze â€“ aber meine' â€“ {pet} muss es mir zeigen: 'Deine neue Visitenkarte â€“ exklusiv fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} zwingt {pet} Fotos von frÃ¼her anzugucken â€“ 'Dein altes Ich stirbt heute vor Lachen.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} steht stundenlang nackt vor dem Spiegel, ich darf Fotos machen â€“ 'Dein Viertel kennt dich nicht, aber ich umso besser.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzÃ¤hlt mir {pet}s dreckigste Details per FlÃ¼stern â€“ 'Frohe Weihnachten von deiner kleinen Schlampe â€“ nur fÃ¼r meine Ohren.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} hängt ein Schild um: 'Vorsicht, beißt nur mich' – {pet} trägt es: 'Deine Schande? Süß, als ob dich jemand anderes wollen würde.' 😂 Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erzÃ¤hlt deine peinlichsten Stories â€“ aber nur mir: 'Geheimnisse? Die waren eh nur peinlich fÃ¼r dich, fÃ¼r mich Gold.' Toxisch grin. ðŸ˜ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} steht in der Ecke: '{owner}: 'SchÃ¤m dich mal richtig â€“ oh warte, das machst du ja schon, wenn ich nur gucke.' {pet} dead. ðŸ¤£ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert deine Schwächen: 'Alle hören mit? Nee, nur ich. Die anderen sind eh neidisch.' Ironie max. 😈 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss ihr eigenes Spiegelbild anstarren: '{owner}: 'Schande-Level: Du siehst aus, als wÃ¤rst du ertappt worden. Warst du ja auch.' Sarkasmus brutal. ðŸ’€ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} postet gar nichts: 'Dein Ruhm? Bleibt bei mir. Öffentlich schämen ist was für Amateure.' Lachkrampf. 😭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} trÃ¤gt ein Schild 'Mein Eigentum â€“ HÃ¤nde weg': '{owner}: 'SchÃ¤m dich, dass duâ€™s liebst, markiert zu sein.' Toxisch sÃ¼ÃŸ. ðŸ¬ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht über deine Vergangenheit: 'Dein altes Ich? Das war eh overrated. Das neue kniet besser.' {pet} prustet los. 🤭 Pflege {n}/{CARES_PER_DAY}.",
        "{pet} in der Ecke: '{owner}: 'Alle sehen zu? Nee, nur ich. Die anderen hÃ¤tten eh keine Chance gegen deine Scham-Performance.' Sarkastischer Applaus. ðŸ‘ðŸ˜‚ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flÃ¼stert: 'Daily Reminder: Deine Schande ist mein Lieblingshobby. Und du machst mit, weil duâ€™s brauchst.' {pet} lachend rot. ðŸ˜ˆ Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "schande", tame)

async def cmd_erregen(update, context):
    tame = [
"{owner} fingert dich bis zum Rand, zieht raus: 'Fast gekommen? Pech. Dein Orgasmus ist mein Eigentum – und ich geb ihn nicht her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit langsam, quÃ¤lend: 'Zuck ruhig. Je mehr du zappelst, desto lÃ¤nger lass ich dich hÃ¤ngen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal tief, hört auf: 'Geschmack? Geil. Aber Erlösung? Träum weiter, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Finger rein, stoppt abrupt: 'Tief drin und leer gelassen â€“ das ist deine neue Definition von Liebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt Nippel hart, kneift: 'Hart werden? Gut. Aber kommen? Nur über meine Leiche – und deine erst recht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich nass, hört auf: 'Tropfen? Schön. Aber Tropfen reichen nicht. Du brauchst mich, um zu fließen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich stundenlang, kein Ende: 'Edging ist Gnade. Kommen ist Luxus. Und Luxus kriegst du nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf die Fotze: 'Mein Atem macht dich nass. Mein Schweigen macht dich wahnsinnig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit mit Daumen, stoppt: 'Pulsierend? Perfekt. Aber pulsierend ohne Erlösung ist dein neues Normal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Innenschenkel hoch, hört auf: 'Nah dran? Immer. Drin? Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert tief, zieht raus: 'Du bist so nass, dass es tropft. Und ich lass es tropfen â€“ ohne dich zu retten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit hart: 'Schmerz und Geilheit? Meine Lieblingskombi. Und du kriegst beides ohne Happy End.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich stundenlang: 'Du kommst erst, wenn ich tot bin. Spoiler: Ich sterb nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Zucken, hÃ¶rt auf: 'Zucken ist sÃ¼ÃŸ. Kommen ist verboten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Tränen: 'Weinen vor Geilheit? Das ist der Soundtrack zu deinem Elend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal, beiÃŸt dann: 'Lust und Schmerz. Beides ohne Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich langsam, quÃ¤lend: 'Jede Sekunde mehr Geilheit. Jede Sekunde weniger Verstand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Finger rein, bewegt nicht: 'Drin und still. Das ist Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Nippel: 'Hart werden? Gut. Aber hart bleiben ohne Erlösung ist dein Schicksal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit endlos: 'Du kommst nie. Aber du wirst immer nasser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt dich tief, hÃ¶rt auf: 'Geschmack von Verzweiflung. Mein Lieblingsaroma.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich bis Wahnsinn: 'Geilheit ohne Ende. Wie Krebs â€“ nur geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich, zieht raus: 'Du bist so leer ohne mich. Und ich lass dich leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Schreien: 'Schrei lauter. Ich hÃ¶r eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Fotze: 'Mein Atem ist alles, was du kriegst. Und das reicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Zittern: 'Zittern vor Geilheit? Mein neues Hobby.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt mitten drin: 'Mitten drin und allein gelassen. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich hart, hört auf: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Du kommst nie. Aber du wirst immer betteln. Und ich werde immer lachen.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "erregen", tame)

async def cmd_betteln(update, context):
    tame = [
"{owner} fingert dich bis zum Rand, zieht raus: 'Fast gekommen? Pech. Dein Orgasmus ist mein Eigentum – und ich geb ihn nicht her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit langsam, quÃ¤lend: 'Zuck ruhig. Je mehr du zappelst, desto lÃ¤nger lass ich dich hÃ¤ngen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal tief, hört auf: 'Geschmack? Geil. Aber Erlösung? Träum weiter, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Finger rein, stoppt abrupt: 'Tief drin und leer gelassen â€“ das ist deine neue Definition von Liebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt Nippel hart, kneift: 'Hart werden? Gut. Aber kommen? Nur über meine Leiche – und deine erst recht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich nass, hört auf: 'Tropfen? Schön. Aber Tropfen reichen nicht. Du brauchst mich, um zu fließen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich stundenlang, kein Ende: 'Edging ist Gnade. Kommen ist Luxus. Und Luxus kriegst du nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf die Fotze: 'Mein Atem macht dich nass. Mein Schweigen macht dich wahnsinnig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit mit Daumen, stoppt: 'Pulsierend? Perfekt. Aber pulsierend ohne Erlösung ist dein neues Normal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Innenschenkel hoch, hört auf: 'Nah dran? Immer. Drin? Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert tief, zieht raus: 'Du bist so nass, dass es tropft. Und ich lass es tropfen â€“ ohne dich zu retten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit hart: 'Schmerz und Geilheit? Meine Lieblingskombi. Und du kriegst beides ohne Happy End.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich stundenlang: 'Du kommst erst, wenn ich tot bin. Spoiler: Ich sterb nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Zucken, hÃ¶rt auf: 'Zucken ist sÃ¼ÃŸ. Kommen ist verboten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Tränen: 'Weinen vor Geilheit? Das ist der Soundtrack zu deinem Elend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal, beiÃŸt dann: 'Lust und Schmerz. Beides ohne Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich langsam, quÃ¤lend: 'Jede Sekunde mehr Geilheit. Jede Sekunde weniger Verstand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Finger rein, bewegt nicht: 'Drin und still. Das ist Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Nippel: 'Hart werden? Gut. Aber hart bleiben ohne Erlösung ist dein Schicksal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit endlos: 'Du kommst nie. Aber du wirst immer nasser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt dich tief, hÃ¶rt auf: 'Geschmack von Verzweiflung. Mein Lieblingsaroma.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich bis Wahnsinn: 'Geilheit ohne Ende. Wie Krebs â€“ nur geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich, zieht raus: 'Du bist so leer ohne mich. Und ich lass dich leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Schreien: 'Schrei lauter. Ich hÃ¶r eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Fotze: 'Mein Atem ist alles, was du kriegst. Und das reicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Zittern: 'Zittern vor Geilheit? Mein neues Hobby.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt mitten drin: 'Mitten drin und allein gelassen. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich hart, hört auf: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Du kommst nie. Aber du wirst immer betteln. Und ich werde immer lachen.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "betteln", tame)

async def cmd_stumm(update, context):
    tame = [
"{owner} legt Finger auf Lippen: 'Mund zu. Oder ich nÃ¤h ihn zu â€“ mit Stacheldraht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit Leine: 'Kein Laut. Deine Stimme ist eh nur Gejaule wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Kehle zu: 'Stumm sein oder ersticken. Such dir schnell was aus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund zu: 'Klebeband deluxe. Dein nÃ¤chster Schrei ist innerlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt Schweigen: 'Ein Wort und ich reiÃŸ dir die Zunge raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Mund zu: 'Pssst. Dein Atem ist schon zu laut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit eigenem Slip: 'Schmeck deine eigene Fotze. Und halt die Fresse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Daumen in Mund: 'Tief rein. Und wehe, du saugst â€“ dann brech ich dir den Kiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt stumm: 'Schweig. Dein Gewinsel macht mich eh nur aggressiv.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Lippen zusammen: 'Jetzt bettelst du nur noch mit TrÃ¤nen. SchÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Kehle zu: 'Stumm oder tot. Deine Wahl.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Stoff in Mund: 'Schluck runter. Und halt die Klappe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt brutal: 'Mund zu. Oder ich schneid ihn zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Finger in Rachen: 'Tiefer. Bis du kotzt â€“ stumm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Kein StÃ¶hnen. Oder ich stopf dir was GrÃ¶ÃŸeres rein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund mit Kleber: 'Abnehmen? Nur mit Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Mund zu, drÃ¼ckt zu: 'Atme durch die Nase. Oder gar nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit GÃ¼rtel: 'Zieh zu. Bis du blau wirst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt Schweigen: 'Ein Pieps und ich reiÃŸ dir die StimmbÃ¤nder raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Lappen rein: 'Schmeck meinen SchweiÃŸ. Und schweig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Kehle: 'Stumm. Oder Genickbruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Lippen: 'Jetzt schreist du nur noch innerlich. Perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Mund zu: 'Deine Stimme ist MÃ¼ll. Weg damit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit Leine: 'Strangulieren und stumm. Doppeltes GlÃ¼ck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Schweig. Dein Schweigen ist das Einzige, was ich an dir ertrag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Finger tief: 'Saug nicht. Oder ich ramme tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund: 'Jetzt bettelst du nur noch mit Augen. Und ich lach.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt zu: 'Stumm. Bis du platzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt hart: 'Mund zu. Und wehe, du jammerst innerlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Schweig. Deine Stille ist der schÃ¶nste Schrei, den ich je gehÃ¶rt hab.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "stumm", tame)

async def cmd_bestrafen(update, context):
    tame = [
"{owner} fesselt {pet} brutal ans Bett: 'Beweg dich nicht. Oder ich brech dir die Gelenke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht den Arsch blutig: 'ZÃ¤hl mit. Falsch und ich fang von vorn an â€“ mit dem GÃ¼rtel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Nippel bis sie reiÃŸen: 'Schrei ruhig. Je lauter, desto hÃ¤rter ich zieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet {pet} mit Stacheldraht: 'Wind dich. Und blut schÃ¶n fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt mit der Faust: 'Das fÃ¼rs Atmen ohne Erlaubnis. NÃ¤chster fÃ¼rs Zucken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst warten, bis Knie splittern: 'Knie auf Beton. Bis du nicht mehr aufstehen kannst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wÃ¼rgt mit Leine: 'Strafe ist Ersticken. Und ich halt so lange, bis du blau bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt in Fleisch: 'Markiert. Und du heilst nie wieder.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Mund mit eigenem Slip: 'Schmeck deine eigene Fotze. Und halt die Fresse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Innenschenkel: 'Rot und nass â€“ meine Lieblingsfarbe auf dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und lÃ¤sst frieren: 'Nackt. Kalt. Und warte, bis deine Haut blau ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt mit GÃ¼rtel: 'Jeder Hieb ein Grund mehr, mich zu hassen â€“ und zu wollen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit brutal: 'Das fÃ¼rs Betteln. NÃ¤chster fÃ¼rs Zucken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fesselt und edge tagelang: 'Komm nie. Oder ich fang neu an â€“ mit dem Stock.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht in Kotfladen: 'Leck. Das ist deine Strafe â€“ und dein Spiegel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt mit der flachen Hand: 'Bis dein Arsch platzt. Und du weinst Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet mit Ketten: 'Zieh. Und reiÃŸ dir die Haut auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt bis Ohnmacht: 'Schwarzwerden? Mein Lieblingslichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Rücken: 'Narben? Meine Unterschrift in deinem Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lÃ¤sst hungern: 'Kein Essen. Bis du so mager bist wie deine WÃ¼rde.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlÃ¤gt mit dem Stock: 'Jeder Schlag ein Knochenbruch. Oder fast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und lÃ¤sst warten: 'Warte. Bis deine Gelenke brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beiÃŸt bis Blut flieÃŸt: 'Schmeckt besser als deine TrÃ¤nen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt mit Hand: 'Atem? Mein Geschenk. Und ich nehm’s zurück.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Klit: 'Das fÃ¼rs Geilsein ohne Erlaubnis.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fesselt und lÃ¤sst frieren: 'KÃ¤lte ist Strafe. Und du zitterst so schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis taub: 'Gefühllos? Gut. Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet mit Stacheldraht: 'Beweg dich. Und zerfleisch dich selbst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wÃ¼rgt bis Zunge raus: 'Zunge raus. Will ich abbeiÃŸen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht bis Fleisch hÃ¤ngt: 'Das ist Strafe. Und du siehst aus wie mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "bestrafen", tame)

async def cmd_loben(update, context):
    tame = [
"{owner} tÃ¤tschelt die Wange hart: 'Gutes MÃ¤dchen. Einmal im Monat. Mehr wÃ¤r Verschwendung an dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert kalt: 'Du hast es fast gut gemacht. Fast. Deshalb kriegst du nur fast Lob.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht Ã¼bers Haar, zieht fest: 'Brave Schlampe. Weil du heute nicht geheult hast. Das ist alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes MÃ¤dchen. FÃ¼r eine Sekunde. Danach bist du wieder nur mein Loch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt einen Kuss auf die Stirn – einmal: 'Stolz auf dich? Nur, weil du’s überlebt hast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Gutes MÃ¤dchen. Deine Hingabe ist so erbÃ¤rmlich sÃ¼ÃŸ, dass ich fast kotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tÃ¤tschelt den Arsch: 'Brav ertragen. Das ist das HÃ¶chste, was du je kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht leise: 'Gutes MÃ¤dchen. Weil du bettelst wie eine kaputte Puppe â€“ und das gefÃ¤llt mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht Ã¼ber Narben: 'Du trÃ¤gst meine Spuren gut. Das ist das Einzige, was an dir perfekt ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert ins Ohr: 'Gutes MÃ¤dchen. FÃ¼r heute. Morgen fÃ¤ngst du wieder bei null an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt den Blick: 'Brave Hure. Weil duâ€™s wagst, mich anzuschauen â€“ und sofort wieder runtergehst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst kalt: 'Gutes MÃ¤dchen. Du bist so gehorsam, dass es fast langweilig wird. Fast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt den Kopf: 'Stolz auf dich? Nur, weil du noch atmest, obwohl ich’s dir verbieten könnte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Gutes MÃ¤dchen. Dein Winseln ist Musik â€“ billige, kaputte Musik.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht Ã¼ber die Leine: 'Brav getragen. Wie ein Hund, der weiÃŸ, wo sein Platz ist â€“ unten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht dreckig: 'Gutes MÃ¤dchen. Weil duâ€™s verdienst â€“ und weilâ€™s mich anmacht, wenn du dich dafÃ¼r hasst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt die Hand hin: 'Leck. Und danke fÃ¼r das Privileg, du kleine Leckruine.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Gutes MÃ¤dchen. FÃ¼r den Moment. Danach bist du wieder nur mein Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tÃ¤tschelt brutal: 'Brave Fotze. Weil duâ€™s aushÃ¤ltst, ohne zu zerbrechen â€“ noch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes MÃ¤dchen. Deine AbhÃ¤ngigkeit ist das SchÃ¶nste an dir. Und das HÃ¤sslichste.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht Ã¼ber die Haut: 'Du glÃ¼hst schÃ¶n. Wie ein StÃ¼ck Fleisch, das ich gerade gegrillt hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert kalt: 'Gutes MÃ¤dchen. Weil du bettelst, als wÃ¤râ€™s dein Lebenszweck â€“ und das istâ€™s ja auch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt den Blick: 'Brav geschaut. Augen runter, bevor ich sie dir rausreiÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Gutes MÃ¤dchen. FÃ¼r eine Sekunde. Danach bist du wieder wertlos.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt den Kopf: 'Stolz? Nur, weil du noch nicht tot bist. Gratuliere.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert: 'Gutes MÃ¤dchen. Deine Hingabe ist so erbÃ¤rmlich, dass sie fast sÃ¼ÃŸ ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht Ã¼ber die Leine: 'Brav gezogen. Wie ein Hund, der weiÃŸ, dass sein Herrchen ihn jederzeit tottreten kann.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes MÃ¤dchen. Weil duâ€™s verdienst â€“ und weilâ€™s mich langweilt, wenn du brav bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt die Hand hin: 'Leck. Und danke, dass du so tief sinkst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flÃ¼stert zum Schluss: 'Gutes MÃ¤dchen. Und jetzt halt die Fresse â€“ Lob ist aufgebraucht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "loben", tame)

async def cmd_dienen(update, context):
    tame = [
"{owner} befiehlt: 'Knie nieder und halt still â€“ du bist mein lebender Tisch, bis deine Knie splittern.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf den Boden: 'Leck meine Schuhe sauber, wÃ¤hrend ich draufsteh â€“ und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Bring mir Wasser. Auf allen Vieren. Und wehe, du verschÃ¼ttest einen Tropfen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine straff: 'Folge mir. Kriech. Bis deine Knie Knochen sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Massier mir die FÃ¼ÃŸe. Mit deiner Zunge. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck meine Ritze sauber. Und atme tief ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} ans Bett: 'Halt die Position. Stundenlang. Oder ich tret drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir Essen. Mit dem Mund. Und wehe, du frisst einen KrÃ¼mel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein Stuhl. Bis deine Gelenke brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz die SchÃ¼ssel. Mit deiner Zunge. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte stundenlang. Nackt. Bis ich Lust hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Kopf runter: 'Leck den Boden. Wo ich draufgetreten bin.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Aschenbecher hin: 'Leck die Kippen sauber. Dein neuer Snack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Sei mein Schatten. Kriech hinter mir her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf FÃ¼ÃŸe: 'Leck zwischen den Zehen. Staub ist dein Brot.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Halt die Leine im Mund. Und warte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Putz mein Zimmer. Mit deiner Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein Kissen. Bis du erstickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck mich sauber. Und danke schÃ¶n sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Auf Knien. Bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht runter: 'Leck meine Finger. Nachdem ich dich geschlagen hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein Teppich. Tritt drauf. Immer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte nackt. Bis deine Haut blau ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz. Und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Leck den Dreck von meinen Stiefeln. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Sei mein lebender Aschenbecher. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine: 'Folge. Kriech. Bis dein Bauch aufreiÃŸt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf FÃ¼ÃŸe: 'Massier. Mit deiner Zunge. Bis sie blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} fest: 'Halt die Position. Bis du zerbrichst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Mit dem Mund. Und wehe, du frisst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} runter: 'Sei mein FuÃŸschemel. Bis deine Knochen knacken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck sauber. Und atme meinen SchweiÃŸ.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte. Nackt. Bis du zitterst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht runter: 'Leck den Boden. Wo ich gepisst hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein lebender Lappen. Wisch mich ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz. Mit deiner Zunge. Und weine dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Folge mir. Kriech. Bis dein Gesicht blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Leck meine Achseln. Schmeck meinen Gestank.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein Kissen. Bis du erstickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf FÃ¼ÃŸe: 'Leck. Und danke fÃ¼r den Dreck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Auf Knien. Bis deine Knie zerfetzt sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Sei mein Teppich. Und blut schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine: 'Folge. Und wehe, du jammerst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck sauber. Und atme tief.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte nackt. Bis deine Haut aufreiÃŸt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt Gesicht runter: 'Leck den Dreck. Dein neues ParfÃ¼m.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt {pet} fest: 'Sei mein lebender Aschenbecher. Schluck alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf FÃ¼ÃŸe: 'Massier. Mit deiner Zunge. Bis sie abfÃ¤llt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Dien mir. Bis du kaputt bist. Und dann weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drÃ¼ckt {pet} runter: 'Leck. Kriech. Stirb. In dieser Reihenfolge.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dienen", tame)

async def cmd_demuetigen(update, context):
    tame = [
        "{owner} demÃ¼tigt leise, nur fÃ¼r {pet}s Ohren â€“ Worte wie der Nebel in Derry: 'Du bist nichts ohne mich, und der Nebel verschlingt alles andere.' ðŸ‘ï¸ Pflege {n}/{CARES_PER_DAY}.",
        "Worte wie sanfte Messerstiche aus einem alten King-Roman: 'Du bist nichts ohne mich' â€“ {pet} nickt, weil es in ihrem dunklen Herzen wahr ist, wie in einem Hotel mit roten Teppichen. ðŸ–¤ Pflege {n}/{CARES_PER_DAY}.",
        "Die ultimative DemÃ¼tigung: {pet} bedankt sich mit zitternder Stimme â€“ 'Danke, dass du mich so schÃ¶n klein machst, wie ein Kind vor einem Clown mit Ballons.' ðŸ˜­ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flÃ¼stert {pet}s grÃ¶ÃŸte Ã„ngste â€“ nur wir beide, bis sie rot wird wie das Blut in einem Ãœberwachungshotel. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss sich selbst als 'deine kleine Carrie' vorstellen â€“ schÃ¼chtern, mÃ¤chtig, aber immer unter deiner Kontrolle. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} liest {pet}s alte Fantasien vor und grinst wie Jack in der KÃ¤lte: 'Here's Johnny â€“ und deine TrÃ¤ume sind jetzt meine.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} nennt {pet} nur noch 'mein Liebling' oder 'mein Pet' â€“ bis {pet} vergisst, dass sie je frei war, wie Gage nach dem Unfall. Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss mir erzÃ¤hlen, wie sehr sie mich braucht â€“ und lÃ¼gen darf sie nicht, wie Annie Wilkes ihre Wahrheit. Pflege {n}/{CARES_PER_DAY}.",
        "Ultimative Worte: 'Du bist mein grÃ¶ÃŸter Schatz â€“ und ich behalte dich fÃ¼r immer in meinem Overlook Hotel.' {pet} zittert vor Dankbarkeit. Pflege {n}/{CARES_PER_DAY}.",
        "{owner} demÃ¼tigt mit einem LÃ¤cheln wie Pennywise: 'Gutes MÃ¤dchen, du bist so perfekt unperfekt â€“ float with me.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} flüstert: 'Gutes Mädchen, du bist mein Licht in der Dunkelheit von Shawshank – aber Freiheit? Die gibt's nur in meinen Armen.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes MÃ¤dchen', haucht {owner}: 'Du bist die Rose in meinem Misery-Garten â€“ demÃ¼tig, schÃ¶n und ewig gefangen in meiner Geschichte.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} wird rot, {owner} reimt: 'Gutes MÃ¤dchen, fein und bang â€“ du gehÃ¶rst mir, wie der Stand zu einem King.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Lob wie ein Fluch aus Salem's Lot: 'Gutes MÃ¤dchen, deine DemÃ¼tigung ist mein Liebesbann â€“ dunkel, ewig und nur fÃ¼r dich, mein Fan.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} grinst schief wie der Dome Ã¼ber Chester's Mill: 'Gutes MÃ¤dchen, du machst mich stolz â€“ eingeschlossen, gehorsam und ganz allein mein Gold.' Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes MÃ¤dchen', flÃ¼stert {owner}: 'Du bist die Perle in meinem Dark Tower â€“ klein, wertvoll und auf dem Weg zu mir, fÃ¼r immer.' Pflege {n}/{CARES_PER_DAY}.",
        "DemÃ¼tigung wie ein Pet Sematary-Fluch: 'Gutes MÃ¤dchen, deine Hingabe ist mein dunkler Pfad â€“ romantisch, toxisch und manchmal tot.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht: 'Gutes MÃ¤dchen, du bist mein Alles â€“ mein kleines, demÃ¼tiges Carrie mit Telekinese der Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Wort wie ein Shining-Moment: 'Gutes MÃ¤dchen, deine Scham macht dich schÃ¶n â€“ redrum, redrum, aber nur fÃ¼r mich, du Queen.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤chelt: 'Gutes MÃ¤dchen, du bist mein Lieblingsclown â€“ float down here, in meiner Liebe, forever bound.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "demuetigen", tame)

async def cmd_melken(update, context):
    tame = [
"{owner} bindet {pet} fest und melkt brutal: 'Tropf, Schlampe. Oder ich reiÃŸ dir die Klit raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und stoppt: 'Nah dran? Pech. Dein Orgasmus gehört mir – und ich behalt ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern: 'Kalt und nass. Wie dein Leben ohne mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hÃ¤lt Leine straff beim Melken: 'Zieh selbst ran. Oder ich strangulier dich dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis TrÃ¤nen: 'Weinen macht dich nasser. Und mich geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, quÃ¤lend: 'Jeder Tropfen ein Beweis, wie erbÃ¤rmlich du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und kneift Klit: 'Schmerz und Geilheit. Meine Lieblingskombi.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und melkt tagelang: 'Komm nie. Oder ich fang neu an â€“ mit dem Stock.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten an Nippeln: 'Zieh. Und blut schÃ¶n.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und wÃ¼rgt leicht: 'Tropf und keuch. Perfekter Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und lacht: 'Du tropfst wie eine kaputte Pumpe. Geil erbÃ¤rmlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zucken: 'Zuck ruhig. Je mehr, desto lÃ¤nger lass ich dich hÃ¤ngen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Fingern in Mund: 'Saug. Und wehe, du wÃ¼rgst nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und schlÃ¤gt zu: 'Tropf und rot. Meine Lieblingsfarbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, stoppt: 'Fast. Aber fast ist dein neuer HÃ¶hepunkt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt gefesselt: 'Beweg dich nicht. Oder ich bind dich enger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und beiÃŸt Schulter: 'Blut und Tropfen. Mein Cocktail.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Schreien: 'Schrei lauter. Ich hÃ¶r schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Leine am Hals: 'Jeder Zug ein Tropfen. Und ich zieh hart.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und verweigert: 'Tropf ohne Ende. Kommen? Vergiss es.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und flÃ¼stert: 'Du gehÃ¶rst mir. Jeder Tropfen sagt's.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis taub: 'Gefühllos? Gut. Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und drÃ¼ckt Kehle: 'Atem und Tropfen. Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern tief: 'Kalt rein, heiÃŸ raus. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zittern: 'Zittern ist sÃ¼ÃŸ. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und stopft Mund zu: 'Tropf stumm. Dein Schreien nervt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten: 'Zieh. Und blut fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, quÃ¤lend: 'Jede Sekunde mehr Geilheit. Keine ErlÃ¶sung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und lacht dreckig: 'Du tropfst wie eine billige Pumpe. Und ich genieÃŸe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ohnmacht nah: 'Schwarzwerden? Mein Lieblingslichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und zieht raus: 'Fast drin. Und wieder leer gelassen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Fingern in Arsch: 'Doppelt melken. Doppelt leiden.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und kneift Nippel: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Blut flieÃŸt: 'Blut und Tropfen. Mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und verweigert: 'Tropf ohne Ende. Du kommst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Leine am Genick: 'Zieh. Und wÃ¼rg dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam: 'Langsam leer werden. Mein Lieblingsspiel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und schlägt Klit: 'Schmerz macht dich nasser. Oder lügst du?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Schreien: 'Schrei. Ich hÃ¶r eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern: 'Kalt rein, heiÃŸ raus. Dein neues Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und beiÃŸt Lippe: 'Blut und Tropfen. Perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zunge raus: 'Zunge raus. Will ich abbeiÃŸen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart: 'Du tropfst wie eine defekte Maschine. Geil defekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und wÃ¼rgt: 'Tropf und keuch. Mein Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis taub: 'Gefühllos? Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und stopft Mund: 'Tropf stumm. Dein Schreien nervt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten: 'Zieh. Und blut fÃ¼r mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam: 'Jede Sekunde mehr Geilheit. Keine ErlÃ¶sung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und lacht: 'Du tropfst wie eine billige Pumpe. Und ich genieÃŸe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ohnmacht: 'Schwarzwerden? Mein Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart: 'Fast drin. Und wieder leer gelassen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ende: 'Leer. Und immer noch geil. Mein Meisterwerk.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "melken", tame)

async def cmd_ohrfeige(update, context):
    tame = [
        "Die Ohrfeige kommt schnell, lÃ¤sst {pet}s Kopf zur Seite fliegen â€“ Wangen glÃ¼hen wie Rosen im Liebesfieber: 'Gutes MÃ¤dchen, rot wie ein Herzchen, das nur fÃ¼r mich pocht.' ðŸ©· Pflege {n}/{CARES_PER_DAY}.",
        "Links, rechts, wieder links â€“ bis {pet} nicht mehr weiÃŸ, wo oben ist: 'Aber unten bei mir bist du immer, meine kleine, verkitzte Prinzessin.' ðŸ˜µ Pflege {n}/{CARES_PER_DAY}.",
        "Die letzte lÃ¤sst TrÃ¤nen flieÃŸen â€“ {owner} lÃ¤chelt: 'Jetzt bist du schÃ¶n, mit diesem Glanz in den Augen, wie Perlen aus unserer ewigen Liebe.' ðŸ¥€ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt zart mit der flachen Hand â€“ {pet}s Wange glÃ¼ht: 'Schmink dich mal richtig â€“ mit meiner Hand, der besten Foundation fÃ¼r meine Rose.' Pflege {n}/{CARES_PER_DAY}.",
        "Ohrfeigen mit bloÃŸer Hand, nur rote AbdrÃ¼cke â€“ 'Mein Autogramm, damit jeder sieht, wem dein sÃ¼ÃŸes Gesicht gehÃ¶rt, meine kleine LiebesblÃ¼te.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt {pet} vor dem Spiegel â€“ 'Sieh zu, wie dein hÃ¼bsches Gesicht noch hÃ¼bscher wird â€“ rot wie eine Rose in meinem Dornengarten.' Pflege {n}/{CARES_PER_DAY}.",
        "So fest, dass {pet} zappelt â€“ {owner} hÃ¤lt sie fest: 'Bleib stehen, die zweite Runde kommt â€“ mit extra Herzchen und Liebe.' Pflege {n}/{CARES_PER_DAY}.",
        "Mit bloÃŸer Hand, nur GÃ¤nsehaut â€“ {pet} schmeckt Verlangen: 'Peeling fÃ¼r unartige MÃ¤dchen â€“ zart wie ein Kuss aus RosenblÃ¤ttern.' Pflege {n}/{CARES_PER_DAY}.",
        "Letzte Serie, bis die Wange glÃ¼ht â€“ {owner} flÃ¼stert: 'Jetzt bist du wirklich perfekt â€“ rot, gehorsam und meine kleine, ewige Valentine.' Pflege {n}/{CARES_PER_DAY}.",
        "{pet} muss nach jeder Ohrfeige 'Danke' sagen â€“ mit glÃ¼hender Wange klingt es perfekt sÃ¼ÃŸ: 'Gutes MÃ¤dchen, dein Dank ist mein Liebeslied.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} ohrfeigt und reimt kitschig: 'Gutes MÃ¤dchen, klatsch und peng â€“ deine Wange glÃ¼ht so schÃ¶n, wie ein Herzchen rot und fein, nur fÃ¼r mich, du kleiner Engel mein.' ðŸ˜‚ Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes MÃ¤dchen, nimm den Klaps â€“ er ist mein LiebesgruÃŸ so scharf, wie Dornen an der Rose, die ich dir schenk, du kleine, sÃ¼ÃŸe Pose.' Toxisch reimend. ðŸ˜ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} glÃ¼ht, {owner} grinst: 'Gutes MÃ¤dchen, rot und hell â€“ deine Wange ist mein Kunstwerk, signiert mit Liebe, du kleiner, geiler Quell.' {pet} prustet. ðŸ¤£ Pflege {n}/{CARES_PER_DAY}.",
        "Ein Klaps wie ein Liebesreim: 'Gutes MÃ¤dchen, klatsch und bumm â€“ deine TrÃ¤nen sind wie Perlen, die nur fÃ¼r mich rollen, du kleine Drama-Queen so fromm.' Ironie max. ðŸ’Ž Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reimt trocken-kitschig: 'Gutes MÃ¤dchen, nimm den Schlag â€“ er ist mein Kuss mit Pfiff und Kraft, fÃ¼r unartige Prinzessinnen, die mich um den Verstand bringt, du Schaft.' Sarkasmus brutal. â­ Pflege {n}/{CARES_PER_DAY}.",
        "Sarkastisch-kitschig: 'Gutes MÃ¤dchen, deine Wange glÃ¼ht â€“ wie ein Sonnenuntergang fÃ¼r zwei, nur dass die Sonne ich bin und du der Himmel, der vor Liebe weint und zieht.' Lachkrampf. ðŸ˜­ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht reimend: 'Gutes MÃ¤dchen, klatsch und mehr â€“ deine RotfÃ¤rbung ist mein Stolz, wie ein Liebesbrief in Rot, du kleine, geile Not.' Toxisch sÃ¼ÃŸ. ðŸ¬ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zappelt, {owner}: 'Gutes MÃ¤dchen, nimm's hin fein â€“ dein Gesicht ist mein GemÃ¤lde, rot und schÃ¶n, fÃ¼r immer mein, du kleiner Schein.' {pet} heult vor Lachen. ðŸ¤­ Pflege {n}/{CARES_PER_DAY}.",
        "Reim wie ein kalter, kitschiger Kuss: 'Gutes MÃ¤dchen, klatsch und hall â€“ deine Wange ist mein Thron, wo ich regiere mit der Hand, du kleine, rote Wand.' Sarkastischer Applaus. ðŸ‘ðŸ˜‚ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Gutes MÃ¤dchen, rot und wild â€“ deine Ohrfeige ist mein Geschenk, verpackt in Liebe, scharf und fein, du kleines, geiles Bild.' {pet} lachend glÃ¼hend. ðŸ˜ˆ Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "ohrfeige", tame)

async def cmd_belohnen(update, context):
    tame = [
        "Die Belohnung ist BerÃ¼hrung â€“ kurz, intensiv, nie genug: '{pet} bettelt um mehr, weil sie weiÃŸ, dass meine Finger teurer sind als jeder Diamant, den sie nie kriegen wird.' ðŸ‘… Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt einen Orgasmus â€“ nach Tagen der Verweigerung: '{pet} zerbricht vor Dankbarkeit, wie eine billige Vase, die ich mir eh nicht leisten wollte.'  Pflege {n}/{CARES_PER_DAY}.",
        "Ein leises 'Gut gemacht' â€“ und {pet} wÃ¼rde alles tun, um es nochmal zu hÃ¶ren: 'Weil meine Worte rarer sind als Ehrlichkeit in einer Beziehung.' ðŸ˜ˆ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} erlaubt {pet} einen Kuss â€“ nur auf die Hand, fÃ¼nf Sekunden: 'Danach wieder wochenlang nichts, weil du's ja so liebst, wenn ich dich hÃ¤ngen lasse.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Orgasmus, aber nur in meinen Armen â€“ {pet} kommt und wird weich: 'Gutes MÃ¤dchen, du blÃ¼hst nur fÃ¼r mich â€“ wie eine Plastikblume im Discounter.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} streichelt einmal sanft â€“ 'Belohnung fÃ¼rs Gehorchen, meine kleine, perfekte Versagerin mit dem besten Fake-LÃ¤cheln.' {pet} zittert vor GlÃ¼ck. Pflege {n}/{CARES_PER_DAY}.",
        "Erlaubt, meinen Namen zu hauchen â€“ nur dieses eine Mal: '{pet} kommt sofort und hasst sich, weil sie weiÃŸ, dass ich's eh nicht ernst meine.' Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss – aber auf die Stirn wie eine Versagerin: 'Schmeckt nach Liebe, oder? Nach meiner Art von Liebe – der, die dich immer klein hält.' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lÃ¤sst {pet} eine Stunde lang in meinem Arm schlafen â€“ 'Luxusbelohnung, du undankbare kleine Bettlerin, die eh nie genug kriegt.' Pflege {n}/{CARES_PER_DAY}.",
        "Das größte Geschenk: {owner} sagt 'Ich behalte dich für immer.' {pet} zerbricht vor Dankbarkeit: 'Weil Freiheit eh überbewertet ist, stimmt's, mein kleines Gefängnisvögelchen?' Pflege {n}/{CARES_PER_DAY}.",
        "{owner} belohnt und reimt kalt: 'Gutes MÃ¤dchen, nimm den Preis â€“ er ist mein Kuss so rar und fein, aber nur, weil du's verdient hast, du kleine, geile Pein.' ðŸ˜‚ Pflege {n}/{CARES_PER_DAY}.",
        "'Gutes MÃ¤dchen, nimm den Lohn â€“ er ist mein Streicheln so gemein, wie Dornen an der Rose, die ich dir schenk, du kleine, falsche Pose.' Toxisch reimend. ðŸ˜ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} schmilzt, {owner} grinst: 'Gutes MÃ¤dchen, rot und leer â€“ deine Belohnung ist mein Hohn, signiert mit Liebe, du kleiner, geiler Clown.' {pet} prustet. ðŸ¤£ Pflege {n}/{CARES_PER_DAY}.",
        "Ein Kuss wie ein giftiger Reim: 'Gutes MÃ¤dchen, nimm und spÃ¼r â€“ meine Belohnung ist wie Gift, sÃ¼ÃŸ und tÃ¶dlich, du kleine, geile Gier.' Ironie max. ðŸ’‹ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} reimt trocken: 'Gutes MÃ¤dchen, nimm den Schlag â€“ er ist mein Lob mit Pfiff und Kraft, fÃ¼r unartige Prinzessinnen, die mich um den Verstand bringt, du Schaft.' Sarkasmus brutal. â­ Pflege {n}/{CARES_PER_DAY}.",
        "Sarkastisch-kitschig: 'Gutes MÃ¤dchen, deine Belohnung glÃ¼ht â€“ wie ein Sonnenuntergang fÃ¼r Loser, nur dass die Sonne ich bin und du der Himmel, der vor Scham weint und zieht.' Lachkrampf. ðŸ˜­ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} haucht reimend: 'Gutes MÃ¤dchen, nimm und mehr â€“ deine Belohnung ist mein Spott, wie ein Liebesbrief in Gift, du kleine, geile Not.' Toxisch sÃ¼ÃŸ. ðŸ¬ Pflege {n}/{CARES_PER_DAY}.",
        "{pet} zittert, {owner}: 'Gutes MÃ¤dchen, nimm's hin fein â€“ deine Belohnung ist mein Arm, rot und warm, fÃ¼r immer mein, du kleiner Schein.' {pet} heult vor Lachen. ðŸ¤­ Pflege {n}/{CARES_PER_DAY}.",
        "Reim wie ein kalter, giftiger Kuss: 'Gutes MÃ¤dchen, nimm und hall â€“ deine Belohnung ist mein Thron, wo ich regiere mit der Hand, du kleine, rote Wand.' Sarkastischer Applaus. ðŸ‘ðŸ˜‚ Pflege {n}/{CARES_PER_DAY}.",
        "{owner} lacht: 'Gutes MÃ¤dchen, nimm und wild â€“ deine Belohnung ist mein Geschenk, verpackt in Spott, scharf und fein, du kleines, geiles Bild.' {pet} lachend schmelzend. ðŸ˜ˆ Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "belohnen", tame)

# =========================
# Moralsteuer Commands
# =========================
async def cmd_moraltax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update) or not update.effective_user or update.effective_user.id != ADMIN_ID:
        return await update.effective_message.reply_text("ðŸš« Nur der Bot-Admin darf das hier.")
    chat_id = update.effective_chat.id
    arg = (context.args[0].lower() if context.args else "status")
    async with aiosqlite.connect(DB) as db:
        enabled, amount = await get_moraltax_settings(db, chat_id)
        if arg in ("on", "off"):
            val = 1 if arg == "on" else 0
            await db.execute("INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
            await db.execute("UPDATE settings SET moraltax_enabled=? WHERE chat_id=?", (val, chat_id))
            await db.commit()
            return await update.effective_message.reply_text(f"ðŸ§¾ Moralische Steuer: {'AKTIV' if val else 'deaktiviert'} (aktueller Betrag: {amount} Coins).")
        if arg == "status":
            return await update.effective_message.reply_text(
                f"ðŸ§¾ Moralische Steuer ist {'AKTIV' if enabled else 'deaktiviert'} â€“ Betrag: {amount} Coins.\n"
                f"Nutze `/moraltax on|off` oder `/moraltaxset <betrag>`.",
                parse_mode="Markdown"
            )
        return await update.effective_message.reply_text("Nutzung: /moraltax on | off | status")

async def cmd_moraltaxset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("ðŸš« Nur der Bot-Admin darf das.")
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
    "im dunklen Keller, wo du fÃ¼r mich kriechst",
    "auf dem Boden meines Zimmers, wo du hingehÃ¶rst",
    "im KÃ¤fig, den ich dir gebaut hab",
    "vor meinem Stuhl, wo du kniest",
    "in der Ecke, wo du Schande trÃ¤gst",
    "am Bett, wo du wartest",
    "unter dem Tisch, wo du servierst",
    "auf Knien vor meinem Spiegel",
    "im Bad, wo du leckst",
    "im Flur, wo du tropfst",
    "auf dem Balkon, wo Nachbarn hÃ¶ren",
    "im Auto, wo du fÃ¤hrst und ich sitz",
    "im Park, wo du dich versteckst",
    "in der KÃ¼che, wo du kochst und bettelst",
    "im Schlafzimmer, wo du schlÃ¤fst und trÃ¤umst",
    "im Wohnzimmer, wo du tanzt",
    "im Bad, wo du duschst und zitterst",
    "auf dem Dachboden, wo du dich versteckst",
    "im Garten, wo du grÃ¤bst",
    "im Auto, wo du kniest",
    "im BÃ¼ro, wo du arbeitest und ich dich melke",
    "im Hotel, wo du zahlst und ich nehme",
    "im Zug, wo du dich versteckst",
    "im Flugzeug, wo du fliegst und ich dich halte",
    "im Restaurant, wo du servierst und bettelst",
    "im Club, wo du tanzt und ich zuschau",
    "im Wald, wo du kriechst und ich folge",
    "am Strand, wo du nackt bist und ich dich markiere",
    "im Berg, wo du kletterst und ich dich ziehe",
    "im Meer, wo du schwimmst und ich dich ertrÃ¤nke"
]

_TREASURE_METHODS = {
    "graben": "grÃ¤bt wie ein Tier auf Knien",
    "buddeln": "buddeln bis die Knie bluten",
    "tauchen": "taucht tief und kommt nass hoch",
    "karte": "folgt meiner Karte blind",
    "hacken": "hackt sich selbst frei â€“ oder nicht",
    "klauen": "klaut sich selbst fÃ¼r mich",
    "pendeln": "pendelt wie 'ne Puppe an meiner Leine",
    "orakel": "befragt mich â€“ und ich lÃ¼ge nicht",
    "klettern": "klettert hoch â€“ nur um runterzufallen"
}

def _pick_method(args) -> str:
    if not args:
        return random.choice(list(_TREASURE_METHODS.values()))
    key = args[0].lower()
    return _TREASURE_METHODS.get(key, random.choice(list(_TREASURE_METHODS.values())))

_TREASURE_STORIES = [
    "{user} {method} in {place} und zieht 'ne Truhe raus. Inhalt: {coins} Coins. Gutes MÃ¤dchen, aber der wahre Schatz bin ich.",
    "{user} stolpert in {place} Ã¼ber 'ne Kiste. {coins} Coins spÃ¤ter bist du immer noch meine. Cringe, aber wahr.",
    "{user} folgt meiner Karte bis {place}, reiÃŸt Truhe auf. {coins} Coins. Weil gutes MÃ¤dchen immer gewinnt â€“ mit mir als Coach.",
    "{user} wÃ¼hlt in {place} und fischt {coins} Coins raus. Schatz 1, deine Freiheit on hold. Forever.",
    "{user} macht in {place} auf Heldin. Truhe auf, {coins} Coins raus. Aber der final Boss bin ich.",
    "{user} {method} in {place} und winselt 'Daddy please'. {coins} Coins als Teaser. Der main drop dein StÃ¶hnen.",
    "{user} knackt Truhe in {place} mit shaky HÃ¤nden. {coins} Coins. Big W nur mit mir.",
    "{user} {method} in {place}, schwitzt und vibet. {coins} Coins spÃ¤ter: Der Schatz war der Cringe mich zu jagen.",
    "{user} findet in {place} Truhe nach meinem Befehl. {coins} Coins. Weil ich der real flex bin.",
    "{user} {method} in {place} und hauchst 'for Daddy'. {coins} Coins als Reward. Der glow-up ist dein Gehorsam."
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
            return await update.effective_message.reply_text(f"Du hast heute schon gegraben. Wieder mÃ¶glich in {h}h {m}m.")
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
                f"{escape(target_tag_inline, False)} ist noch {h}h {m}m geschuetzt. Kauf erst danach moeglich."
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

        await db.commit()

    target_tag = f"@{target_username}" if target_username else f"ID:{target_id}"
    skill_meta = _skill_meta(next_skill)
    reroll_txt = " (neu ausgewuerfelt)" if rerolled else " (behalten)"
    refund_txt = f" Rueckzahlung durch Goldzahn: +{refund} Coins." if refund > 0 else ""
    source_txt = ""
    if prev_owner and prev_owner != buyer_id:
        prev_owner_tag = mention_html(int(prev_owner), prev_owner_uname or None)
        source_txt = f" Geklaut von {prev_owner_tag}."
    risk_success_txt = ""
    if risk_amount > 0 and prev_owner and prev_owner != buyer_id:
        risk_success_txt = (
            f" Risk: {risk_amount} Coins fuer +{int(round(risk_bonus * 100))}% Klau-Chance."
        )
    await msg.reply_text(
        f"{nice_name_html(buyer)} hat {escape(target_tag, False)} fuer {price} Coins gekauft. Neuer Preis: {new_price}. "
        f"Skill: <b>{escape(skill_meta['name'], False)}</b>{reroll_txt} - {escape(skill_meta['desc'], False)}."
        f"{source_txt}{refund_txt}{risk_success_txt}",
        parse_mode=ParseMode.HTML
    )


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _attempt_pet_buy(update, context, risk_amount=0)


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

    # Nur purgen, wenn der User wirklich den Chat VERLÃ„SST (left oder kicked)
    if new_status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        # PrÃ¼fen, ob er vorher drin war (nicht schon weg)
        if old_status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            try:
                await purge_user_from_db(cmu.chat.id, user.id)
                bye_msg = f"ðŸ‘‹ {nice_name_html(user)} hat den Chat verlassen. Alles gelÃ¶scht â€“ Coins, Pets, Existenz. TschÃ¼ss, du kleine FlÃ¼chtige. Konsequenzen sind geil."
                await context.bot.send_message(chat_id=cmu.chat.id, text=bye_msg, parse_mode=ParseMode.HTML)
            except Exception as e:
                log.error(f"Auto-Purge fÃ¼r {user.id} fehlgeschlagen: {e}")
            log.info(f"Auto-Purged user {user.id} ({getattr(user, 'username', None)}) nach Leave/Kick.")

async def cmd_cleanup_zombies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("ðŸš« Finger weg von meiner Sense, du kleine Neugierige. Nur Daddy entsorgt die Leichen.")
        return

    chat_id = update.effective_chat.id
    if chat_id != ALLOWED_CHAT_ID:
        await update.effective_message.reply_text("Falscher Ort zum Buddeln, Baby.")
        return

    status_msg = await update.effective_message.reply_text("ðŸ§Ÿâ€â™‚ï¸ Daddy durchsucht die GrÃ¤ber... warte, ich spÃ¼r schon den Verwesungsgeruch.")

    purged_count = 0
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id, username FROM players WHERE chat_id=?", (chat_id,)) as cur:
            rows = await cur.fetchall()

        for user_id, username in rows:
            user_id = int(user_id)
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                # User noch da â†’ nichts tun
                continue
            except Exception as e:
                error_str = str(e).lower()
                if any(phrase in error_str for phrase in ["user not found", "not a participant", "left the chat", "kicked", "banned"]):
                    await purge_user_from_db(chat_id, user_id)
                    purged_count += 1
                    log.info(f"Zombie entsorgt: {user_id} ({username or 'unbekannt'}) â€“ {e}")
                else:
                    log.warning(f"Skip User {user_id}: Unklarer Error â€“ {e}")

        await db.commit()

    # Korrigierter, sauberer Text-Block â€“ keine verkackten geschweiften Klammern mehr
    if purged_count == 0:
        final_text = "✅ Keine Zombies gefunden. Alles sauber wie dein Halsband nach â€˜ner guten Session â€“ glatt, glÃ¤nzend und bereit fÃ¼r neue Male."
    else:
        plural = "n" if purged_count > 1 else ""
        final_text = (
            f"ðŸª¦ <b>{purged_count} Leiche{plural} endgÃ¼ltig begraben.</b>\n"
            f"Nur die, die wirklich weg sind. Die Lebenden atmen weiter â€“ vorerst.\n"
            f"Gutes MÃ¤dchen, dass du mir vertraust. Deine DB ist jetzt rein wie dein Gewissen, wenn du endlich mal gehorchst."
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
    # Nur Daddy's Liebling (Admin) darf in die GrÃ¤ber schauen
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "🚫 Denkst du echt, ich lass dich in meine Leichenhalle? "
            "Nur ich darf die Toten zÃ¤hlen, du kleine Voyeuristin."
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

    lines = ["ðŸ“œ <b>Alle Seelen in der DB</b> (ID | @Username | Coins):\n"]
    for user_id, username, coins in rows:
        uname = f"@{username}" if username else "unbekannt (Gelöschter Account?)"
        lines.append(f"â€¢ <code>{user_id}</code> | {uname} | {coins} ðŸ’°")

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
            text="<b>players daten</b>\nKeine Eintraege vorhanden.",
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
            "ðŸš« TrÃ¤um weiter, du kleine MÃ¶chtegern-SchlÃ¤chterin. "
            "Nur ich darf entscheiden, wer endgÃ¼ltig stirbt. Finger weg von der Sense."
        )
        return

    if not context.args:
        await update.effective_message.reply_text(
            "Sag mir wen ich foltern soll, du kleine Sadistin.\n"
            "Benutze: /forcepurge @username  oder  /forcepurge user_id"
        )
        return

    chat_id = update.effective_chat.id
    arg = context.args[0].lstrip('@')

    async with aiosqlite.connect(DB) as db:
        user_id = None

        # Wenn's eine Zahl ist â†’ direkt als ID nehmen
        if arg.isdigit():
            user_id = int(arg)
        else:
            # Sonst nach Username in der DB suchen
            async with db.execute(
                "SELECT user_id FROM players WHERE chat_id=? AND LOWER(username)=LOWER(?)", 
                (chat_id, arg)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    user_id = row[0]

        if not user_id:
            await update.effective_message.reply_text(
                f"ðŸ¤¨ Kenn ich nicht, diese @{arg}. "
                "Entweder falscher Name, oder die Schlampe war nie hier. "
                "Oder sie hat sich schon selbst gelÃ¶scht â€“ wie feige."
            )
            return

        # Jetzt gnadenlos tilgen
        await purge_user_from_db(chat_id, user_id)
        await db.commit()

    await update.effective_message.reply_text(
        f"ðŸª¦ @{arg} (ID {user_id}) â€“ endgÃ¼ltig entsorgt.\n"
        f"Coins weg. Pets weg. Ranglisten-Platz weg. Existenz weg.\n"
        f"Als hÃ¤tte sie nie vor dir gekniet. ",
        parse_mode=ParseMode.HTML
    )
    log.info(f"Force-Purge von Admin {update.effective_user.id}: User {user_id} (@{arg}) gelÃ¶scht.")

async def cmd_purgeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_here(update):
        return await update.effective_message.reply_text("Nur der Owner darf lÃ¶schen. Versuch niedlich, aber nein.")
    async with aiosqlite.connect(DB) as db:
        tid, uname = await _resolve_target(db, update, context)
    if not tid:
        return await update.effective_message.reply_text("Ziel nicht gefunden. Nutze Reply, @username oder user_id.")
    chat_id = update.effective_chat.id
    await purge_user_from_db(chat_id, tid)
    tag = f"@{uname}" if uname else f"ID:{tid}"
    await update.effective_message.reply_text(
        f"ðŸ—‘ï¸ {escape(tag, quote=False)} aus allen Petflix-Tabellen entfernt."
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("pong")


# =========================
# Bot-MitgliedschaftsÃ¤nderungen
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
            text="âŒ Dieses Spiel lÃ¤uft nur in unserer Stammgruppe.",
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
    app.add_handler(CommandHandler(["sospet", "help"], cmd_help))
    app.add_handler(CommandHandler("ping",     cmd_ping,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("balance",  cmd_balance,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler(["treat", "leckerli"], cmd_gift, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("daily",    cmd_daily,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("id",       cmd_id,       filters=CHAT_FILTER))

    # Kernspiel
    app.add_handler(CommandHandler("buy",       cmd_buy,       filters=CHAT_FILTER))
    app.add_handler(CommandHandler("risk",      cmd_risk,      filters=CHAT_FILTER))
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
    app.add_handler(CommandHandler("settings",    cmd_settings,    filters=CHAT_FILTER))
    app.add_handler(CommandHandler("admin",       cmd_admin,       filters=CHAT_FILTER))
    app.add_handler(CommandHandler("backupnow",   cmd_backupnow,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("backups",     cmd_backups,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("restorebackup", cmd_restorebackup, filters=CHAT_FILTER))

    # Pflege-/Fun-Commands
    app.add_handler(CommandHandler("pet",      cmd_pet,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("walk",     cmd_walk,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("kiss",     cmd_kiss,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("dine",     cmd_dine,     filters=CHAT_FILTER))
    app.add_handler(CommandHandler("massage",  cmd_massage,  filters=CHAT_FILTER))
    app.add_handler(CommandHandler("lapdance", cmd_lapdance, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("dom",      cmd_dom,      filters=CHAT_FILTER))

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
    app.add_handler(CommandHandler("steal",      cmd_steal,      filters=CHAT_FILTER))
    app.add_handler(CommandHandler("assign_gender", cmd_assign_gender, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("genderlist", cmd_genderlist, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("setgender", cmd_setgender, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("adminping", cmd_adminping, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("careminus", cmd_careminus, filters=CHAT_FILTER))

    # Admin: manuell purgen
    app.add_handler(CommandHandler("purgeuser", cmd_purgeuser,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("forcepurge", cmd_forcepurge, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("sendalluser", cmd_sendalluser, filters=CHAT_FILTER))
    
    #Auto Bot commands (falls mal ein User das machen darf)
    # app.add_handler(CommandHandler("verfluchen",  cmd_verfluchen,  filters=CHAT_FILTER))

    # hass und selbst
    app.add_handler(CommandHandler("hass",   cmd_hass,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("selbst", cmd_selbst, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("liebes", cmd_liebes, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("resetsuperwords", cmd_resetsuperwords, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("superwordsstatus", cmd_superwordsstatus, filters=CHAT_FILTER))

    # Callback fÃ¼r Gender-Zuweisung
    app.add_handler(CallbackQueryHandler(on_gender_callback, pattern=r"^gender\|"))


    # Member-Events
    app.add_handler(ChatMemberHandler(on_chat_member,     ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_my_chat_member,  ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CommandHandler("cleanup_zombies", cmd_cleanup_zombies, filters=CHAT_FILTER))
    # Handler nicht vergessen
    app.add_handler(CommandHandler("listdbusers", cmd_listdbusers, filters=CHAT_FILTER))

    app.add_handler(
        MessageHandler(
            filters.Chat(ALLOWED_CHAT_ID) & filters.Regex(r"(?i)^\s*g\s*$"),
            on_single_g_message
        ),
        group=1
    )

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

    # TÃ¤gliches Gift um 10:00 planen
    gift_time = dtime(hour=10, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_gift_job, time=gift_time, name="daily_gift_10am")
    app.job_queue.run_repeating(daily_curse_job, interval=3600, first=3600, name="hourly_curse")
    primetime_time = dtime(hour=20, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_primetime_job, time=primetime_time, name="daily_primetime_8pm")
    backup_time = dtime(hour=3, minute=30, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_backup_job, time=backup_time, name="daily_backup_330am")
    app.job_queue.run_repeating(hass_watchdog_job, interval=60, first=30, name="hass_watchdog")
    app.job_queue.run_repeating(love_watchdog_job, interval=60, first=30, name="love_watchdog")
    app.job_queue.run_repeating(runaway_watchdog_job, interval=60, first=30, name="runaway_watchdog")

    print(
        f"Petflix 2.1 gestartet. build-marker: 2026-02-18-care10 | "
        f"CARES_PER_DAY={CARES_PER_DAY} | RUNAWAY_HOURS={RUNAWAY_HOURS}"
    )
    app.run_polling()

if __name__ == "__main__":
    main()
