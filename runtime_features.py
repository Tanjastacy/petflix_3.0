def create_runtime_features(deps: dict):
    aiosqlite = deps["aiosqlite"]
    datetime = deps["datetime"]
    os = deps["os"]
    shutil = deps["shutil"]
    time = deps["time"]
    escape = deps["escape"]
    ParseMode = deps["ParseMode"]
    BACKUP_DIR = deps["BACKUP_DIR"]
    BACKUP_KEEP_FILES = deps["BACKUP_KEEP_FILES"]
    DB = deps["DB"]
    MORAL_TAX_DEFAULT = deps["MORAL_TAX_DEFAULT"]
    DAILY_CURSE_ENABLED = deps["DAILY_CURSE_ENABLED"]
    AUTO_CURSE_ENABLED = deps["AUTO_CURSE_ENABLED"]
    ALLOWED_CHAT_ID = deps["ALLOWED_CHAT_ID"]
    _is_admin_here = deps["_is_admin_here"]
    is_allowed_chat = deps["is_allowed_chat"]
    log = deps["log"]

    async def get_runtime_settings(db, chat_id: int) -> dict:
        await db.execute(
            "INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id,)
        )
        async with db.execute(
            """
            SELECT
                COALESCE(moraltax_enabled, 1),
                COALESCE(moraltax_amount, ?),
                COALESCE(daily_curse_enabled, ?),
                COALESCE(auto_curse_enabled, ?)
            FROM settings
            WHERE chat_id=?
            """,
            (MORAL_TAX_DEFAULT, 1 if DAILY_CURSE_ENABLED else 0, 1 if AUTO_CURSE_ENABLED else 0, chat_id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {
                "moraltax_enabled": True,
                "moraltax_amount": MORAL_TAX_DEFAULT,
                "daily_curse_enabled": DAILY_CURSE_ENABLED,
                "auto_curse_enabled": AUTO_CURSE_ENABLED,
            }
        return {
            "moraltax_enabled": bool(int(row[0] or 0)),
            "moraltax_amount": int(row[1] or MORAL_TAX_DEFAULT),
            "daily_curse_enabled": bool(int(row[2] or 0)),
            "auto_curse_enabled": bool(int(row[3] or 0)),
        }

    async def set_runtime_flag(db, chat_id: int, key: str, enabled: bool):
        if key not in {"moraltax_enabled", "daily_curse_enabled", "auto_curse_enabled"}:
            raise ValueError("invalid runtime flag")
        await db.execute(
            "INSERT INTO settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id,)
        )
        await db.execute(
            f"UPDATE settings SET {key}=? WHERE chat_id=?",
            (1 if enabled else 0, chat_id)
        )

    def _backup_file_prefix(chat_id: int) -> str:
        return f"petflix_backup_{chat_id}_"

    def _backup_path(chat_id: int, ts: int | None = None) -> str:
        ts = ts or int(time.time())
        stamp = datetime.datetime.fromtimestamp(ts).strftime("%Y%m%d_%H%M%S")
        return os.path.join(BACKUP_DIR, f"{_backup_file_prefix(chat_id)}{stamp}.db")

    def _list_backups(chat_id: int) -> list[str]:
        if not os.path.isdir(BACKUP_DIR):
            return []
        prefix = _backup_file_prefix(chat_id)
        files = []
        for name in os.listdir(BACKUP_DIR):
            if not name.startswith(prefix) or not name.endswith(".db"):
                continue
            files.append(os.path.join(BACKUP_DIR, name))
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files

    def _rotate_backups(chat_id: int, keep: int = BACKUP_KEEP_FILES) -> int:
        files = _list_backups(chat_id)
        removed = 0
        for path in files[keep:]:
            try:
                os.remove(path)
                removed += 1
            except Exception:
                pass
        return removed

    async def _create_backup(chat_id: int) -> str:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dst = _backup_path(chat_id)
        try:
            async with aiosqlite.connect(DB) as src:
                async with aiosqlite.connect(dst) as target:
                    await src.backup(target)
                    await target.commit()
        except Exception:
            shutil.copy2(DB, dst)
        _rotate_backups(chat_id, BACKUP_KEEP_FILES)
        return dst

    async def cmd_backupnow(update, context):
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur Admin.")
        chat_id = update.effective_chat.id
        try:
            path = await _create_backup(chat_id)
            await update.effective_message.reply_text(
                f"Backup erstellt: <code>{escape(path, quote=True)}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await update.effective_message.reply_text(f"Backup fehlgeschlagen: {type(e).__name__}: {e}")

    async def cmd_backups(update, context):
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur Admin.")
        chat_id = update.effective_chat.id
        files = _list_backups(chat_id)
        if not files:
            return await update.effective_message.reply_text("Keine Backups gefunden.")
        lines = ["<b>Backups (neu -> alt)</b>"]
        for p in files[:10]:
            name = os.path.basename(p)
            size_kb = max(1, int(os.path.getsize(p) / 1024))
            lines.append(f"- <code>{escape(name, quote=True)}</code> ({size_kb} KB)")
        await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_restorebackup(update, context):
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur Admin.")
        if not context.args:
            return await update.effective_message.reply_text("Nutzung: /restorebackup <dateiname.db>")

        name = os.path.basename(context.args[0].strip())
        src = os.path.join(BACKUP_DIR, name)
        if not os.path.isfile(src):
            return await update.effective_message.reply_text("Backup-Datei nicht gefunden.")

        try:
            shutil.copy2(src, DB)
            for suffix in ("-wal", "-shm"):
                sidecar = DB + suffix
                if os.path.exists(sidecar):
                    os.remove(sidecar)
            await update.effective_message.reply_text(
                f"Restore abgeschlossen aus <code>{escape(name, quote=True)}</code>.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await update.effective_message.reply_text(f"Restore fehlgeschlagen: {type(e).__name__}: {e}")

    async def cmd_settings(update, context):
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur Admin.")
        chat_id = update.effective_chat.id
        key_map = {
            "moraltax": "moraltax_enabled",
            "dailycurse": "daily_curse_enabled",
        }
        async with aiosqlite.connect(DB) as db:
            if len(context.args) >= 2:
                k = context.args[0].lower()
                v = context.args[1].lower()
                if k in key_map and v in {"on", "off"}:
                    await set_runtime_flag(db, chat_id, key_map[k], v == "on")
                    await db.commit()
                else:
                    return await update.effective_message.reply_text(
                        "Nutzung: /settings <moraltax|dailycurse> <on|off> oder /settings status"
                    )
            runtime = await get_runtime_settings(db, chat_id)
            await db.commit()
        text = (
            "<b>Settings</b>\n"
            f"- Moraltax: {'on' if runtime['moraltax_enabled'] else 'off'} (amount={runtime['moraltax_amount']})\n"
            f"- Daily Curse: {'on' if runtime['daily_curse_enabled'] else 'off'}\n"
            "Beispiel: /settings dailycurse on"
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_admin(update, context):
        if not _is_admin_here(update):
            return await update.effective_message.reply_text("Nur Admin.")
        chat_id = update.effective_chat.id
        now = int(time.time())
        day_start = now - 86400
        async with aiosqlite.connect(DB) as db:
            runtime = await get_runtime_settings(db, chat_id)
            async with db.execute("SELECT COUNT(*) FROM players WHERE chat_id=?", (chat_id,)) as cur:
                players = int((await cur.fetchone())[0] or 0)
            async with db.execute("SELECT COUNT(*) FROM pets WHERE chat_id=?", (chat_id,)) as cur:
                pets = int((await cur.fetchone())[0] or 0)
            async with db.execute("SELECT COUNT(*) FROM hass_challenges WHERE chat_id=? AND active=1", (chat_id,)) as cur:
                hass_active = int((await cur.fetchone())[0] or 0)
            async with db.execute("SELECT COUNT(*) FROM love_challenges WHERE chat_id=? AND active=1", (chat_id,)) as cur:
                love_active = int((await cur.fetchone())[0] or 0)
            async with db.execute("SELECT COUNT(*) FROM care_events WHERE chat_id=? AND ts>=?", (chat_id, day_start)) as cur:
                care_events_24h = int((await cur.fetchone())[0] or 0)
            await db.commit()

        backups = _list_backups(chat_id)
        latest_backup = os.path.basename(backups[0]) if backups else "keins"
        text = (
            "<b>Admin Dashboard</b>\n"
            f"- Players: {players}\n"
            f"- Pets: {pets}\n"
            f"- Active Hass: {hass_active}\n"
            f"- Active Love: {love_active}\n"
            f"- Care Events (24h): {care_events_24h}\n"
            f"- Moraltax: {'on' if runtime['moraltax_enabled'] else 'off'} ({runtime['moraltax_amount']})\n"
            f"- Daily Curse: {'on' if runtime['daily_curse_enabled'] else 'off'}\n"
            f"- Auto Curse: {'on' if runtime['auto_curse_enabled'] else 'off'}\n"
            f"- Latest Backup: <code>{escape(latest_backup, quote=True)}</code>"
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def daily_backup_job(context):
        chat_id = ALLOWED_CHAT_ID
        try:
            await _create_backup(chat_id)
        except Exception as e:
            log.error(f"daily backup failed: {e}")

    async def cmd_help(update, context):
        if not is_allowed_chat(update):
            await update.effective_message.reply_text("Dieses Spiel läuft nur in der vorgesehenen Gruppe.")
            return
        text = (
            "<b>PETFLIX 3.0 - SOS PET</b>\n\n"
            "Willkommen bei Petflix.\n"
            "Ein Gruppen-Spiel mit Coins, Pets, Ownern, Brandmarken, Klauen, Boxen, Challenges und genug digitaler Schande für alle Beteiligten.\n\n"
            "<b>Kurz gesagt:</b>\n"
            "Du schreibst in der Gruppe, sammelst Coins, kaufst User, wirst gekauft, pflegst Pets, trägst Brandmarken, öffnest Boxen, klaust, verlierst, gewinnst und wirst dabei öffentlich zum Verwaltungsproblem.\n\n"
            "<b>WICHTIGSTE BEFEHLE</b>\n"
            "/profil - deine wichtigste Übersicht: Coins, Kaufpreis, Besitzer, Pets, Brandmarken, Skill, Laune, Bindung, Pflege und Status.\n"
            "/profil @user - Profil eines anderen Users.\n"
            "/balance - kurzer Coinstand.\n"
            "/top - reichste User der Gruppe.\n"
            "/prices - aktuelle Kaufpreise.\n\n"
            "<b>PET- UND OWNER-SYSTEM</b>\n"
            "/buy @user - kauft einen User als Pet.\n"
            "/risk @user - riskanter Kaufversuch. Kann sich lohnen. Kann auch peinlich werden. Also genau dein Niveau.\n"
            "/owner - dein Owner-/Pet-Status.\n"
            "/owner @user - Status eines anderen Users.\n"
            "/ownerlist - aktive Besitzverhältnisse.\n"
            "/release - gibt dein Pet frei. Manchmal ist Loslassen auch nur ein Command.\n\n"
            "<b>BRANDMARKEN</b>\n"
            "Brandmarken sind kaufbare Titel. Du kannst dir selbst eine kaufen oder als Owner deinem Pet eine aufzwingen. Wenn das Pet sie nicht will, kann es sie gegen Coins ablegen. Würde ist hier also käuflich.\n"
            "/brandshop - Brandmarken-Shop.\n"
            "/brandkaufen Name der Brandmarke - kauft dir eine Brandmarke.\n"
            "/brandsetzen Name der Brandmarke - setzt eine gekaufte Brandmarke aktiv.\n"
            "/meinebrands - zeigt deine gekauften und aktiven Brandmarken.\n"
            "/brandpet @user Name der Brandmarke - zwingt deinem eigenen Pet eine Brandmarke auf.\n"
            "/brandablegen - legt eine aufgezwungene Owner-Brand gegen Coins ab.\n\n"
            "<b>COINS</b>\n"
            "Du bekommst Coins durch Aktivität, Boni, Events und manche Aktionen. Du verlierst Coins durch Pech, Flüche, Strafen, Boxen, Klauversuche oder weil du offensichtlich schlechte Entscheidungen liebst.\n"
            "/daily - Tagesbonus.\n"
            "/treat @user Betrag - verschenkt Coins.\n"
            "/leckerli @user Betrag - Alias für /treat.\n\n"
            "<b>BOXEN</b>\n"
            "/boxen - verfügbare Boxen.\n"
            "/buybox - normale Box.\n"
            "/buyboxkeller - Kellerkiste.\n"
            "/buyboxabyss - Abyss-Kiste.\n"
            "Boxen können Coins, Titel, XP, Schilde, Verluste oder andere Gemeinheiten bringen. Kurz: Glücksspiel, aber mit mehr Kellergeruch.\n\n"
            "<b>KLAUEN UND BLUTSCHULD</b>\n"
            "/steal @user - versucht Coins zu klauen.\n"
            "/snatchsteal @user - härterer Steal mit mehr Pet-Drama.\n"
            "/fehde - aktive Blutschuld/Fehden.\n"
            "Pets können schützen, verraten, helfen oder in Drama verwickelt werden. Völlig normal. Für diesen Bot jedenfalls.\n\n"
            "<b>PFLEGE</b>\n"
            "Owner können ihre Pets pflegen. Pflege beeinflusst Bindung, Laune, XP, Prägung und Status. Wer sein Pet ignoriert, bekommt Rebellion, schlechte Laune oder andere Probleme. Verantwortung, aber als Telegram-Befehl. Schlimm genug.\n"
            "Wichtig: /pet, /walk, /kiss, /dine, /massage, /loben, /belohnen.\n"
            "Es gibt weitere härtere Petplay-Befehle. Findest du raus. Oder du fragst jemanden, der hier schon länger seine Würde verloren hat.\n\n"
            "<b>CHALLENGES UND EVENTS</b>\n"
            "/hass - Hass-Challenge.\n"
            "/selbst - wird für bestimmte Hass-Challenges genutzt.\n"
            "/liebes - Liebesgeständnis-Challenge.\n"
            "Außerdem gibt es Zufallsboni, Superwörter, Moraltax, Flüche, Prime-Time-Events und andere kleine Katastrophen.\n\n"
            "<b>HILFE UND ADMIN</b>\n"
            "/help - zeigt diese Hilfe.\n"
            "/sospet - zeigt diese Hilfe.\n"
            "/id - zeigt deine Telegram-ID.\n"
            "Admin-Befehle sind nur für Admins gedacht. Wenn du kein Admin bist, geh weiter Coins verlieren.\n\n"
            "<b>TIPP</b>\n"
            "Wenn du nicht weißt, wo du stehst, nutze /profil. Dort siehst du, ob du reich, verkauft, markiert, gepflegt, vernachlässigt oder einfach nur Teil dieses sozialen Unfalls bist."
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def cmd_start(update, context):
        if not is_allowed_chat(update):
            await update.effective_message.reply_text("Dieses Spiel läuft nur in der vorgesehenen Gruppe.")
            return
        await update.effective_message.reply_text(
            "Petflix läuft. Coins sammeln, User kaufen, Pets pflegen, Steals riskieren und Drama auslösen. Nutze /sospet für die Übersicht."
        )

    return {
        "get_runtime_settings": get_runtime_settings,
        "set_runtime_flag": set_runtime_flag,
        "cmd_backupnow": cmd_backupnow,
        "cmd_backups": cmd_backups,
        "cmd_restorebackup": cmd_restorebackup,
        "cmd_settings": cmd_settings,
        "cmd_admin": cmd_admin,
        "daily_backup_job": daily_backup_job,
        "cmd_help": cmd_help,
        "cmd_start": cmd_start,
    }
