# Admin Hub - Broadcast, Maintenance, Stats & Dynamic Module Toggles
import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

import config
import database

log = logging.getLogger("turbodl.admin")

BOT_OWNER_ID = getattr(config, "BOT_OWNER_ID", 5283516841)
_maintenance_active = False

MODULES_FILE = os.path.join(getattr(config, "DB_DIR", "data"), "modules_state.json")
DEFAULT_MODULES = {
    "downloader": True,
    "student": True,
    "media": True,
    "games": True,
}


def _load_modules_state() -> Dict[str, bool]:
    try:
        if os.path.exists(MODULES_FILE):
            with open(MODULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_MODULES, **data}
    except Exception as e:
        log.warning("Failed to load modules state: %s", e)
    return dict(DEFAULT_MODULES)


def _save_modules_state(state: Dict[str, bool]) -> None:
    try:
        os.makedirs(os.path.dirname(MODULES_FILE), exist_ok=True)
        with open(MODULES_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.error("Failed to save modules state: %s", e)


def is_module_enabled(mod_name: str) -> bool:
    """Check whether a given hub/module is enabled."""
    state = _load_modules_state()
    return state.get(mod_name, True)


def set_module_enabled(mod_name: str, enabled: bool) -> None:
    state = _load_modules_state()
    state[mod_name] = enabled
    _save_modules_state(state)


# ============================================================
# 1. Advanced /stats Command (Users, System Load, Active Tasks)
# ============================================================

def _get_system_metrics() -> Dict[str, str]:
    """Retrieve system CPU, RAM and disk stats cleanly via psutil if available."""
    metrics = {"cpu": "N/A", "ram": "N/A", "disk": "N/A"}
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(config.BASE_DIR)
        metrics["cpu"] = f"{cpu_percent:.1f}%"
        metrics["ram"] = f"{mem.percent:.1f}% ({mem.used // (1024*1024)}MB / {mem.total // (1024*1024)}MB)"
        metrics["disk"] = f"{disk.percent:.1f}% ({disk.free // (1024*1024*1024)}GB free)"
    except Exception:
        pass
    return metrics


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats - Comprehensive system status and activity report."""
    user = update.effective_user
    if not user or (user.id != BOT_OWNER_ID and user.id not in getattr(config, "ADMIN_IDS", [])):
        await update.effective_message.reply_text("⛔ هذا الأمر مخصص للمطور/المشرفين فقط.")
        return

    started = database.stats_get("started_at")
    uptime_sec = int(time.time() - started) if started else 0
    hrs, rem = divmod(uptime_sec, 3600)
    mins, _ = divmod(rem, 60)
    uptime_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"

    # Queue stats from downloader
    try:
        from downloader import download_queue
        active_dl = download_queue.active_count
        queued_dl = download_queue.queued_count
    except Exception:
        active_dl, queued_dl = 0, 0

    metrics = _get_system_metrics()
    modules_state = _load_modules_state()
    mods_str = " | ".join(f"{k}: {'✅' if v else '❌'}" for k, v in modules_state.items())

    text = (
        f"📊 *لوحة إحصائيات النظام الشاملة* — TurboDL\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *المستخدمون:* `{database.user_count()}` | ⭐ *بريميوم:* `{database.premium_count()}`\n"
        f"📥 *التحميلات:* `{database.total_downloads()}` (اليوم: `{database.downloads_today()}`)\n"
        f"⚡ *المهام النشطة:* `{active_dl}` قيد المعالجة | `{queued_dl}` في الانتظار\n"
        f"💰 *إيراد اليوم:* `{database.revenue_today():,}` د.ع\n"
        f"🚫 *المحظورون:* `{len(database.banned_users())}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 *أداء الخادم (System Load):*\n"
        f"• *CPU:* `{metrics['cpu']}`\n"
        f"• *RAM:* `{metrics['ram']}`\n"
        f"• *Disk:* `{metrics['disk']}`\n"
        f"• *Uptime:* `{uptime_str}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧩 *حالة الموديلات:*\n`{mods_str}`"
    )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 تحديث", callback_data="adm:stats_refresh")],
            [InlineKeyboardButton("🧩 إدارة الموديلات", callback_data="adm:modules_panel")],
        ]
    )
    await update.effective_message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)


# ============================================================
# 2. Dynamic Module Toggles (/modules)
# ============================================================

def _modules_keyboard() -> InlineKeyboardMarkup:
    state = _load_modules_state()
    rows = []
    labels = {
        "downloader": "⬇️ التحميل (Downloader)",
        "student": "🎓 خدمات الطلاب (Student Hub)",
        "media": "🛠️ أدوات الميديا (Media Tools)",
        "games": "🎮 الألعاب والنقاط (Games Hub)",
    }
    for key, label in labels.items():
        is_on = state.get(key, True)
        icon = "✅ مفعل" if is_on else "❌ معطل"
        rows.append([InlineKeyboardButton(f"{label}: {icon}", callback_data=f"mt:{key}")])
    rows.append([InlineKeyboardButton("⬅️ إغلاق", callback_data="adm:close")])
    return InlineKeyboardMarkup(rows)


async def modules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/modules - toggle bot modules on the fly."""
    user = update.effective_user
    if not user or (user.id != BOT_OWNER_ID and user.id not in getattr(config, "ADMIN_IDS", [])):
        await update.effective_message.reply_text("⛔ هذا الأمر مخصص للمطور فقط.")
        return

    await update.effective_message.reply_text(
        "🧩 *إدارة تشغيل وتعطيل الموديلات بشكل ديناميكي:*\nاضغط على أي موديل لتغيير حالته فوراً:",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=_modules_keyboard()
    )


async def modules_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle module on callback."""
    query = update.callback_query
    user = update.effective_user
    if not user or (user.id != BOT_OWNER_ID and user.id not in getattr(config, "ADMIN_IDS", [])):
        await query.answer("⛔ غير مصرح لك.", show_alert=True)
        return

    mod_key = query.data.split(":", 1)[1]
    current = is_module_enabled(mod_key)
    set_module_enabled(mod_key, not current)

    await query.answer(f"تم {'تفعيل' if not current else 'تعطيل'} موديل {mod_key}")
    await query.edit_message_reply_markup(reply_markup=_modules_keyboard())


# ============================================================
# 3. Broadcast & Maintenance Commands
# ============================================================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/broadcast <message> - send message to all registered users."""
    user = update.effective_user
    if not user or (user.id != BOT_OWNER_ID and user.id not in getattr(config, "ADMIN_IDS", [])):
        await update.effective_message.reply_text("⛔ للمطور والمشرفين فقط.")
        return

    args = context.args
    if not args and not update.message.reply_to_message:
        await update.effective_message.reply_text("الاستخدام: `/broadcast نص الرسالة` أو قم بالرد على رسالة بـ `/broadcast`.")
        return

    broadcast_text = " ".join(args) if args else (update.message.reply_to_message.text or "")
    all_users = database.all_users()
    total = len(all_users)
    status_msg = await update.effective_message.reply_text(f"⏳ جاري بدء الإرسال إلى {total} مستخدم...")

    sent, failed = 0, 0
    batch_size = getattr(config, "BROADCAST_BATCH_SIZE", 25)

    for i in range(0, total, batch_size):
        batch = all_users[i:i + batch_size]
        for u in batch:
            chat_id = u.get("telegram_id")
            if not chat_id:
                continue
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=broadcast_text,
                    parse_mode=constants.ParseMode.MARKDOWN
                )
                sent += 1
            except (Forbidden, BadRequest, TelegramError):
                failed += 1
        await asyncio.sleep(0.4)

    await status_msg.edit_text(f"✅ اكتمل البث:\n• تم الإرسال بنجاح: `{sent}`\n• فشل الإرسال (حظر/حذف): `{failed}`", parse_mode=constants.ParseMode.MARKDOWN)


async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/maintenance on|off - toggle maintenance mode."""
    global _maintenance_active
    user = update.effective_user
    if not user or user.id != BOT_OWNER_ID:
        await update.effective_message.reply_text("⛔ للمطور الأساسي فقط.")
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.effective_message.reply_text("الاستخدام: `/maintenance on` أو `/maintenance off`")
        return

    state = (args[0].lower() == "on")
    _maintenance_active = state
    context.bot_data["maintenance"] = state

    status_str = "تفعيل 🔒" if state else "تعطيل 🔓"
    await update.effective_message.reply_text(f"✅ تم {status_str} وضع الصيانة بنجاح.")


async def maintenance_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[bool]:
    """Check maintenance mode."""
    global _maintenance_active
    if context.bot_data.get("maintenance", _maintenance_active):
        user = update.effective_user
        if user and (user.id == BOT_OWNER_ID or user.id in getattr(config, "ADMIN_IDS", [])):
            return None
        try:
            if update.effective_message:
                await update.effective_message.reply_text("⚠️ البوت تحت الصيانة والتحديث حالياً، سنعود قريباً جداً!")
            elif update.callback_query:
                await update.callback_query.answer("⚠️ البوت تحت الصيانة حالياً!", show_alert=True)
            return True
        except Exception:
            return True
    return None
