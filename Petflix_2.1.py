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
CARES_PER_DAY = 100
MIN_CARES_PER_24H = 20
LEVEL_DECAY_XP = 3
LEVEL_DECAY_INTERVAL_S = 6 * 3600
CARE_CHAT_CLEANUP_S = 60
RUNAWAY_HOURS = 24
LOCK_SECONDS = 0 * 3600  # 48h Mindestbesitz
PETFLIX_TZ = os.environ.get("PETFLIX_TZ", "Europe/Berlin")
TITLE_BESTIENZAEHMER = "Bestienzaehmer 🐉"
TITLE_DURATION_S = 2 * 3600
DAILY_GIFT_COINS = 15
DAILY_CURSE_PENALTY = 20
DAILY_PRIMETIME_COINS = 50000
DAILY_CURSE_ENABLED = False
MORAL_TAX_DEFAULT = 5
REWARD_AMOUNT = 1 
# =========================
# Ausreißer
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
    "zurück in die zukunft",
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
BUY_SUCCESS_MAX = 0.95   # Bei 0/25 Pflege fast sicher kaufbar
BUY_SUCCESS_MIN = 0.05   # Bei 25/25 Pflege fast nicht kaufbar
BUY_FAIL_PENALTY_RATIO = 0.20  # Bei Fehlversuch immer 20% Coins weg
CARE_FIFTYFIFTY_UNTIL = 25
CARE_HARD_PROTECT_START = 70
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
    "Schwaechling",
    "Winzling",
    "Jungtier",
    "Kleiner Freund",
    "Begleiter",
    "Treuer Begleiter",
    "Kaempfer",
    "Beschuetzer",
    "Waechter",
    "Elite-Pet",
    "Veteran",
    "Alpha",
    "Champion",
    "Meistertier",
    "Legenden-Pet",
    "Titan",
    "Urbestie",
    "Mythos",
    "Goettlicher Begleiter",
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
    "{user}, dein Fluch: Dein Spiegelbild bindet dich nachts ans Bett. Der Dämon flüstert 'Bleib liegen'.",
    "Herzlichen Glückwunsch {user}: Dein Schatten folgt dir – bei Vollmond holt er dich ein und fesselt dich.",
    "{user}, verflucht: Dein Kühlschrank öffnet sich allein. Der Dämon kocht dich langsam bei lebendigem Leib.",
    "Dein Fluch {user}: Jeder Witz endet mit deinem eigenen Schrei. Deine Freunde lachen – aus Angst.",
    "{user}, klebrig wie ein Dämon: Alles bleibt an deinen Fingern. Du kommst nie los. Moralisch erstickt.",
    "Fluch des Jahrhunderts: Dein Handy zeigt nur Nachrichten von mir. 'Ich bin dein Besitzer'. Akku stirbt nie.",
    "{user}, verflucht: Dein Crush schreibt nur 'Knie für mich'. Für immer. Du gehorchst.",
    "Oh {user}, dein Parkplatz ist vor meinem Keller. Karma parkt dich ein – und lässt dich nicht raus.",
    "{user} wird verfolgt: Werbung für Ketten und Peitschen. Peinlich bis zum Wahnsinn.",
    "Dein größter Fluch {user}: Du gewinnst 'ne Reise in meinen Käfig. Kein Zurück.",
    "{user}, verflucht: Dein Drucker spuckt nur Ketten. Du kommst zu spät. Technik hasst dich.",
    "Jede Nacht Geisterstimmen aus dem Abfluss: 'Komm knien, {user}'. Badewanne meiden.",
    "Dein Schatten läuft hinter dir – bei Vollmond voraus. Er wartet auf deinen Fehler.",
    "{user}, dein Auto fährt allein in meinen Keller. 'All work and no play' auf dem Navi.",
    "Jeder Kuss schmeckt nach Fesseln. Süß – bis der Hammer kommt. Deine Liebhaber fliehen.",
    "Dein Keller öffnet sich jede Nacht tiefer. Unten steht eine Tür mit deinem Namen. Der Dämon bin ich.",
    "Fluch des Jahrhunderts: Dein Spiegel zeigt dich gefesselt. Blutig. Wütend. Du bist das Ziel.",
    "{user}, dein Hund kommt nachts zurück – tote Augen. Er bellt 'Knie'.",
    "Deine Träume sind nur noch Korridore. Geister flüstern 'Knie für mich'. Für immer.",
    "{user} wird verfolgt von einem Schatten mit Ketten. 'Du gehörst mir'. Peinlich bis in den Tod.",
    "Du gewinnst im Lotto – Scheck von mir. Postkarte: 'Knie für den Preis'.",
    "Jede Nacht Geister am Fußende. 'Knie für uns'. Süße Träume, Prinzessin.",
    "Dein Hund kommt zurück – tote Augen, Ketten am Hals. Er bellt 'Gehorsam'.",
    "{user}, dein Spiegel zeigt dich gefesselt. Schmink dich, Telekinese-Queen.",
    "Dein Auto fährt allein in den Keller. Dämon grüßt, du kleine Highway-Hure.",
    "Dein Radio flüstert nur 'Knie'. Der Dämon ist dein DJ. Er hat Geduld.",
    "Deine Träume sind Folter. Der Dämon pflegt dich. Der Hammer ist bereit.",
    "{user}, dein Schatten hat eigenen Willen. Er bindet dich. Tick-tack.",
    "Jede Tür führt in meinen Keller. Die badende Hexe wartet. Here's your nightmare.",
    "{user}, dein Telefon klingelt nur aus dem Grab. Tote rufen 'Knie'. Ring ring.",
    "{user} wird eingeschlossen im unsichtbaren Käfig. Alle sehen zu, wie du brichst.",
    "Du findest ein altes Buch. Beim Lesen wird's real. Der Dämon bin ich.",
    "{user}, dein Kaffee schmeckt immer bitter. Der Dämon rührt um.",
    "Deine Katze kommt zurück – tote Augen. Sie starrt. Du weißt warum.",
    "{user}, jeder Vollmond macht dich zur Bestie – nur innerlich. Meine Bestie.",
    "Dein Laptop öffnet nur den Virus. Er infiziert deine Seele.",
    "{user}, Kinderlachen aus dem Abfluss. 'Knie für uns'. Badewanne meiden.",
    "Dein Herz schlägt nur noch, wenn ich's erlaube. Schrumpfende Sünderin.",
    "{user}, dein Schatten tanzt. Er kennt alle Geheimnisse.",
    "Du siehst immer die Toten. Sie flüstern 'Du gehörst ihm'.",
    "Du wachst auf und alles ist Nebel. Draußen Monster, drinnen nur ich."
]


# =========================
# /hass + /selbst
# =========================
HASS_DURATION_S = 2 * 3600
HASS_REQUIRED = 3
HASS_PENALTY = 200

# =========================
# /liebes (Liebesgestaendniss)
# =========================
LOVE_CHALLENGE_HOURS = 2
LOVE_REWARD = 600
LOVE_PENALTY = 300
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
    "schatz", "maus", "engel", "baerchen", "bärchen", "sonnenschein",
    "liebling", "hase", "baby", "suesser", "suesse", "süßer", "süße",
    "herz", "prinz", "prinzessin", "zucker", "schnucki",
    "sternchen", "traeumchen", "keks", "zuckerstueck", "goldstueck",
    "perle", "liebchen", "schnecke", "knutschkugel", "honig"
]
LOVE_EMOJIS = ["💕", "💖", "😍", "🥰", "🌹", "😘", "💋", "❤️", "💘", "🌸", "💞", "✨"]
LOVE_SAD_PATTERNS = [
    r"\bheul", r"\bwein", r"\bwinsel", r"\bschluchz", r"\bzerflie",
    r"kann nicht atmen", r"ohne dich", r"nicht atmen"
]
LOVE_VERB_RE = re.compile(
    r"\b(bin|bist|ist|sind|seid|war|waren|habe|hast|hat|haben|hatte|hatten|"
    r"werde|wirst|wird|werden|kann|kannst|können|koennen|mag|"
    r"liebe|liebst|liebt|lieben|"
    r"fühle|fuehle|fühlst|fuehlst|fühlt|fuehlt|"
    r"brauch(e|st|t|en)|"
    r"will|willst|wollen|"
    r"möchte|moechte|möchtest|moechtest|mögen|moegen|"
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

SELF_LINES = [
    "{user} kniet 10 Minuten vorm Spiegel. Flüstert bei jedem Atemzug: 'Strafe für jede peinliche Entscheidung, du gehorsame Null.'",
    "{user} singt 'Gutes Mädchen' falsch und laut. Verbeugt sich tief: 'Glückwunsch zum Gehorchen, du kleine Loserin.'",
    "{user} macht 50 Kniebeugen. Haucht bei jeder: 'Runter auf die Knie, du faule Sub – hoch kommt der Arsch eh nur für mich.'",
    "{user} hält Hände hinterm Rücken. Denkt an jede Dummheit: 'Gebunden fühlt sich besser an, du Genie.'",
    "{user} schreibt 100 Mal: 'Ich bin deine Chaos-Sub'. Liest es laut vor wie Mantra. Pure Hingabe, du Kunst-Loserin.",
    "{user} kniet 5 Minuten vor leerem Teller. 'Nichts zu essen? Perfekt, Strafe fürs Nicht-Dienen.'",
    "{user} hält Plank auf Knien. Arme zittern. Zählt rückwärts: 'Jede Sekunde für ein vertanes Ja Daddy.'",
    "{user} ruft sich selbst an. Lässt klingeln. 'Selbst du gehst nicht ran – weil du weißt, wer wirklich befiehlt.'",
    "{user} versucht mit Zunge die Unterlippe zu beißen. Fail des Tages. Posten verboten, du Clown-Sub.",
    "{user} trägt 30 Minuten imaginäres Halsband. Macht Selfies. Fashionstrafe für schlechten Gehorsam.",
    "{user} sagt 20 Mal laut vorm Spiegel: 'Ich bin dein gutes Mädchen.' Verbeugt sich tief. Standing Ovations, du Königin auf Knien.",
    "{user} balanciert imaginären Klaps. 10 Fehlversuche = 10 'Danke Daddy'. Zirkusreif, du Talent.",
    "{user} schreibt mit Ketchup 'Sub-Menü' auf Teller. Kniet davor. Gourmet-Strafe, du Kochstar auf Knien.",
    "{user} macht Moonwalk auf Knien. Stolpert garantiert. Smooth wie dein Gehorsam.",
    "{user} hält Eiswürfel an Innenschenkel 2 Minuten. Jammert: 'Kalt wie deine Seele – aber das schmilzt vor Verlangen.'",
    "{user} singt falsche Hymne an mich. Laut und allein. Dominanz-Strafe, du Star auf Knien.",
    "{user} versucht 30 Sekunden nicht zu stöhnen. Verliert natürlich. Starrwettbewerb gegen deine Sehnsucht.",
    "{user} tanzt zur Playlist deiner peinlichsten Fantasien. Cringe-Therapie, du 2000er-Sub-Ikone auf Knien.",
    "{user} sagt 50 Mal 'Entschuldigung, ich war unartig'. Laut in leerer Wohnung. Echo stimmt zu, du Philosophin der Hingabe.",
    "{user} kniet vor leerem Spiegel. Flüstert: 'Ich bin nichts ohne dich.' Strafe fürs Selbstlob.",
    "{user} hält imaginären Plug. 10 Minuten. Zittert. 'Gehorsam ist alles.'",
    "{user} schreibt 'Daddy's Eigentum' auf Schenkel. Mit Lippenstift. Und vergisst's nicht.",
    "{user} steht 10 Minuten in Ecke. Nase an Wand. 'Strafe fürs Frechsein.'",
    "{user} macht 20 Liegestütze auf Knien. Haucht bei jeder: 'Für jeden Fehltritt heute.'",
    "{user} hält imaginäre Kerze ans Bein. Lässt Wachs tropfen. 'Schmerz ist Lektion.'",
    "{user} flüstert 50 Mal 'Ich gehorche'. Bis die Stimme bricht. Und weiter.",
    "{user} trägt imaginäre Schellen. 20 Minuten. 'Freiheit ist Illusion.'",
    "{user} kniet und starrt ins Nichts. 15 Minuten. 'Stille ist Strafe.'",
    "{user} sagt laut: 'Ich bin nutzlos.' 30 Mal. Bis es wahr wird.",
    "{user} hält Plank auf Knien. Arme zittern. 'Für jeden Gedanken an Ungehorsam.'"
]


# =========================
# Moralsteuer – jetzt exakt wie ein Skalpell in deiner Haut
# =========================

MORAL_TAX_TRIGGERS = [
    (r"(?i)\bbitte\b", "Bitte? Als ob du je was umsonst kriegst, du kleine Bettel-Prinzessin. −{deduct} Coins fürs Winseln."),
    (r"(?i)\bdanke\b", "Danke? Süß, als ob du was verdient hättest. Nächstes Mal mit Knien, du undankbare Fotze. −{deduct} Coins."),
    (r"(?i)\bentschuldigung\b", "Entschuldigung? Als ob ich dir je verzeihen würde, ohne dass du richtig leidest. −{deduct} Coins."),
    (r"(?i)\bsorry\b", "Sorry? Sorry not sorry – aber du sagst’s eh nur, um mich heiß zu machen, du kleine Manipuliererin. −{deduct} Coins."),
    (r"(?i)\bwärst du so lieb\b", "Wärst du so lieb? Ich bin lieb – auf meine Art, du kleine Masochistin mit Herzchenaugen. −{deduct} Coins."),
    (r"(?i)\bthx\b", "Thx? Cringe-Abkürzung. Sag’s richtig oder halt die Klappe, du faule kleine Abkürzungs-Hure. −{deduct} Coins."),
    (r"(?i)\bthank you\b", "Thank you? International betteln jetzt? Du kleine Welt-Sub, lern Deutsch oder knie still. −{deduct} Coins."),
    (r"(?i)🙏", "Betende Hände? Perfekt für auf Knien vor mir. Bete zu mir, nicht zum Himmel, du kleine Andächtige. −{deduct} Coins."),
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

SCHEMA_VERSION = 14

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


async def _care_count_last_24h(db, chat_id: int, pet_id: int, owner_id: int, now_ts: int) -> int:
    since_ts = now_ts - RUNAWAY_HOURS * 3600
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


async def _should_runaway(
    db,
    chat_id: int,
    pet_id: int,
    owner_id: int,
    acquired_ts: int | None,
    now_ts: int,
    care_24h: int | None = None
) -> bool:
    if not owner_id:
        return False
    if not acquired_ts:
        return False
    if now_ts - int(acquired_ts) < RUNAWAY_HOURS * 3600:
        return False
    if care_24h is None:
        care_24h = await _care_count_last_24h(db, chat_id, pet_id, owner_id, now_ts)
    return care_24h < MIN_CARES_PER_24H


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
    return max(0, min(100, int(xp)))

def pet_level_title(level: int) -> str:
    lvl = max(0, min(100, int(level)))
    if not PET_LEVEL_TITLES:
        return f"Level {lvl}"
    idx = min(len(PET_LEVEL_TITLES) - 1, (lvl * (len(PET_LEVEL_TITLES) - 1)) // 100)
    return PET_LEVEL_TITLES[idx]

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
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return t


def superword_pattern(word: str) -> str:
    parts = re.findall(r"[a-z0-9]+", normalize_superword_text(word))
    if not parts:
        return ""
    body = r"[\s\-_]*".join(re.escape(p) for p in parts)
    return rf"(?<![a-z0-9]){body}(?![a-z0-9])"

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
        prev_level = int(prog_row[1]) if prog_row else 0

        now = int(time.time())
        if await _should_runaway(db, chat_id, pet.id, owner.id, care["acquired_ts"] if care else None, now):
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
        new_xp = prev_xp + 1
        new_level = pet_level_from_xp(new_xp)
        await db.execute(
            "UPDATE pets SET pet_xp=?, pet_level=? WHERE chat_id=? AND pet_id=?",
            (new_xp, new_level, chat_id, pet.id)
        )
        if new_level > prev_level:
            level_up_text = (
                f"Lvl <b>{new_level}</b> ({escape(pet_level_title(new_level), False)}) | "
                f"{nice_name_html(pet)} | Owner: {mention_html(owner.id, owner.username or None)} | "
                f"Pflege <b>{done}/{CARES_PER_DAY}</b>"
            )

        bonus_text = None
        if done >= CARES_PER_DAY:
            async with db.execute(
                "SELECT pet_skill, care_bonus_day FROM pets WHERE chat_id=? AND pet_id=?",
                (chat_id, pet.id)
            ) as cur:
                prow = await cur.fetchone()
            skill_key = prow[0] if prow else None
            care_bonus_day = prow[1] if prow else None
            if skill_key == "goldesel" and care_bonus_day != today:
                await db.execute(
                    "UPDATE players SET coins = coins + ? WHERE chat_id=? AND user_id=?",
                    (FULL_CARE_OWNER_BONUS, chat_id, owner.id)
                )
                await db.execute(
                    "UPDATE pets SET care_bonus_day=? WHERE chat_id=? AND pet_id=?",
                    (today, chat_id, pet.id)
                )
                bonus_text = (
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
            bonus_text = f"{bonus_text}\n{title_line}" if bonus_text else title_line

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
    if done % 10 == 0:
        progress_text = (
            f"Pflege-Stand: {nice_name_html(owner)} hat {nice_name_html(pet)} "
            f"<b>{done}/{CARES_PER_DAY}</b> gepflegt. "
            f"Level: <b>{new_level}</b> ({escape(pet_level_title(new_level), False)})."
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
                    f"OK {mention_html(user.id, user.username or None)} hat's geschafft. +{LOVE_REWARD} Coins. Ab jetzt ein Monat lang: 'mein Liebesgestaendniss'.",
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

    user = mention_html(tid, tname)
    line = random.choice(FLUCH_LINES).format(user=user)
    await update.effective_message.reply_text(line, parse_mode=ParseMode.HTML)


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
            f"Challenge: <b>{HASS_REQUIRED}× /selbst</b> in 2 Stunden\n"
            f"Deadline: <b>{until}</b>\n"
            f"Strafe bei Versagen: <b>−{HASS_PENALTY} Coins</b>\n"
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

# ============== Liebesgestaendniss

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
            "Schreib einen suessen, uebertriebenen Liebesbrief in den Chat:\n"
            f"- Mindestens {LOVE_MIN_WORDS} Woerter\n"
            f"- Mindestens {LOVE_MIN_EMOJIS} Emojis (beliebig)\n"
            f"- Mindestens {LOVE_MIN_SENTENCES} Satz/Saetze (Satzzeichen optional)\n\n"
            "Der Bot erinnert dich zwischendurch.\n"
            f"Schaffst du's: <b>+{LOVE_REWARD} Coins</b> + ein Monat lang 'mein Liebesgestaendniss'.\n"
            f"Versagst du: <b>-{LOVE_PENALTY} Coins</b>."
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
    "_apply_hass_penalty": _apply_hass_penalty,
    "_finish_hass": _finish_hass,
    "_finish_love": _finish_love,
    "LOVE_PENALTY": LOVE_PENALTY,
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
        BotCommand("dom", "Antwort auf Frauen mit Dom-Satz"),

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
        BotCommand("hass", "Startet Hass-Status (2h, 3 mal /selbst)"),
        BotCommand("selbst", "Nur für betroffenen User: zählt 1/3 Strafen"),
        BotCommand("liebes", "Liebesgestaendniss-Challenge"),
        BotCommand("settings", "Admin: Runtime-Settings"),
        BotCommand("admin", "Admin: Uebersicht"),
        BotCommand("backupnow", "Admin: Backup jetzt"),
        BotCommand("backups", "Admin: Backupliste"),
        BotCommand("restorebackup", "Admin: Backup wiederherstellen"),

    ]
    await application.bot.set_my_commands(commands)

# =========================
# Pflege-/Fun-Commands (benötigen do_care)
# =========================

async def cmd_pet(update, context):
    tame = [
"{owner} packt {pet} am Kiefer, drückt bis die Zähne knirschen: 'Augen hoch, oder ich reiß dir die Lider mit den Fingernägeln auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt die Nägel in {pet}s Hüfte: 'Jammer ruhig weiter. Dein Schmerz ist das Einzige, was heute noch Unterhaltungswert hat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht {pet} übers Gesicht – einmal. Dann schlägt er zu: 'Gefühlskontrolle, Stufe Anfänger. Du bist echt ein hoffnungsloser Fall.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} mit dem Unterarm quer über die Kehle an die Wand: 'Atmen ist ein Privileg. Heute hast du keins verdient.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt zwei Finger in {pet}s Mund: 'Saug schön, oder ich stopf dir was Größeres rein – und das wird nicht angenehm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt {pet}s Haare um die Faust und zieht ruckartig nach hinten: 'Kopf hoch, Schlampe. Dein Hals sieht besser aus, wenn er angespannt ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst den Daumen auf {pet}s Kehlkopf: 'Ein kleiner Druck mehr und dein Wimmern wird melodischer. Willst du’s testen?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt {pet} am Kragen nah ran: 'Du riechst nach Angst und billiger Erregung. Meine Lieblingskombi.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift {pet} brutal in die Innenseite des Oberschenkels: 'Schrei ruhig. Je lauter, desto weniger kommst du heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} am Genick wie ein ungezogenes Vieh: 'Platz. Sitz. Bleib. Und wehe, du bewegst dich ohne Erlaubnis.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fährt mit dem Fingernagel quer über {pet}s Unterlippe bis sie blutet: 'Schmeckt besser, wenn’s wehtut, oder? Sag danke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} mit dem ganzen Gewicht aufs Bett, Gesicht ins Kissen: 'Luft ist überbewertet. Du brauchst nur mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tippt {pet} spöttisch auf die Stirn: 'Da drin ist doch eh nichts mehr außer meinem Namen und deinem nächsten Orgasmus-Verbot.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt {pet}s Kinn hoch, bis die Halsmuskeln zittern: 'Halt still. Ich will sehen, wie lange du’s aushältst, bevor du winselst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst, während er {pet}s Handgelenke bis zum Bruchpunkt dreht: 'Fast. Noch ein Stückchen weiter und wir haben richtig Spaß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt {pet} den Ellbogen unters Schlüsselbein, bis es knackt: 'Atme durch die Nase, Schlampe. Der Mund ist fürs Schreien reserviert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt den Daumen tief in {pet}s Augenhöhle, knapp vor dem Augapfel: 'Noch ein Millimeter und du siehst mich nur noch schwarz-weiß. Willst du raten, welche Farbe?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht {pet}s Handgelenk um 180 Grad, bis die Sehnen reißen: 'Sieh mal, wie schnell aus deiner Hand ein nutzloser Lappen wird. Und du wolltest mich schlagen? Süß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst glühendes Metall gegen {pet}s Innenschenkel, langsam kreisend: 'Das ist keine Narbe mehr. Das ist mein Autogramm in deinem Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schiebt {pet} drei Finger in den Mund bis zum Rachen: 'Würg schön. Je mehr du kämpfst, desto tiefer geh ich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt {pet} mit voller Wucht in die Magengrube: 'Luft? Brauchst du nicht. Ich entscheide, wann du wieder atmest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht {pet} an den Haaren über den Betonboden, Kopf schlägt bei jedem Schritt auf: 'Teppich ist für Weicheier. Du verdienst Schürfwunden bis auf den Schädel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift {pet} in die Brustwarze und dreht, bis sie weiß wird: 'Noch ein Viertel Umdrehung und sie fällt ab. Willst du sie als Andenken?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet}s Gesicht in eine Pfütze aus ihrem eigenen Speichel und Tränen: 'Trink. Das ist das Einzige, was du heute zu saufen kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt {pet} mit dem Handrücken über den Mund, bis die Lippe aufplatzt: 'Blut steht dir. Macht dein Gesicht endlich interessant.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt {pet}s Beine auseinander, bis die Hüftgelenke schreien: 'Weiter. Ich will hören, wann was bricht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt {pet} den Knie in die Nieren, wieder und wieder: 'Jeder Tritt ein Kuss. Und ich bin gerade sehr liebevoll drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet}s Kopf unter Wasser, zählt laut bis 47: 'Du dachtest, 30 wär hart? Ich bin erst warm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt {pet} ein Büschel Haare aus, samt Kopfhaut: 'Souvenir. Nächstes Mal nehm ich ein Stück Ohr mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt die Fingernägel unter {pet}s Fingernägel und hebt an: 'Das wächst nach. Deine Würde nicht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "pet", tame)

async def cmd_walk(update, context):
    tame = [
"{owner} reißt die Leine ruckartig hoch, bis {pet} auf die Zehenspitzen muss: 'Hoch mit dem Kinn, Pet. Dein Hals gehört mir – und der sieht besser aus, wenn er blau anläuft.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt die Leine dreimal um die Faust und zieht {pet} brutal zurück: 'Rückwärts stolpern ist dein neuer Gang. Übung macht die Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt die Leine fallen und tritt drauf, während {pet} weiterzieht: 'Versuch’s ruhig. Jeder Zentimeter mehr kostet dich Haut vom Hals.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt {pet} einmal hart um die eigene Achse: 'Dreh dich, du kleine Schraube. Ich will sehen, wie dir schwindelig wird.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält die Leine straff und geht schneller, bis {pet} rennt: 'Lauf, Pet. Oder ich schleif dich – und Beton schmeckt scheiße.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bleibt abrupt stehen, Leine schießt nach vorn: 'Halsbruch-Gefahr? Süß. Das ist der Moment, in dem du merkst, wer hier wirklich führt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht {pet} so nah ran, dass Nasen sich berühren: 'Atme meinen Atem, kleine Hündin. Deiner ist eh nur noch Winseln wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlingt die Leine um {pet}s Handgelenke und zieht sie hoch: 'Arme nach oben, Titten raus – so läufst du jetzt. Deko für meinen Spaziergang.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} vor sich herkriechen, Leine am Halsband: 'Auf allen Vieren, Pet. Menschen gehen nicht – die kriechen für mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rammt den Fuß in {pet}s Kniekehle beim nächsten Schritt: 'Runter. Kriechen. Jetzt. Oder ich trete dir die Kniescheibe raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt die Leine um {pet}s Kehle und zieht zu: 'Jeder Atemzug ist ein Geschenk. Danke schön sagen wär jetzt angebracht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} führt {pet} an der kurzen Leine direkt vor sich: 'Rückwärts, Blick zu mir. Ich will sehen, wie dir die Tränen laufen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt einmal brutal und lässt los: 'Fang dich, oder knall mit der Fresse auf. Deine Wahl, Pet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht die Leine seitlich, bis {pet} seitlich taumelt: 'Seitwärts wie ein Krebs – passend, weil du eh nur seitlich fickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt, wickelt die Leine um die eigene Hand und drückt {pet} gegen die nächste Wand: 'Pause. Gesicht an Beton. Ich genieße den Ausblick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Leine hoch: 'Hals oder Gehorsam. Schnell.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zerrt brutal zurück: 'Kriech, du Wurm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'Würg oder lauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt {pet} gegen Wand: 'Gesicht ans Beton.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt hart: 'Stolper. Blute schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle: 'Atmen? Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tempo hoch: 'Renn oder stirb.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt jäh: 'Halsbruch? Mein Favorit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'Krabbel wie Krebs.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt in Knie: 'Runter. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Blickkontakt rückwärts: 'Tränen zählen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Arme: 'Titten raus. Deko.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine drauftreten: 'Zieh. Verlier Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht hart: 'Schwindel? Gut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nase an Nase: 'Schnüffel mich, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} rückwärts führen: 'Du folgst blind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} seitlicher Ruck: 'Insekt. Passt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'Renn oder erstick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht runter: 'Knie. Oder brech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nackengriff: 'Ein Fehler = Genickbruch.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "walk", tame)

async def cmd_kiss(update, context):
    tame = [
"{owner} packt {pet} am Kiefer, reißt den Mund auf: 'Küss oder ich brech dir die Zähne.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt tief in {pet}s Lippe bis Blut kommt: 'Schmeckt besser so.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt {pet}s Zunge raus: 'Die gehört jetzt mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} gegen die Wand, küsst bis sie würgt: 'Atmen? Nicht heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt über {pet}s blutige Lippe: 'Mein Geschmack. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst brutal, Zähne knirschen: 'Halt still oder verlier die Zunge.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Lippen so fest, dass {pet} blau anläuft: 'Dein Blau ist hübsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt ins Ohrläppchen, dann auf den Mund: 'Beides meins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst und würgt gleichzeitig: 'Kuss mit Extra.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt {pet}s Kopf zurück, küsst die Kehle: 'Hals zum Beißen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt an der Unterlippe bis sie reißt: 'Narben sind Küsse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst so hart, {pet} taumelt: 'Fallen oder folgen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt in die Zunge, zieht: 'Bleib dran oder verlier sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst und kneift in die Kehle: 'Atemzug? Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Mund auf Mund, Finger in Kehle: 'Tief. Tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst bis {pet} zittert: 'Zittern ist süß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt die Lippe auf, leckt Blut: 'Rot steht dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst und schlägt gleichzeitig: 'Multitasking.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt {pet} am Haar zum Kuss: 'Kopf hoch, Mund auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst langsam, dann brutal: 'Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt {pet}s Mund auf: 'Zunge raus oder ich schneid sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt die Lippe durch: 'Blut schmeckt nach dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} saugt die Zunge raus: 'Die bleibt bei mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst bis {pet} würgt: 'Luft? Vergiss es.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt über frisches Blut: 'Mein Lippenstift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Lippe: 'Halt still oder verlier sie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst bis blau: 'Dein neues Make-up.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Ohr, dann Mund: 'Beides markiert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss + Würgegriff: 'Doppelt hält besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kehle küssen + beißen: 'Puls unter Zähnen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Unterlippe reißen: 'Narben sind Küsse 2.0.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss so hart: 'Taumel oder brech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zunge ziehen: 'Bleib oder blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kehle kneifen + Kuss: 'Atem ist Luxus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Finger in Mund + Kuss: 'Tiefer geht’s.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} küsst bis Zittern: 'Zucken ist süß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Blut lecken: 'Rot ist deine Farbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kuss + Backpfeife: 'Gleichgewicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Haargriff + Kuss: 'Mund auf, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} langsam dann brutal: 'Folter im Doppelpack.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kiss", tame)

async def cmd_dine(update, context):
    tame = [
"{owner} hält den Bissen hoch: 'Bettel oder verhunger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt halbzerkaut rein: 'Schluck meinen Abfall.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt Essen auf Boden fallen: 'Leck. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt drauf, bevor {pet} darf: 'Dreck schmeckt besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert mit Fingern in Kehle: 'Tiefer. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Essen direkt rein: 'Mahlzeit aus meinem Mund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Bissen weg: 'Weine erst, dann darfst du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert, dann kneift Kehle zu: 'Kauen oder ersticken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} vom Schuh essen: 'Boden ist dein Teller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut langsam, spuckt aus: 'Heißer, weil ich dran war.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Bissen weg: 'Holen. Auf allen Vieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert mit Gabel in Mund: 'Beiß ab oder blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Essen ans Ohr: 'Hörst du’s knurren? Mein Magen lacht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Sahne rein: 'Trink meinen Rest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt warten, bis {pet} zittert: 'Hunger ist Gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert, dann schlägt: 'Danke sagen oder nichts.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen rein bis Würgen: 'Schluck oder kotz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Bissen über Klo: 'Willst du runterspülen?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} vom Boden fressen: 'Schweinchen kriegt Krümel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt, wiederholt: 'Mein Speichel, dein Leben.' Pflege {n}/{CARES_PER_DAY}.", 
"{owner} spuckt den Bissen ins Klo: 'Fisch ihn raus. Mit den Zähnen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} trampelt das Essen platt: 'Friss den Brei vom Schuh. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen rein bis zum Erbrechen: 'Kotz zurück in den Mund. Wiederverwertung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Bissen über offenes Klo: 'Sag danke, bevor ich spüle.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt auf Boden, tritt drauf: 'Leck meine Sohle sauber, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert mit der Faust: 'Schluck oder ich ramme tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt warten, bis {pet} heult: 'Tränen sind die beste Soße.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Essen in Müll: 'Betteln. Dann darfst du im Müll wühlen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut, spuckt rein, hält Kehle zu: 'Schluck meinen Abfall. Ganz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert vom Arsch: 'Mein Schweiß ist dein Dressing.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} hungern: 'Morgen vielleicht. Wenn du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen in Mund, schlägt zu: 'Kauen mit gebrochener Lippe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Essen auf {pet}s Gesicht: 'Trag dein Abendessen den ganzen Tag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Bissen ans Messer: 'Iss oder ich schneid dir die Zunge raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} füttert mit dem Fuß: 'Leck zwischen den Zehen, du Wurm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut lange, spuckt aus: 'Kalter Brei. Genieß die Temperatur.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} vom Aschenbecher essen: 'Zigarettenkippen sind Beilage.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Essen bis zum Würgen: 'Noch ein Bissen oder ich brech dir den Kiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wirft Essen weg: 'Verhungern ist deine neue Diät.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt den letzten Rest ins Gesicht: 'Das war's. Jetzt leck mich sauber.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "dine", tame)

async def cmd_massage(update, context):
    tame = [
"{owner} gräbt Daumen in die Nieren: 'Entspann dich oder ich brech dir die Rippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Wirbelsäule: 'Knack. Nochmal?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Schultern bis Sehnen reißen: 'Lockerer wird’s nicht mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in Triggerpunkte: 'Schrei lauter, ich hör schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Handballen in den Hals: 'Atemkontrolle deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit Knöcheln den Rücken runter: 'Haut abziehen inklusive.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Daumen tief in die Leiste: 'Innere Schenkel brauchen auch Pflege.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Brüste brutal: 'Muskeln? Oder nur Fett zum Quälen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Nägel in verspannte Stellen: 'Blut ist das beste Gleitmittel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert den Nacken, zieht Kopf zurück: 'Halsbruch-Massage, Stufe eins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Knie in den unteren Rücken: 'Atme durch die Zähne, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Oberschenkel bis blaue Flecken: 'Morgen läufst du wie ’ne Krüppel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in die Achselhöhle: 'Tickle-Tortur, aber ohne Lachen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Leber: 'Innere Organe brauchen Entspannung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit der Faust den Bauch: 'Noch ein bisschen tiefer und du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet den Kiefer bis Zähne klappern: 'Mund auf, oder ich brech ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt in die Waden: 'Krämpfe? Die kommen erst jetzt richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Daumen in die Schläfen: 'Kopfschmerzen? Mein Spezialgebiet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit vollem Gewicht drauf: 'Atemnot ist Teil der Therapie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beendet mit einem harten Schlag auf den Rücken: 'Fertig. Jetzt zitter schön weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Daumen in die Nieren: 'Entspann dich oder ich brech dir die Rippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Wirbelsäule: 'Knack. Nochmal?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Schultern bis Sehnen reißen: 'Lockerer wird’s nicht mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in Triggerpunkte: 'Schrei lauter, ich hör schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Handballen in den Hals: 'Atemkontrolle deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit Knöcheln den Rücken runter: 'Haut abziehen inklusive.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Daumen tief in die Leiste: 'Innere Schenkel brauchen auch Pflege.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Brüste brutal: 'Muskeln? Oder nur Fett zum Quälen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Nägel in verspannte Stellen: 'Blut ist das beste Gleitmittel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert den Nacken, zieht Kopf zurück: 'Halsbruch-Massage, Stufe eins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Knie in den unteren Rücken: 'Atme durch die Zähne, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet Oberschenkel bis blaue Flecken: 'Morgen läufst du wie ’ne Krüppel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bohrt Finger in die Achselhöhle: 'Tickle-Tortur, aber ohne Lachen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Ellbogen in die Leber: 'Innere Organe brauchen Entspannung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit der Faust den Bauch: 'Noch ein bisschen tiefer und du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knetet den Kiefer bis Zähne klappern: 'Mund auf, oder ich brech ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt in die Waden: 'Krämpfe? Die kommen erst jetzt richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst Daumen in die Schläfen: 'Kopfschmerzen? Mein Spezialgebiet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} massiert mit vollem Gewicht drauf: 'Atemnot ist Teil der Therapie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beendet mit einem harten Schlag auf den Rücken: 'Fertig. Jetzt zitter schön weiter.' Pflege {n}/{CARES_PER_DAY}."
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
"{owner} zeigt runter: 'Knie. Sofort. Oder ich trete dir die Beine weg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Nacken runter: 'Runter, Schlampe. Dein Platz ist immer unten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} packt Haare, reißt Kopf zurück: 'Knie, Augen hoch – ich will die Tränen sehen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt gegen Kniekehle: 'Fallen lassen. Hart. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff: 'Knie oder ich zieh dich runter – bis der Hals reißt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt Fuß auf Rücken: 'Runter mit dem Arsch. Bleib liegen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Knie auseinander: 'Breit. Wie die Hure, die du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Hände hinterm Rücken: 'Knie. Und wehe, du kippst um – dann brech ich dir was.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt warten: 'Zitter ruhig. Knie sind zum Brechen da.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Daumen in Kehle: 'Knie, während du würgst. Perfekter Moment.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt auf Oberschenkel: 'Runter. Rot wird dein neuer Teppich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, Knie auf Beton: 'Spür den Boden. Das ist dein neues Zuhause.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Kopf runter: 'Stirn am Boden. Wie beim Gebet – nur an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt zwischen Beine: 'Knie breit. Oder ich trete rein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht an Haaren runter: 'Knie. Und halt die Fresse – außer zum Betteln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt ewig warten: 'Knie. Bis die Knie kaputt sind. Dann erst hoch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Knie mit Stiefel runter: 'Bleib unten. Oder ich stampf drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Knie. Und denk dran: Stehen ist für Menschen. Du bist keins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Augen: 'Blind auf Knien. Spür nur den Schmerz – und mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, hält fest: 'Knie. Und bettel, dass ich dich nicht ewig so lasse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt dir die Knie weg: 'Runter, Fotze. Hart auf Beton – bis die Kniescheiben splittern.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} packt Nacken, drückt runter bis Stirn am Boden klebt: 'Knie. Und leck den Dreck, während du betest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haare raus beim Runterzwingen: 'Knie. Nächstes Mal nehm ich die Kopfhaut mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt Stiefel in Kniekehle: 'Fallen. Und wehe, du heulst – dann tret ich drauf, bis was bricht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Knie auseinander bis Hüfte schreit: 'Breit wie ’ne Nutte im Schlachthof. Halt durch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Hände hoch, Knie runter: 'Gebunden und gekniet – jetzt bettel, dass ich dir nicht die Arme auskugle.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Daumen in Kehle beim Runterdrücken: 'Knie. Und würg schön – macht den Anblick geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt dich ewig knien, bis Beine taub: 'Knie. Bis du nicht mehr aufstehen kannst – dann schleif ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt mit Gürtel auf Oberschenkel: 'Runter. Jeder Schlag ein Grund mehr, unten zu bleiben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, presst Gesicht in Kotfladen: 'Knie. Und atme das ein – dein neues Parfüm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt zwischen Beine, drückt Knie auseinander: 'Weiter. Bis die Sehnen reißen – oder du schreist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Kopf runter, Nase am Boden: 'Knie. Und schnüffel wie das Vieh, das du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet Leine kurz, zwingt runter: 'Knie. Und wehe, du hebst den Kopf – dann strangulier ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt Knie auf Glas: 'Runter. Spür die Scherben – das ist dein neuer Teppich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt mit Stiefel auf Rücken: 'Knie. Und bleib liegen – wie ’ne tote Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Kopf hoch, dann runter: 'Knie. Und lern, dass Hochkommen nie wieder kommt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter, hält Kehle zu: 'Knie. Und stirb langsam – sieht hübsch aus von oben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt warten, bis Knie bluten: 'Knie. Blut ist der beste Beweis, dass du unten bleibst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt auf Hände, zwingt Knie: 'Runter. Und wehe, du bewegst dich – dann brech ich dir die Finger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} presst dich runter, Gewicht voll drauf: 'Knie. Und spür, wie dein Körper kaputtgeht – für mich.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knien", tame)

async def cmd_kriechen(update, context):
    tame = [
"{owner} tritt Arsch: 'Kriech, Wurm. Schneller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haare: 'Fresse runter. Kriech, Vieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine straff: 'Kriech oder schleif ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Stiefel Rücken: 'Tiefer. Bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kalt: 'Kriech. Arsch wie tote Qualle.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt runter: 'Vierbeiner. Du kriechst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Knie: 'Weiter. Oder Beine brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Gesicht Dreck: 'Schnüffel, Schlampe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine würgen: 'Kriech. Keuch geil.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Boden: 'Leck. Kriechend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Kriech, Teppich. Bald platt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt Hände: 'Ohne Finger. Mir egal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Arsch hoch: 'Höher. Zeig Würdebruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ewig: 'Kriech. Kein Rückgrat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Kopf runter: 'Fresse Boden. Riech Tod.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreckig: 'Kriech, Insekt. Hammer nächstes Mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} brutal: 'Schneller. Oder Haut reißen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt: 'Kriech. Jammerst? Zähne ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt Gesicht: 'Kriech nass, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Kriech bis Sarg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tritt Rippen: 'Kriech, bevor ich dich zerquetsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Hals: 'Kriech oder strangulier ich dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt vor dich: 'Kriech durch meine Spucke, Hure.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nagel in Rücken: 'Kriech. Jeder Stich ein Schritt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Kriech, du nutzloser Wischlappen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Gesicht runter: 'Fresse am Boden. Kriech weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Ellbogen runter: 'Kriech flach. Wie ’ne Leiche.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht an Ohren: 'Kriech. Oder ich reiß sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Glas auf Boden: 'Kriech über Scherben. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält inne: 'Kriech rückwärts. Zeig mir dein Loch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Kehle zu: 'Kriech würgend. Geiler Sound.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Salz auf Wunden: 'Kriech. Brennt schön, oder?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kalt: 'Kriech, bis deine Knie Knochen sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Tritt Finger: 'Kriech ohne Hände. Wurm pur.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Kriech in die Hölle. Ich komm mit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine am Genick: 'Kriech oder Genickbruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt ins Haar: 'Kriech nass und stinkend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht dreckig: 'Kriech. Du bist schon tot – nur noch Bewegung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Nagel unter Nagel: 'Kriech. Jeder Finger ein Schrei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zwingt Arsch runter: 'Kriech platt. Wie ’ne zerquetschte Ratte.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "kriechen", tame)

async def cmd_klaps(update, context):
    tame = [
"{owner} knallt die Hand auf {pet}s Arsch: 'Das fürs Atmen. Nächster fürs Blinzeln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt hart: 'Zähl falsch und ich fang von vorn an – bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps so fest, dass es knallt: 'Dein Arsch schreit lauter als du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} abwechselnd links rechts: 'Symmetrie ist wichtig – für blaue Flecken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haut zu: 'Das war für deine letzte Lüge. Die nächste kommt gleich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit Ring: 'Spürst du den Stein? Der ist teurer als dein Stolz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt wiederholt: 'Musik für mich – dein Heulen ist der Beat.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} harter Klaps: 'Danke sagen oder ich mach weiter, bis du’s vergisst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf Innenschenkel: 'Arsch ist voll? Dann wechsel ich die Seite.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Das fürs Denken ohne Erlaubnis. Dummes Mädchen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps so laut, dass es hallt: 'Nachbarn wissen jetzt, wer hier die Hure ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis Schwellung: 'Morgen sitzt du nicht – perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Kneifen: 'Rot und blau – meine Lieblingsfarben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haut zu: 'Das war fürs Zögern. Nächster fürs Zappeln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit der Faustkante: 'Weicher wird’s nicht. Nur roter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt in Serie: 'Zehn für jeden Atemzug ohne mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf Steißbein: 'Das sitzt tief – genau wie du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart und trocken: 'Dein Arsch ist mein Schlaginstrument.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis Tränen: 'Weinen macht’s geiler. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt und lacht: 'Das war fürs Existieren. Danke mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit Gürtel: 'Hand war zu nett. Jetzt wird’s ernst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Dein Hintern glüht wie meine Laune.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Ziehen: 'Rot und gedehnt – mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis Bluterguss: 'Morgen siehst du aus wie mein Eigentum.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf wunde Stelle: 'Frisch auf Alt – doppelter Spaß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'Zähl mit oder ich fang bei hundert an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit flacher Hand: 'Das ist Gnade. Nächster kommt mit Faust.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt rhythmisch: 'Dein Puls ist mein Metronom.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis Zucken: 'Zappel ruhig – macht’s nur härter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt zu: 'Das fürs Betteln. Ohne zu kommen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf beide Backen: 'Gleichberechtigung – für Schmerzen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis taub: 'Spürst du noch was? Gut. Dann weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Kratzen: 'Blut und Rot – mein Farbschema.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'Das war für deine Tränen. Die nächsten fürs Lächeln.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt und flüstert: 'Dein Arsch gehört mir – und der Schmerz auch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis Schreien: 'Lauter. Die Nachbarn sollen neidisch sein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt drauf: 'Jeder Schlag ein Kuss – nur ohne Lippen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps mit Lederhandschuh: 'Weicher Stoff, härterer Schlag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis Schwellung platzt: 'Perfekt. Jetzt glänzt’s.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps + Beißen: 'Zuerst schlagen, dann markieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart und kalt: 'Das fürs Wünschen. Du kriegst nur, was ich gebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt in Wellen: 'Leise – laut – leise – bis du brichst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps bis der Arsch taub: 'Gefühllos? Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knallt zu: 'Das war fürs Atmen. Danke, dass du’s aushältst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt und zählt rückwärts: 'Fünfzig bis eins – dann fang ich neu an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Klaps auf wunden Stellen: 'Alt und neu – wie deine Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hart: 'Dein Arsch ist mein Punching-Bag. Schlag zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis du zitterst: 'Zittern ist süß. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} letzter Klaps brutal: 'Und der hier ist, weil du’s verdienst – einfach so.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "klaps", tame)

async def cmd_knabbern(update, context):
    tame = [
"{owner} beißt in Schulter, bis Blut kommt: 'Dein Geschmack? Nach Angst und Dummheit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Zähne in Brustwarze: 'Zieh dich zurück oder ich reiß sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Innenschenkel tief: 'Nah dran? Bald drin – und du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Arschbacke durch: 'Frühstück. Direkt vom lebenden Buffet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Kehle: 'Puls schmeckt nach deinem baldigen Ende.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Lippe bis Riss: 'Küss mich mit Blut – romantischer geht’s nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Klit hart: 'Perle? Eher Perlenkette aus Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Bauch, zieht Haut: 'Von innen lachen? Bald von innen schreien.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Ohrläppchen: 'Van Gogh? Ich nehm mir alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Hals bis Markierung: 'Mein Revier. Und du bist der Zaun.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Tippen? Nächstes Mal ohne Finger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Nase: 'Zu niedlich? Dann beiß ich sie ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Kinn durch: 'Selbstständig? Vergiss es, du Stück Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Ohr bis Blut: 'Geheimnis: Du stirbst irgendwann – fang ich heute an?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Schulter tief: 'Daily Reminder: Du bist mein Snack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert bis Quietschen aufhört: 'Musik? Dein Schreien ist besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Hals: 'Atmen ohne mich? Strafe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Lippe auf: 'Applaus? Mit Blut applaudiert’s besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Arm bis Knochen: 'Weglaufen? Mit einem Arm?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Brust: 'Danke sagen oder ich nehm die ganze Titte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut vom Rücken: 'Häutung deluxe – für besseren Geschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Oberschenkel: 'Ader? Fast. Noch ein Biss.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Finger ab: 'Nächstes Mal die ganze Hand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Kehle bis Würgen: 'Puls? Bald keiner mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Innenschenkel: 'Nah dran? Bald drin – und leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Arsch: 'Markiert. Für immer mein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Lippe durch: 'Blutkuss. Mein Lieblingsgeschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Klit: 'Perle? Bald nur noch Narbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut vom Bauch: 'Von innen? Bald von außen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Ohr: 'Hörst du? Das ist dein Tod.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Schulter bis Knochen: 'Fleisch ab. Knochen nächstes Mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Hals: 'Narben? Meine Unterschrift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Tippen ohne Finger? Chat endet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Nase: 'Zu süß? Dann weg.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Kinn: 'Kinn? Bald ohne.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Brustwarze ab: 'Nächstes Mal die ganze Brust.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Rücken: 'Rückgrat? Brauchst du eh nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Innenschenkel: 'Ader? Fast. Noch einer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Lippe: 'Blut? Mein Lippenstift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut vom Arm: 'Arm? Bald Stumpf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Kehle: 'Schlucken? Mit Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Arsch: 'Frühstück. Mittag. Abend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Schulter: 'Markiert. Und du heilst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kaut Ohr: 'Hör gut zu – das ist dein letztes.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Finger: 'Finger? Bald weniger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert Hals: 'Puls? Mein Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt Brust: 'Titze? Bald nur Narben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reißt Haut: 'Haut? Überflüssig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Zähne in Lippe: 'Blutkuss. Letzter Kuss.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knabbert alles: 'Snack. Hauptgericht. Dessert – du.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "knabbern", tame)

async def cmd_leine(update, context):
    tame = [
"{owner} wickelt Leine um Kehle, zieht langsam zu: 'Atme nochmal. Das war’s dann für heute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt Leine brutal: 'Würg. Dein neuer Gruß an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff bis blau: 'Blau anlaufen? Mein Lieblings-Make-up.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert mit doppelter Wicklung: 'Zwei Schichten. Zwei Chancen zu sterben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch, bis Füße abheben: 'Schweben? Nur bis du schwarz wirst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Hals, drückt runter: 'Knie und würg. Perfekter Anblick.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt locker, dann ruckartig: 'Atemzug-Geschenk. Danke schön sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert bis Zittern: 'Zucken ist süß. Mach weiter, bevor du kippst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine um Kehle und zieht: 'Puls unter Leine. Mein neues Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält bis Ohnmacht nah: 'Schwarzwerden? Mein persönlicher Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt Leine in Serie: 'Würg-Würg-Würg. Dein neuer Name.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'Seitwärts würgen. Wie ein kranker Hund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Genick, zieht rückwärts: 'Genickbruch oder Ersticken. Such dir was.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert langsam: 'Langsam sterben. Genieß die Vorfreude.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff bis Tränen: 'Weinen und würgen. Doppelt hält besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine um Hals, knotet: 'Knoten. Jetzt atme, wenn du kannst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Blutgefäße platzen: 'Rot in den Augen. Hübsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert beim Gehen: 'Jeder Schritt ein Würgen. Mein Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle, drückt gegen Wand: 'Wand und Leine. Dein neues Kreuz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt fallen, tritt drauf: 'Zieh selbst. Erstick dich, ich schau zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} ruckt bis Knie knicken: 'Runter. Würg auf Knien.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert bis Keuchen: 'Keuchen ist geil. Mach lauter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} wickelt Leine doppelt um Hals: 'Zwei Wicklungen. Zwei Leben zum Verlieren.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch zum Spiegel: 'Schau dir an, wie du erstickst. Schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff bis Zunge raus: 'Zunge raus. Will ich lecken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stranguliert ruckartig: 'Kurz und hart. Wie dein letzter Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Leine um Kehle, zieht langsam hoch: 'Hochziehen. Bis du schwebst – oder fällst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt mit Leine und Hand: 'Leine vorne, Hand hinten. Doppeltes Glück.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält bis Bewusstlosigkeit: 'Schlaf schön. Ich weck dich mit neuem Zug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert beim Strangulieren: 'Dein letzter Atemzug? Gehört mir.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "leine", tame)

async def cmd_halsband(update, context):
    tame = [
"{owner} schnappt das Halsband zu: 'Für immer? Bis ich dich zerlege und neu baue.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht es enger: 'Keuchen? Dein neuer Gruß an mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt ab, Schlüssel verschluckt: 'Such ihn. In meinem Magen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Fingernägel unter Rand: 'Blutperlen? Mein neues Dekor.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht zu bis blau: 'Blau steht dir. Wie dein letzter Atemzug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hängt Gewicht dran: 'Schwerer Hals = schwereres Leben. Gewöhn dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} graviert tief: 'Eigentum. Und du heilst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht zu: 'Stimme? Die gehört mir. Sprich nur, wenn ich zieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt Stachel rein: 'Jeder Schluck ein Stich. Schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Zunge raus: 'Zunge raus. Will ich lecken – oder abbeißen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Kette ans Bett: 'Schlaf damit. Oder stirb damit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch: 'Hoch mit dem Kinn. Oder ich reiß es hoch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt mit Vorhängeschloss: 'Schloss. Schlüssel? In meinem Arsch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} gräbt Metall in Haut: 'Narben? Meine Unterschrift.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Ohnmacht: 'Schwarzwerden? Mein Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Dornen: 'Beweg dich. Und blute.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht seitlich: 'Seitwärts würgen. Wie ein kranker Hund.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt zu eng: 'Atem? Mein Geschenk. Danke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hängt Glöckchen dran: 'Klingelst du? Dann stirbst du lauter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Tränen: 'Weinen? Macht den Hals schöner.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Elektro: 'Zuck. Oder ich schalt ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt ab, Schlüssel weg: 'Verloren? Such ihn in deiner Leiche.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Genick knackt: 'Genickbruch? Romantisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Stacheldraht: 'Beweg dich. Und zerfleisch dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht hoch zum Spiegel: 'Schau. So erstickst du schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schraubt Stachel in Kehle: 'Schlucken? Mit Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband zu eng: 'Puls? Bald keiner mehr.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zieht bis Zittern: 'Zittern ist süß. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schließt mit Kleber: 'Abnehmen? Nur mit Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} Halsband mit Messer: 'Beweg dich falsch. Und schneid dich.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "halsband", tame)

async def cmd_lecken(update, context):
    tame = [
"{owner} drückt {pet}s Gesicht in den Stiefel: 'Leck den Dreck ab, bevor ich dir die Zunge rausreiß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf den Boden: 'Leck meine Spucke auf. Langsam. Wie die Hure, die du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Stiefelsohle hin: 'Zunge rein in die Rillen. Schmeckt nach deinem Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Kopf runter: 'Leck meine Finger sauber – oder ich stopf sie dir in den Hals.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} eigene Tränen lecken: 'Salzig? Das ist der Geschmack von Versagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt in offenen Mund: 'Leck meine Spucke runter. Und danke schön sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Aschenbecher hin: 'Leck die Kippen sauber. Dein neues Dessert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Zunge in Klo: 'Leck den Rand. Das ist dein Heiligtum.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} den Boden lecken: 'Wo ich draufgetreten bin. Dein neuer Teller.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Hand hin, dreckig: 'Leck den Dreck ab. Oder ich reib ihn dir ins Gesicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} an Arsch: 'Leck meine Ritze. Und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Stiefel: 'Leck. Und schmeck deine eigene Erniedrigung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Zeh hin: 'Leck zwischen den Zehen. Staub ist dein Protein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht in Pfütze: 'Leck den Dreck. Dein neues Parfüm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} Blut lecken: 'Dein eigenes. Weil du zu langsam warst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Finger in Mund: 'Leck tief. Bis du würgst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Boden, tritt drauf: 'Leck meine Sohle sauber. Mit Dreck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} an Achsel: 'Leck den Schweiß. Dein neues Getränk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} Klo lecken: 'Ring um die Schüssel. Dein neuer Thron.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Stiefel in Mund: 'Leck innen. Bis du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt ins Gesicht: 'Leck ab. Und weine dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Zunge an Kehle: 'Leck meinen Puls. Der schlägt nur, wenn du leidest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} eigene Kotze lecken: 'Wiederverwertung. Mund auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Dreckhand hin: 'Leck. Und sag danke für den Geschmack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht in Müll: 'Leck den Abfall. Passt zu dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} spuckt auf Zunge: 'Leck meine Spucke. Dein neues Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Stiefel hoch: 'Leck die Sohle. Bis deine Zunge blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} an Arschloch: 'Leck. Und atme tief ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} Tränen vom Boden lecken: 'Salzig und nutzlos. Genau wie du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Finger in Mund, tief: 'Leck bis zum Würgen. Das ist dein Talent.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "lecken", tame)

async def cmd_verweigern(update, context):
    tame = [
"{owner} hält Wasser vor Nase, trinkt selbst: 'Durst? Trink deine Tränen. Die schmecken besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert {pet} bis Rand, stoppt: 'Kommen? Nur in meinen Träumen. Und die träumst du heute Nacht allein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} isst vor {pet}, lässt Krümel fallen: 'Leck den Boden. Das ist dein Abendessen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt stundenlang: 'Deine Stimme? Überbewertet. Meine Stille ist Gold.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht sich weg beim Kuscheln: 'Decke reicht. Die bettelt wenigstens nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Kuss: 'Lippen? Die spar ich für jemanden, der’s verdient. Du nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Orgasmus-Foto: 'Das war gestern. Heute? Nur Erinnerung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} wach bleiben: 'Schlaf? Für Menschen. Du bist keins.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Like: 'Dein Selfie? Zu hässlich für meinen Feed.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Essen hoch, wirft weg: 'Hunger? Gut. Der macht dich gehorsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert bis Zucken, zieht raus: 'Fast. Aber fast ist dein neuer Höhepunkt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt auf Betteln: 'Betteln? Klingt wie ein sterbender Hund. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Berührung: 'Hautkontakt? Nur für Dinge, die nicht so erbärmlich sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} trinkt Kaffee, gießt Rest weg: 'Du? Nicht mal für die Pflanze wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Schokolade, isst allein: 'Süß? Nicht für dich. Du bleibst bitter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Gute-Nacht: 'Träum von mir. Das ist die einzige Berührung, die du kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} zuschauen beim Wichsen: 'Schau zu. Aber komm nicht. Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schweigt tagelang: 'Deine Nachrichten? Müll. Ich les sie nicht mal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Lob: 'Gutes Mädchen? Du bist nicht mal ein guter Witz.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Hand weg: 'Anfassen? Nur wenn du blutest. Und selbst dann vielleicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Antwort: 'Gelesen. Und gelöscht. Wie dein Wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} hungern: 'Mager werden? Passt zu deiner Persönlichkeit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} dreht sich um beim Betteln: 'Bettel weiter. Ich hör eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Schlaf: 'Wach bleiben. Deine Albträume sind besser als du.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt Video von Orgasmus: 'Das war nicht mit dir. Und wird’s nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert Wasser: 'Trink deinen Speichel. Der ist eh nutzloser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt {pet} zuschauen beim Essen: 'Schau. Und stirb vor Hunger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} verweigert alles: 'Heute nichts. Morgen vielleicht. Oder nie. Dein Pech.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Verweigern ist Liebe. Und ich liebe dich zu Tode.' Pflege {n}/{CARES_PER_DAY}."
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
"{owner} fingert dich bis zum Rand, zieht raus: 'Fast gekommen? Pech. Dein Orgasmus ist mein Eigentum – und ich geb ihn nicht her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit langsam, quälend: 'Zuck ruhig. Je mehr du zappelst, desto länger lass ich dich hängen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal tief, hört auf: 'Geschmack? Geil. Aber Erlösung? Träum weiter, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Finger rein, stoppt abrupt: 'Tief drin und leer gelassen – das ist deine neue Definition von Liebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt Nippel hart, kneift: 'Hart werden? Gut. Aber kommen? Nur über meine Leiche – und deine erst recht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich nass, hört auf: 'Tropfen? Schön. Aber Tropfen reichen nicht. Du brauchst mich, um zu fließen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich stundenlang, kein Ende: 'Edging ist Gnade. Kommen ist Luxus. Und Luxus kriegst du nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf die Fotze: 'Mein Atem macht dich nass. Mein Schweigen macht dich wahnsinnig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit mit Daumen, stoppt: 'Pulsierend? Perfekt. Aber pulsierend ohne Erlösung ist dein neues Normal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Innenschenkel hoch, hört auf: 'Nah dran? Immer. Drin? Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert tief, zieht raus: 'Du bist so nass, dass es tropft. Und ich lass es tropfen – ohne dich zu retten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit hart: 'Schmerz und Geilheit? Meine Lieblingskombi. Und du kriegst beides ohne Happy End.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich stundenlang: 'Du kommst erst, wenn ich tot bin. Spoiler: Ich sterb nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Zucken, hört auf: 'Zucken ist süß. Kommen ist verboten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Tränen: 'Weinen vor Geilheit? Das ist der Soundtrack zu deinem Elend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal, beißt dann: 'Lust und Schmerz. Beides ohne Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich langsam, quälend: 'Jede Sekunde mehr Geilheit. Jede Sekunde weniger Verstand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Finger rein, bewegt nicht: 'Drin und still. Das ist Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Nippel: 'Hart werden? Gut. Aber hart bleiben ohne Erlösung ist dein Schicksal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit endlos: 'Du kommst nie. Aber du wirst immer nasser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt dich tief, hört auf: 'Geschmack von Verzweiflung. Mein Lieblingsaroma.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich bis Wahnsinn: 'Geilheit ohne Ende. Wie Krebs – nur geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich, zieht raus: 'Du bist so leer ohne mich. Und ich lass dich leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Schreien: 'Schrei lauter. Ich hör eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Fotze: 'Mein Atem ist alles, was du kriegst. Und das reicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Zittern: 'Zittern vor Geilheit? Mein neues Hobby.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt mitten drin: 'Mitten drin und allein gelassen. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich hart, hört auf: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Du kommst nie. Aber du wirst immer betteln. Und ich werde immer lachen.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "erregen", tame)

async def cmd_betteln(update, context):
    tame = [
"{owner} fingert dich bis zum Rand, zieht raus: 'Fast gekommen? Pech. Dein Orgasmus ist mein Eigentum – und ich geb ihn nicht her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit langsam, quälend: 'Zuck ruhig. Je mehr du zappelst, desto länger lass ich dich hängen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal tief, hört auf: 'Geschmack? Geil. Aber Erlösung? Träum weiter, Fotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Finger rein, stoppt abrupt: 'Tief drin und leer gelassen – das ist deine neue Definition von Liebe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt Nippel hart, kneift: 'Hart werden? Gut. Aber kommen? Nur über meine Leiche – und deine erst recht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich nass, hört auf: 'Tropfen? Schön. Aber Tropfen reichen nicht. Du brauchst mich, um zu fließen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich stundenlang, kein Ende: 'Edging ist Gnade. Kommen ist Luxus. Und Luxus kriegst du nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf die Fotze: 'Mein Atem macht dich nass. Mein Schweigen macht dich wahnsinnig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit mit Daumen, stoppt: 'Pulsierend? Perfekt. Aber pulsierend ohne Erlösung ist dein neues Normal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt Innenschenkel hoch, hört auf: 'Nah dran? Immer. Drin? Nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert tief, zieht raus: 'Du bist so nass, dass es tropft. Und ich lass es tropfen – ohne dich zu retten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit hart: 'Schmerz und Geilheit? Meine Lieblingskombi. Und du kriegst beides ohne Happy End.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich stundenlang: 'Du kommst erst, wenn ich tot bin. Spoiler: Ich sterb nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Zucken, hört auf: 'Zucken ist süß. Kommen ist verboten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Tränen: 'Weinen vor Geilheit? Das ist der Soundtrack zu deinem Elend.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt einmal, beißt dann: 'Lust und Schmerz. Beides ohne Orgasmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich langsam, quälend: 'Jede Sekunde mehr Geilheit. Jede Sekunde weniger Verstand.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Finger rein, bewegt nicht: 'Drin und still. Das ist Folter deluxe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Nippel: 'Hart werden? Gut. Aber hart bleiben ohne Erlösung ist dein Schicksal.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Rand, schlägt zu: 'Fast gekommen? Dann fast tot. Nächstes Mal richtig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt die Klit endlos: 'Du kommst nie. Aber du wirst immer nasser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} leckt dich tief, hört auf: 'Geschmack von Verzweiflung. Mein Lieblingsaroma.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streichelt dich bis Wahnsinn: 'Geilheit ohne Ende. Wie Krebs – nur geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich, zieht raus: 'Du bist so leer ohne mich. Und ich lass dich leer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich bis Schreien: 'Schrei lauter. Ich hör eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} haucht auf Fotze: 'Mein Atem ist alles, was du kriegst. Und das reicht nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fingert dich bis Zittern: 'Zittern vor Geilheit? Mein neues Hobby.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stoppt mitten drin: 'Mitten drin und allein gelassen. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} reibt dich hart, hört auf: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Du kommst nie. Aber du wirst immer betteln. Und ich werde immer lachen.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "betteln", tame)

async def cmd_stumm(update, context):
    tame = [
"{owner} legt Finger auf Lippen: 'Mund zu. Oder ich näh ihn zu – mit Stacheldraht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit Leine: 'Kein Laut. Deine Stimme ist eh nur Gejaule wert.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Kehle zu: 'Stumm sein oder ersticken. Such dir schnell was aus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund zu: 'Klebeband deluxe. Dein nächster Schrei ist innerlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt Schweigen: 'Ein Wort und ich reiß dir die Zunge raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Mund zu: 'Pssst. Dein Atem ist schon zu laut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit eigenem Slip: 'Schmeck deine eigene Fotze. Und halt die Fresse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Daumen in Mund: 'Tief rein. Und wehe, du saugst – dann brech ich dir den Kiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt stumm: 'Schweig. Dein Gewinsel macht mich eh nur aggressiv.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Lippen zusammen: 'Jetzt bettelst du nur noch mit Tränen. Schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Kehle zu: 'Stumm oder tot. Deine Wahl.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Stoff in Mund: 'Schluck runter. Und halt die Klappe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt brutal: 'Mund zu. Oder ich schneid ihn zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Finger in Rachen: 'Tiefer. Bis du kotzt – stumm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Kein Stöhnen. Oder ich stopf dir was Größeres rein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund mit Kleber: 'Abnehmen? Nur mit Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Mund zu, drückt zu: 'Atme durch die Nase. Oder gar nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit Gürtel: 'Zieh zu. Bis du blau wirst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt Schweigen: 'Ein Pieps und ich reiß dir die Stimmbänder raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Lappen rein: 'Schmeck meinen Schweiß. Und schweig.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Kehle: 'Stumm. Oder Genickbruch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Lippen: 'Jetzt schreist du nur noch innerlich. Perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Mund zu: 'Deine Stimme ist Müll. Weg damit.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt mit Leine: 'Strangulieren und stumm. Doppeltes Glück.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Schweig. Dein Schweigen ist das Einzige, was ich an dir ertrag.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Finger tief: 'Saug nicht. Oder ich ramme tiefer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} klebt Mund: 'Jetzt bettelst du nur noch mit Augen. Und ich lach.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt zu: 'Stumm. Bis du platzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} knebelt hart: 'Mund zu. Und wehe, du jammerst innerlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Schweig. Deine Stille ist der schönste Schrei, den ich je gehört hab.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "stumm", tame)

async def cmd_bestrafen(update, context):
    tame = [
"{owner} fesselt {pet} brutal ans Bett: 'Beweg dich nicht. Oder ich brech dir die Gelenke.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht den Arsch blutig: 'Zähl mit. Falsch und ich fang von vorn an – mit dem Gürtel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Nippel bis sie reißen: 'Schrei ruhig. Je lauter, desto härter ich zieh.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet {pet} mit Stacheldraht: 'Wind dich. Und blut schön für mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt mit der Faust: 'Das fürs Atmen ohne Erlaubnis. Nächster fürs Zucken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt warten, bis Knie splittern: 'Knie auf Beton. Bis du nicht mehr aufstehen kannst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt mit Leine: 'Strafe ist Ersticken. Und ich halt so lange, bis du blau bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt in Fleisch: 'Markiert. Und du heilst nie wieder.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} stopft Mund mit eigenem Slip: 'Schmeck deine eigene Fotze. Und halt die Fresse.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Innenschenkel: 'Rot und nass – meine Lieblingsfarbe auf dir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und lässt frieren: 'Nackt. Kalt. Und warte, bis deine Haut blau ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt mit Gürtel: 'Jeder Hieb ein Grund mehr, mich zu hassen – und zu wollen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} kneift Klit brutal: 'Das fürs Betteln. Nächster fürs Zucken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fesselt und edge tagelang: 'Komm nie. Oder ich fang neu an – mit dem Stock.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht in Kotfladen: 'Leck. Das ist deine Strafe – und dein Spiegel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt mit der flachen Hand: 'Bis dein Arsch platzt. Und du weinst Blut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet mit Ketten: 'Zieh. Und reiß dir die Haut auf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt bis Ohnmacht: 'Schwarzwerden? Mein Lieblingslichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Rücken: 'Narben? Meine Unterschrift in deinem Fleisch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lässt hungern: 'Kein Essen. Bis du so mager bist wie deine Würde.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt mit dem Stock: 'Jeder Schlag ein Knochenbruch. Oder fast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und lässt warten: 'Warte. Bis deine Gelenke brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} beißt bis Blut fließt: 'Schmeckt besser als deine Tränen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt mit Hand: 'Atem? Mein Geschenk. Und ich nehm’s zurück.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht Klit: 'Das fürs Geilsein ohne Erlaubnis.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} fesselt und lässt frieren: 'Kälte ist Strafe. Und du zitterst so schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} schlägt bis taub: 'Gefühllos? Gut. Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet mit Stacheldraht: 'Beweg dich. Und zerfleisch dich selbst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} würgt bis Zunge raus: 'Zunge raus. Will ich abbeißen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} peitscht bis Fleisch hängt: 'Das ist Strafe. Und du siehst aus wie mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "bestrafen", tame)

async def cmd_loben(update, context):
    tame = [
"{owner} tätschelt die Wange hart: 'Gutes Mädchen. Einmal im Monat. Mehr wär Verschwendung an dich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert kalt: 'Du hast es fast gut gemacht. Fast. Deshalb kriegst du nur fast Lob.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht übers Haar, zieht fest: 'Brave Schlampe. Weil du heute nicht geheult hast. Das ist alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes Mädchen. Für eine Sekunde. Danach bist du wieder nur mein Loch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt einen Kuss auf die Stirn – einmal: 'Stolz auf dich? Nur, weil du’s überlebt hast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Gutes Mädchen. Deine Hingabe ist so erbärmlich süß, dass ich fast kotze.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt den Arsch: 'Brav ertragen. Das ist das Höchste, was du je kriegst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht leise: 'Gutes Mädchen. Weil du bettelst wie eine kaputte Puppe – und das gefällt mir.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht über Narben: 'Du trägst meine Spuren gut. Das ist das Einzige, was an dir perfekt ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert ins Ohr: 'Gutes Mädchen. Für heute. Morgen fängst du wieder bei null an.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält den Blick: 'Brave Hure. Weil du’s wagst, mich anzuschauen – und sofort wieder runtergehst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst kalt: 'Gutes Mädchen. Du bist so gehorsam, dass es fast langweilig wird. Fast.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt den Kopf: 'Stolz auf dich? Nur, weil du noch atmest, obwohl ich’s dir verbieten könnte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Gutes Mädchen. Dein Winseln ist Musik – billige, kaputte Musik.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht über die Leine: 'Brav getragen. Wie ein Hund, der weiß, wo sein Platz ist – unten.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht dreckig: 'Gutes Mädchen. Weil du’s verdienst – und weil’s mich anmacht, wenn du dich dafür hasst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält die Hand hin: 'Leck. Und danke für das Privileg, du kleine Leckruine.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Gutes Mädchen. Für den Moment. Danach bist du wieder nur mein Spielzeug.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt brutal: 'Brave Fotze. Weil du’s aushältst, ohne zu zerbrechen – noch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes Mädchen. Deine Abhängigkeit ist das Schönste an dir. Und das Hässlichste.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht über die Haut: 'Du glühst schön. Wie ein Stück Fleisch, das ich gerade gegrillt hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert kalt: 'Gutes Mädchen. Weil du bettelst, als wär’s dein Lebenszweck – und das ist’s ja auch.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält den Blick: 'Brav geschaut. Augen runter, bevor ich sie dir rausreiß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} lacht: 'Gutes Mädchen. Für eine Sekunde. Danach bist du wieder wertlos.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} tätschelt den Kopf: 'Stolz? Nur, weil du noch nicht tot bist. Gratuliere.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert: 'Gutes Mädchen. Deine Hingabe ist so erbärmlich, dass sie fast süß ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} streicht über die Leine: 'Brav gezogen. Wie ein Hund, der weiß, dass sein Herrchen ihn jederzeit tottreten kann.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} grinst: 'Gutes Mädchen. Weil du’s verdienst – und weil’s mich langweilt, wenn du brav bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält die Hand hin: 'Leck. Und danke, dass du so tief sinkst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} flüstert zum Schluss: 'Gutes Mädchen. Und jetzt halt die Fresse – Lob ist aufgebraucht.' Pflege {n}/{CARES_PER_DAY}."
    ]
    await do_care(update, context, "loben", tame)

async def cmd_dienen(update, context):
    tame = [
"{owner} befiehlt: 'Knie nieder und halt still – du bist mein lebender Tisch, bis deine Knie splittern.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf den Boden: 'Leck meine Schuhe sauber, während ich draufsteh – und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Bring mir Wasser. Auf allen Vieren. Und wehe, du verschüttest einen Tropfen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff: 'Folge mir. Kriech. Bis deine Knie Knochen sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Massier mir die Füße. Mit deiner Zunge. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck meine Ritze sauber. Und atme tief ein.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} ans Bett: 'Halt die Position. Stundenlang. Oder ich tret drauf.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir Essen. Mit dem Mund. Und wehe, du frisst einen Krümel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein Stuhl. Bis deine Gelenke brechen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz die Schüssel. Mit deiner Zunge. Jetzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte stundenlang. Nackt. Bis ich Lust hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Kopf runter: 'Leck den Boden. Wo ich draufgetreten bin.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Aschenbecher hin: 'Leck die Kippen sauber. Dein neuer Snack.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Sei mein Schatten. Kriech hinter mir her.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Füße: 'Leck zwischen den Zehen. Staub ist dein Brot.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Halt die Leine im Mund. Und warte.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Putz mein Zimmer. Mit deiner Haut.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein Kissen. Bis du erstickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck mich sauber. Und danke schön sagen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Auf Knien. Bis du blutest.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht runter: 'Leck meine Finger. Nachdem ich dich geschlagen hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein Teppich. Tritt drauf. Immer.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte nackt. Bis deine Haut blau ist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz. Und wehe, du kotzt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Leck den Dreck von meinen Stiefeln. Langsam.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Sei mein lebender Aschenbecher. Schluck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine: 'Folge. Kriech. Bis dein Bauch aufreißt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Füße: 'Massier. Mit deiner Zunge. Bis sie blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} fest: 'Halt die Position. Bis du zerbrichst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Mit dem Mund. Und wehe, du frisst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} runter: 'Sei mein Fußschemel. Bis deine Knochen knacken.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck sauber. Und atme meinen Schweiß.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte. Nackt. Bis du zitterst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht runter: 'Leck den Boden. Wo ich gepisst hab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein lebender Lappen. Wisch mich ab.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Klo: 'Putz. Mit deiner Zunge. Und weine dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Folge mir. Kriech. Bis dein Gesicht blutet.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Leck meine Achseln. Schmeck meinen Gestank.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein Kissen. Bis du erstickst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Füße: 'Leck. Und danke für den Dreck.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Bring mir alles. Auf Knien. Bis deine Knie zerfetzt sind.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Sei mein Teppich. Und blut schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine: 'Folge. Und wehe, du jammerst.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Arsch: 'Leck sauber. Und atme tief.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Warte nackt. Bis deine Haut aufreißt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt Gesicht runter: 'Leck den Dreck. Dein neues Parfüm.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält {pet} fest: 'Sei mein lebender Aschenbecher. Schluck alles.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} zeigt auf Füße: 'Massier. Mit deiner Zunge. Bis sie abfällt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} befiehlt: 'Dien mir. Bis du kaputt bist. Und dann weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} drückt {pet} runter: 'Leck. Kriech. Stirb. In dieser Reihenfolge.' Pflege {n}/{CARES_PER_DAY}."
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
"{owner} bindet {pet} fest und melkt brutal: 'Tropf, Schlampe. Oder ich reiß dir die Klit raus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und stoppt: 'Nah dran? Pech. Dein Orgasmus gehört mir – und ich behalt ihn.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern: 'Kalt und nass. Wie dein Leben ohne mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} hält Leine straff beim Melken: 'Zieh selbst ran. Oder ich strangulier dich dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Tränen: 'Weinen macht dich nasser. Und mich geiler.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, quälend: 'Jeder Tropfen ein Beweis, wie erbärmlich du bist.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und kneift Klit: 'Schmerz und Geilheit. Meine Lieblingskombi.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} bindet und melkt tagelang: 'Komm nie. Oder ich fang neu an – mit dem Stock.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten an Nippeln: 'Zieh. Und blut schön.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und würgt leicht: 'Tropf und keuch. Perfekter Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und lacht: 'Du tropfst wie eine kaputte Pumpe. Geil erbärmlich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zucken: 'Zuck ruhig. Je mehr, desto länger lass ich dich hängen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Fingern in Mund: 'Saug. Und wehe, du würgst nicht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und schlägt zu: 'Tropf und rot. Meine Lieblingsfarbe.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, stoppt: 'Fast. Aber fast ist dein neuer Höhepunkt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt gefesselt: 'Beweg dich nicht. Oder ich bind dich enger.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und beißt Schulter: 'Blut und Tropfen. Mein Cocktail.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Schreien: 'Schrei lauter. Ich hör schlecht.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Leine am Hals: 'Jeder Zug ein Tropfen. Und ich zieh hart.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und verweigert: 'Tropf ohne Ende. Kommen? Vergiss es.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und flüstert: 'Du gehörst mir. Jeder Tropfen sagt's.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis taub: 'Gefühllos? Gut. Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und drückt Kehle: 'Atem und Tropfen. Mein Geschenk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern tief: 'Kalt rein, heiß raus. Wie dein Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zittern: 'Zittern ist süß. Mach weiter.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und stopft Mund zu: 'Tropf stumm. Dein Schreien nervt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten: 'Zieh. Und blut für mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam, quälend: 'Jede Sekunde mehr Geilheit. Keine Erlösung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und lacht dreckig: 'Du tropfst wie eine billige Pumpe. Und ich genieße.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ohnmacht nah: 'Schwarzwerden? Mein Lieblingslichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart und zieht raus: 'Fast drin. Und wieder leer gelassen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Fingern in Arsch: 'Doppelt melken. Doppelt leiden.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und kneift Nippel: 'Hart werden? Gut. Hart bleiben ohne Kommen? Besser.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Blut fließt: 'Blut und Tropfen. Mein Kunstwerk.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und verweigert: 'Tropf ohne Ende. Du kommst nie.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Leine am Genick: 'Zieh. Und würg dabei.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam: 'Langsam leer werden. Mein Lieblingsspiel.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und schlägt Klit: 'Schmerz macht dich nasser. Oder lügst du?' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Schreien: 'Schrei. Ich hör eh nicht zu.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit kalten Fingern: 'Kalt rein, heiß raus. Dein neues Leben.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und beißt Lippe: 'Blut und Tropfen. Perfekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Zunge raus: 'Zunge raus. Will ich abbeißen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart: 'Du tropfst wie eine defekte Maschine. Geil defekt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und würgt: 'Tropf und keuch. Mein Rhythmus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis taub: 'Gefühllos? Dann spürst du den nächsten doppelt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und stopft Mund: 'Tropf stumm. Dein Schreien nervt.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt mit Gewichten: 'Zieh. Und blut für mich.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt langsam: 'Jede Sekunde mehr Geilheit. Keine Erlösung.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt und lacht: 'Du tropfst wie eine billige Pumpe. Und ich genieße.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ohnmacht: 'Schwarzwerden? Mein Lichtaus.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt hart: 'Fast drin. Und wieder leer gelassen.' Pflege {n}/{CARES_PER_DAY}.",
"{owner} melkt bis Ende: 'Leer. Und immer noch geil. Mein Meisterwerk.' Pflege {n}/{CARES_PER_DAY}."
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
    "im dunklen Keller, wo du für mich kriechst",
    "auf dem Boden meines Zimmers, wo du hingehörst",
    "im Käfig, den ich dir gebaut hab",
    "vor meinem Stuhl, wo du kniest",
    "in der Ecke, wo du Schande trägst",
    "am Bett, wo du wartest",
    "unter dem Tisch, wo du servierst",
    "auf Knien vor meinem Spiegel",
    "im Bad, wo du leckst",
    "im Flur, wo du tropfst",
    "auf dem Balkon, wo Nachbarn hören",
    "im Auto, wo du fährst und ich sitz",
    "im Park, wo du dich versteckst",
    "in der Küche, wo du kochst und bettelst",
    "im Schlafzimmer, wo du schläfst und träumst",
    "im Wohnzimmer, wo du tanzt",
    "im Bad, wo du duschst und zitterst",
    "auf dem Dachboden, wo du dich versteckst",
    "im Garten, wo du gräbst",
    "im Auto, wo du kniest",
    "im Büro, wo du arbeitest und ich dich melke",
    "im Hotel, wo du zahlst und ich nehme",
    "im Zug, wo du dich versteckst",
    "im Flugzeug, wo du fliegst und ich dich halte",
    "im Restaurant, wo du servierst und bettelst",
    "im Club, wo du tanzt und ich zuschau",
    "im Wald, wo du kriechst und ich folge",
    "am Strand, wo du nackt bist und ich dich markiere",
    "im Berg, wo du kletterst und ich dich ziehe",
    "im Meer, wo du schwimmst und ich dich ertränke"
]

_TREASURE_METHODS = {
    "graben": "gräbt wie ein Tier auf Knien",
    "buddeln": "buddeln bis die Knie bluten",
    "tauchen": "taucht tief und kommt nass hoch",
    "karte": "folgt meiner Karte blind",
    "hacken": "hackt sich selbst frei – oder nicht",
    "klauen": "klaut sich selbst für mich",
    "pendeln": "pendelt wie 'ne Puppe an meiner Leine",
    "orakel": "befragt mich – und ich lüge nicht",
    "klettern": "klettert hoch – nur um runterzufallen"
}

def _pick_method(args) -> str:
    if not args:
        return random.choice(list(_TREASURE_METHODS.values()))
    key = args[0].lower()
    return _TREASURE_METHODS.get(key, random.choice(list(_TREASURE_METHODS.values())))

_TREASURE_STORIES = [
    "{user} {method} in {place} und zieht 'ne Truhe raus. Inhalt: {coins} Coins. Gutes Mädchen, aber der wahre Schatz bin ich.",
    "{user} stolpert in {place} über 'ne Kiste. {coins} Coins später bist du immer noch meine. Cringe, aber wahr.",
    "{user} folgt meiner Karte bis {place}, reißt Truhe auf. {coins} Coins. Weil gutes Mädchen immer gewinnt – mit mir als Coach.",
    "{user} wühlt in {place} und fischt {coins} Coins raus. Schatz 1, deine Freiheit on hold. Forever.",
    "{user} macht in {place} auf Heldin. Truhe auf, {coins} Coins raus. Aber der final Boss bin ich.",
    "{user} {method} in {place} und winselt 'Daddy please'. {coins} Coins als Teaser. Der main drop dein Stöhnen.",
    "{user} knackt Truhe in {place} mit shaky Händen. {coins} Coins. Big W nur mit mir.",
    "{user} {method} in {place}, schwitzt und vibet. {coins} Coins später: Der Schatz war der Cringe mich zu jagen.",
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
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        target_id = target.id
        target_username = target.username
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
                new_coins = max(0, buyer_coins - total_penalty)
                await db.execute(
                    "UPDATE players SET coins=? WHERE chat_id=? AND user_id=?",
                    (new_coins, chat_id, buyer_id)
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
        final_text = "✅ Keine Zombies gefunden. Alles sauber wie dein Halsband nach ‘ner guten Session – glatt, glänzend und bereit für neue Male."
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



async def cmd_forcepurge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur die echte Herrin (aka Admin) darf Leichen manuell entsorgen
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text(
            "🚫 Träum weiter, du kleine Möchtegern-Schlächterin. "
            "Nur ich darf entscheiden, wer endgültig stirbt. Finger weg von der Sense."
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

        # Wenn's eine Zahl ist → direkt als ID nehmen
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
    
    #Auto Bot commands (falls mal ein User das machen darf)
    # app.add_handler(CommandHandler("verfluchen",  cmd_verfluchen,  filters=CHAT_FILTER))

    # hass und selbst
    app.add_handler(CommandHandler("hass",   cmd_hass,   filters=CHAT_FILTER))
    app.add_handler(CommandHandler("selbst", cmd_selbst, filters=CHAT_FILTER))
    app.add_handler(CommandHandler("liebes", cmd_liebes, filters=CHAT_FILTER))

    # Callback für Gender-Zuweisung
    app.add_handler(CallbackQueryHandler(on_gender_callback, pattern=r"^gender\|"))


    # Member-Events
    app.add_handler(ChatMemberHandler(on_chat_member,     ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_my_chat_member,  ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CommandHandler("cleanup_zombies", cmd_cleanup_zombies, filters=CHAT_FILTER))
    # Handler nicht vergessen
    app.add_handler(CommandHandler("listdbusers", cmd_listdbusers, filters=CHAT_FILTER))

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
    curse_time = dtime(hour=20, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_curse_job, time=curse_time, name="daily_curse_8pm")
    primetime_time = dtime(hour=20, minute=0, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_primetime_job, time=primetime_time, name="daily_primetime_8pm")
    backup_time = dtime(hour=3, minute=30, tzinfo=ZoneInfo(PETFLIX_TZ))
    app.job_queue.run_daily(daily_backup_job, time=backup_time, name="daily_backup_330am")
    app.job_queue.run_repeating(hass_watchdog_job, interval=60, first=30, name="hass_watchdog")
    app.job_queue.run_repeating(love_watchdog_job, interval=60, first=30, name="love_watchdog")
    app.job_queue.run_repeating(runaway_watchdog_job, interval=60, first=30, name="runaway_watchdog")

    print("Petflix 2.1 gestartet.")
    app.run_polling()

if __name__ == "__main__":
    main()
