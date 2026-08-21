import asyncio
import collections
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yt_dlp

import config

log = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]  # (percent, status_text)

UNSUPPORTED_HINT = "https://t.me/TurboDL_bot"

# A single URL per message is expected. Extracts the first http(s) link.
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Error fragments that mean an Instagram extraction hit auth/rate limits and
# may still succeed via the gallery-dl fallback (or with cookies).
_INSTAGRAM_RETRY_HINTS = (
    "empty media response",
    "login required",
    "rate-limit",
    "rate limit",
    "429",
    "not available",
    "private",
    "restricted",
    "unauthorized",
)


def is_instagram(url: str) -> bool:
    """True when the link points at Instagram."""
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return "instagram.com" in host or "instagr.am" in host


def _cookies_file() -> Optional[str]:
    """Absolute path to the yt-dlp cookies file when it exists, else None."""
    raw = (config.YTDLP_COOKIES_FILE or "").strip()
    if not raw:
        return None
    path = raw if os.path.isabs(raw) else os.path.join(config.BASE_DIR, raw)
    return path if os.path.isfile(path) else None


class DownloadError(Exception):
    pass


class DownloadCancelled(Exception):
    pass


class QueueSlot:
    """A granted place in the download queue; `await slot.release()` when done."""

    __slots__ = ("_queue", "_released")

    def __init__(self, queue: "DownloadQueue") -> None:
        self._queue = queue
        self._released = False

    async def __aenter__(self) -> "QueueSlot":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        async with self._queue._cond:
            self._queue.active = max(0, self._queue.active - 1)
            self._queue._cond.notify_all()


class DownloadQueue:
    """Global FIFO gate that caps how many downloads run at once.

    `acquire()` returns a :class:`QueueSlot` once a spot is free. While
    waiting, the optional ``on_position(pos)`` coroutine is called whenever
    the caller's position in line changes (1 = next to start). Call
    ``await slot.release()`` (or use ``async with``) when the work finished.
    """

    def __init__(self, max_active: int = 3) -> None:
        self.max_active = max(1, int(max_active))
        self.active = 0
        self._waiters = collections.deque()
        self._cond = asyncio.Condition()

    @property
    def active_count(self) -> int:
        return self.active

    @property
    def queued_count(self) -> int:
        return len(self._waiters)

    async def acquire(
        self, on_position: Optional[Callable[[int], Any]] = None
    ) -> QueueSlot:
        """Wait for a free slot, reporting queue position changes."""
        waiter = object()
        last_pos: Optional[int] = None
        async with self._cond:
            self._waiters.append(waiter)

        async def _notify() -> None:
            nonlocal last_pos
            if not on_position:
                return
            async with self._cond:
                if waiter not in self._waiters:
                    return
                pos = self._waiters.index(waiter) + 1
            if pos != last_pos:
                last_pos = pos
                await on_position(pos)

        try:
            while True:
                async with self._cond:
                    if self._waiters[0] is waiter and self.active < self.max_active:
                        self._waiters.popleft()
                        self.active += 1
                        return QueueSlot(self)
                    await self._cond.wait()
                await _notify()
        except asyncio.CancelledError:
            async with self._cond:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
            raise


# The single shared download gate, used across all chats.
download_queue = DownloadQueue(max_active=config.MAX_ACTIVE_DOWNLOADS)


@dataclass
class FormatOption:
    key: str
    label: str
    format_selector: str
    video: bool
    audio_only: bool = False


FORMAT_OPTIONS: List[FormatOption] = [
    FormatOption("best", "Best quality", "bestvideo*+bestaudio/best", True),
    FormatOption("720", "HD 720p", "bestvideo*[height<=720]+bestaudio/best[height<=720]/best", True),
    FormatOption("480", "SD 480p", "bestvideo*[height<=480]+bestaudio/best[height<=480]/best", True),
    FormatOption("360", "Low 360p", "bestvideo*[height<=360]+bestaudio/best[height<=360]/best", True),
    FormatOption("audio", "Audio only (MP3)", "bestaudio/best", True, audio_only=True),
]


def _sanitize_filename(name: str, max_len: int = config.MAX_FILENAME_LEN) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip()
    name = re.sub(r"\s+", " ", name).strip(". ")
    return name[:max_len] or "file"


def _common_opts() -> dict:
    """Options shared by info/search/download passes so every platform
    (YouTube, TikTok, Instagram, Facebook, Pinterest, SoundCloud, Twitter/X,
    Threads, ...) uses the same resilient settings."""
    opts: dict = {
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    # Netscape cookies.txt (exported from a logged-in browser session) lifts
    # Instagram's anonymous rate limits and fixes "empty media response".
    cookies = _cookies_file()
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def get_info(
    url: str, noplaylist: bool = True, limit: Optional[int] = None
) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (info_dict, error_message).

    With ``noplaylist=False`` (and ``limit``) the raw result is returned,
    including a possibly full ``entries`` list so playlists can be detected.
    """
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    opts.update(_common_opts())
    if noplaylist:
        opts["noplaylist"] = True
    elif limit:
        opts["playlist_items"] = f"1-{limit}"
    else:
        opts["noplaylist"] = False
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        return None, str(exc).replace("ERROR: ", "")
    except Exception as exc:  # noqa: BLE001
        log.exception("get_info failed")
        return None, str(exc)

    if not info:
        return None, "No info returned."

    if noplaylist and info.get("_type") in ("playlist", "multi_video"):
        info = (info.get("entries") or [None])[0]
        if not info:
            return None, "Could not read this link."
    return info, None


def get_playlist(url: str, limit: int) -> Tuple[Optional[str], List[dict]]:
    """Fetches a playlist's entries (capped to ``limit``).

    Returns (playlist_title, entries). Entries are dicts with
    ``index``, ``title`` and ``url`` (resolved for the next download step).
    """
    info, err = get_info(url, noplaylist=False, limit=limit)
    if err or not info:
        return None, []
    if info.get("_type") not in ("playlist", "multi_video"):
        return None, []
    is_youtube = "youtube" in (info.get("extractor") or "")
    entries: List[dict] = []
    for i, e in enumerate((info.get("entries") or []), start=1):
        if not e:
            continue
        item_url = (
            e.get("webpage_url")
            or e.get("original_url")
            or e.get("url")
        )
        if not item_url:
            continue
        if is_youtube and not str(item_url).startswith("http"):
            item_url = f"https://www.youtube.com/watch?v={item_url}"
        entries.append(
            {
                "index": i,
                "title": e.get("title") or f"Item {i}",
                "url": item_url,
            }
        )
    return info.get("title") or "Playlist", entries


def search_youtube(query: str, limit: int = config.SEARCH_RESULTS) -> Tuple[List[dict], Optional[str]]:
    """Searches YouTube, returning up to ``limit`` results."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    opts.update(_common_opts())
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("search failed: %s", exc)
        return [], str(exc).replace("ERROR: ", "")
    entries = (info or {}).get("entries") or []
    results: List[dict] = []
    for e in entries:
        if not e:
            continue
        results.append(
            {
                "title": e.get("title") or "Untitled",
                "url": (
                    e.get("webpage_url")
                    or e.get("original_url")
                    or e.get("url")
                ),
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or e.get("channel") or "",
            }
        )
    return results, None


def _base_opts(
    url: str,
    outdir: str,
    format_selector: str,
    audio_only: bool,
    premium: bool,
    progress_hook,
    allow_hls: bool,
) -> dict:
    postprocessors: List[dict] = []
    if audio_only:
        postprocessors.append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        )

    opts: dict = {
        "format": format_selector,
        "outtmpl": os.path.join(outdir, "%(title).100B.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "postprocessors": postprocessors,
    }
    opts.update(_common_opts())

    if not allow_hls:
        opts["format_sort"] = ["res", "ext:mp4:m4a", "proto:https"]

    connections = (
        config.ARIA2_CONNECTIONS_PREMIUM if premium else config.ARIA2_CONNECTIONS_FREE
    )
    if shutil.which("aria2c"):
        opts["external_downloader"] = {"default": "aria2c"}
        opts["external_downloader_args"] = {
            "default": ["-x", str(connections), "-s", str(connections), "-k", "1M"]
        }
    return opts


def download(
    url: str,
    format_selector: str,
    audio_only: bool,
    premium: bool,
    progress_cb: ProgressCb,
    allow_hls: bool = False,
    trim: Optional[Tuple[float, float]] = None,
    size_limit: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Downloads the media (optionally trimmed with ffmpeg).

    ``size_limit`` overrides the plan's default cap in bytes (admin
    /setlimit feature). Raises DownloadError when the file exceeds it.
    Returns (file_path, title, error_message).
    """
    # Unique per job: millisecond timestamps collide under concurrency and one
    # job's cleanup would then delete another job's in-progress .part file.
    job_dir = Path(config.DOWNLOAD_DIR) / f"job_{uuid.uuid4().hex[:12]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    outdir = str(job_dir)

    state = {"last_percent": 0.0, "last_update": 0.0, "status": "start"}

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100) if total else 0.0
            state["status"] = "downloading"
            now = time.time()
            if percent - state["last_percent"] >= 2 or now - state["last_update"] > 2.5:
                state["last_percent"] = percent
                state["last_update"] = now
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0
                progress_cb(percent, _progress_text(percent, speed, eta))
        elif d.get("status") == "finished":
            state["status"] = "processing"
            progress_cb(100.0, "⚙️ Processing...")

    opts = _base_opts(
        url,
        outdir,
        format_selector,
        audio_only,
        premium,
        hook,
        allow_hls,
    )

    err_msg: Optional[str] = None
    info: Optional[dict] = None
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc).replace("ERROR: ", "")
            if "aria2" in msg.lower() or "does not support" in msg.lower():
                opts.pop("external_downloader", None)
                opts.pop("external_downloader_args", None)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl2:
                        info = ydl2.extract_info(url, download=True)
                except yt_dlp.utils.DownloadError as exc2:
                    err_msg = str(exc2).replace("ERROR: ", "")
                except Exception as exc2:  # noqa: BLE001
                    if isinstance(exc2, DownloadCancelled):
                        _rmtree(job_dir)
                        raise
                    err_msg = str(exc2)
            else:
                err_msg = msg
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, DownloadCancelled):
                _rmtree(job_dir)
                raise
            log.exception("download failed")
            err_msg = str(exc)

    # Instagram failover: yt-dlp often hits login walls / anonymous
    # rate limits ("empty media response"). gallery-dl uses a separate
    # extraction pipeline that frequently still works.
    if info is None and err_msg and is_instagram(url):
        progress_cb(10.0, "🔁 Trying alternative extractor...")
        fb_path, fb_title, fb_err = _gallery_dl_fallback(url, job_dir)
        if fb_path:
            log.info("Instagram fallback succeeded for %s", url)
            info = {"title": fb_title, "_type": "regular"}
        elif fb_err:
            err_msg = fb_err
            # User-friendly Instagram rate limit message
            if "429" in (err_msg or "").lower() or "rate limit" in (err_msg or "").lower():
                err_msg = "⚠️ المحتوى غير متاح حالياً من إنستغرام debido a limitaciones temporales, por favor inténtalo de nuevo"

    if info is None:
        _rmtree(job_dir)
        return None, None, err_msg or "Download failed."

    files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith(".part")]
    if not files:
        _rmtree(job_dir)
        return None, None, "Download finished but no output file was found."

    file_path = str(max(files, key=lambda p: p.stat().st_size))

    if trim:
        try:
            file_path = _trim_file(file_path, trim[0], trim[1])
        except DownloadError:
            _rmtree(job_dir)
            raise

    size = os.path.getsize(file_path)
    limit = size_limit or (
        config.PREMIUM_MAX_FILE_SIZE if premium else config.FREE_MAX_FILE_SIZE
    )
    if size > limit:
        _rmtree(job_dir)
        limit_mb = limit / 1024 / 1024
        raise DownloadError(
            f"File is too large ({size / 1024 / 1024:.0f} MB) — your plan allows up to "
            f"{limit_mb:.0f} MB."
        )

    title = (info or {}).get("title") or Path(file_path).stem
    return file_path, title, None


def _gallery_dl_fallback(
    url: str, job_dir: Path
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Secondary Instagram extraction via gallery-dl.

    Returns (file_path, title, error_message). Files are placed directly in
    job_dir so the caller's generic file-discovery picks them up.
    """
    exe = shutil.which("gallery-dl")
    if exe:
        cmd: List[str] = [exe]
    else:
        cmd = [sys.executable, "-m", "gallery_dl"]
    cmd += ["-D", str(job_dir), "--no-colors", "--no-part", url]
    cookies = _cookies_file()
    if cookies:
        cmd += ["--cookies", cookies]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return None, None, "Instagram fallback timed out."
    except FileNotFoundError:
        log.warning("gallery-dl is not installed; Instagram fallback unavailable.")
        return None, None, None  # silent: primary error stands

    files = [
        p for p in job_dir.iterdir()
        if p.is_file() and not p.name.endswith(".part") and p.stat().st_size > 0
    ] if job_dir.is_dir() else []
    if proc.returncode != 0 or not files:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else f"exit code {proc.returncode}"
        log.warning("gallery-dl failed for %s: %s", url, detail)
        return None, None, f"Instagram fallback failed: {detail}"

    file_path = str(max(files, key=lambda p: p.stat().st_size))
    title = _instagram_title_from_url(url) or Path(file_path).stem
    return file_path, title, None


def _instagram_title_from_url(url: str) -> Optional[str]:
    """Best-effort title from an Instagram URL shortcode."""
    try:
        parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
        for label in ("p", "reel", "reels", "tv"):
            if label in parts:
                idx = parts.index(label)
                if idx + 1 < len(parts):
                    return f"Instagram_{parts[idx + 1]}"
        return parts[-1] if parts else None
    except Exception:  # noqa: BLE001
        return None


def _progress_text(percent: float, speed: float, eta: int) -> str:
    bar_len = 12
    filled = int(bar_len * percent / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    line = f"{bar} {percent:5.1f}%"
    if speed:
        line += f"  ⬇ {speed / 1024 / 1024:.1f} MB/s"
    if eta:
        line += f"  ⏱ {int(eta)}s"
    return line


def _ffmpeg_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _trim_file(path: str, start: float, end: float) -> str:
    """Cuts a segment out of a downloaded file with ffmpeg (stream copy)."""
    ffmpeg = config.FFMPEG_BIN
    if not ffmpeg or not shutil.which(ffmpeg):
        raise DownloadError("Trim requires ffmpeg to be installed on the server.")
    duration = float(end) - float(start)
    if duration <= 0:
        raise DownloadError("Invalid trim range.")
    out = os.path.join(os.path.dirname(path), "trimmed_" + os.path.basename(path))
    cmd = [
        ffmpeg, "-y",
        "-ss", _ffmpeg_time(start),
        "-i", path,
        "-t", _ffmpeg_time(duration),
        "-c", "copy",
        out,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out) or os.path.getsize(out) <= 0:
        # Fall back to a re-encode (some containers don't support stream copy).
        cmd2 = [
            ffmpeg, "-y",
            "-ss", _ffmpeg_time(start),
            "-i", path,
            "-t", _ffmpeg_time(duration),
            out,
        ]
        subprocess.run(cmd2, capture_output=True, text=True)
    if not os.path.exists(out) or os.path.getsize(out) <= 0:
        raise DownloadError("Could not trim the file.")
    return out


def _rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        log.warning("Failed to remove %s", path)
