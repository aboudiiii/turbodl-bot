import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_text(key: str, default: str = "") -> str:
    """Env string with dotenv-style literal \\n escapes expanded."""
    return os.environ.get(key, default).replace("\\n", "\n").strip()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
BOT_TOKEN = _env("BOT_TOKEN")

# Comma-separated Telegram user IDs of admins, e.g. "123456789,987654321"
ADMIN_IDS = [int(x) for x in _env("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

# Comma-separated list of user IDs allowed to download while bot is in
# "private launch mode" (see PRIVATE_MODE). Leave empty to allow everyone.
ALLOWED_USER_IDS = [
    int(x) for x in _env("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()
]

# When True, only ALLOWED_USER_IDS may use the bot. Useful for beta launch.
PRIVATE_MODE = _env("PRIVATE_MODE", "false").lower() in ("1", "true", "yes")

# Optional Telegram Local Bot API server (https://github.com/tdlib/telegram-bot-api).
# When set, the bot talks to the local server instead of api.telegram.org, which
# lifts the 50 MB Cloud API upload cap so files up to 2 GB can be sent.
TELEGRAM_LOCAL_API_URL = _env("TELEGRAM_LOCAL_API_URL", "").rstrip("/")

# ---------------------------------------------------------------------------
# Premium / Zain Cash
# ---------------------------------------------------------------------------
PREMIUM_PRICE_IQD = _env_int("PREMIUM_PRICE_IQD", 5000)
PREMIUM_DURATION_DAYS = _env_int("PREMIUM_DURATION_DAYS", 30)
ZAIN_CASH_NUMBER = _env("ZAIN_CASH_NUMBER", "")

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
FREE_DAILY_LIMIT = _env_int("FREE_DAILY_LIMIT", 3)
FREE_MAX_FILE_SIZE = _env_int("FREE_MAX_FILE_SIZE_MB", 50) * 1024 * 1024
PREMIUM_MAX_FILE_SIZE = _env_int("PREMIUM_MAX_FILE_SIZE_MB", 2048) * 1024 * 1024

# Telegram cloud Bot API hard limit is 50 MB per upload. If you run the
# Local Bot API server (recommended), set this to 2048 so premium users can
# receive files up to 2 GB.
TELEGRAM_UPLOAD_LIMIT = _env_int("TELEGRAM_UPLOAD_LIMIT_MB", 50) * 1024 * 1024

# Admins/owner bypass the 50 MB upload cap entirely, up to Telegram's full
# bot limit (2 GB). They do not need to be premium subscribers for this.
ADMIN_MAX_FILE_SIZE = _env_int("ADMIN_MAX_FILE_SIZE_MB", 2048) * 1024 * 1024

# Aria2 connections. Premium gets 16, free gets 4.
ARIA2_CONNECTIONS_PREMIUM = _env_int("ARIA2_CONNECTIONS_PREMIUM", 16)
ARIA2_CONNECTIONS_FREE = _env_int("ARIA2_CONNECTIONS_FREE", 4)

# A user's download queue is considered stuck (and auto-cleared) after this
# many seconds with no progress update.
STUCK_DOWNLOAD_TIMEOUT = _env_int("STUCK_DOWNLOAD_TIMEOUT", 900)

# How many media downloads may run at the same time across all users. The
# downloads are gated by a global FIFO queue, so everything else waits and
# sees its position in line.
MAX_ACTIVE_DOWNLOADS = _env_int("MAX_ACTIVE_DOWNLOADS", 3)

# How long to keep cached file_id entries for duplicate URLs (days). A
# repeated link/format is forwarded instantly from cache instead of re-downloading.
CACHE_TTL_DAYS = _env_int("CACHE_TTL_DAYS", 7)

# Master switch for the media cache. When false, duplicate URLs are always
# re-downloaded and no file_ids are stored.
CACHE_ENABLED = _env("CACHE_ENABLED", "true").lower() in ("1", "true", "yes")

# Cap on cached file_id rows. Oldest entries are pruned first once exceeded.
MAX_CACHE_ENTRIES = _env_int("MAX_CACHE_ENTRIES", 2000)

# How many users each /broadcast batch is sent to before a short pause.
# Higher = faster delivery, but hits the API harder at once.
BROADCAST_BATCH_SIZE = _env_int("BROADCAST_BATCH_SIZE", 25)

# Bonus download quota granted to a user for each successful referral.
REFERRAL_BONUS_DOWNLOADS = _env_int("REFERRAL_BONUS_DOWNLOADS", 3)

# Optional bonus Premium days per referral (0 = disabled).
REFERRAL_BONUS_PREMIUM_DAYS = _env_int("REFERRAL_BONUS_PREMIUM_DAYS", 0)

# Max videos a single playlist "download all" will process in one job.
PLAYLIST_MAX_ITEMS = _env_int("PLAYLIST_MAX_ITEMS", 30)

# Max playlist items shown in the "pick a video" selector.
PLAYLIST_PICK_LIMIT = _env_int("PLAYLIST_PICK_LIMIT", 12)

# How many results /search returns.
SEARCH_RESULTS = _env_int("SEARCH_RESULTS", 5)

# ffmpeg binary used for the trim/cut feature. Empty value disables trimming.
FFMPEG_BIN = _env("FFMPEG_BIN", "ffmpeg")

# ---------------------------------------------------------------------------
# Welcome banner (optional)
# ---------------------------------------------------------------------------
# Set either a public https:// image URL or a local image file path (absolute,
# or relative to this file). The image is shown as a photo above the main menu
# on /start and when the user returns to the main menu. Leave both empty to
# keep the plain-text menu.
#
# The default points at the bundled brand banner "banner.png" in the project
# root. To use a different file, update WELCOME_BANNER_PATH (or the URL) in
# your .env — the env value overrides this default.
WELCOME_BANNER_URL = _env("WELCOME_BANNER_URL", "")
WELCOME_BANNER_PATH = _env("WELCOME_BANNER_PATH", "banner.png")

# ---------------------------------------------------------------------------
# Force channel join (optional)
# ---------------------------------------------------------------------------
# Comma-separated list of channels users must join before using the bot, e.g.
# "@channel1,@channel2" or numeric chat ids "-1001234567890". The bot must be
# an admin in each channel to check membership. Leave empty to disable.
FORCE_SUB_CHANNELS = [
    c.strip() for c in _env("FORCE_SUB_CHANNELS", "").split(",") if c.strip()
]

# Legacy single-channel setting (kept for backward compatibility): used when
# FORCE_SUB_CHANNELS is empty.
FORCE_SUB_CHANNEL = _env("FORCE_SUB_CHANNEL", "")
if not FORCE_SUB_CHANNELS and FORCE_SUB_CHANNEL:
    FORCE_SUB_CHANNELS = [FORCE_SUB_CHANNEL]

# Optional invite link fallback for channels given as numeric ids (a t.me link
# is generated automatically for "@name" entries).
FORCE_SUB_INVITE = _env("FORCE_SUB_INVITE", "")

# Bonus download credits granted once when a user passes the channel check.
FORCE_SUB_BONUS_CREDITS = _env_int("FORCE_SUB_BONUS_CREDITS", 5)

# ---------------------------------------------------------------------------
# Admin notifications
# ---------------------------------------------------------------------------
# Primary admin Telegram user id receiving live join/referral alerts. Falls
# back to the first ADMIN_IDS entry when empty.
_admin_env = _env("ADMIN_ID", "")
ADMIN_ID = int(_admin_env) if _admin_env.lstrip("-").isdigit() else (
    ADMIN_IDS[0] if ADMIN_IDS else 0
)

# Channel/chat id receiving system logs (new users, referrals, downloads).
# Falls back to ADMIN_ID when empty. The bot must be a member/admin there.
_log_env = _env("LOG_CHANNEL_ID", "")
LOG_CHANNEL_ID = int(_log_env) if _log_env.lstrip("-").isdigit() else ADMIN_ID

# ---------------------------------------------------------------------------
# Start screen (BotFather) texts — set on startup via the Bot API
# ---------------------------------------------------------------------------
# Each startup pushes both the short description (profile / start button text,
# max 120 chars per language) and the long description (empty-chat intro text,
# max 512 chars) through setMyShortDescription / setMyDescription. Leave a value
# empty to skip that language (Telegram then shows the default language text).
# Literal "\n" in env values are converted to newlines.
BOT_PROFILE_SETUP = _env("BOT_PROFILE_SETUP", "true").lower() in ("1", "true", "yes")

BOT_SHORT_DESCRIPTION_AR = _env_text(
    "BOT_SHORT_DESCRIPTION_AR",
    "بوت توربودي إل العراقي — تحميل فيديو و MP3 سريع من أكثر من 15 موقع. "
    "حصة مجانية يومياً، وبريميوم حتى 2 جيجا.",
)
BOT_SHORT_DESCRIPTION_EN = _env_text(
    "BOT_SHORT_DESCRIPTION_EN",
    "TurboDL Iraq Bot — fast video & MP3 downloads from 15+ sites. "
    "Free daily quota, premium files up to 2 GB.",
)
BOT_DESCRIPTION_AR = _env_text(
    "BOT_DESCRIPTION_AR",
    "بوت توربودي إل — حمّل الفيديو والصوت والـ MP3 من يوتيوب وتيك توك "
    "وانستغرام وفيسبوك وتويتر وساوند كلاود وغيرها.\n\n"
    "⚡ جودة حتى 1080p\n🎵 استخراج MP3\n▶️ قوائم تشغيل وبحث يوتيوب\n"
    "✂️ قص واقتطاع المقاطع\n🗂 إرسال فوري للملفات المتكررة\n\n"
    "3 تحميلات مجانية كل يوم.\nبريميوم ترفع الحجم إلى 2 جيجا دون حد يومي.\n\n"
    "أرسل الرابط للبدء 🚀",
)
BOT_DESCRIPTION_EN = _env_text(
    "BOT_DESCRIPTION_EN",
    "TurboDL Iraq Bot\n\nDownload videos, audio and MP3 from YouTube, TikTok, "
    "Instagram, Facebook, Twitter, SoundCloud and more.\n\n"
    "⚡ Quality choices up to 1080p\n🎵 MP3 audio extraction\n"
    "▶️ Playlists & YouTube /search\n✂️ Trim any segment\n"
    "🗂 Instant resend for repeated links\n\n"
    "3 free downloads every day.\nPremium unlocks 2 GB files — no daily limit.\n\n"
    "Send a link to start 🚀",
)

# Delete downloaded files immediately after sending (recommended: true).
CLEANUP_FILES = _env("CLEANUP_FILES", "true").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Runtime / paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
DB_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "turbodl.db")
MAX_FILENAME_LEN = 80

DEFAULT_LANGUAGE = "ar"
