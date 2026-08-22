# Media Tools State Handlers and Utilities
import asyncio
import logging
import os
import re
import subprocess
import time
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

import config
import database

log = logging.getLogger("turbodl.media")


def _t(lang: str, ar: str, en: str) -> str:
    return en if lang == "en" else ar


def _fmt_dur(seconds: float) -> str:
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


def _fmt_size(n_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n_bytes < 1024.0:
            return f"{n_bytes:3.1f} {unit}"
        n_bytes /= 1024.0
    return f"{n_bytes:.1f} TB"


def _parse_timestamp(ts: str) -> Optional[float]:
    """Parse mm:ss or hh:mm:ss to seconds."""
    parts = ts.strip().split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return None


async def _download_media_file(msg, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Optional[str]:
    """Download video, audio, voice, or document to downloads directory."""
    try:
        tg_file_obj = msg.video or msg.audio or msg.voice or msg.video_note or msg.document
        if not tg_file_obj:
            return None
        file_obj = await tg_file_obj.get_file()
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        ext = ".mp4" if msg.video else (".mp3" if msg.audio else (".ogg" if msg.voice else ".bin"))
        if msg.document and msg.document.file_name:
            _, e = os.path.splitext(msg.document.file_name)
            if e:
                ext = e
        path = os.path.join(config.DOWNLOAD_DIR, f"media_{user_id}_{int(time.time()*1000)}{ext}")
        await file_obj.download_to_drive(path)
        return path
    except Exception as e:
        log.error("Failed to download media file: %s", e)
        return None


# ============================================================
# 1. Video to MP3 Audio Extraction
# ============================================================

async def convert_video_to_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Extract MP3 audio stream from an uploaded video file."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("media_op", None)

    msg = update.effective_message
    if not (msg.video or (msg.document and (msg.document.mime_type or "").startswith("video/"))):
        await msg.reply_text(_t(lang, "⚠️ يرجى إرسال مقطع فيديو لاستخراج الصوت منه.", "⚠️ Please send a video file."))
        return

    status = await msg.reply_text(_t(lang, "🎵 جاري استخراج الصوت بصيغة MP3...", "🎵 Extracting audio to MP3..."))
    video_path = await _download_media_file(msg, context, user.id)
    if not video_path:
        await status.edit_text(_t(lang, "❌ فشل تحميل الفيديو.", "❌ Failed to download video."))
        return

    mp3_path = os.path.splitext(video_path)[0] + ".mp3"
    ffmpeg_bin = getattr(config, "FFMPEG_BIN", "ffmpeg")

    loop = asyncio.get_running_loop()
    def _run_ffmpeg():
        cmd = [
            ffmpeg_bin, "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            mp3_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
        return res.returncode == 0

    try:
        ok = await loop.run_in_executor(None, _run_ffmpeg)
    except Exception as e:
        log.error("FFmpeg mp3 extract failed: %s", e)
        ok = False

    try:
        os.remove(video_path)
    except Exception:
        pass

    if ok and os.path.exists(mp3_path):
        size = os.path.getsize(mp3_path)
        with open(mp3_path, "rb") as f:
            await context.bot.send_audio(
                chat_id=user.id,
                audio=f,
                filename=f"Audio_{int(time.time())}.mp3",
                caption=_t(lang, f"🎵 تم استخراج الصوت بنجاح ({_fmt_size(size)})", f"🎵 Audio extracted ({_fmt_size(size)})")
            )
        try:
            os.remove(mp3_path)
        except Exception:
            pass
        await status.delete()
    else:
        await status.edit_text(_t(lang, "❌ فشل تحويل الفيديو إلى MP3.", "❌ Failed to convert video to MP3."))


# ============================================================
# 2. Video Trimmer / Cutter
# ============================================================

async def video_trim_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store the video and ask the user for the trim timestamps."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    msg = update.effective_message
    if not (msg.video or (msg.document and (msg.document.mime_type or "").startswith("video/"))):
        await msg.reply_text(_t(lang, "⚠️ يرجى إرسال مقطع فيديو لقصّه.", "⚠️ Please send a video."))
        return

    status = await msg.reply_text(_t(lang, "⏳ جاري استلام الفيديو...", "⏳ Receiving video..."))
    video_path = await _download_media_file(msg, context, user.id)
    if not video_path:
        await status.edit_text(_t(lang, "❌ فشل تحميل الفيديو.", "❌ Failed to download video."))
        return

    context.user_data["media_trim_src"] = video_path
    context.user_data["awaiting_media_trim_times"] = True
    context.user_data.pop("media_op", None)

    await status.edit_text(
        _t(
            lang,
            "✂️ أرسل وقت البداية والنهاية للقص بالتنسيق التالي:\n"
            "`00:10 - 00:45` أو `01:00 - 02:30`",
            "✂️ Send the start and end timestamps to cut:\n"
            "`00:10 - 00:45` or `01:00 - 02:30`"
        ),
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def video_trim_process_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cut the video according to the provided timestamps."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_media_trim_times", None)

    src_path = context.user_data.pop("media_trim_src", None)
    if not src_path or not os.path.exists(src_path):
        await update.effective_message.reply_text(
            _t(lang, "⚠️ لم يتم العثور على الفيديو، يرجى إعادة إرساله.", "⚠️ Video not found, please resend.")
        )
        return

    raw = (update.effective_message.text or "").strip()
    m = re.match(r"^\s*(\d+(?::\d+)?(?::\d+)?)\s*[-–—]\s*(\d+(?::\d+)?(?::\d+)?)\s*$", raw)
    if not m:
        try:
            os.remove(src_path)
        except Exception:
            pass
        await update.effective_message.reply_text(
            _t(lang, "❌ تنسيق الوقت غير صالح. مثال: `00:10 - 00:45`", "❌ Invalid time format. Example: `00:10 - 00:45`"),
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    t_start = _parse_timestamp(m.group(1))
    t_end = _parse_timestamp(m.group(2))
    if t_start is None or t_end is None or t_end <= t_start:
        try:
            os.remove(src_path)
        except Exception:
            pass
        await update.effective_message.reply_text(
            _t(lang, "❌ وقت النهاية يجب أن يكون أكبر من وقت البداية.", "❌ End time must be greater than start time.")
        )
        return

    status = await update.effective_message.reply_text(_t(lang, "✂️ جاري قص المقطع بدقة...", "✂️ Trimming video clip..."))
    out_path = os.path.splitext(src_path)[0] + "_trimmed.mp4"
    ffmpeg_bin = getattr(config, "FFMPEG_BIN", "ffmpeg")

    loop = asyncio.get_running_loop()
    def _run_trim():
        cmd = [
            ffmpeg_bin, "-y",
            "-ss", str(t_start),
            "-to", str(t_end),
            "-i", src_path,
            "-c", "copy",
            out_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
        return res.returncode == 0

    try:
        ok = await loop.run_in_executor(None, _run_trim)
    except Exception as e:
        log.error("FFmpeg trim failed: %s", e)
        ok = False

    try:
        os.remove(src_path)
    except Exception:
        pass

    if ok and os.path.exists(out_path):
        with open(out_path, "rb") as f:
            await context.bot.send_video(
                chat_id=user.id,
                video=f,
                caption=_t(lang, f"✂️ تم قص المقطع بنجاح ({raw})", f"✂️ Video trimmed ({raw})")
            )
        try:
            os.remove(out_path)
        except Exception:
            pass
        await status.delete()
    else:
        await status.edit_text(_t(lang, "❌ فشل قص الفيديو.", "❌ Failed to trim video."))


# ============================================================
# 3. Auto-Caption Generator
# ============================================================

async def auto_caption_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate metadata-based and AI-enhanced caption for video/audio."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("media_op", None)

    msg = update.effective_message
    media_obj = msg.video or msg.audio or msg.voice or msg.document
    if not media_obj:
        await msg.reply_text(_t(lang, "⚠️ يرجى إرسال ملف فيديو أو صوت.", "⚠️ Please send a video or audio file."))
        return

    status = await msg.reply_text(_t(lang, "📋 جاري استخراج معلومات الملف وتوليد الوصف...", "📋 Generating auto-caption..."))

    # Extract metadata
    duration_s = getattr(media_obj, "duration", None)
    file_size = getattr(media_obj, "file_size", 0)
    file_name = getattr(media_obj, "file_name", "Media File")
    width = getattr(media_obj, "width", None)
    height = getattr(media_obj, "height", None)

    dur_str = _fmt_dur(duration_s) if duration_s else "N/A"
    size_str = _fmt_size(file_size) if file_size else "N/A"
    res_str = f"{width}x{height}" if width and height else ""

    bot_uname = context.bot_data.get("bot_username", "TurboDL_Iraq_bot")
    tag = f"@{bot_uname}" if bot_uname else "#TurboDL"

    caption = (
        f"🎬 *{file_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ *المدة:* `{dur_str}`\n"
        f"💾 *الحجم:* `{size_str}`\n"
    )
    if res_str:
        caption += f"📐 *الدقة:* `{res_str}`\n"
    caption += f"━━━━━━━━━━━━━━━━━━\n📥 تم التحميل بواسطة {tag}"

    await status.edit_text(caption, parse_mode=constants.ParseMode.MARKDOWN)


# Backward compatibility wrappers
async def trim_video_handler(update, context):
    await video_trim_receive_file(update, context)

async def stt_handler(update, context):
    pass

async def mp3_converter_handler(update, context):
    await convert_video_to_mp3(update, context)
