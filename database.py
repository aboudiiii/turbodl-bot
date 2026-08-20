import datetime
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

import config

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _secure_permissions() -> None:
    """Restrict the database directory and files (POSIX only; no-op on Windows)."""
    if os.name != "posix":
        return
    try:
        os.makedirs(config.DB_DIR, exist_ok=True)
        os.chmod(config.DB_DIR, 0o700)
        for path in (config.DB_PATH, config.DB_PATH + "-wal", config.DB_PATH + "-shm"):
            if os.path.exists(path):
                os.chmod(path, 0o600)
    except OSError:
        pass


def init_db() -> None:
    os.makedirs(config.DB_DIR, exist_ok=True)
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id      INTEGER PRIMARY KEY,
                username         TEXT,
                first_name       TEXT,
                is_premium       INTEGER DEFAULT 0,
                premium_expiry   TEXT,
                daily_downloads  INTEGER DEFAULT 0,
                last_download_date TEXT,
                total_downloads  INTEGER DEFAULT 0,
                joined_date      TEXT,
                language         TEXT DEFAULT 'ar'
            );

            CREATE TABLE IF NOT EXISTS payments (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id       INTEGER NOT NULL,
                username          TEXT,
                amount            INTEGER,
                payment_method    TEXT DEFAULT 'zain_cash',
                screenshot_file_id TEXT,
                status            TEXT DEFAULT 'pending',
                submitted_date    TEXT,
                processed_date    TEXT,
                admin_id          INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            """
        )
    _secure_permissions()


def today() -> str:
    return datetime.date.today().isoformat()


def add_user(telegram_id: int, username: str, first_name: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users
                (telegram_id, username, first_name, joined_date, language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, username, first_name, today(), config.DEFAULT_LANGUAGE),
        )
        conn.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
            (username, first_name, telegram_id),
        )


def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return dict(row) if row else None


def is_premium(telegram_id: int) -> bool:
    # Bot owners/admins always have permanent premium access.
    if telegram_id in config.ADMIN_IDS:
        return True
    user = get_user(telegram_id)
    if not user or not user["is_premium"]:
        return False
    expiry = user["premium_expiry"]
    if expiry and expiry < today():
        with _lock, _conn() as conn:
            conn.execute(
                "UPDATE users SET is_premium = 0 WHERE telegram_id = ?",
                (telegram_id,),
            )
        return False
    return True


def remaining_daily_downloads(telegram_id: int) -> int:
    if is_premium(telegram_id):
        return -1  # unlimited
    user = get_user(telegram_id)
    if not user:
        return config.FREE_DAILY_LIMIT
    if user["last_download_date"] != today():
        with _lock, _conn() as conn:
            conn.execute(
                "UPDATE users SET daily_downloads = 0, last_download_date = ? WHERE telegram_id = ?",
                (today(), telegram_id),
            )
        return config.FREE_DAILY_LIMIT
    return max(0, config.FREE_DAILY_LIMIT - (user["daily_downloads"] or 0))


def consume_download(telegram_id: int) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, last_download_date, daily_downloads, total_downloads, joined_date)
            VALUES (?, ?, 1, 1, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                last_download_date = excluded.last_download_date,
                daily_downloads = daily_downloads + 1,
                total_downloads = total_downloads + 1
            """,
            (telegram_id, today(), today()),
        )


def activate_premium(telegram_id: int, days: int = config.PREMIUM_DURATION_DAYS) -> None:
    now = today()
    user = get_user(telegram_id)
    base = user["premium_expiry"] if user and user["premium_expiry"] and user["premium_expiry"] > now else now
    expiry = (
        datetime.date.fromisoformat(base) + datetime.timedelta(days=days)
    ).isoformat()
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET is_premium = 1, premium_expiry = ? WHERE telegram_id = ?",
            (expiry, telegram_id),
        )


def revoke_premium(telegram_id: int) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )


def set_language(telegram_id: int, language: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET language = ? WHERE telegram_id = ?", (language, telegram_id)
        )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
def add_payment(
    telegram_id: int,
    username: str,
    amount: int,
    screenshot_file_id: str,
) -> int:
    with _lock, _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO payments
                (telegram_id, username, amount, screenshot_file_id, submitted_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, username, amount, screenshot_file_id, today()),
        )
        return int(cur.lastrowid)


def get_payment(payment_id: int) -> Optional[Dict[str, Any]]:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
    return dict(row) if row else None


def update_payment_status(
    payment_id: int, status: str, admin_id: Optional[int] = None
) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            UPDATE payments SET status = ?, processed_date = ?, admin_id = ?
            WHERE id = ?
            """,
            (status, today(), admin_id, payment_id),
        )


def pending_payments() -> List[Dict[str, Any]]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats / broadcast
# ---------------------------------------------------------------------------
def all_users() -> List[Dict[str, Any]]:
    with _lock, _conn() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
    return [dict(r) for r in rows]


def user_count() -> int:
    with _lock, _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def premium_count() -> int:
    with _lock, _conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_premium = 1"
        ).fetchone()[0]


def total_downloads() -> int:
    with _lock, _conn() as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(total_downloads), 0) FROM users"
        ).fetchone()[0]


def downloads_today() -> int:
    with _lock, _conn() as conn:
        return conn.execute(
            "SELECT COALESCE(SUM(daily_downloads), 0) FROM users WHERE last_download_date = ?",
            (today(),),
        ).fetchone()[0]


def revenue_today() -> int:
    with _lock, _conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE status = 'approved' AND processed_date = ?
            """,
            (today(),),
        ).fetchone()
    return int(row[0])


def backup_database(dest_path: str) -> Optional[str]:
    """Writes a consistent online copy of the database to dest_path.

    Safe to run while the bot is live (uses SQLite's online backup API).
    Returns the backup path on success, None on failure.
    """
    try:
        with _lock, _conn() as src, sqlite3.connect(dest_path) as dst:
            src.backup(dst)
        if os.name == "posix":
            os.chmod(dest_path, 0o600)
        return dest_path
    except Exception:  # noqa: BLE001
        return None
