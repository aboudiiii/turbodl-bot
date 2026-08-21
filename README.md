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
   - ارفع طبقة الحساب إلى **Pay As You Go** بالبطاقة المجمّدة لكي تستخدم موارد Free Tier
     (لا تُدفع أي رسوم إذا بقيت ضمن حدود Always Free).
   - بعد التفعيل اضغط **Create a VM instance**.
2. **المنطقة (Region):** اختر أقرب منطقة إليك (مثل Frankfurt / London هم أولاً
   يظهرون علامة **"Always Free eligible"** على الشكل المُختار إن كانت السعة متوفرة).
3. في تبويب **Image and shape**:
   - Image: **Canonical Ubuntu 22.04 (aarch64)** — أو 24.04.
   - اضغط **Change shape** → **Specialty and legacy** → **Ampere** → **A1.Flex**.
   - حدد **4 OCPUs + 24 GB RAM** (هذا الحد الأقصى المجاني: 4 OCPU / 24GB).
     - إذا لم تتوفر السعة، جرّب شكلًا أصغر (مثل 2 OCPU / 12GB) أو منطقة أخرى.
4. **Boot volume:** اختر **200 GB** (متضمن في الحد المجاني) لوضع مريح،
   أو اترك الحجم الافتراضي (47GB يكفي).
5. **Networking:** اترك الإعدادات الافتراضية (IP عام + فتح منفذ SSH 22 مسبقًا).
6. في **SSH keys**: اختر **Generate a key pair for me** وحمّل المفتاح الخاص
   (`ssh-key-...pem`) واحفظه بملف آمن، أو استخدم مفتاحك الخاص.
7. اضغط **Create** وانتظر حتى تظهر الحالة **Running**.

#### 2) الاتصال بالخادم (SSH)
**من نظام Windows (PowerShell):**
```powershell
ssh -i "C:\path\to\ssh-key-2026-...pem" ubuntu@<IP_PUBLIC>
```
> إذا واجهت مشكلة صلاحيات المفتاح على Windows: انسخ المفتاح إلى
> `%USERPROFILE%\.ssh\` ثم نفّذ: `icacls key.pem /inheritance:r /grant:r "$env:USERNAME:R"`

**من Mac / Linux:**
```bash
chmod 400 ~/.ssh/ssh-key-2026....pem
ssh -i ~/.ssh/ssh-key-2026....pem ubuntu@<IP_PUBLIC>
```
> الـ IP تجده في صفحة الـ instance تحت **Instance access → Public IP**.
> استبدل `<IP_PUBLIC>` بمنصة النص.

#### 3) التثبيت بسطر واحد ⚡ (الطريقة الأسرع)
ارفع الكود أولاً إلى **GitHub** (راجع قسم *Git* في نهاية الدليل)، ثم شغّل
هذا الأمر **فسطر واحد** على الخادم (يحذف الملفات القديمة، ينزّل الكود،
يكتب الإعدادات، وينشر عبر systemd تلقائيًا):

```bash
sudo bash -c 'apt-get update -qq && apt-get install -y -qq git && rm -rf /home/ubuntu/turbodl-bot && git clone --depth=1 https://github.com/YOUR_USERNAME/turbodl-bot /home/ubuntu/turbodl-bot && cd /home/ubuntu/turbodl-bot && ./deploy.sh --token "YOUR_BOT_TOKEN" --admin-ids "YOUR_TELEGRAM_ID" --zain "YOUR_ZAIN_NUMBER"'
```
> استبدل: `YOUR_USERNAME` (اسمك في GitHub)، `YOUR_BOT_TOKEN` (من BotFather)،
> `YOUR_TELEGRAM_ID`، `YOUR_ZAIN_NUMBER`.
>
> 💡 **لرفع حد 50MB وإرسال ملفات حتى 2GB**: أضف `--local-api-id "رقمك" --local-api-hash "هاشك"`
> (من [my.telegram.org](https://my.telegram.org/api)) لتثبيت Local Bot API Server تلقائيًا.

#### 4) الطريقة اليدوية (بدون سطر واحد)
```bash
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/turbodl-bot.git
cd turbodl-bot
cp .env.example .env
nano .env        # عدّل BOT_TOKEN و ADMIN_IDS و ZAIN_CASH_NUMBER ثم احفظ (Ctrl+X, Y, Enter)
sudo ./deploy.sh
```

السكربت (في الحالتين) يقوم تلقائيًا بـ:
- تثبيت Python 3.11 + ffmpeg + aria2 + git + sqlite3
- إنشاء virtualenv وتثبيت المتطلبات وتحديث yt-dlp
- تجهيز مجلدات `data/` الآمنة وحماية قاعدة البيانات (chmod 600)
- إنشاء service باسم **turbodl** ليعمل البوت 24/7 ويعيد التشغيل عند إعادة إقلاع الخادم
- جدولة نسخة احتياطية يومية لقاعدة البيانات (backup.sh عبر cron — 03:00)

#### 5) التشغيل والمتابعة
```bash
systemctl status turbodl           # حالة الخدمة
journalctl -u turbodl -f           # مشاهدة السجلات مباشرة
tail -f /home/ubuntu/turbodl-bot/logs/turbodl.log   # أو من هنا
```
> ملاحظة: في الطريقة اليدوية، بعد أي تعديل على `.env` نفّذ:
> `sudo systemctl restart turbodl`.
> في الطريقة بسطر واحد الإعدادات كُتبت تلقائيًا وليست هناك حاجة لإعادة التشغيل.

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
2. Upgrade the account to **Pay As You Go** with a frozen card to lift soft limits —
   you still pay **nothing** as long as you stay inside the Always Free envelope.
3. Click **Create a VM instance**.
4. **Region:** pick the closest one (e.g. Frankfurt/London). The chosen shape shows
   an **"Always Free eligible"** badge only when that region has free capacity —
   try another region if it doesn't.
5. Image and shape:
   - Image: **Canonical Ubuntu 22.04 (aarch64)** — or 24.04.
   - **Change shape** → **Specialty and legacy** → **Ampere** → **A1.Flex**.
   - Choose **4 OCPUs + 24 GB RAM** (the always-free ceiling is 4 OCPU / 24 GB).
   - If capacity is unavailable, try a smaller shape (e.g. 2 OCPU / 12 GB) or another region.
6. **Boot volume:** set **200 GB** (included free) or keep the default 47 GB.
7. Networking: keep defaults (public IPv4 + SSH port 22 opened automatically).
8. SSH keys: **Generate a key pair for me** and download the `.pem` key (keep it safe),
   or paste your own public key.
9. Click **Create**, wait until status is **Running**.

### 2. Connect over SSH
**Windows (PowerShell):**
```powershell
ssh -i "C:\path\to\ssh-key-2026-....pem" ubuntu@<PUBLIC_IP>
```
> Windows key-permission fix, if needed:
> `icacls key.pem /inheritance:r /grant:r "$env:USERNAME:R"`

**macOS / Linux:**
```bash
chmod 400 ~/.ssh/ssh-key-2026-....pem
ssh -i ~/.ssh/ssh-key-2026-....pem ubuntu@<PUBLIC_IP>
```
The public IP is shown under **Instance access → Public IP**.

### 3. One-line deployment ⚡ (fastest)
First push this repository to **GitHub** (see the *Git* section below), then run this
single command on the server. It removes old copies, clones the repo, writes your
`.env` settings, runs `deploy.sh`, and registers the bot as a systemd service —
all automatically:

```bash
sudo bash -c 'apt-get update -qq && apt-get install -y -qq git && rm -rf /home/ubuntu/turbodl-bot && git clone --depth=1 https://github.com/YOUR_USERNAME/turbodl-bot /home/ubuntu/turbodl-bot && cd /home/ubuntu/turbodl-bot && ./deploy.sh --token "YOUR_BOT_TOKEN" --admin-ids "YOUR_TELEGRAM_ID" --zain "YOUR_ZAIN_NUMBER"'
```
Replace `YOUR_USERNAME` (GitHub username), `YOUR_BOT_TOKEN` (from BotFather),
`YOUR_TELEGRAM_ID`, and `YOUR_ZAIN_NUMBER`.

### 4. Manual method (no one-liner)
```bash
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/turbodl-bot.git
cd turbodl-bot
cp .env.example .env
nano .env        # set BOT_TOKEN, ADMIN_IDS, ZAIN_CASH_NUMBER, then Ctrl+X, Y, Enter
sudo ./deploy.sh
```

Either way, `deploy.sh` automatically:
- Installs **Python 3.11**, **ffmpeg**, **aria2**, **git**, **sqlite3**
- Creates a virtualenv, installs `requirements.txt`, and upgrades yt-dlp
- Creates the secure `data/` directory and locks the SQLite DB (`chmod 600`)
- Installs a **systemd service** (`turbodl`) so the bot runs 24/7, restarts on crash
  and starts on boot
- Schedules a **daily SQLite backup** (cron, 03:00)

### 5. Run & monitor
```bash
systemctl status turbodl
journalctl -u turbodl -f
```
> Manual method: after editing `.env`, run `sudo systemctl restart turbodl`.
> (The one-line method already wrote the settings, so no restart is needed.)

Open the bot in Telegram, send `/start`, then any link. 🎉

### 6. Enable 2 GB uploads (Local Bot API server) 🚀

The standard Telegram Cloud API caps uploads at **50 MB**. To send files up to
**2 GB**, run your own [Telegram Local Bot API server](https://core.telegram.org/bots/api#using-a-local-bot-api-server)
on the same machine (the bot then talks to `127.0.0.1:8081` instead of
`api.telegram.org`). You need your own `api_id` / `api_hash` from
[my.telegram.org](https://my.telegram.org/api).

`deploy.sh` can install and register it automatically — just add the two extra
flags to the one-line command:

```bash
./deploy.sh --token "YOUR_BOT_TOKEN" --admin-ids "YOUR_TELEGRAM_ID" --zain "YOUR_ZAIN_NUMBER" \
  --local-api-id "YOUR_API_ID" --local-api-hash "YOUR_API_HASH"
```

What it does:
- Downloads the official `telegram-bot-api` server binary to `local-api/`
  (x86_64: prebuilt; ARM Ampere: prints the official build instructions —
  see <https://tdlib.github.io/telegram-bot-api/build.html> — and expects you to
  place the binary there, then rerun `deploy.sh --local-api-id ...`)
- Installs a `telegram-bot-api.service` systemd unit, running with `--local`
  (this unlocks uploads up to 2000 MB and unlimited downloads)
- Writes `TELEGRAM_LOCAL_API_URL=http://127.0.0.1:8081` and
  `TELEGRAM_UPLOAD_LIMIT_MB=2048` into `.env`, then restarts the bot

After a successful setup, both the **premium** plan and **admins**
(`ADMIN_IDS`) can receive files up to 2 GB.

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
| `ADMIN_MAX_FILE_SIZE_MB` | `2048` | Admins bypass the upload cap entirely, up to Telegram's full 2 GB bot limit |
| `ARIA2_CONNECTIONS_PREMIUM` | `16` | Aria2 connections for premium |
| `ARIA2_CONNECTIONS_FREE` | `4` | Aria2 connections for free |
| `STUCK_DOWNLOAD_TIMEOUT` | `900` | Auto-clear a user's queue after Ns of no progress |
| `CLEANUP_FILES` | `true` | Delete temp files after upload |

> **Note on the upload limit:** the standard Telegram bot API caps file uploads
> at **50 MB**. To let users (premium and admins) actually receive files up to
> 2 GB, run the
> [Telegram Local Bot API server](https://core.telegram.org/bots/api#using-a-local-bot-api-server)
> on the same machine, then set `TELEGRAM_UPLOAD_LIMIT_MB=2048`. Without it,
> every file > 50 MB is rejected by Telegram regardless of the plan. Admins
> (`ADMIN_IDS`) bypass the cap via `ADMIN_MAX_FILE_SIZE_MB` (default 2 GB) and
> are not subject to any premium subscription check.

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

## Git — push this repo to GitHub

If you have not pushed the repository yet, do it once from this computer so the
server can `git clone` it:

```bash
cd turbodl-bot
git remote add origin https://github.com/YOUR_USERNAME/turbodl-bot.git
git branch -M main
git push -u origin main
```

> On the server, keep or edit the file `deploy.sh` with optional CLI flags:
> `--token`, `--admin-ids`, `--zain` (used by the one-line deployment).
> Update the code anytime on the server with:
> ```bash
> cd /home/ubuntu/turbodl-bot && git pull
> sudo systemctl restart turbodl
> ```

---

## Tips

- Keep `CLEANUP_FILES=true` — files are deleted right after upload.
- Re-run `/purge` after heavy days to clear anything left behind.
- Upgrade to the **Local Bot API server** before advertising premium 2 GB files.
- After big code changes: `sudo systemctl restart turbodl`.
- Watch the service: `journalctl -u turbodl -f` runs forever and shows errors immediately.