import importlib.util
import sys
import time
import uuid
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
import pytest_asyncio

from ownership_features import create_ownership_features
from runtime_features import create_runtime_features


TEST_CHAT_ID = -100123
TEST_ADMIN_ID = 999


async def init_test_db(db_path: Path):
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(
            """
            CREATE TABLE players(
              chat_id   INTEGER,
              user_id   INTEGER,
              username  TEXT,
              coins     INTEGER DEFAULT 0,
              price     INTEGER DEFAULT 100,
              PRIMARY KEY(chat_id, user_id)
            );
            CREATE TABLE cooldowns(
              chat_id INTEGER,
              user_id INTEGER,
              key     TEXT,
              ts      INTEGER,
              PRIMARY KEY(chat_id, user_id, key)
            );
            CREATE TABLE pets(
              chat_id         INTEGER,
              pet_id          INTEGER,
              owner_id        INTEGER,
              care_done_today INTEGER DEFAULT 0,
              day_ymd         TEXT,
              PRIMARY KEY(chat_id, pet_id)
            );
            """
        )
        await db.commit()


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
        (chat_id, user_id, username or "", 0, 100),
    )


async def set_player_coins(db_path: Path, user_id: int, username: str, coins: int, chat_id: int = TEST_CHAT_ID):
    async with aiosqlite.connect(db_path) as db:
        await ensure_player(db, chat_id, user_id, username)
        await db.execute(
            "UPDATE players SET coins=? WHERE chat_id=? AND user_id=?",
            (coins, chat_id, user_id),
        )
        await db.commit()


async def get_player_coins(db_path: Path, user_id: int, chat_id: int = TEST_CHAT_ID) -> int:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT coins FROM players WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ) as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def set_pet_care(db_path: Path, pet_id: int, care_done_today: int, day_ymd: str, chat_id: int = TEST_CHAT_ID):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO pets(chat_id, pet_id, owner_id, care_done_today, day_ymd)
            VALUES(?,?,?,?,?)
            ON CONFLICT(chat_id, pet_id) DO UPDATE SET
              care_done_today=excluded.care_done_today,
              day_ymd=excluded.day_ymd
            """,
            (chat_id, pet_id, 0, care_done_today, day_ymd),
        )
        await db.commit()


async def set_cd(db, chat_id: int, user_id: int, key: str, seconds: int):
    ts = int(time.time()) + seconds
    await db.execute(
        """
        INSERT INTO cooldowns(chat_id, user_id, key, ts)
        VALUES(?,?,?,?)
        ON CONFLICT(chat_id, user_id, key) DO UPDATE SET ts=excluded.ts
        """,
        (chat_id, user_id, key, ts),
    )


async def get_cd_left(db, chat_id: int, user_id: int, key: str) -> int:
    async with db.execute(
        "SELECT ts FROM cooldowns WHERE chat_id=? AND user_id=? AND key=?",
        (chat_id, user_id, key),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return 0
    return max(0, int(row[0]) - int(time.time()))


async def _ensure_player_entry(db, chat_id: int, user_id: int, username: str | None):
    await ensure_player(db, chat_id, user_id, username or "")


async def _get_coins(db, chat_id: int, user_id: int) -> int:
    async with db.execute(
        "SELECT coins FROM players WHERE chat_id=? AND user_id=?",
        (chat_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0


def _parse_amount_from_args(context) -> int | None:
    if not getattr(context, "args", None):
        return None
    for token in reversed(context.args):
        raw = str(token).strip()
        if raw.isdigit():
            return int(raw)
    return None


async def _resolve_target(db, update, context):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        return target.id, target.username or None

    for token in getattr(context, "args", []):
        raw = str(token).strip().lstrip("@")
        if not raw or raw.isdigit():
            continue
        async with db.execute(
            "SELECT user_id, username FROM players WHERE chat_id=? AND lower(username)=lower(?)",
            (update.effective_chat.id, raw),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return int(row[0]), row[1]

    numeric_tokens = [int(str(token).strip()) for token in getattr(context, "args", []) if str(token).strip().isdigit()]
    if len(numeric_tokens) >= 2:
        user_id = numeric_tokens[0]
        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (update.effective_chat.id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return user_id, row[0] if row else None
    if len(numeric_tokens) == 1:
        user_id = numeric_tokens[0]
        async with db.execute(
            "SELECT username FROM players WHERE chat_id=? AND user_id=?",
            (update.effective_chat.id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return user_id, row[0] if row else None

    return None, None


def mention_html(user_id: int, username: str | None) -> str:
    label = f"@{username}" if username else f"ID:{user_id}"
    return f"<a href='tg://user?id={user_id}'>{escape(label, quote=False)}</a>"


def is_group(update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type in {"group", "supergroup"})


def _is_admin_here(update) -> bool:
    return update.effective_chat.id == TEST_CHAT_ID and update.effective_user.id == TEST_ADMIN_ID


class FakeRandom:
    def __init__(self, values=None):
        self.values = list(values or [])

    def random(self):
        if self.values:
            return self.values.pop(0)
        return 0.0


@dataclass
class FakeUser:
    id: int
    username: str | None = None
    full_name: str = "Test User"
    first_name: str = "Test"
    is_bot: bool = False


@dataclass
class FakeChat:
    id: int = TEST_CHAT_ID
    type: str = "group"


@dataclass
class FakeSentMessage:
    text: str
    kwargs: dict
    message_id: int
    edits: list[dict] = field(default_factory=list)

    async def edit_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        self.text = text
        self.kwargs = kwargs
        return self


@dataclass
class FakeBot:
    sent_messages: list[dict] = field(default_factory=list)
    chat_member_results: dict[int, object] = field(default_factory=dict)
    chat_member_errors: dict[int, Exception] = field(default_factory=dict)

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append({"chat_id": chat_id, "text": text, **kwargs})

    async def get_chat_member(self, chat_id, user_id):
        if user_id in self.chat_member_errors:
            raise self.chat_member_errors[user_id]
        return self.chat_member_results.get(user_id, SimpleNamespace())

    async def delete_message(self, chat_id, message_id):
        return None


@dataclass
class FakeJobQueue:
    jobs: list[dict] = field(default_factory=list)

    def run_once(self, callback, when, data=None, name=None):
        self.jobs.append({"callback": callback, "when": when, "data": data, "name": name})
        return SimpleNamespace(callback=callback, when=when, data=data, name=name)


@dataclass
class FakeApplication:
    bot_data: dict = field(default_factory=dict)


@dataclass
class FakeMessage:
    from_user: FakeUser | None = None
    reply_to_message: "FakeMessage | None" = None
    replies: list[dict] = field(default_factory=list)
    text: str | None = None
    forward_date: object | None = None
    message_id: int = 1000
    _next_message_id: int = 2000

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": text, **kwargs})
        sent = FakeSentMessage(text=text, kwargs=kwargs, message_id=self._next_message_id)
        self._next_message_id += 1
        return sent

    async def edit_text(self, text, **kwargs):
        self.replies.append({"text": text, **kwargs, "edited": True})
        self.text = text
        return self


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    effective_chat: FakeChat
    effective_message: FakeMessage

    @property
    def message(self):
        return self.effective_message


@dataclass
class FakeContext:
    args: list[str]
    bot: FakeBot = field(default_factory=FakeBot)
    application: FakeApplication = field(default_factory=FakeApplication)
    job_queue: FakeJobQueue | None = None


def load_petflix_main(module_path: Path):
    module_name = f"petflix_test_main_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


async def init_full_test_db(main_module, db_path: Path):
    async with aiosqlite.connect(db_path) as db:
        await main_module.migrate_db(db)
        await db.commit()


async def upsert_player(
    db_path: Path,
    user_id: int,
    username: str,
    *,
    chat_id: int = TEST_CHAT_ID,
    coins: int | None = None,
    price: int | None = None,
    gender: str | None = None,
    opted_out: int | None = None,
    last_seen: int | None = None,
):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO players(chat_id, user_id, username)
            VALUES(?,?,?)
            ON CONFLICT(chat_id, user_id) DO NOTHING
            """,
            (chat_id, user_id, username),
        )
        columns = {"username": username}
        if coins is not None:
            columns["coins"] = coins
        if price is not None:
            columns["price"] = price
        if gender is not None:
            columns["gender"] = gender
        if opted_out is not None:
            columns["opted_out"] = opted_out
        if last_seen is not None:
            columns["last_seen"] = last_seen
        assignments = ", ".join(f"{key}=?" for key in columns)
        values = list(columns.values()) + [chat_id, user_id]
        await db.execute(f"UPDATE players SET {assignments} WHERE chat_id=? AND user_id=?", values)
        await db.commit()


async def upsert_pet(
    db_path: Path,
    pet_id: int,
    owner_id: int | None,
    *,
    chat_id: int = TEST_CHAT_ID,
    acquired_ts: int | None = None,
    last_care_ts: int | None = None,
    care_done_today: int | None = None,
    day_ymd: str | None = None,
    purchase_lock_until: int | None = None,
    pet_skill: str | None = None,
    pet_xp: int | None = None,
    pet_level: int | None = None,
    fullcare_days: int | None = None,
    fullcare_streak: int | None = None,
):
    async with aiosqlite.connect(db_path) as db:
        now = int(time.time())
        await db.execute(
            """
            INSERT INTO pets(chat_id, pet_id, owner_id, acquired_ts, last_care_ts, care_done_today, day_ymd)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(chat_id, pet_id) DO NOTHING
            """,
            (
                chat_id,
                pet_id,
                owner_id,
                acquired_ts if acquired_ts is not None else now,
                last_care_ts if last_care_ts is not None else now,
                care_done_today if care_done_today is not None else 0,
                day_ymd or "2026-04-05",
            ),
        )
        columns = {"owner_id": owner_id}
        if acquired_ts is not None:
            columns["acquired_ts"] = acquired_ts
        if last_care_ts is not None:
            columns["last_care_ts"] = last_care_ts
        if care_done_today is not None:
            columns["care_done_today"] = care_done_today
        if day_ymd is not None:
            columns["day_ymd"] = day_ymd
        if purchase_lock_until is not None:
            columns["purchase_lock_until"] = purchase_lock_until
        if pet_skill is not None:
            columns["pet_skill"] = pet_skill
        if pet_xp is not None:
            columns["pet_xp"] = pet_xp
        if pet_level is not None:
            columns["pet_level"] = pet_level
        if fullcare_days is not None:
            columns["fullcare_days"] = fullcare_days
        if fullcare_streak is not None:
            columns["fullcare_streak"] = fullcare_streak
        assignments = ", ".join(f"{key}=?" for key in columns)
        values = list(columns.values()) + [chat_id, pet_id]
        await db.execute(f"UPDATE pets SET {assignments} WHERE chat_id=? AND pet_id=?", values)
        await db.commit()


async def fetch_scalar(db_path: Path, sql: str, params=()):
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, params) as cur:
            row = await cur.fetchone()
    return row[0] if row else None


@pytest_asyncio.fixture
async def db_path(tmp_path):
    path = tmp_path / "test_petflix.sqlite3"
    await init_test_db(path)
    return path


@pytest.fixture
def parse_mode():
    return SimpleNamespace(HTML="HTML")


@pytest.fixture
def admin_deps_factory(db_path, parse_mode):
    def factory(random_values=None):
        return {
            "aiosqlite": aiosqlite,
            "DB": str(db_path),
            "ADMIN_ID": TEST_ADMIN_ID,
            "ParseMode": parse_mode,
            "escape": escape,
            "random": FakeRandom(random_values),
            "STEAL_SUCCESS_CHANCE": 0.48,
            "STEAL_COOLDOWN_S": 300,
            "STEAL_FAIL_PENALTY_RATIO": 0.2,
            "set_cd": set_cd,
            "get_cd_left": get_cd_left,
            "mention_html": mention_html,
            "today_ymd": lambda: "2026-04-05",
            "is_group": is_group,
            "_is_admin_here": _is_admin_here,
            "_resolve_target": _resolve_target,
            "_ensure_player_entry": _ensure_player_entry,
            "_get_coins": _get_coins,
            "_parse_amount_from_args": _parse_amount_from_args,
        }

    return factory


@pytest.fixture
def economy_deps_factory(db_path, parse_mode):
    def factory(random_values=None):
        return {
            "aiosqlite": aiosqlite,
            "DB": str(db_path),
            "ParseMode": parse_mode,
            "random": FakeRandom(random_values),
            "is_group": is_group,
            "_parse_amount_from_args": _parse_amount_from_args,
            "_resolve_target": _resolve_target,
            "_ensure_player_entry": _ensure_player_entry,
            "_get_coins": _get_coins,
            "mention_html": mention_html,
            "ensure_player": ensure_player,
            "get_cd_left": get_cd_left,
            "set_cd": set_cd,
            "DAILY_COINS": 250,
            "DAILY_COOLDOWN_S": 3600,
            "BLACKJACK_COOLDOWN_S": 120,
            "BLACKJACK_MIN_BET": 10,
            "BLACKJACK_MAX_BET": 200,
            "BLACKJACK_OUTCOMES": [
                ("bust", 0.30, 0.0, "Bust"),
                ("push", 0.20, 1.0, "Push"),
                ("win", 0.40, 2.0, "Win"),
                ("blackjack", 0.10, 2.5, "Blackjack"),
            ],
        }

    return factory


@pytest.fixture
def make_update():
    def factory(
        user_id: int,
        username: str | None = None,
        *,
        chat_id: int = TEST_CHAT_ID,
        chat_type: str = "group",
        reply_from_user: FakeUser | None = None,
        reply_text: str | None = None,
        is_bot: bool = False,
        message_text: str | None = None,
        with_job_queue: bool = False,
    ):
        user = FakeUser(
            user_id,
            username=username,
            full_name=username or f"user-{user_id}",
            first_name=username or f"user-{user_id}",
            is_bot=is_bot,
        )
        reply_message = FakeMessage(from_user=reply_from_user, text=reply_text, message_id=1500) if reply_from_user else None
        msg = FakeMessage(from_user=user, reply_to_message=reply_message, text=message_text, message_id=1000)
        update = FakeUpdate(
            effective_user=user,
            effective_chat=FakeChat(id=chat_id, type=chat_type),
            effective_message=msg,
        )
        context = FakeContext(args=[], job_queue=FakeJobQueue() if with_job_queue else None)
        return update, context

    return factory


@pytest.fixture
def main_module(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("ADMIN_ID", str(TEST_ADMIN_ID))
    monkeypatch.setenv("ALLOWED_CHAT_ID", str(TEST_CHAT_ID))
    monkeypatch.setenv("DB_PATH", str(repo_root / "tests" / "placeholder.sqlite3"))
    monkeypatch.setenv("BACKUP_DIR", str(repo_root / "tests" / "backups"))
    monkeypatch.setenv("PETFLIX_TZ", "Europe/Berlin")
    return load_petflix_main(repo_root / "Petflix_3.0.py")


@pytest_asyncio.fixture
async def main_db_path(tmp_path, main_module, monkeypatch):
    path = tmp_path / "main_petflix.sqlite3"
    await init_full_test_db(main_module, path)
    monkeypatch.setattr(main_module, "DB", str(path))
    monkeypatch.setattr(main_module, "ALLOWED_CHAT_ID", TEST_CHAT_ID)
    monkeypatch.setattr(main_module, "ADMIN_ID", TEST_ADMIN_ID)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(main_module, "BACKUP_DIR", str(backup_dir))
    return path


@pytest.fixture
def ownership_commands(main_module, main_db_path):
    deps = {
        "aiosqlite": aiosqlite,
        "DB": str(main_db_path),
        "time": main_module.time,
        "escape": main_module.escape,
        "MAX_CHUNK": main_module.MAX_CHUNK,
        "ALLOWED_CHAT_ID": TEST_CHAT_ID,
        "is_group": main_module.is_group,
        "get_user_price": main_module.get_user_price,
        "get_pet_skill": main_module.get_pet_skill,
        "_skill_label": main_module._skill_label,
        "pet_level_title": main_module.pet_level_title,
        "fullcare_evolution_title": main_module.fullcare_evolution_title,
        "get_pet_lock_until": main_module.get_pet_lock_until,
        "get_active_titles_map": main_module.get_active_titles_map,
        "with_title_suffix": main_module.with_title_suffix,
        "_skill_meta": main_module._skill_meta,
    }
    return create_ownership_features(deps)


@pytest.fixture
def runtime_commands(main_module, main_db_path):
    deps = {
        "aiosqlite": aiosqlite,
        "datetime": main_module.datetime,
        "os": main_module.os,
        "shutil": main_module.shutil,
        "time": main_module.time,
        "escape": main_module.escape,
        "ParseMode": main_module.ParseMode,
        "BACKUP_DIR": main_module.BACKUP_DIR,
        "BACKUP_KEEP_FILES": main_module.BACKUP_KEEP_FILES,
        "DB": str(main_db_path),
        "MORAL_TAX_DEFAULT": main_module.MORAL_TAX_DEFAULT,
        "DAILY_CURSE_ENABLED": main_module.DAILY_CURSE_ENABLED,
        "AUTO_CURSE_ENABLED": main_module.AUTO_CURSE_ENABLED,
        "ALLOWED_CHAT_ID": TEST_CHAT_ID,
        "_is_admin_here": main_module._is_admin_here,
        "is_allowed_chat": main_module.is_allowed_chat,
        "log": main_module.log,
    }
    return create_runtime_features(deps)
