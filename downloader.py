import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yt_dlp

import config

log = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]  # (percent, status_text)

UNSUPPORTED_HINT = "https://t.me/TurboDL_bot"

# A single URL per message is expected. Extracts the first http(s) link.
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


class DownloadError(Exception):
    pass


class DownloadCancelled(Exception):
    pass


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


def get_info(url: str) -> Tuple[Optional[dict], Optional[str]]:
    """Returns (info_dict, error_message)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
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
    if info.get("_type") in ("playlist", "multi_video"):
        info = (info.get("entries") or [None])[0]
        if not info:
            return None, "Could not read this link."
    return info, None


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
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 5,
    }

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
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Downloads the media.

    Returns (file_path, title, error_message).
    Raises DownloadError if the file exceeds the user's size limit.
    """
    job_dir = Path(config.DOWNLOAD_DIR) / f"job_{int(time.time() * 1000)}"
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

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            _rmtree(job_dir)
            msg = str(exc).replace("ERROR: ", "")
            if "aria2" in msg.lower() or "does not support" in msg.lower():
                opts.pop("external_downloader", None)
                opts.pop("external_downloader_args", None)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl2:
                        info = ydl2.extract_info(url, download=True)
                except yt_dlp.utils.DownloadError as exc2:
                    _rmtree(job_dir)
                    return None, None, str(exc2).replace("ERROR: ", "")
            else:
                _rmtree(job_dir)
                return None, None, msg
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, DownloadCancelled):
                _rmtree(job_dir)
                raise
            log.exception("download failed")
            _rmtree(job_dir)
            return None, None, str(exc)

    files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith(".part")]
    if not files:
        _rmtree(job_dir)
        return None, None, "Download finished but no output file was found."

    file_path = str(max(files, key=lambda p: p.stat().st_size))
    size = os.path.getsize(file_path)
    limit = config.PREMIUM_MAX_FILE_SIZE if premium else config.FREE_MAX_FILE_SIZE
    if size > limit:
        _rmtree(job_dir)
        limit_mb = limit / 1024 / 1024
        raise DownloadError(
            f"File is too large ({size / 1024 / 1024:.0f} MB) — your plan allows up to "
            f"{limit_mb:.0f} MB."
        )

    title = (info or {}).get("title") or Path(file_path).stem
    return file_path, title, None


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


def _rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        log.warning("Failed to remove %s", path)
