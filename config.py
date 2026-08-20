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

# Aria2 connections. Premium gets 16, free gets 4.
ARIA2_CONNECTIONS_PREMIUM = _env_int("ARIA2_CONNECTIONS_PREMIUM", 16)
ARIA2_CONNECTIONS_FREE = _env_int("ARIA2_CONNECTIONS_FREE", 4)

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
