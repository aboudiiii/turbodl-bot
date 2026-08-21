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
                language         TEXT DEFAULT 'ar',
                bonus_quota      INTEGER DEFAULT 0,
                force_verified   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id  INTEGER NOT NULL,
                referee_id   INTEGER NOT NULL,
                bonus        INTEGER DEFAULT 0,
                joined_date  TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_referrals_referee
                ON referrals(referee_id);
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer
                ON referrals(referrer_id);

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

            CREATE TABLE IF NOT EXISTS media_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash    TEXT NOT NULL,
                file_id     TEXT NOT NULL,
                kind        TEXT NOT NULL,
                title       TEXT,
                duration    INTEGER,
                quality     TEXT,
                size_bytes  INTEGER DEFAULT 0,
                chat_id     INTEGER,
                created_at  TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_media_cache_key
                ON media_cache(url_hash, kind, quality);
            CREATE INDEX IF NOT EXISTS idx_media_cache_created
                ON media_cache(created_at);

            CREATE TABLE IF NOT EXISTS bot_stats (
                key   TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            );
            """
        )
    _migrate(conn)
    _secure_permissions()


def _migrate(conn) -> None:
    """Adds columns missing from databases created by older versions."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "bonus_quota" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN bonus_quota INTEGER DEFAULT 0")
    if "force_verified" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN force_verified INTEGER DEFAULT 0")


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
        daily_left = config.FREE_DAILY_LIMIT
    else:
        daily_left = max(0, config.FREE_DAILY_LIMIT - (user["daily_downloads"] or 0))
    return daily_left + (user["bonus_quota"] or 0)


def consume_download(telegram_id: int) -> None:
    user = get_user(telegram_id)
    bonus = (user or {}).get("bonus_quota") if user else 0
    if bonus and bonus > 0:
        # Referral bonus credits are spent first.
        with _lock, _conn() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, bonus_quota, daily_downloads, total_downloads, joined_date)
                VALUES (?, ?, 0, 1, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    bonus_quota = MAX(0, bonus_quota - 1),
                    total_downloads = total_downloads + 1
                """,
                (telegram_id, max(0, bonus - 1), today()),
            )
        return
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
# Referrals
# ---------------------------------------------------------------------------
def add_referral(referrer_id: int, referee_id: int, bonus: int) -> bool:
    """Records a referral. Returns False when self/duplicate or missing referrer."""
    if referrer_id == referee_id:
        return False
    if not get_user(referrer_id):
        return False
    with _lock, _conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO referrals (referrer_id, referee_id, bonus, joined_date)
                VALUES (?, ?, ?, ?)
                """,
                (referrer_id, referee_id, bonus, today()),
            )
        except sqlite3.IntegrityError:
            return False
        if cur.rowcount == 0:
            return False
        conn.execute(
            "UPDATE users SET bonus_quota = bonus_quota + ? WHERE telegram_id = ?",
            (bonus, referrer_id),
        )
    return True


def count_referrals(user_id: int) -> int:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def has_referral(referee_id: int) -> bool:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM referrals WHERE referee_id = ? LIMIT 1", (referee_id,)
        ).fetchone()
    return row is not None


def today_referrals(user_id: int) -> int:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND joined_date = ?",
            (user_id, today()),
        ).fetchone()
    return int(row[0]) if row else 0


def grant_bonus_quota(user_id: int, downloads: int) -> None:
    if downloads <= 0:
        return
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET bonus_quota = bonus_quota + ? WHERE telegram_id = ?",
            (downloads, user_id),
        )


def is_force_verified(user_id: int) -> bool:
    """True once the user has completed the force-sub channel verification."""
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT force_verified FROM users WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
    return bool(row and row[0])


def mark_force_verified(user_id: int) -> None:
    """Persists that the user passed the force-sub check (one-time reward)."""
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET force_verified = 1 WHERE telegram_id = ?",
            (user_id,),
        )


# ---------------------------------------------------------------------------
# Media cache / bot stats
# ---------------------------------------------------------------------------
def _cache_ttl() -> datetime.timedelta:
    return datetime.timedelta(days=config.CACHE_TTL_DAYS)


def cache_put(
    url_hash: str,
    file_id: str,
    kind: str,
    title: str,
    duration: Optional[int],
    quality: str,
    size_bytes: int,
    chat_id: int,
) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO media_cache
                (url_hash, file_id, kind, title, duration, quality, size_bytes, chat_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash, kind, quality) DO UPDATE SET
                file_id = excluded.file_id,
                title = excluded.title,
                duration = excluded.duration,
                size_bytes = excluded.size_bytes,
                chat_id = excluded.chat_id,
                created_at = excluded.created_at
            """,
            (
                url_hash,
                file_id,
                kind,
                title,
                duration,
                quality,
                size_bytes,
                chat_id,
                today(),
            ),
        )


def cache_get(url_hash: str, kind: str, quality: str) -> Optional[Dict[str, Any]]:
    with _lock, _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM media_cache
            WHERE url_hash = ? AND kind = ? AND quality = ?
            """,
            (url_hash, kind, quality),
        ).fetchone()
    return dict(row) if row else None


def cache_delete(url_hash: str, kind: str, quality: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "DELETE FROM media_cache WHERE url_hash = ? AND kind = ? AND quality = ?",
            (url_hash, kind, quality),
        )


def cache_prune(
    max_days: Optional[int] = None, max_entries: Optional[int] = None
) -> int:
    """Prunes expired cache rows, then trims to the newest max_entries.

    Returns the total number of rows removed.
    """
    days = max_days or config.CACHE_TTL_DAYS
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    limit = max_entries if max_entries is not None else config.MAX_CACHE_ENTRIES
    removed = 0
    with _lock, _conn() as conn:
        cur = conn.execute("DELETE FROM media_cache WHERE created_at < ?", (cutoff,))
        removed += int(cur.rowcount or 0)
        if limit and limit > 0:
            cur = conn.execute(
                """
                DELETE FROM media_cache WHERE id IN (
                    SELECT id FROM media_cache
                    ORDER BY created_at DESC, id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (limit,),
            )
            removed += int(cur.rowcount or 0)
        return removed


def cache_count() -> int:
    with _lock, _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM media_cache").fetchone()[0]


def stats_set(key: str, value: int) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO bot_stats (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def stats_increment(key: str, delta: int = 1) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO bot_stats (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = value + excluded.value
            """,
            (key, delta),
        )


def stats_get(key: str) -> int:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT value FROM bot_stats WHERE key = ?", (key,)
        ).fetchone()
    return int(row[0]) if row else 0


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
