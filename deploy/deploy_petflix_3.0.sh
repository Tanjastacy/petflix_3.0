#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="petflix_3.0"
APP_DIR="/opt/petflix_3.0"
VENV_DIR="$APP_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
ENV_FILE="$APP_DIR/.env"
DATA_DIR="$APP_DIR/data"
DB_FILE="$DATA_DIR/petflix_3.0.db"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

RESET_DB=0

for arg in "$@"; do
  case "$arg" in
    --reset-db)
      RESET_DB=1
      ;;
    *)
      echo "Unbekannte Option: $arg" >&2
      echo "Nutzung: sudo bash deploy/deploy_petflix_3.0.sh [--reset-db]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$APP_DIR" ]]; then
  echo "App-Verzeichnis fehlt: $APP_DIR" >&2
  exit 1
fi

if [[ ! -f "$APP_DIR/Petflix_3.0.py" ]]; then
  echo "Bot-Datei fehlt: $APP_DIR/Petflix_3.0.py" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env fehlt: $ENV_FILE" >&2
  echo "Bitte zuerst .env mit BOT_TOKEN, ALLOWED_CHAT_ID, ADMIN_ID, DB_PATH, BACKUP_DIR und PETFLIX_TZ anlegen." >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$PIP_BIN" install -r "$APP_DIR/requirements.txt"

mkdir -p "$DATA_DIR"

if [[ $RESET_DB -eq 1 ]]; then
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$DB_FILE" "$DB_FILE-shm" "$DB_FILE-wal"
fi

if [[ -n "${SUDO_USER:-}" ]]; then
  APP_USER="$SUDO_USER"
else
  APP_USER="$(id -un)"
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Petflix 3.0 Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON_BIN $APP_DIR/Petflix_3.0.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
echo "Deploy fertig."
echo "Service: $SERVICE_NAME"
echo "App dir: $APP_DIR"
echo "DB: $DB_FILE"
echo
systemctl --no-pager --full status "$SERVICE_NAME" || true
