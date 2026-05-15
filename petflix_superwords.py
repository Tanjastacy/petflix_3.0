import os
import re
import time


SUPERWORDS_FALLBACK = [
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
SUPERWORDS_CLEAN_FILE = "texts/superwords_active.txt"
def load_superwords() -> list[str]:
    words = list(SUPERWORDS_FALLBACK)
    if os.path.exists(SUPERWORDS_CLEAN_FILE):
        words = []
        with open(SUPERWORDS_CLEAN_FILE, "r", encoding="utf-8-sig") as f:
            for line in f:
                word = line.strip()
                if word and not word.startswith("#"):
                    words.append(word)
    else:
        for superwords_path in SUPERWORDS_FILES:
            if not os.path.exists(superwords_path):
                continue
            with open(superwords_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith("#"):
                        words.append(word)


    return list(dict.fromkeys(_add_umlaut_variants(words)))


SUPERWORDS = load_superwords()

def normalize_superword_text(text: str) -> str:
    t = (text or "").casefold()
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return t


def superword_key(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_superword_text(word))


def superword_pattern(word: str) -> str:
    parts = re.findall(r"[a-z0-9]+", normalize_superword_text(word))
    if not parts:
        return ""
    body = r"[\s\-_]*".join(re.escape(p) for p in parts)
    return rf"(?<![a-z0-9]){body}(?![a-z0-9])"


SUPERWORD_KEYS = {
    superword_key(word)
    for word in SUPERWORDS
    if superword_key(word)
}


async def claim_superword_once(db, chat_id: int, word: str, user_id: int, cooldown_s: int) -> bool:
    now = int(time.time())
    key = (word or "").lower()
    async with db.execute(
        "SELECT found_ts FROM superwords_found WHERE chat_id=? AND word=?",
        (chat_id, key),
    ) as cur:
        row = await cur.fetchone()
    if row and row[0] is not None:
        found_ts = int(row[0])
        if now - found_ts < cooldown_s:
            return False

    await db.execute(
        """
        INSERT INTO superwords_found(chat_id, word, found_by, found_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(chat_id, word) DO UPDATE SET
          found_by=excluded.found_by,
          found_ts=excluded.found_ts
        """,
        (chat_id, key, user_id, now),
    )
    return True


async def count_active_superword_cooldowns(db, chat_id: int, active_cutoff: int) -> int:
    if not SUPERWORD_KEYS:
        return 0
    async with db.execute(
        "SELECT word FROM superwords_found WHERE chat_id=? AND found_ts>?",
        (chat_id, active_cutoff)
    ) as cur:
        rows = await cur.fetchall()
    return sum(1 for row in rows if row and str(row[0]).lower() in SUPERWORD_KEYS)
