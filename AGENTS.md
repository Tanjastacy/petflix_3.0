# Repository Guidelines

## Project Structure & Module Organization
- `Petflix_3.0.py` is the main Telegram bot implementation and contains all handlers and database logic.
- `petflix_3.0.db` is the SQLite database used by default (or a sample copy for local runs).
- `data/` stores backups when `BACKUP_DIR` points there.
- `.venv/` is a local Python virtual environment (do not commit changes from it).

## Build, Test, and Development Commands
- `python -m venv .venv` creates a local virtual environment.
- `pip install -r requirements.txt` installs runtime dependencies.
- Set required environment variables: `BOT_TOKEN`, `ALLOWED_CHAT_ID`, `ADMIN_ID`, `DB_PATH`, `BACKUP_DIR`, `PETFLIX_TZ`. Use `.env` as a local template, but do not commit real tokens.
- `python Petflix_3.0.py` runs the bot in polling mode.

## Coding Style & Naming Conventions
- Use 4-space indentation and keep Python code PEP 8 compliant.
- Name constants in `UPPER_SNAKE_CASE`; functions and variables in `snake_case`.
- Keep configuration values near the top of the file; group related handlers together for readability.
- No formatter or linter is configured; keep diffs small and consistent with existing style.

## Testing Guidelines
- No automated test suite or `tests/` directory is currently present.
- If you add tests, use `pytest` with `test_*.py` naming and run with `python -m pytest` after adding the dependency.

## Commit & Pull Request Guidelines
- Commit messages are short, lowercase, and imperative (for example: `fix bug moraltax`). Follow that pattern.
- Pull requests should explain user-facing behavior changes, note any config or database impacts, and include manual validation steps.

## Security & Configuration Tips
- Never commit real bot tokens or production database files.
- Keep secrets in local environment variables or a private `.env` file and update `DB_PATH` for non-local deployments.
- Database schema/content changes must always happen via code migrations (`migrate_db` path), never by manually editing `.db` files.
- Never rely on a locally modified `.db` file for deployment behavior (especially AWS); migration code is the single source of truth.

## Collaboration Defaults (Persistent)
- Preferred language for communication is German.
- For normal requests, implement changes directly first and ask follow-up questions only when requirements are ambiguous or risky.
- Keep diffs small and focused; avoid unrelated refactors in `Petflix_3.0.py`.
- After code changes, run a quick syntax check with `python -m py_compile Petflix_3.0.py` when possible.
- In every final response, include:
  - short summary of what changed,
  - touched file paths,
  - what was verified (or what could not be verified).
- Do not change secrets in `.env` and do not commit database content changes unless explicitly requested.
- ALWAYS perform DB changes through migrations only; do not create/alter tables manually in SQLite files.
