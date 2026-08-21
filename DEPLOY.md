# Deploying TurboDL on Koyeb (100% free)

The repo ships a `Dockerfile`, so Koyeb detects everything automatically.
Total setup time: ~5 minutes.

## 0. Know the cloud limits first

| Limitation | Detail |
|---|---|
| Upload size | Telegram **Cloud** Bot API caps uploads at **50 MB** (`TELEGRAM_LOCAL_API_URL` must stay **empty** — there is no local server on Koyeb) |
| Storage | Free instances are **ephemeral**: `data/turbodl.db` and settings reset on every redeploy/restart. User quotas/cache are not permanent. |
| yt-dlp | YouTube changes break extractors over time — redeploy occasionally to pull a fresh `yt-dlp`. |

## 1. Push this repo to GitHub

```bash
git init
git add .
git commit -m "TurboDL bot"
git remote add origin https://github.com/<your-username>/turbodl-bot.git
git push -u origin main
```

`.env`, `local-api/`, `data/`, `logs/`, `downloads/` are git-ignored — your
token never leaves the machine.

## 2. Create the Koyeb service

1. Sign up / log in at <https://app.koyeb.com> (GitHub login works).
2. Click **Create App** (or **Create Web Service**).
3. Choose **GitHub** as the deployment source and authorize Koyeb.
4. Select your fork/repo (`turbodl-bot`) and branch (`main`).
5. Koyeb auto-detects the **Dockerfile** — keep that builder selected.
6. Instance: pick the **Free** instance.
7. Exposed port: leave the default **8000** (the bot reads `PORT`
   automatically and serves a health endpoint on it).
8. Do **not** enable autoscaling; 1 instance is enough.

## 3. Set Environment Variables

In the service creation form, expand **Environment Variables** and add:

| Variable | Value | Required |
|---|---|---|
| `BOT_TOKEN` | token from @BotFather | ✅ |
| `ADMIN_ID` | your numeric Telegram user id (e.g. `5283516841`) | recommended |
| `LOG_CHANNEL_ID` | log channel/chat id (e.g. `-1003943704540`) | optional (falls back to ADMIN_ID) |
| `ZAIN_CASH_NUMBER` | payment number shown to users | optional |
| `FORCE_SUB_CHANNELS` | e.g. `@yourchannel` (bot must be admin there) | optional |

Do **NOT** set `TELEGRAM_LOCAL_API_URL` on Koyeb.

Click **Deploy** and wait for the build (~2–3 min).

## 4. Verify

Open the **Runtime Logs** tab in the Koyeb dashboard. You should see:

```
... - turbodl - INFO - TurboDL started
... - turbodl - INFO - Health server listening on 0.0.0.0:8000
... httpx ... getUpdates "HTTP/1.1 200 OK"
```

Then open your bot in Telegram and send `/start`.

## 5. Redeploys & updates

Every `git push` to the connected branch triggers an automatic rebuild.
To refresh `yt-dlp` without code changes: **Deploy → Redeploy** (rebuilds
from the Dockerfile with a fresh pip install).

## Local Bot API note (2 GB uploads)

Koyeb's free tier cannot run the companion `telegram-bot-api` server, so
cloud limits apply. For 2 GB uploads use the bundled `deploy.sh` on a free
Oracle Cloud / VPS box instead.
