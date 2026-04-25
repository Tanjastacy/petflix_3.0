# AWS setup

Der Service-Name ist `petflix_3.0`.

Normale Updates:

```bash
cd /opt/petflix_3.0
git pull
sudo bash deploy/deploy_petflix_3.0.sh
```

Neuaufbau mit frischer Datenbank:

```bash
cd /opt/petflix_3.0
git pull
sudo bash deploy/deploy_petflix_3.0.sh --reset-db
```

Beispiel fuer die `.env`:

```env
BOT_TOKEN=...
ALLOWED_CHAT_ID=...
ADMIN_ID=...
DB_PATH=/opt/petflix_3.0/data/petflix_3.0.db
BACKUP_DIR=/opt/petflix_3.0/data
PETFLIX_TZ=Europe/Berlin
```

Erstinstallation auf AWS:

```bash
cd /opt
sudo git clone https://github.com/Tanjastacy/petflix_3.0.git
sudo chown -R $USER:$USER /opt/petflix_3.0
cd /opt/petflix_3.0
nano .env
sudo bash deploy/deploy_petflix_3.0.sh
```

Danach:

```bash
sudo systemctl restart petflix_3.0
sudo systemctl status petflix_3.0
journalctl -u petflix_3.0 -n 100 --no-pager
```
