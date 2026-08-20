import asyncio
import logging
import os
import shutil
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import database
import downloader
from downloader import DownloadError, FORMAT_OPTIONS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("turbodl")

# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------
T = {
    "ar": {
        "start": (
            "مرحباً بك في TurboDL 🚀\n\n"
            "البوت الأسرع لتحميل الفيديوهات، الصور، والصوتيات من"
            " (يوتيوب، تيك توك، إنستغرام، تويتر، وغيرها) بأعلى جودة وبدون إعلانات.\n\n"
            "أرسل أي رابط لبدء التحميل فوراً! ⚡"
        ),
        "paid_limited": (
            "⚡ *العروض المتاحة:*\n"
            "• مجاني: 3 تحميلات يومياً (حتى 50MB)\n"
            "• بريميوم: تحميلات غير محدودة حتى 2GB\n\n"
            "🎯 للاشتراك استخدم `/subscribe`"
        ),
        "limit_reached": (
            "❌ استخدمت كل تحميلاتك المجانية اليوم.\n\n"
            "⚡ اشترك في البريميوم لتحميل بدون حدود — `/subscribe`"
        ),
        "busy": "⏳ عندك تحميل ما خلص. خلصه أو الغيه أولاً.",
        "checking": "🔍 جاري فحص الرابط...",
        "no_url": "🤔 هذا ما يبدو عليه رابط. أرسل رابط فيديو صحيح.",
        "unsupported": (
            "❌ ما گدرت أفتح هذا الرابط.\n\n"
            "تأكد إن الرابط يدعمه البوت، أو جرّب رابط آخر.\n"
            "دعم: يوتيوب، تيك توك، انستقرام، تويتر، سناب شات، فيسبوك، وكل الروابط المباشرة."
        ),
        "too_big": (
            "⚠️ الملف أكبر من الحد المسموح لخطتك ({limit} MB).\n\n"
            "⚡ البريميوم يسمح بتحميل حتى 2GB — `/subscribe`"
        ),
        "choose_format": (
            "📥 اختر الجودة:\n\n"
            "{title}\n"
            "👤 {site}"
        ),
        "cancel": "🚫 أُلغي التحميل.",
        "downloading": "⬇️ جاري التحميل...",
        "uploading": "📤 جاري الرفع إلى تيليجرام...",
        "download_error": "❌ فشل التحميل: {error}",
        "done": "✅ تم بنجاح!",
        "share": "🚀 شارك البوت مع أصدقائك",
        "subscribe_btn": "⭐ اشترك في البريميوم",
        "subscribe": (
            "⭐ *TurboDL Premium*\n\n"
            "🎯 بسعر {price} د.ع شهرياً، تحصل على:\n"
            "• تحميلات غير محدودة\n"
            "• ملفات حتى 2GB\n"
            "• أولوية في السرعة (Aria2 — 16 اتصال)\n"
            "• دعم HLS streams (.m3u8)\n"
            "• بدون أي انتظار أو حدود\n\n"
            "💳 *طريقة الدفع:*\n"
            "حول المبلغ إلى رقم Zain Cash:\n\n"
            "📍 *{number}*\n\n"
            "بعد التحويل، أرسل صورة الإيصال هنا 📸\n"
            "سيتم تفعيل حسابك خلال 24 ساعة."
        ),
        "already_premium": (
            "🌟 أنت مشترك بريميوم حتى *{date}* 🎉"
        ),
        "premium_owner": (
            "👑 أنت مالك البوت — بريميوم دائم بدون أي حدود!"
        ),
        "awaiting_photo": "📸 جاهز لاستلام الإيصال. أرسل صورة التحويل الآن.",
        "payment_received": (
            "✅ استلمنا إيصالك!\n"
            "🕒 جارٍ مراجعة الدفع (خلال 24 ساعة).\n"
            "سنخبرك فور التفعيل."
        ),
        "payment_pending_exists": "⏳ عندك إيصال قيد المراجعة. انتظر الموافقة عليه.",
        "payment_approved_admin": "✅ تمت الموافقة على الدفع #{pid}",
        "payment_rejected_admin": "❌ تم رفض الدفع #{pid}",
        "payment_approved_user": (
            "🎉 *مبروك! حسابك أصبح بريميوم!*\n"
            "من اليوم يمكنك التحميل بدون حدود حتى {date} 🚀"
        ),
        "payment_rejected_user": (
            "❌ عذراً، تم رفض إيصالك.\n"
            "ربما المبلغ غير مكتمل أو الصورة غير واضحة.\n"
            "جرّب التحويل مرة أخرى — `/subscribe`"
        ),
        "menu_subscribe": "⭐ الاشتراك",
        "menu_help": "❓ المساعدة",
        "help": (
            "❓ *كيف تستخدم البوت:*\n\n"
            "1️⃣ أرسل أي رابط فيديو\n"
            "2️⃣ اختر الجودة\n"
            "3️⃣ استلم الملف\n\n"
            "يدعم: يوتيوب، تيك توك، انستقرام، تويتر/X،"
            " فيسبوك، ريديت، فيميو، ساوند كلاود، دايل موشن،"
            " بينترست، سناب شات، وكل الروابط المباشرة.\n\n"
            " مجاني: 3 تحميلات/يوم — حتى 50MB\n"
            " ⭐ بريميوم: غير محدود — حتى 2GB\n\n"
            "للاشتراك: /subscribe"
        ),
        "stats": (
            "📊 *إحصائيات البوت*\n\n"
            "👥 المستخدمون: {users}\n"
            "⭐ البريميوم: {premium}\n"
            "⬇️ التحميلات الكلية: {downloads}\n"
            "⬇️ تحميلات اليوم: {today}\n"
            "💰 إيراد اليوم: {revenue} د.ع"
        ),
        "broadcast_sent": "✅ تم إرسال الرسالة لـ {ok} من {total} مستخدم.",
        "broadcast_usage": "الاستخدام: /broadcast <الرسالة>",
        "approved_user": "✅ تم تفعيل البريميوم لمستخدم {uid} حتى {date}.",
        "revoked_user": "✅ تم إلغاء البريميوم لمستخدم {uid}.",
        "setexpiry_user": "✅ تم تمديد بريميوم المستخدم {uid} لـ {days} يوم (حتى {date}).",
        "user_not_found": "❌ المستخدم ما موجود.",
        "admin_usage": "الاستخدام: /approve <user_id>",
        "usage_setexpiry": "الاستخدام: /setexpiry <user_id> <days>",
        "not_admin": "⛔ هذا الأمر للمشرفين فقط.",
        "not_allowed": "⛔ البوت حالياً في وضع الإطلاق الخاص. ما ملحوق إنك تستخدمه الآن.",
        "pay_preview": (
            "💳 *إيصال دفع جديد*\n\n"
            "🆔 المستخدم: {uid}\n"
            "👤 اليوزر: @{username}\n"
            "💰 المبلغ: {amount} د.ع\n"
            "🕒 التاريخ: {date}"
        ),
        "purge_start": "🧹 جاري تنظيف الملفات القديمة...",
        "purge_done": "✅ تم إزالة {n} ملف قديم.",
    },
    "en": {
        "start": (
            "👋 *Welcome to TurboDL!*\n\n"
            "⬇️ Send any video link and get the file here directly.\n"
            "Supports: YouTube, TikTok, Instagram, Twitter, Facebook and more.\n\n"
            "Just send me any link to start 🚀"
        ),
        "paid_limited": (
            "⚡ *Plans:*\n"
            "• Free: 3 downloads/day (up to 50MB)\n"
            "• Premium: Unlimited downloads up to 2GB\n\n"
            "🎯 Subscribe with `/subscribe`"
        ),
        "limit_reached": (
            "❌ You've used all your free downloads today.\n\n"
            "⚡ Upgrade to Premium for unlimited downloads — `/subscribe`"
        ),
        "busy": "⏳ You have a download running. Finish or cancel it first.",
        "checking": "🔍 Checking the link...",
        "no_url": "🤔 That doesn't look like a link. Send a valid video link.",
        "unsupported": (
            "❌ Couldn't process this link.\n\n"
            "Make sure the site is supported, or try another link.\n"
            "Support: YouTube, TikTok, Instagram, Twitter, Snapchat, Facebook"
            " and any direct file link."
        ),
        "too_big": (
            "⚠️ The file is larger than your plan allows ({limit} MB).\n\n"
            "⚡ Premium allows downloads up to 2GB — `/subscribe`"
        ),
        "choose_format": (
            "📥 Choose quality:\n\n"
            "{title}\n"
            "👤 {site}"
        ),
        "cancel": "🚫 Download cancelled.",
        "downloading": "⬇️ Downloading...",
        "uploading": "📤 Uploading to Telegram...",
        "download_error": "❌ Download failed: {error}",
        "done": "✅ Done!",
        "share": "🚀 Share the bot with your friends",
        "subscribe_btn": "⭐ Subscribe to Premium",
        "subscribe": (
            "⭐ *TurboDL Premium*\n\n"
            "🎯 For {price} IQD/month you get:\n"
            "• Unlimited downloads\n"
            "• Files up to 2GB\n"
            "• Priority speed (Aria2 — 16 connections)\n"
            "• HLS stream support (.m3u8)\n"
            "• No waiting, no limits\n\n"
            "💳 *Payment method:*\n"
            "Send the amount to this Zain Cash number:\n\n"
            "📍 *{number}*\n\n"
            "Then send the payment screenshot here 📸\n"
            "Your account is activated within 24 hours."
        ),
        "already_premium": "🌟 You are Premium until *{date}* 🎉",
        "premium_owner": "👑 You are the bot owner — permanent premium, no limits!",
        "awaiting_photo": "📸 Ready to receive the receipt. Send the payment screenshot now.",
        "payment_received": (
            "✅ We got your receipt!\n"
            "🕒 Payment is being reviewed (within 24 hours).\n"
            "We'll notify you once it's activated."
        ),
        "payment_pending_exists": "⏳ You already have a receipt under review. Please wait.",
        "payment_approved_admin": "✅ Payment #{pid} approved",
        "payment_rejected_admin": "❌ Payment #{pid} rejected",
        "payment_approved_user": (
            "🎉 *Congratulations! You are now Premium!*\n"
            "Download without limits until {date} 🚀"
        ),
        "payment_rejected_user": (
            "❌ Sorry, your receipt was rejected.\n"
            "The amount may be incomplete or the image unclear.\n"
            "Try sending the transfer again — `/subscribe`"
        ),
        "menu_subscribe": "⭐ Subscribe",
        "menu_help": "❓ Help",
        "help": (
            "❓ *How to use:*\n\n"
            "1️⃣ Send any video link\n"
            "2️⃣ Choose the quality\n"
            "3️⃣ Receive the file\n\n"
            "Supports: YouTube, TikTok, Instagram, Twitter/X, Facebook,"
            " Reddit, Vimeo, SoundCloud, Dailymotion, Pinterest, Snapchat"
            " and any direct file link.\n\n"
            " Free: 3 downloads/day — up to 50MB\n"
            " ⭐ Premium: Unlimited — up to 2GB\n\n"
            "Subscribe: /subscribe"
        ),
        "stats": (
            "📊 *Bot stats*\n\n"
            "👥 Users: {users}\n"
            "⭐ Premium: {premium}\n"
            "⬇️ Total downloads: {downloads}\n"
            "⬇️ Today's downloads: {today}\n"
            "💰 Today's revenue: {revenue} IQD"
        ),
        "broadcast_sent": "✅ Message sent to {ok} of {total} users.",
        "broadcast_usage": "Usage: /broadcast <message>",
        "approved_user": "✅ Activated premium for {uid} until {date}.",
        "revoked_user": "✅ Revoked premium for {uid}.",
        "setexpiry_user": "✅ Extended premium for {uid} by {days} days (until {date}).",
        "user_not_found": "❌ User not found.",
        "admin_usage": "Usage: /approve <user_id>",
        "usage_setexpiry": "Usage: /setexpiry <user_id> <days>",
        "not_admin": "⛔ Admin command only.",
        "not_allowed": "⛔ The bot is in private launch mode. You can't use it right now.",
        "pay_preview": (
            "💳 *New payment receipt*\n\n"
            "🆔 User: {uid}\n"
            "👤 Username: @{username}\n"
            "💰 Amount: {amount} IQD\n"
            "🕒 Date: {date}"
        ),
        "purge_start": "🧹 Cleaning old files...",
        "purge_done": "✅ Removed {n} old files.",
    },
}


def tr(lang: str, key: str, **fmt: Any) -> str:
    return T.get(lang, T["ar"]).get(key, key).format(**fmt)


def lang_of(user: Optional[Dict[str, Any]]) -> str:
    if user and user.get("language") in ("ar", "en"):
        return user["language"]
    return config.DEFAULT_LANGUAGE


def is_admin(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id in config.ADMIN_IDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(tr(lang, "menu_subscribe"), callback_data="menu:subscribe"),
                InlineKeyboardButton(tr(lang, "menu_help"), callback_data="menu:help"),
            ]
        ]
    )


def _share_keyboard(lang: str, bot_username: str) -> Optional[InlineKeyboardMarkup]:
    if bot_username:
        share_text = f"🚀 {tr(lang, 'share')}"
        url = (
            "https://t.me/share/url?url="
            + urllib.parse.quote(f"https://t.me/{bot_username}", safe="")
            + "&text="
            + urllib.parse.quote(share_text, safe="")
        )
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(tr(lang, "share"), url=url)]]
        )
    return None


def _format_options_keyboard(job_id: str, available_keys: List[str], lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key in available_keys:
        opt = next((f for f in FORMAT_OPTIONS if f.key == key), None)
        if not opt:
            continue
        label = opt.label
        if lang == "ar":
            label = {
                "best": "🎬 أفضل جودة",
                "720": "📺 HD 720p",
                "480": "📺 480p",
                "360": "📺 360p",
                "audio": "🎵 صوت فقط MP3",
            }.get(key, opt.label)
        rows.append([InlineKeyboardButton(label, callback_data=f"fmt:{job_id}:{key}")])
    rows.append(
        [
            InlineKeyboardButton(
                "⭐ Premium", callback_data="menu:subscribe"
            ),
            InlineKeyboardButton(
                "🚫 إلغاء" if lang == "ar" else "🚫 Cancel",
                callback_data=f"fmt:{job_id}:cancel",
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Entry / welcome
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    database.add_user(user.id, user.username or "", user.first_name or "")
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if db_user and db_user["language"] in ("ar", "en"):
        await update.effective_message.reply_text(
            tr(lang, "start"),
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=_menu_keyboard(lang),
        )
    else:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("العربية 🇮🇶", callback_data="lang:ar"),
                 InlineKeyboardButton("English 🇬🇧", callback_data="lang:en")]
            ]
        )
        await update.effective_message.reply_text(
            "⭐ TurboDL\n\nاختر لغتك / Choose your language:",
            reply_markup=kb,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    await update.effective_message.reply_text(
        tr(lang, "help"), parse_mode=constants.ParseMode.MARKDOWN
    )


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if database.is_premium(user.id):
        if is_admin(update) or not (db_user or {}).get("premium_expiry"):
            await update.effective_message.reply_text(
                tr(lang, "premium_owner"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            expiry = db_user["premium_expiry"] or ""
            await update.effective_message.reply_text(
                tr(lang, "already_premium", date=expiry),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        return

    if not config.ZAIN_CASH_NUMBER:
        await update.effective_message.reply_text("⚠️ Payment not configured yet.")
        return

    # Block duplicate pending payments
    for p in database.pending_payments():
        if p["telegram_id"] == user.id:
            await update.effective_message.reply_text(tr(lang, "payment_pending_exists"))
            return

    context.user_data["awaiting_payment"] = True
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🚫 إلغاء" if lang == "ar" else "🚫 Cancel", callback_data="sub:cancel")]]
    )
    await update.effective_message.reply_text(
        tr(lang, "subscribe", price=config.PREMIUM_PRICE_IQD, number=config.ZAIN_CASH_NUMBER),
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def receive_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if not context.user_data.get("awaiting_payment"):
        await update.effective_message.reply_text(tr(lang, "help"))
        return

    if not update.message.photo:
        await update.effective_message.reply_text(tr(lang, "awaiting_photo"))
        return

    for p in database.pending_payments():
        if p["telegram_id"] == user.id:
            await update.effective_message.reply_text(tr(lang, "payment_pending_exists"))
            return

    photo = update.message.photo[-1]
    payment_id = database.add_payment(
        user.id, user.username or "-", config.PREMIUM_PRICE_IQD, photo.file_id
    )
    context.user_data["awaiting_payment"] = False

    caption = tr(
        lang,
        "pay_preview",
        uid=user.id,
        username=user.username or "-",
        amount=config.PREMIUM_PRICE_IQD,
        date=database.today(),
    )
    approve = InlineKeyboardButton("✅ Approve", callback_data=f"pay:{payment_id}:approve")
    reject = InlineKeyboardButton("❌ Reject", callback_data=f"pay:{payment_id}:reject")
    kb = InlineKeyboardMarkup([[approve, reject]])

    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=f"{caption}\n\nوصل دفع جديد / New receipt — review it:",
                reply_markup=kb,
            )
        except TelegramError as exc:
            log.warning("Could not forward payment to admin %s: %s", admin_id, exc)

    await update.effective_message.reply_text(tr(lang, "payment_received"))


# ---------------------------------------------------------------------------
# Admin: payments
# ---------------------------------------------------------------------------
async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        return

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "pay":
        return
    payment_id, action = int(parts[1]), parts[2]

    payment = database.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await query.edit_message_text(
            "⏳ This payment was already processed.", parse_mode=constants.ParseMode.HTML
        )
        return

    db_user = database.get_user(payment["telegram_id"])
    lang = lang_of(db_user) if db_user else "ar"

    if action == "approve":
        database.update_payment_status(payment_id, "approved", update.effective_user.id)
        expiry = database.activate_premium(payment["telegram_id"])
        db_user = database.get_user(payment["telegram_id"])
        expiry = db_user["premium_expiry"] if db_user else ""
        try:
            await context.bot.send_message(
                chat_id=payment["telegram_id"],
                text=tr(lang, "payment_approved_user", date=expiry),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError as exc:
            log.warning("Could not notify user %s: %s", payment["telegram_id"], exc)
        await query.edit_message_text(
            tr(lang, "payment_approved_admin", pid=payment_id),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    elif action == "reject":
        database.update_payment_status(payment_id, "rejected", update.effective_user.id)
        try:
            await context.bot.send_message(
                chat_id=payment["telegram_id"],
                text=tr(lang, "payment_rejected_user"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError as exc:
            log.warning("Could not notify user %s: %s", payment["telegram_id"], exc)
        await query.edit_message_text(
            tr(lang, "payment_rejected_admin", pid=payment_id),
            parse_mode=constants.ParseMode.MARKDOWN,
        )


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    await update.effective_message.reply_text(
        tr(
            lang,
            "stats",
            users=database.user_count(),
            premium=database.premium_count(),
            downloads=database.total_downloads(),
            today=database.downloads_today(),
            revenue=database.revenue_today(),
        ),
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    text = (update.effective_message.text or "").split(maxsplit=1)
    msg = text[1].strip() if len(text) > 1 else ""
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    if not msg:
        await update.effective_message.reply_text(tr(lang, "broadcast_usage"))
        return

    users = database.all_users()
    ok, total = 0, len(users)
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["telegram_id"], text=msg)
            ok += 1
            await asyncio.sleep(0.05)
        except TelegramError:
            continue
    await update.effective_message.reply_text(
        tr(lang, "broadcast_sent", ok=ok, total=total)
    )


async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    args = context.args
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    if not args or not args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text(tr(lang, "admin_usage"))
        return
    uid = int(args[0])
    if not database.get_user(uid):
        await update.effective_message.reply_text(tr(lang, "user_not_found"))
        return
    database.activate_premium(uid, config.PREMIUM_DURATION_DAYS)
    db_user = database.get_user(uid)
    expiry = db_user["premium_expiry"]
    try:
        await context.bot.send_message(
            chat_id=uid,
            text=tr(lang_of(db_user), "payment_approved_user", date=expiry),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    except TelegramError as exc:
        log.warning("Notify failed: %s", exc)
    await update.effective_message.reply_text(tr(lang, "approved_user", uid=uid, date=expiry))


async def revoke_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    args = context.args
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    if not args or not args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text(tr(lang, "admin_usage"))
        return
    uid = int(args[0])
    if not database.get_user(uid):
        await update.effective_message.reply_text(tr(lang, "user_not_found"))
        return
    database.revoke_premium(uid)
    await update.effective_message.reply_text(tr(lang, "revoked_user", uid=uid))


async def set_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    args = context.args
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    if len(args) < 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await update.effective_message.reply_text(tr(lang, "usage_setexpiry"))
        return
    uid, days = int(args[0]), int(args[1])
    if not database.get_user(uid):
        await update.effective_message.reply_text(tr(lang, "user_not_found"))
        return
    database.activate_premium(uid, days)
    expiry = database.get_user(uid)["premium_expiry"]
    await update.effective_message.reply_text(
        tr(lang, "setexpiry_user", uid=uid, days=days, date=expiry)
    )


async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    await update.effective_message.reply_text(tr(lang, "purge_start"))
    n = 0
    for d in os.listdir(config.DOWNLOAD_DIR):
        path = os.path.join(config.DOWNLOAD_DIR, d)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
            n += 1
        except OSError:
            continue
    await update.effective_message.reply_text(tr(lang, "purge_done", n=n))


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    database.add_user(user.id, user.username or "", user.first_name or "")
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if config.PRIVATE_MODE and config.ALLOWED_USER_IDS and user.id not in config.ALLOWED_USER_IDS:
        await update.effective_message.reply_text(tr(lang, "not_allowed"))
        return

    text = update.effective_message.text or ""
    match = downloader.URL_RE.search(text)
    if not match:
        await update.effective_message.reply_text(tr(lang, "no_url"))
        return
    url = match.group(0)

    if context.user_data.get("active_download"):
        await update.effective_message.reply_text(tr(lang, "busy"))
        return

    if database.is_premium(user.id):
        remaining = -1
    else:
        remaining = database.remaining_daily_downloads(user.id)
        if remaining <= 0:
            await update.effective_message.reply_text(
                tr(lang, "limit_reached"),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_menu_keyboard(lang),
            )
            return

    status = await update.effective_message.reply_text(tr(lang, "checking"))

    info, err = await asyncio.to_thread(downloader.get_info, url)
    if err or not info:
        try:
            await status.edit_text(
                tr(lang, "unsupported"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        return

    premium = database.is_premium(user.id)
    limit = config.PREMIUM_MAX_FILE_SIZE if premium else config.FREE_MAX_FILE_SIZE
    est = (
        info.get("filesize")
        or info.get("filesize_approx")
        or max(
            (f.get("filesize") or 0 for f in (info.get("formats") or [])),
            default=0,
        )
    )
    if est and est > limit:
        try:
            await status.edit_text(
                tr(lang, "too_big", limit=limit // 1024 // 1024),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        return

    formats = info.get("formats") or []
    heights = sorted({f.get("height") for f in formats if f.get("height")}, reverse=True)
    max_h = heights[0] if heights else 0

    job_id = uuid.uuid4().hex[:10]
    context.user_data.setdefault("jobs", {})
    context.user_data["jobs"][job_id] = {"url": url, "info": info}

    # Direct/single-format files skip the quality chooser.
    direct = len(formats) <= 1 or info.get("_type") == "url_transparent"
    if direct:
        context.user_data["jobs"][job_id]["format"] = "best"
        try:
            await status.edit_text(tr(lang, "downloading"))
        except TelegramError:
            pass
        await _run_format(update, context, job_id, "best", status, db_user)
        return

    available = ["best"]
    if max_h > 720:
        available.append("720")
    if max_h > 480:
        available.append("480")
    elif max_h > 360:
        available.append("360")
    available.append("audio")

    title = (info.get("title") or "Video").strip()
    if len(title) > 60:
        title = title[:60] + "…"
    site = info.get("extractor_key") or info.get("extractor") or ""

    try:
        await status.edit_text(
            tr(lang, "choose_format", title=title, site=site),
            reply_markup=_format_options_keyboard(job_id, available, lang),
        )
    except TelegramError:
        pass


async def _run_format(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    job_id: str,
    format_key: str,
    status,
    db_user,
) -> None:
    user = update.effective_user
    lang = lang_of(db_user)
    job = context.user_data.get("jobs", {}).get(job_id)
    if not job:
        try:
            await status.edit_text(tr(lang, "no_url"))
        except TelegramError:
            pass
        return

    url = job["url"]
    premium = database.is_premium(user.id)
    if not premium:
        remaining = database.remaining_daily_downloads(user.id)
        if remaining <= 0:
            try:
                await status.edit_text(
                    tr(lang, "limit_reached"),
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            except TelegramError:
                pass
            return

    opt = next((f for f in FORMAT_OPTIONS if f.key == format_key), FORMAT_OPTIONS[0])
    context.user_data["active_download"] = True
    job["cancel"] = False
    job["done"] = False
    chat_id = user.id
    message_id = status.message_id

    state = {"last_text": ""}

    async def edit_progress(text: str) -> None:
        if job.get("done") or text == state["last_text"]:
            return
        state["last_text"] = text
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text
            )
        except TelegramError:
            pass

    def progress_cb(percent: float, text: str) -> None:
        if job.get("cancel"):
            raise downloader.DownloadCancelled()
        context.application.create_task(edit_progress(text))

    try:
        try:
            await status.edit_text(tr(lang, "downloading"))
        except TelegramError:
            pass
        context.user_data["jobs"][job_id]["format"] = format_key

        path, title, err = await asyncio.to_thread(
            downloader.download,
            url,
            opt.format_selector,
            opt.audio_only,
            premium,
            progress_cb,
            allow_hls=premium,
        )
    except downloader.DownloadCancelled:
        job["done"] = True
        try:
            await status.edit_text(tr(lang, "cancel"))
        except TelegramError:
            pass
        context.user_data["active_download"] = False
        return
    except DownloadError as exc:
        job["done"] = True
        try:
            await status.edit_text(tr(lang, "download_error", error=str(exc)))
        except TelegramError:
            pass
        context.user_data["active_download"] = False
        return

    if err or not path:
        job["done"] = True
        try:
            await status.edit_text(
                tr(lang, "download_error", error=err or "Unknown error"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        context.user_data["active_download"] = False
        return

    size = os.path.getsize(path)
    job["done"] = True
    if size > config.TELEGRAM_UPLOAD_LIMIT:
        try:
            await status.edit_text(
                tr(lang, "too_big", limit=config.TELEGRAM_UPLOAD_LIMIT // 1024 // 1024),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        await asyncio.to_thread(_cleanup_file, path)
        context.user_data["active_download"] = False
        return

    try:
        await status.edit_text(tr(lang, "uploading"))
    except TelegramError:
        pass

    try:
        if opt.audio_only:
            with open(path, "rb") as fh:
                sent = await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=fh,
                    title=title,
                )
        elif path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
            with open(path, "rb") as fh:
                sent = await context.bot.send_video(
                    chat_id=chat_id,
                    video=fh,
                    caption=title,
                    supports_streaming=True,
                )
        else:
            with open(path, "rb") as fh:
                sent = await context.bot.send_document(
                    chat_id=chat_id,
                    document=fh,
                    filename=os.path.basename(path),
                )
    except TelegramError as exc:
        log.warning("Upload failed for %s: %s", user.id, exc)
        try:
            await status.edit_text(
                tr(lang, "download_error", error="Telegram upload failed. File too big?"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        await asyncio.to_thread(_cleanup_file, path)
        context.user_data["active_download"] = False
        return
    finally:
        await asyncio.to_thread(_cleanup_file, path)

    database.consume_download(user.id)

    bot_username = context.bot_data.get("bot_username", "")
    markup = None
    if not premium and not opt.audio_only:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(tr(lang, "subscribe_btn"), callback_data="menu:subscribe")]]
        )
    elif bot_username:
        markup = _share_keyboard(lang, bot_username)

    done_text = tr(lang, "done")
    if not premium:
        left = database.remaining_daily_downloads(user.id)
        if left >= 0:
            done_text += f"\n\n📅 باقي لك اليوم: {left}"
    try:
        await status.edit_text(done_text, reply_markup=markup)
    except TelegramError:
        pass

    context.user_data["active_download"] = False
    context.user_data["jobs"].pop(job_id, None)


def _cleanup_file(path: str) -> None:
    try:
        if config.CLEANUP_FILES:
            parent = os.path.dirname(path)
            if os.path.isdir(parent):
                shutil.rmtree(parent, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = lang_of(db_user) if db_user else config.DEFAULT_LANGUAGE

    if query.data.startswith("lang:"):
        code = query.data.split(":", 1)[1]
        if code in ("ar", "en"):
            database.set_language(user.id, code)
        await query.answer()
        await query.edit_message_text(
            tr(code, "start"),
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=_menu_keyboard(code),
        )
        return

    if query.data.startswith("menu:"):
        action = query.data.split(":", 1)[1]
        await query.answer()
        if action == "subscribe":
            await query.edit_message_text(
                tr(lang, "subscribe", price=config.PREMIUM_PRICE_IQD, number=config.ZAIN_CASH_NUMBER),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        elif action == "help":
            await query.edit_message_text(
                tr(lang, "help"), parse_mode=constants.ParseMode.MARKDOWN
            )
        return

    if query.data.startswith("sub:cancel"):
        await query.answer()
        context.user_data["awaiting_payment"] = False
        await query.edit_message_text(tr(lang, "cancel"))
        return

    if query.data.startswith("pay:"):
        await payment_action(update, context)
        return

    if query.data.startswith("fmt:"):
        await query.answer()
        _, job_id, key = query.data.split(":")
        try:
            status = query.message
            await _run_format(update, context, job_id, key, status, db_user)
        except KeyError:
            pass
        return


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
        raise SystemExit(1)

    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    database.init_db()

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .read_timeout(120)
        .write_timeout(120)
        .connect_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("revoke", revoke_user))
    app.add_handler(CommandHandler("setexpiry", set_expiry))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(
        CallbackQueryHandler(callback_handler, pattern=r"^(lang|menu|sub|pay|fmt):")
    )
    app.add_handler(MessageHandler(filters.PHOTO, receive_payment_photo))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Entity("url"),
            handle_link,
        )
    )

    async def cache_username(app_ref: Application) -> None:
        try:
            me = await app_ref.bot.get_me()
            app_ref.bot_data["bot_username"] = me.username or ""
        except TelegramError:
            app_ref.bot_data["bot_username"] = ""

    app.post_init = cache_username

    log.info("TurboDL started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()