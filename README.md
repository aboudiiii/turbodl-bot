# TurboDL — Telegram Download Bot

A Telegram bot that downloads videos/audio from 1800+ sites (YouTube, TikTok,
Instagram, Twitter/X, Facebook, Snapchat, Reddit, direct links, ...) and sends
them straight to the user's chat — with a free tier and a premium subscription
paid via Zain Cash.

> Built with Python 3.11, `python-telegram-bot`, `yt-dlp`, `aria2` and `ffmpeg`.
> Hosted for **$0/year** on Oracle Cloud Always Free Tier.

---

## Table of contents

- [Features](#features)
- [Deploy on Oracle Cloud (النشر بالعربية)](#deploy-on-oracle-cloud-arabic)
- [Deploy on Oracle Cloud (English guide)](#deploy-on-oracle-cloud-english)
- [Project structure](#project-structure)
- [Environment variables](#environment-variables)
- [Admin commands](#admin-commands)
- [How the download pipeline works](#how-the-download-pipeline-works)
- [Backups](#backups)
- [Tips](#tips)

---

## Features

**Free tier**
- 3 downloads per day, up to 50 MB per file
- Quality selection (best / 720p / 480p / 360p / MP3 audio)
- Progress bar + speed/ETA live in chat
- Supports every site yt-dlp supports + any direct file link

**Premium (5000 IQD/month)**
- Unlimited downloads, files up to 2 GB
- Aria2 with 16 parallel connections (much faster than one connection)
- HLS stream (.m3u8) support

**Owner (ADMIN_IDS)**
- Automatic permanent premium — no limits, no expiry
- Full admin command access

---

## Deploy on Oracle Cloud (Arabic)

### النشر على Oracle Cloud — الدليل العربي 🇮🇶

خطوات كاملة لنشر البوت على **Oracle Cloud Free Tier** (مجاني دائمًا):
سيرفر ARM Ampere بحجم **4 مراكز / 24GB رام / 200GB قرص** مع **Ubuntu 22.04/24.04**.

#### 1) إنشاء السيرفر المجاني
1. سجّل حسابًا مجانيًا على: **https://www.oracle.com/cloud/free**
   - استخدم بريد حقيقي ورقم هاتف (التحقق إلزامي).
   - بعد التفعيل، اضغط **Create a VM instance**.
2. في تبويب **Image and shape**:
   - اختر **Canonical Ubuntu — 22.04 (or 24.04) (aarch64)**.
   - اضغط **Change shape** ثم اختر **Specialty and legacy** → **Ampere** → **A1.Flex**.
   - حدد **4 OCPUs + 24 GB RAM** (داخل حدود Always Free).
3. في **Networking**: اترك الإعدادات الافتراضية (سيأخذ IP عام تلقائيًا).
4. في **SSH keys**: اختر **Generate a key pair for me** وحمّل المفتاح الخاص
   (`ssh-key-...pem`) واحفظه بملف آمن، أو استخدم مفتاحك الخاص.
5. اضغط **Create** وانتظر حتى تظهر الحالة **Running**.

#### 2) الاتصال بالخادم (SSH)
**من نظام Windows (PowerShell):**
```powershell
ssh -i "C:\path\to\ssh-key-2026-...pem" ubuntu@<IP_PUBLIC>
```
**من Mac / Linux:**
```bash
chmod 400 ~/.ssh/ssh-key-2026....pem
ssh -i ~/.ssh/ssh-key-2026....pem ubuntu@<IP_PUBLIC>
```
> الـ IP تجده في صفحة الـ instance تحت **Instance access → Public IP**.
> استبدل `<IP_PUBLIC>` بمنصة النص.

#### 3) الحصول على الكود على الخادم
```bash
# خيار 1 — عبر GitHub (بعد رفع الكود):
git clone https://github.com/YOUR_USERNAME/turbodl-bot.git
cd turbodl-bot

# أو خيار 2 — ارفع الكود من جهازك:
scp -i "C:\path\to\key.pem" -r turbodl-bot/* ubuntu@<IP_PUBLIC>:/home/ubuntu/turbodl-bot/
```

#### 4) إعداد ملف الإعدادات `.env`
```bash
cd turbodl-bot
cp .env.example .env
nano .env        # عدّل BOT_TOKEN و ADMIN_IDS و ZAIN_CASH_NUMBER ثم احفظ (Ctrl+X, Y, Enter)
```

#### 5) تشغيل سكربت النشر (مرة واحدة)
```bash
sudo ./deploy.sh
```
السكربت يقوم تلقائيًا بـ:
- تثبيت Python 3.11 + ffmpeg + aria2 + git + sqlite3
- إنشاء virtualenv وتثبيت المتطلبات وتحديث yt-dlp
- تجهيز مجلدات `data/` الآمنة وحماية قاعدة البيانات (chmod 600)
- إنشاء service باسم **turbodl** ليعمل البوت 24/7 ويعيد التشغيل عند إعادة إقلاع الخادم
- جدولة نسخة احتياطية يومية لقاعدة البيانات (backup.sh عبر cron — 03:00)

#### 6) التشغيل والمتابعة
```bash
sudo systemctl restart turbodl     # أعد التشغيل بعد تعديل .env
systemctl status turbodl           # حالة الخدمة
journalctl -u turbodl -f           # مشاهدة السجلات مباشرة
tail -f /home/ubuntu/turbodl-bot/logs/turbodl.log   # أو من هنا
```
افتح البوت في تيليجرام وأرسل **/start** ثم أي رابط للاختبار. 🎉

#### النسخ الاحتياطي
- تلقائي: كل يوم 03:00 → `turbodl-bot/backups/`
- يدوي: `sudo -u ubuntu ./backup.sh`
- الاستعادة: أوقف الخدمة وانسخ ملف النسخة إلى `data/turbodl.db` ثم أعد التشغيل.

---

## Deploy on Oracle Cloud (English)

Step-by-step, free forever hosting on **Oracle Cloud Always Free Tier**:
**ARM Ampere A1.Flex — 4 OCPUs / 24 GB RAM / 200 GB** boot volume, **Ubuntu 22.04/24.04**.

### 1. Create the free instance
1. Sign up at **https://www.oracle.com/cloud/free** (real email + phone verification).
2. Click **Create a VM instance**.
3. Image and shape:
   - Image: **Canonical Ubuntu 22.04 (or 24.04)**.
   - **Change shape** → **Specialty and legacy** → **Ampere** → **A1.Flex**.
   - Choose **4 OCPUs + 24 GB RAM** (inside the Always Free envelope).
4. Networking: keep defaults (public IP assigned automatically).
5. SSH keys: **Generate a key pair for me** and download the `.pem` key (keep it safe),
   or paste your own public key.
6. Click **Create**, wait until status is **Running**.

### 2. Connect over SSH
**Windows (PowerShell):**
```powershell
ssh -i "C:\path\to\ssh-key-2026-....pem" ubuntu@<PUBLIC_IP>
```
**macOS / Linux:**
```bash
chmod 400 ~/.ssh/ssh-key-2026-....pem
ssh -i ~/.ssh/ssh-key-2026-....pem ubuntu@<PUBLIC_IP>
```
The public IP is shown under **Instance access → Public IP**.

### 3. Get the code on the server
```bash
# Option A — via GitHub (after pushing this repo):
git clone https://github.com/YOUR_USERNAME/turbodl-bot.git
cd turbodl-bot

# Option B — upload from this PC:
#   scp -i "C:\path\to\key.pem" -r turbodl-bot ubuntu@<PUBLIC_IP>:/home/ubuntu/
```

### 4. Configure `.env`
```bash
cd turbodl-bot
cp .env.example .env
nano .env        # set BOT_TOKEN, ADMIN_IDS, ZAIN_CASH_NUMBER, then Ctrl+X, Y, Enter
```

### 5. Run the deployment script (once)
```bash
sudo ./deploy.sh
```
It automatically:
- Installs **Python 3.11**, **ffmpeg**, **aria2**, **git**, **sqlite3**
- Creates a virtualenv, installs `requirements.txt`, and upgrades yt-dlp
- Creates the secure `data/` directory and locks the SQLite DB (`chmod 600`)
- Installs a **systemd service** (`turbodl`) so the bot runs 24/7, restarts on crash
  and starts on boot
- Schedules a **daily SQLite backup** (cron, 03:00)

### 6. Run & monitor
```bash
sudo systemctl restart turbodl
systemctl status turbodl
journalctl -u turbodl -f
```
Open the bot in Telegram, send `/start`, then any link. 🎉

### Backups
- Automatic: daily 03:00 → `turbodl-bot/backups/`
- Manual: `sudo -u ubuntu ./backup.sh`
- Restore: stop the service, copy a backup file over `data/turbodl.db`, start again.

---

## Project structure

```
turbodl-bot/
├── bot.py            # Telegram bot: handlers, subscription flow, admin commands
├── downloader.py     # yt-dlp + aria2 + ffmpeg download engine
├── database.py       # SQLite: users, premium, payments (+ online backup)
├── config.py         # All settings (read from .env)
├── deploy.sh         # One-command deployment on Ubuntu (installs + systemd + cron)
├── backup.sh         # Safe SQLite backup (hot, while bot is running)
├── requirements.txt
├── .env.example      # Copy to .env and fill in
├── .gitignore
├── data/             # SQLite database lives here (chmod 700/600)
├── downloads/        # Temp files, auto-deleted after each upload
├── backups/          # Daily database backups
└── logs/             # Service logs (written by systemd)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Telegram bot token (required) |
| `ADMIN_IDS` | — | Comma-separated admin user IDs (owners get permanent premium) |
| `PRIVATE_MODE` | `false` | `true` = only `ALLOWED_USER_IDS` can use the bot |
| `ALLOWED_USER_IDS` | — | Comma-separated user IDs (beta launch) |
| `PREMIUM_PRICE_IQD` | `5000` | Monthly premium price |
| `PREMIUM_DURATION_DAYS` | `30` | Days added per approval |
| `ZAIN_CASH_NUMBER` | — | Payment number shown to users |
| `FREE_DAILY_LIMIT` | `3` | Free downloads per day |
| `FREE_MAX_FILE_SIZE_MB` | `50` | Free file size cap (MB) |
| `PREMIUM_MAX_FILE_SIZE_MB` | `2048` | Premium file size cap (MB) |
| `TELEGRAM_UPLOAD_LIMIT_MB` | `50` | Upload limit (see note below) |
| `ARIA2_CONNECTIONS_PREMIUM` | `16` | Aria2 connections for premium |
| `ARIA2_CONNECTIONS_FREE` | `4` | Aria2 connections for free |
| `CLEANUP_FILES` | `true` | Delete temp files after upload |

> **Note on the upload limit:** the standard Telegram bot API caps file uploads
> at **50 MB**. To let premium users actually receive files up to 2 GB, run the
> [Telegram Local Bot API server](https://core.telegram.org/bots/api#using-a-local-bot-api-server)
> on the same machine, then set `TELEGRAM_UPLOAD_LIMIT_MB=2048`. Without it,
> every file > 50 MB is rejected by Telegram regardless of the plan.

---

## Admin commands

| Command | Description |
|---|---|
| `/stats` | Users, premium count, total downloads, today's revenue |
| `/broadcast <msg>` | Send a message to every user |
| `/approve <user_id>` | Manually activate premium (+30 days) |
| `/revoke <user_id>` | Cancel premium |
| `/setexpiry <user_id> <days>` | Extend premium for N days |
| `/purge` | Delete leftover temp files |

Admins (from `ADMIN_IDS`) always have **permanent premium**: unlimited daily
downloads, 2 GB files, no expiry.

---

## How the download pipeline works

```
user sends a link
   → yt-dlp extracts available formats
   → bot shows quality buttons
   → yt-dlp downloads the chosen format (aria2 = N parallel connections)
   → ffmpeg merges video+audio into MP4 (or extracts MP3)
   → bot sends the file to the user
   → temp files deleted from disk
```

All downloads run in a worker thread so the bot stays responsive, and a
live progress bar is pushed to the user via `edit_message_text`.

---

## Backups

`database.py` exposes `backup_database(dest)` using SQLite's **online backup API**
(safe while the bot is live). `backup.sh` wraps it with the `sqlite3` CLI:

- Creates `backups/turbodl_YYYYMMDD_HHMMSS.db`
- Keeps the newest 30 backups, prunes the rest
- Locks files with `chmod 600`

`deploy.sh` schedules it daily at **03:00 UTC** via cron.

---

## Tips

- Keep `CLEANUP_FILES=true` — files are deleted right after upload.
- Re-run `/purge` after heavy days to clear anything left behind.
- Upgrade to the **Local Bot API server** before advertising premium 2 GB files.
- After big code changes: `sudo systemctl restart turbodl`.
- Watch the service: `journalctl -u turbodl -f` runs forever and shows errors immediately.