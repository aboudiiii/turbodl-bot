#!/usr/bin/env bash
#
# TurboDL — deployment script for Oracle Cloud Free Tier (Ubuntu 22.04 / 24.04)
#
# Installs system dependencies, Python 3.11 + virtualenv, the pip requirements,
# secures the data files, installs a systemd service so the bot runs 24/7
# (auto-restart + boot), and schedules a daily SQLite backup via cron.
#
# Run as root/sudo inside the cloned repository:
#   sudo ./deploy.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="turbodl"
# Run the bot as the user who invoked sudo (or the current user).
SERVICE_USER="${SUDO_USER:-$(id -un)}"
BACKUP_TAG="turbodl-backup"

echo "==> TurboDL deploy started (dir: ${APP_DIR}, user: ${SERVICE_USER})"

if [ "$(id -u)" -ne 0 ]; then
    echo "!! Please run as root:  sudo ./deploy.sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
echo "==> Installing system packages (git ffmpeg aria2 sqlite3 ca-certs ...)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates curl git ffmpeg aria2 sqlite3 lsb-release \
    software-properties-common

# ---------------------------------------------------------------------------
# 2. Python 3.11+
# ---------------------------------------------------------------------------
echo "==> Ensuring Python 3.11"

install_python() {  # Ubuntu 22.04/24.04 via deadsnakes PPA
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        python3.11 python3.11-venv python3.11-dev
}

if ! command -v python3.11 >/dev/null 2>&1; then
    install_python
fi

PYTHON_BIN="$(command -v python3.11 || command -v python3)"
[[ -n "${PYTHON_BIN}" ]] || { echo "!! Python 3.11 not found"; exit 1; }
echo "   Using ${PYTHON_BIN} ($("${PYTHON_BIN}" --version 2>&1 | tail -n1))"

# ---------------------------------------------------------------------------
# 3. Virtual environment + dependencies
# ---------------------------------------------------------------------------
echo "==> Creating virtualenv and installing requirements"
"${PYTHON_BIN}" -m venv --prompt turbodl "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip wheel setuptools
"${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"
# Keep yt-dlp up to date (YouTube changes break older builds quickly).
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade yt-dlp

# ---------------------------------------------------------------------------
# 4. Configuration
# ---------------------------------------------------------------------------
echo "==> Preparing .env"
if [ ! -f "${APP_DIR}/.env" ]; then
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    echo "!! IMPORTANT: edit ${APP_DIR}/.env  ->  BOT_TOKEN, ADMIN_IDS, ZAIN_CASH_NUMBER"
fi
chmod 600 "${APP_DIR}/.env"

echo "==> Creating data / logs / backups directories"
mkdir -p "${APP_DIR}/data" "${APP_DIR}/logs" "${APP_DIR}/backups" "${APP_DIR}/downloads"
chmod 700 "${APP_DIR}/data" "${APP_DIR}/backups" "${APP_DIR}/downloads"
chmod 600 "${APP_DIR}/data"/*.db 2>/dev/null || true

# ---------------------------------------------------------------------------
# 5. systemd service (run 24/7, restart on crash/reboot)
# ---------------------------------------------------------------------------
echo "==> Installing systemd service (${SERVICE}.service)"
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=TurboDL Telegram Bot
Wants=network-online.target
After=network.target network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/bot.py
Restart=always
RestartSec=5
UMask=0077
NoNewPrivileges=true
StandardOutput=append:${APP_DIR}/logs/turbodl.log
StandardError=append:${APP_DIR}/logs/turbodl.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"
systemctl restart "${SERVICE}"

# ---------------------------------------------------------------------------
# 6. Daily database backup (03:00 UTC)
# ---------------------------------------------------------------------------
echo "==> Scheduling daily database backup (backup.sh via cron)"
chmod +x "${APP_DIR}/backup.sh"
# Remove any previous TurboDL cron line, then add the fresh one for SERVICE_USER.
crontab -u "${SERVICE_USER}" -l 2>/dev/null | grep -v "${BACKUP_TAG}" > /tmp/.turbodl_cron || true
echo "0 3 * * * ${APP_DIR}/backup.sh ${BACKUP_TAG}" >> /tmp/.turbodl_cron
crontab -u "${SERVICE_USER}" /tmp/.turbodl_cron
rm -f /tmp/.turbodl_cron

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
echo
echo "=============================================================="
echo " TurboDL deployed successfully! 🚀"
echo "=============================================================="
echo " Service   : systemctl status ${SERVICE}"
echo " Logs      : journalctl -u ${SERVICE} -f"
echo "            (also stored in ${APP_DIR}/logs/turbodl.log)"
echo " Restart   : sudo systemctl restart ${SERVICE}"
echo " Stop      : sudo systemctl stop ${SERVICE}"
echo " Backup    : ${APP_DIR}/backups  (daily at 03:00 UTC)"
echo " Manual    : ${APP_DIR}/backup.sh"
echo "----------------------"
echo " Next: edit ${APP_DIR}/.env first, then:"
echo "   sudo systemctl restart ${SERVICE}"
echo " Then open the bot in Telegram and send /start"
echo "=============================================================="