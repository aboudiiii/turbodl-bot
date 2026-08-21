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
#
# One-line deployment (auto-writes .env, no editing needed):
#   sudo ./deploy.sh --token "BOT_TOKEN" --admin-ids "ID1,ID2" --zain "07800000000"
#
# Optional: install + run a Telegram Local Bot API server (2 GB uploads):
#   sudo ./deploy.sh --token "..." --admin-ids "..." --zain "..." \
#       --local-api-id "YOUR_API_ID" --local-api-hash "YOUR_API_HASH"

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="turbodl"
# Run the bot as the user who invoked sudo (or the current user).
SERVICE_USER="${SUDO_USER:-$(id -un)}"
BACKUP_TAG="turbodl-backup"

# ---------------------------------------------------------------------------
# CLI options (optional, for fully automated one-line deployment)
# ---------------------------------------------------------------------------
OPT_TOKEN=""
OPT_ADMIN=""
OPT_ZAIN=""
OPT_API_ID=""
OPT_API_HASH=""
while [ $# -gt 0 ]; do
    case "$1" in
        --token)         OPT_TOKEN="${2:-}"   ; shift 2 ;;
        --admin-ids)     OPT_ADMIN="${2:-}"   ; shift 2 ;;
        --zain)          OPT_ZAIN="${2:-}"    ; shift 2 ;;
        --local-api-id)  OPT_API_ID="${2:-}"  ; shift 2 ;;
        --local-api-hash) OPT_API_HASH="${2:-}" ; shift 2 ;;
        -h|--help)   grep -E "^(#|$)" "$0" ; exit 0 ;;
        *) echo "!! Unknown option: $1"; exit 1 ;;
    esac
done

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
fi

# Write config values passed on the command line (one-line deployment mode).
if [ -n "${OPT_TOKEN}" ]; then
    sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${OPT_TOKEN}|" "${APP_DIR}/.env"
fi
if [ -n "${OPT_ADMIN}" ]; then
    sed -i "s|^ADMIN_IDS=.*|ADMIN_IDS=${OPT_ADMIN}|" "${APP_DIR}/.env"
fi
if [ -n "${OPT_ZAIN}" ]; then
    sed -i "s|^ZAIN_CASH_NUMBER=.*|ZAIN_CASH_NUMBER=${OPT_ZAIN}|" "${APP_DIR}/.env"
fi

if [ ! -s "${APP_DIR}/.env" ]; then
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
# 5b. Optional: Telegram Local Bot API server (uploads up to 2 GB)
#
# Enabled when BOTH --local-api-id and --local-api-hash are passed (values come
# from https://my.telegram.org/api). Installs the telegram-bot-api server in
# local mode on 127.0.0.1:8081 as a systemd unit, then points the bot at it.
# ---------------------------------------------------------------------------
if [ -n "${OPT_API_ID}" ] && [ -n "${OPT_API_HASH}" ]; then
    echo "==> Installing Local Bot API server (2 GB uploads)"
    LOCAL_API_DIR="${APP_DIR}/local-api"
    LOCAL_API_BIN="${LOCAL_API_DIR}/telegram-bot-api"
    mkdir -p "${LOCAL_API_DIR}"

    if [ ! -x "${LOCAL_API_BIN}" ]; then
        DOWNLOAD_URL="https://github.com/jakbin/telegram-bot-api-binary/releases/latest/download/telegram-bot-api"
        echo "   Downloading telegram-bot-api binary..."
        if curl -fSL --retry 3 -o "${LOCAL_API_BIN}" "${DOWNLOAD_URL}"; then
            chmod +x "${LOCAL_API_BIN}"
        else
            rm -f "${LOCAL_API_BIN}"
            echo "!! Could not download a prebuilt binary."
            echo "!! Build the official server at https://tdlib.github.io/telegram-bot-api/build.html"
            echo "   (choose your OS; on ARM Ampere select 'Other'/arm64), then place the"
            echo "   'telegram-bot-api' binary at: ${LOCAL_API_BIN}"
            echo "   and rerun: sudo ./deploy.sh --local-api-id ... --local-api-hash ..."
        fi
    fi

    if [ -x "${LOCAL_API_BIN}" ]; then
        cat > "/etc/systemd/system/telegram-bot-api.service" <<EOF
[Unit]
Description=Telegram Bot API local server (2 GB uploads)
After=network.target network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${LOCAL_API_DIR}
ExecStart=${LOCAL_API_BIN} --api-id=${OPT_API_ID} --api-hash=${OPT_API_HASH} --local --http-port=8081 --dir=${LOCAL_API_DIR}/data --temp-dir=${LOCAL_API_DIR}/tmp
Restart=always
RestartSec=5
NoNewPrivileges=true
StandardOutput=append:${APP_DIR}/logs/telegram-bot-api.log
StandardError=append:${APP_DIR}/logs/telegram-bot-api.log

[Install]
WantedBy=multi-user.target
EOF
        mkdir -p "${LOCAL_API_DIR}/data" "${LOCAL_API_DIR}/tmp"
        chmod 700 "${LOCAL_API_DIR}/data" "${LOCAL_API_DIR}/tmp"
        systemctl daemon-reload
        systemctl enable --now telegram-bot-api
        systemctl restart telegram-bot-api

        # Point the bot at the local server and lift the 50 MB cap.
        if grep -q "^TELEGRAM_LOCAL_API_URL=" "${APP_DIR}/.env"; then
            sed -i "s|^TELEGRAM_LOCAL_API_URL=.*|TELEGRAM_LOCAL_API_URL=http://127.0.0.1:8081|" "${APP_DIR}/.env"
        else
            echo "TELEGRAM_LOCAL_API_URL=http://127.0.0.1:8081" >> "${APP_DIR}/.env"
        fi
        if grep -q "^TELEGRAM_UPLOAD_LIMIT_MB=" "${APP_DIR}/.env"; then
            sed -i "s|^TELEGRAM_UPLOAD_LIMIT_MB=.*|TELEGRAM_UPLOAD_LIMIT_MB=2048|" "${APP_DIR}/.env"
        else
            echo "TELEGRAM_UPLOAD_LIMIT_MB=2048" >> "${APP_DIR}/.env"
        fi
        systemctl restart "${SERVICE}"
        echo "   Local Bot API server installed on 127.0.0.1:8081 (systemd: telegram-bot-api)"
    else
        echo "!! Local Bot API server NOT installed. The bot keeps 50 MB Cloud API limit for now."
    fi
fi

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
if [ -n "${OPT_API_ID}" ] && [ -n "${OPT_API_HASH}" ]; then
    if systemctl is-active --quiet telegram-bot-api; then
        echo " Local API : ACTIVE on 127.0.0.1:8081 (2 GB uploads OK)"
    else
        echo " Local API : requested but not running — see logs/telegram-bot-api.log"
    fi
fi
echo "----------------------"
echo " Next: edit ${APP_DIR}/.env first, then:"
echo "   sudo systemctl restart ${SERVICE}"
echo " (auto-configured .env? just restart is enough)"
echo " Then open the bot in Telegram and send /start"
echo "=============================================================="