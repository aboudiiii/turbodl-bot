"""TurboDL edge-case test suite for bot.py / downloader.py.

Run:  python -X utf8 test_edge_cases.py

Covers:
  A. Link handling   — URL extraction: Shorts, Playlists, TikTok, IG Reels,
                       invalid/broken URLs, trailing garbage.
  B. Helpers         — filename sanitizing, duration formatting, Markdown
                       escaping, captions, quality labels, share URLs.
  C. Size logic      — admin bypass vs standard cap, tiny-vs-large config
                       invariants for the Local Bot API (2 GB).
  D. Error recovery  — harmless failures: garbage URLs, blackholed hosts,
                       private/deleted-style errors, size-limit rejection,
                       job-dir cleanup.
  E. Real network    — get_info on Shorts / playlist / TikTok / IG Reels with
                       watchdogs (graceful either way).

Exit code 0 = all passed, 1 = failures.
"""

import gc
import importlib.util
import os
import queue
import shutil
import sys
import threading
import time
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import config  # noqa: E402
import downloader  # noqa: E402
import bot  # noqa: E402

PASS = []
FAIL = []
SCRATCH = os.path.join(os.environ.get("TEMP", BASE), "turbodl_test_scratch")


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [ PASS ] {name}")
    else:
        FAIL.append(name)
        print(f"  [ FAIL ] {name}  ->  {detail}")


def check_graceful(name, result, allow_info=True, allow_err=True):
    """Validates the (info, err) contract: exactly one is set, no exception."""
    ok = isinstance(result, tuple) and len(result) == 2
    detail = result if not ok else f"info={'yes' if result[0] else 'no'}, err={str(result[1])[:90]!r}"
    if ok:
        info, err = result
        ok = (info is not None and allow_info) or (err and allow_err)
    check(name, ok, detail)


def watchdog(timeout, fn, *args):
    """Run a blocking call in a thread; abort if it exceeds `timeout` seconds."""
    out = queue.Queue()

    def runner():
        try:
            out.put(("ok", fn(*args)))
        except Exception as exc:  # noqa: BLE001
            out.put(("exc", "%s: %s" % (type(exc).__name__, str(exc)[:200])))

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return ("timeout", f"> {timeout}s")
    return out.get()


# ---------------------------------------------------------------------------
# A. Link handling — URL_RE
# ---------------------------------------------------------------------------
print("\n== A. Link handling (URL_RE) ==")

A_URLS = {
    "youtube_standard": "Watch https://www.youtube.com/watch?v=jNQXAC9IVRw&t=10s",
    "youtube_shorts": "https://youtube.com/shorts/aqz-KE-bpKQ",
    "youtube_short": "https://youtu.be/jNQXAC9IVRw",
    "youtube_playlist": "https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY",
    "tiktok_video": "https://www.tiktok.com/@user/video/7412345678901234567",
    "instagram_reel": "https://www.instagram.com/reel/Cx3ZTxpou_8/",
    "direct_file": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
}


def extract_first(text):
    match = downloader.URL_RE.search(text)
    return match.group(0) if match else None


for name, text in A_URLS.items():
    got = extract_first(text)
    check(f"A.url_extract.{name}", got is not None and got.startswith("http"), f"got={got}")

via_video = extract_first(A_URLS["youtube_standard"])
check(
    "A.trailing.query_preserved",
    via_video is not None and "t=10s" in via_video,
    via_video,
)
check(
    "A.bare_host_not_matched",
    extract_first("go watch www.example.com/video.mp4 now") is None,
    "bare host without scheme must not match",
)
check(
    "A.no_scheme_not_matched",
    extract_first("watch/folder/video.mp4") is None,
    "relative path without scheme must not match",
)
check(
    "A.garbage_not_matched",
    extract_first("this is https:// not a URL") is None
    or extract_first("this is https:// not a URL") == "https://",
    "malformed scheme must not extract a usable URL",
)

# ---------------------------------------------------------------------------
# B. Helpers (bot.py)
# ---------------------------------------------------------------------------
print("\n== B. Helpers ==")

check(
    "B.sanitize.illegal_chars",
    downloader._sanitize_filename('a\\b:c*d?"e<f>g|h') == "a_b_c_d__e_f_g_h",
    downloader._sanitize_filename('a\\b:c*d?"e<f>g|h'),
)
check(
    "B.sanitize.truncate",
    len(downloader._sanitize_filename("x" * 200)) <= config.MAX_FILENAME_LEN,
    "len=%d" % len(downloader._sanitize_filename("x" * 200)),
)
check(
    "B.sanitize.empty",
    downloader._sanitize_filename("   ") == "file",
    downloader._sanitize_filename("   "),
)
check(
    "B.md_escape",
    bot._md_escape("a_b*c[d]`e") == r"a\_b\*c\[d\]\`e",
    bot._md_escape("a_b*c[d]`e"),
)
check(
    "B.duration.hms",
    bot._fmt_duration(3725) == "1:02:05",
    bot._fmt_duration(3725),
)
check(
    "B.duration.mmss",
    bot._fmt_duration(215.7) == "03:35",
    bot._fmt_duration(215.7),
)
check(
    "B.duration.none",
    bot._fmt_duration(None) == "" and bot._fmt_duration(0) == "" and bot._fmt_duration("bad") == "",
    "",
)
check(
    "B.quality.ar",
    bot._quality_label("720", "ar") == "📺 HD 720p",
    bot._quality_label("720", "ar"),
)
check(
    "B.quality.en",
    bot._quality_label("best", "en") == "Best quality",
    bot._quality_label("best", "en"),
)
check(
    "B.quality.unknown",
    bot._quality_label("nonexistent", "ar") == "",
    bot._quality_label("nonexistent", "ar"),
)

cap = bot._file_caption("ar", "My_Video", bot._quality_label("720", "ar"), 25, "TurboDL_Iraq_bot", 215.7)
check("B.caption.title_bold", "**My\\_Video**" in cap, cap)
check("B.caption.quality", "720p" in cap, cap)
check("B.caption.duration", "⏱️ 03:35" in cap, cap)
check("B.caption.size", "25 MB" in cap, cap)
check("B.caption.byline", "@TurboDL_Iraq_bot" in cap, cap)

cap_no_dur = bot._file_caption("en", "Song", bot._quality_label("audio", "en"), 4, "TurboDL_Iraq_bot", None)
check("B.caption.no_duration", "⏱️" not in cap_no_dur, cap_no_dur)

kb = bot._share_keyboard("ar", "TurboDL_Iraq_bot")
check("B.share.returns_markup", kb is not None, "")
if kb:
    url = kb.inline_keyboard[0][0].url
    check("B.share.scheme", url.startswith("https://t.me/share/url?url="), url)
    check("B.share.encodes_bot", urllib.parse.quote("https://t.me/TurboDL_Iraq_bot", safe="") in url, url)
check("B.share.no_username_is_none", bot._share_keyboard("ar", "") is None, "")

# ---------------------------------------------------------------------------
# C. Size logic — admin bypass + Local Bot API 2 GB invariants
# ---------------------------------------------------------------------------
print("\n== C. Size logic / file-size handling ==")

check("C.owner_true", bot.is_owner(5283516841) is True, "")
check("C.owner_false", bot.is_owner(12345678) is False, "")

# Isolate the branch: temporarily flip the two caps to prove selection logic.
_admin_was, _user_was = config.ADMIN_MAX_FILE_SIZE, config.TELEGRAM_UPLOAD_LIMIT
config.ADMIN_MAX_FILE_SIZE = 100 * 2**20
config.TELEGRAM_UPLOAD_LIMIT = 50 * 2**20
check("C.bypass_owner", bot._upload_limit_for(5283516841) == 100 * 2**20, bot._upload_limit_for(5283516841))
check("C.bypass_other", bot._upload_limit_for(12345678) == 50 * 2**20, bot._upload_limit_for(12345678))
config.ADMIN_MAX_FILE_SIZE, config.TELEGRAM_UPLOAD_LIMIT = _admin_was, _user_was

# Local API lane: caps must allow >50 MB up to 2 GB.
check("C.local_api_url_set", config.TELEGRAM_LOCAL_API_URL == "http://127.0.0.1:8081", config.TELEGRAM_LOCAL_API_URL)
check(
    "C.upload_cap_2gb",
    config.TELEGRAM_UPLOAD_LIMIT == 2048 * 2**20,
    f"TELEGRAM_UPLOAD_LIMIT={config.TELEGRAM_UPLOAD_LIMIT // 2**20}MB",
)
check(
    "C.admin_cap_2gb",
    config.ADMIN_MAX_FILE_SIZE >= config.PREMIUM_MAX_FILE_SIZE >= 2048 * 2**20,
    f"admin={config.ADMIN_MAX_FILE_SIZE // 2**20}MB, premium={config.PREMIUM_MAX_FILE_SIZE // 2**20}MB",
)

# downloader-level size limit must raise DownloadError (free tier).
_saved_limit, _saved_dir = config.FREE_MAX_FILE_SIZE, config.DOWNLOAD_DIR
config.DOWNLOAD_DIR = os.path.join(SCRATCH, "dlsize")
os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
try:
    config.FREE_MAX_FILE_SIZE = 1024  # 1 KB
    kind, payload = watchdog(90, downloader.download,
                             "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
                             "best", False, False, lambda p, t: None, True)
    check("C.downloader_rejects_big", kind == "exc" and "File is too large" in payload, f"{kind}:{payload}")
    check("C.downloader_cleans_after_reject", not os.listdir(config.DOWNLOAD_DIR), os.listdir(config.DOWNLOAD_DIR) or "(empty)")
finally:
    config.FREE_MAX_FILE_SIZE = _saved_limit
    config.DOWNLOAD_DIR = _saved_dir
    shutil.rmtree(SCRATCH, ignore_errors=True)

# ---------------------------------------------------------------------------
# D. Error recovery
# ---------------------------------------------------------------------------
print("\n== D. Error recovery ==")

os.makedirs(os.path.join(SCRATCH, "errs"), exist_ok=True)
config.DOWNLOAD_DIR = os.path.join(SCRATCH, "errs")
try:
    for name, url in {
        "D.info.garbage": "https://www.thisdomaindoesnotexist12345.com/video?x=1",
        "D.info.bad_path": "https://www.w3.org/2010/05/sintel/trailer.mp4",  # 404
        "D.info.deleted_video": "https://www.youtube.com/watch?v=" + "d" * 11 + "invalid",
    }.items():
        kind, payload = watchdog(60, downloader.get_info, url)
        if kind in ("ok",):
            info, err = payload
            check(name, info is None and isinstance(err, str) and err, f"info={info}, err={err[:80]!r}")
        elif kind == "exc":
            check(name, False, f"raised {payload}")
        else:
            check(name, False, payload)

    # Blackhole / unroutable timeout: must return an error, never hang forever.
    kind, payload = watchdog(45, downloader.get_info, "http://10.255.255.1/x.mp4")
    ok = kind == "ok" and payload[0] is None and isinstance(payload[1], str)
    check("D.info.blackhole_graceful", ok, f"{kind}:{payload if not ok else payload[1][:60]!r}")

    # download() on garbage must return (None,None,error) and leave no dirs.
    before = {p for p in os.listdir(config.DOWNLOAD_DIR)}
    kind, payload = watchdog(60, downloader.download,
                             "https://www.thisdomaindoesnotexist12345.com/video?x=2",
                             "best", False, True, lambda p, t: None, True)
    if kind == "ok":
        path, title, err = payload
        check("D.download.garbage_graceful", path is None and title is None and err, f"{payload!r}")
        check("D.download.no_dir_left", not set(os.listdir(config.DOWNLOAD_DIR)) - before, os.listdir(config.DOWNLOAD_DIR))
    else:
        check("D.download.garbage_graceful", False, f"{kind}:{payload}")
finally:
    config.DOWNLOAD_DIR = _saved_dir
    shutil.rmtree(SCRATCH, ignore_errors=True)

# ---------------------------------------------------------------------------
# E. Real network (watchdog-guarded)
# ---------------------------------------------------------------------------
print("\n== E. Real network handles ==")

NET = {
    "E.net.youtube_shorts": "https://youtube.com/shorts/aqz-KE-bpKQ",
    "E.net.youtube_playlist_missing": "https://www.youtube.com/playlist?list=PL8dPuuaLjXtN0ge7yDk_VA0bdK4stpHbx",
    "E.net.tiktok": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    "E.net.instagram_reel": "https://www.instagram.com/reel/Cx3ZTxpou_8/",
}

for name, url in NET.items():
    kind, payload = watchdog(50, downloader.get_info, url)
    if kind == "ok":
        check_graceful(name, payload)
    elif kind == "timeout":
        check(name, False, "timed out >50s")
    else:
        check(name, False, f"raised {payload}")

# ---------------------------------------------------------------------------
is_net_ok = any(p for p in PASS if p.startswith("E.net"))
print(
    "\n============================================================\n"
    f"EDGE-CASE SUMMARY: {len(PASS)} passed, {len(FAIL)} failed"
    "  (network lane not proven reachable)" if not is_net_ok else
    f"EDGE-CASE SUMMARY: {len(PASS)} passed, {len(FAIL)} failed"
)
print("============================================================")
sys.exit(1 if FAIL else 0)