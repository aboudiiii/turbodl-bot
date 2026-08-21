import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    TelegramError,
    TimedOut,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ExtBot,
    MessageHandler,
    filters,
)

import config
import database
import downloader
from downloader import DownloadError, FORMAT_OPTIONS, download_queue

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
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
            "أرسل أي رابط لبدء التحميل فوراً! ⚡\n\n"
            "⚠️ تنبيه: البوت أداة مخصصة للاستخدام الشخصي والمباح فقط. "
            "يُحظر استخدامه في تحميل أي محتوى يخالف الشريعة الإسلامية، "
            "والمستخدم يتحمل المسؤولية الكاملة."
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
        "queued": "⏳ في قائمة الانتظار — مكانك الآن: #{pos}",
        "cached": (
            "⚡ سبق تحميل هذا الملف — أرسلناه لك فوراً دون إعادة التنزيل!"
        ),
        "choose_type": (
            "📥 اختر نوع التحميل:\n\n"
            "{title}\n"
            "👤 {site}"
        ),
        "btn_video": "🎬 فيديو",
        "btn_audio": "🎵 صوت فقط MP3",
        "btn_trim_video": "✂️ قص مقطع فيديو",
        "btn_trim_audio": "✂️ قص مقطع صوت",
        "trim_prompt": (
            "✂️ أرسل المدة المطلوب قصّها:\n"
            "`البداية-النهاية`\n\n"
            "مثال: `01:00-02:30`"
        ),
        "trim_bad": "❌ صيغة غير صحيحة. استخدم مثل: `01:00-02:30`",
        "back_btn": "🔙 رجوع",
        "menu_referral": "👥 نظام الدعوات",
        "referral_menu": (
            "👥 *نظام الدعوات*\n\n"
            "🔗 رابط الدعوة الخاص بك:\n`{link}`\n\n"
            "👥 عدد من دعوتهم: {count}\n"
            "🎁 المكافأة لكل صديق: {bonus} تحميلات\n"
            "💎 رصيدك الإضافي: {quota} تحميلات\n\n"
            "شارك الرابط مع أصدقائك وعندما ينضمون عبره تحصل على المكافأة!"
        ),
        "ref_bonus_granted": (
            "🎉 أحد أصدقائك انضم عبر رابطك! حصلت على {bonus} تحميلات إضافية 🎁"
        ),
        "ref_self": "❌ لا يمكنك استخدام رابط دعوتك الخاص!",
        "ref_dup": "❌ هذا الرابط مستخدم مسبقاً أو غير صالح.",
        "search_prompt": "🔎 ابحث في يوتيوب:\n`/search <كلمة البحث>`",
        "search_results": (
            "🔎 *نتائج البحث عن:* {q}\n\n"
            "اختر مقطعاً للتحميل مباشرة ↓"
        ),
        "search_none": "❌ لا توجد نتائج لهذا البحث.",
        "choose_pl": (
            "🎞️ *قائمة تشغيل:* {title}\n\n"
            "اختر طريقة التحميل:"
        ),
        "btn_pl_all": "⬇️ تحميل الكل ({n})",
        "btn_pl_pick": "📋 اختيار مقاطع",
        "pl_pick_title": "🎞️ {title}\n\nاختر مقطعاً:",
        "pl_too_many": (
            "⚠️ القائمة ضخمة جداً ({n} مقطع). اختر مقاطع محددة بدلاً من تحميل الكل."
        ),
        "pl_start": "⬇️ جاري تحميل قائمة التشغيل... ({done}/{total})",
        "pl_item_done": "✅ ({i}/{total}) {title}",
        "pl_item_fail": "❌ ({i}/{total}) فشل: {title}",
        "pl_finished": "✅ انتهى تحميل قائمة التشغيل: {ok} نجح من {total}",
        "force_text": (
            "📢 مرحباً! للاستخدام يجب أن تنضم إلى القناة أولاً 👇\n\n"
            "{link}"
        ),
        "lock_title": "الوصول مقفل",
        "lock_hint": "اشترك في القنوات أدناه ثم اضغط زر التحقق 👇",
        "force_join_btn": "📢 انضم: {channel}",
        "force_join": "🚀 انضم الآن",
        "force_check": "🔄 تحقق من الاشتراك",
        "force_welcome": "✅ شكراً لانضمامك! يمكنك البدء بالتحميل الآن.",
        "unlock_open": "تم فتح القفل! جارٍ التحضير...",
        "bonus_added": "🎁 تم إضافة {n} تحميلات مجانية لحسابك!",
        "still_need": "❌ لم تكمل الاشتراك بعد!\nالقنوات المطلوبة: {channels}",
        "download_hub_title": "📥 قسم التحميل",
        "student_hub_title": "🎓 قسم خدمات الطلاب",
        "media_hub_title": "🛠️ قسم أدوات الميديا",
        "games_hub_title": "🎮 قسم المسابقات والألعاب",
        "profile_hub_title": "👤 قسم الحساب والاشتراك",
        "locked_toast": "🔒 يجب الاشتراك في القنوات المطلوبة أولاً!",
        "downloading": "⬇️ جاري التحميل...",
        "uploading": "📤 جاري الرفع إلى تيليجرام...",
        "download_error": "❌ فشل التحميل: {error}",
        "done": "✅ تم التحميل بنجاح!",
        "share": "🚀 مشاركة البوت مع أصدقائك",
        "share_text": (
            "⚡ TurboDL — أسرع بوت تحميل من"
            " (يوتيوب، تيك توك، انستقرام، تويتر) بدون إعلانات 🚀"
        ),
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
        "stuck_cleared": (
            "♻️ تم إنهاء تحميل قديم عالق تلقائيًا.\n"
            "يمكنك إرسال الرابط والبدء من جديد الآن!"
        ),
        "reset_done": (
            "♻️ تم تنظيف حالة التحميل والانتظار.\n"
            "يمكنك البدء بالتحميل من جديد الآن."
        ),
        "reset_done_idle": "✅ لا توجد حالة تحميل عالقة. كل شيء نظيف.",
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
            "🔎 ابحث في يوتيوب: /search <كلمة>\n\n"
            "يدعم: يوتيوب، تيك توك، انستقرام، تويتر/X، فيسبوك،"
            " ريديت، فيميو، ساوند كلاود، بينترست، ثريدز، وكل الروابط المباشرة.\n\n"
            " مجاني: 3 تحميلات/يوم — حتى 50MB\n"
            " ⭐ بريميوم: غير محدود — حتى 2GB\n\n"
            "للاشتراك: /subscribe"
        ),
        "stats": (
            "📊 *إحصائيات البوت*\n\n"
            "👥 المستخدمون: {users}\n"
            "⭐ البريميوم: {premium}\n"
            "⬇️ إجمالي التحميلات: {downloads}\n"
            "🔄 تحميلات اليوم: {today}\n"
            "🧵 نشط: {active} · بالانتظار: {queued}\n"
            "💾 ملفات مُرسلة: {files}\n"
            "📦 بيانات منقولة: {data}\n"
            "⚡ من الذاكرة المؤقتة: {cache}\n"
            "💰 إيراد اليوم: {revenue} د.ع\n"
            "⏱️ وقت التشغيل: {uptime}"
        ),
        "broadcast_sent": "✅ تم إرسال الرسالة لـ {ok} من {total} مستخدم.",
        "broadcast_report": (
            "✅ تم الإرسال إلى {ok} من {total} مستخدم (تعذّر الوصول لـ {failed})."
        ),
        "broadcast_usage": "الاستخدام: /broadcast <الرسالة>\n(أو أرسل /broadcast رداً على صورة/فيديو/صوت لإرسالها للجميع)",
        "approved_user": "✅ تم تفعيل البريميوم لمستخدم {uid} حتى {date}.",
        "revoked_user": "✅ تم إلغاء البريميوم لمستخدم {uid}.",
        "setexpiry_user": "✅ تم تمديد بريميوم المستخدم {uid} لـ {days} يوم (حتى {date}).",
        "user_not_found": "❌ المستخدم ما موجود.",
        "admin_usage": "الاستخدام: /approve <user_id>",
        "usage_setexpiry": "الاستخدام: /setexpiry <user_id> <days>",
        "not_admin": "⛔ هذا الأمر للمشرفين فقط.",
        "banned": "⛔ تم حظرك من استخدام هذا البوت. تواصل مع المالك إذا كنت تعتقد أن هذا خطأ.",
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
            "Just send me any link to start 🚀\n\n"
            "⚠️ Disclaimer: This bot is intended for personal permissible use only. "
            "It is prohibited to use it for downloading any content that violates Islamic "
            "law, and the user bears full responsibility."
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
        "queued": "⏳ In the queue — your position: #{pos}",
        "cached": (
            "⚡ This file was downloaded before — sent instantly from cache!"
        ),
        "choose_type": (
            "📥 Choose download type:\n\n"
            "{title}\n"
            "👤 {site}"
        ),
        "btn_video": "🎬 Video",
        "btn_audio": "🎵 Audio only (MP3)",
        "btn_trim_video": "✂️ Trim video clip",
        "btn_trim_audio": "✂️ Trim audio clip",
        "trim_prompt": (
            "✂️ Send the segment to cut:\n"
            "`start-end`\n\n"
            "Example: `01:00-02:30`"
        ),
        "trim_bad": "❌ Invalid format. Use something like: `01:00-02:30`",
        "back_btn": "🔙 Back",
        "menu_referral": "👥 Invite System",
        "referral_menu": (
            "👥 *Invite System*\n\n"
            "🔗 Your invite link:\n`{link}`\n\n"
            "👥 People you invited: {count}\n"
            "🎁 Reward per friend: {bonus} downloads\n"
            "💎 Your bonus balance: {quota} downloads\n\n"
            "Share the link — each friend who joins rewards you!"
        ),
        "ref_bonus_granted": (
            "🎉 A friend joined through your link! You got {bonus} extra downloads 🎁"
        ),
        "ref_self": "❌ You can't use your own invite link!",
        "ref_dup": "❌ This link was already used or is invalid.",
        "search_prompt": "🔎 Search YouTube:\n`/search <query>`",
        "search_results": (
            "🔎 *Search results for:* {q}\n\n"
            "Pick an item to download instantly ↓"
        ),
        "search_none": "❌ No results for that search.",
        "choose_pl": (
            "🎞️ *Playlist:* {title}\n\n"
            "Choose how to download:"
        ),
        "btn_pl_all": "⬇️ Download all ({n})",
        "btn_pl_pick": "📋 Pick videos",
        "pl_pick_title": "🎞️ {title}\n\nPick a video:",
        "pl_too_many": (
            "⚠️ The playlist is huge ({n} videos). Pick specific items instead of downloading all."
        ),
        "pl_start": "⬇️ Downloading playlist... ({done}/{total})",
        "pl_item_done": "✅ ({i}/{total}) {title}",
        "pl_item_fail": "❌ ({i}/{total}) Failed: {title}",
        "pl_finished": "✅ Playlist finished: {ok} of {total} succeeded",
        "force_text": (
            "📢 Welcome! To use the bot you must join the channel first 👇\n\n"
            "{link}"
        ),
        "lock_title": "Access locked",
        "lock_hint": "Join the channels below, then tap Verify 👇",
        "force_join_btn": "📢 Join: {channel}",
        "force_join": "🚀 Join now",
        "force_check": "🔄 Verify subscription",
        "force_welcome": "✅ Thanks for joining! You can start downloading now.",
        "unlock_open": "Unlocked! Preparing...",
        "bonus_added": "🎁 {n} free downloads added to your account!",
        "still_need": "❌ Subscription incomplete!\nRequired channels: {channels}",
        "download_hub_title": "📥 Downloader Hub",
        "student_hub_title": "🎓 Student & AI Hub",
        "media_hub_title": "🛠️ Media Tools Hub",
        "games_hub_title": "🎮 Games & Loyalty",
        "profile_hub_title": "👤 User Profile",
        "locked_toast": "🔒 Join the required channels first!",
        "downloading": "⬇️ Downloading...",
        "uploading": "📤 Uploading to Telegram...",
        "download_error": "❌ Download failed: {error}",
        "done": "✅ Download complete!",
        "share": "🚀 Share the bot with your friends",
        "share_text": (
            "⚡ TurboDL — the fastest download bot for YouTube, TikTok,"
            " Instagram & Twitter, no ads 🚀"
        ),
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
        "stuck_cleared": (
            "♻️ A stuck download was cleared automatically.\n"
            "You can send a link and start again now!"
        ),
        "reset_done": "♻️ Download/waiting state cleared. You can start downloading again now.",
        "reset_done_idle": "✅ No stuck download state. Everything is clean.",
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
            "🔎 Search YouTube: /search <query>\n\n"
            "Supports: YouTube, TikTok, Instagram, Twitter/X, Facebook,"
            " Reddit, Vimeo, SoundCloud, Pinterest, Threads and any direct link.\n\n"
            " Free: 3 downloads/day — up to 50MB\n"
            " ⭐ Premium: Unlimited — up to 2GB\n\n"
            "Subscribe: /subscribe"
        ),
        "stats": (
            "📊 *Bot stats*\n\n"
            "👥 Users: {users}\n"
            "⭐ Premium: {premium}\n"
            "⬇️ Total downloads: {downloads}\n"
            "🔄 Today's downloads: {today}\n"
            "🧵 Active: {active} · Queued: {queued}\n"
            "💾 Files sent: {files}\n"
            "📦 Data transferred: {data}\n"
            "⚡ From cache: {cache}\n"
            "💰 Today's revenue: {revenue} IQD\n"
            "⏱️ Uptime: {uptime}"
        ),
        "broadcast_sent": "✅ Message sent to {ok} of {total} users.",
        "broadcast_report": (
            "✅ Sent to {ok} of {total} users ({failed} unreachable)."
        ),
        "broadcast_usage": "Usage: /broadcast <message>\n(or reply to a photo/video/audio with /broadcast to send it to all users)",
        "approved_user": "✅ Activated premium for {uid} until {date}.",
        "revoked_user": "✅ Revoked premium for {uid}.",
        "setexpiry_user": "✅ Extended premium for {uid} by {days} days (until {date}).",
        "user_not_found": "❌ User not found.",
        "admin_usage": "Usage: /approve <user_id>",
        "usage_setexpiry": "Usage: /setexpiry <user_id> <days>",
        "not_admin": "⛔ Admin command only.",
        "banned": "⛔ You have been banned from using this bot. Contact the owner if you believe this is a mistake.",
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


def is_owner(user_id: int) -> bool:
    """True for BOT_OWNER_ID or any ADMIN_IDS member."""
    return (
        user_id == config.BOT_OWNER_ID or user_id in config.ADMIN_IDS
    ) if user_id else False


def is_admin(update: Update) -> bool:
    return update.effective_user is not None and is_owner(update.effective_user.id)


def _upload_limit_for(user_id: int) -> int:
    """Admins bypass the standard upload cap entirely, up to Telegram's 2 GB bot limit."""
    return config.ADMIN_MAX_FILE_SIZE if is_owner(user_id) else config.TELEGRAM_UPLOAD_LIMIT


def _url_hash(url: str) -> str:
    """Stable short hash used to key duplicate-URL cache rows."""
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]


def _fmt_bytes(n: int) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0 MB"
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.1f} MB"


def _fmt_uptime(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "-"
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def _cache_kinds(opt) -> List[str]:
    """Which cache 'kind' columns to try for a given format option."""
    if opt.audio_only:
        return ["audio"]
    return ["video", "document"]


def _cache_filename(entry: Dict[str, Any], title: str) -> str:
    ext = {"audio": "mp3", "video": "mp4", "document": "bin"}.get(entry.get("kind"), "bin")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title or "media").strip()[:60] or "media"
    return f"{name}.{ext}"


def _send_cached(context, chat_id: int, entry: Dict[str, Any], caption: str, title: str, filename: str):
    """Forwards a cached file_id to another chat. Raises TelegramError on failure
    (stale file) so the caller can fall back to a real download."""
    kind = entry["kind"]
    if kind == "audio":
        return context.bot.send_audio(
            chat_id=chat_id,
            audio=entry["file_id"],
            title=title,
            caption=caption,
            parse_mode=constants.ParseMode.MARKDOWN,
            filename=filename,
        )
    if kind == "video":
        return context.bot.send_video(
            chat_id=chat_id,
            video=entry["file_id"],
            caption=caption,
            parse_mode=constants.ParseMode.MARKDOWN,
            supports_streaming=True,
        )
    return context.bot.send_document(
        chat_id=chat_id,
        document=entry["file_id"],
        caption=caption,
        parse_mode=constants.ParseMode.MARKDOWN,
        filename=filename,
    )


def _clear_stuck_active(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Clears a user's stale 'active download' marker.

    A download that produced no updates for STUCK_DOWNLOAD_TIMEOUT seconds is
    considered stuck (e.g. after a crash / manual kill). Returns True when a
    stuck queue was just cleared so callers can tell the user.
    """
    if not context.user_data.get("active_download"):
        return False
    since = context.user_data.get("active_download_since") or 0
    if time.time() - since > config.STUCK_DOWNLOAD_TIMEOUT:
        context.user_data["active_download"] = False
        context.user_data.pop("active_download_since", None)
        for job in context.user_data.get("jobs", {}).values():
            job["cancel"] = True
        context.user_data.pop("jobs", None)
        return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(tr(lang, "menu_subscribe"), callback_data="menu:subscribe"),
                InlineKeyboardButton(tr(lang, "menu_help"), callback_data="menu:help"),
            ],
            [
                InlineKeyboardButton(tr(lang, "menu_referral"), callback_data="menu:referral"),
            ],
        ]
    )


def _share_keyboard(lang: str, bot_username: str) -> Optional[InlineKeyboardMarkup]:
    if not bot_username:
        return None
    bot_link = f"https://t.me/{bot_username}"
    url = (
        "https://t.me/share/url?url="
        + urllib.parse.quote(bot_link, safe="")
        + "&text="
        + urllib.parse.quote(tr(lang, "share_text"), safe="")
    )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr(lang, "share"), url=url)]]
    )


def _md_escape(text: str) -> str:
    return re.sub(r"([_*\[\]`])", r"\\\1", text)


def _fmt_duration(seconds: Any) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _quality_label(key: str, lang: str) -> str:
    opt = next((f for f in FORMAT_OPTIONS if f.key == key), None)
    if not opt:
        return ""
    if lang == "ar":
        return {
            "best": "🎬 أفضل جودة",
            "720": "📺 HD 720p",
            "480": "📺 480p",
            "360": "📺 360p",
            "audio": "🎵 صوت فقط MP3",
        }.get(key, opt.label)
    return opt.label


def _file_caption(
    lang: str,
    title: str,
    quality: str,
    size_mb: int,
    bot_username: str,
    duration: Any = None,
) -> str:
    clean_title = (_md_escape(title or "Video").strip())[:100]
    lines = [f"🎬 **{clean_title}**", f"⚡️ {quality}"]
    meta = [f"📦 {size_mb} MB"]
    duration_str = _fmt_duration(duration)
    if duration_str:
        meta.insert(0, f"⏱️ {duration_str}")
    lines.append(" · ".join(meta))
    by = "⚡️ بواسطة @" if lang == "ar" else "⚡️ by @"
    lines.append(by + (bot_username or "TurboDL_bot"))
    return "\n\n".join(lines)


def _back_keyboard(lang: str, job_id: Optional[str] = None) -> InlineKeyboardMarkup:
    back_data = f"nav:{job_id}" if job_id else "nav:main"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr(lang, "back_btn"), callback_data=back_data)]]
    )


# ---------------------------------------------------------------------------
# Category navigation keyboards
# ---------------------------------------------------------------------------

def _category_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Main category selection keyboard with all hubs."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 التحميل", callback_data="cat:download")],
            [InlineKeyboardButton("🎓 خدمات الطلاب", callback_data="cat:student"),
             InlineKeyboardButton("🛠️ أدوات الميديا", callback_data="cat:media")],
            [InlineKeyboardButton("🎮 الألعاب والنظام", callback_data="cat:games"),
             InlineKeyboardButton("👤 الحساب", callback_data="cat:profile")],
        ]
    )


def _download_sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Sub-menu inside the Downloader Hub."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬇️ فيديو", callback_data="down:video")],
            [InlineKeyboardButton("🎵 صوت", callback_data="down:audio")],
            [InlineKeyboardButton("▶️ قوائم تشغيل", callback_data="down:playlist")],
            [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main:menu")],
        ]
    )


def _student_sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Sub-menu inside the Student & AI Hub."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 صورة إلى PDF", callback_data="student:pdf")],
            [InlineKeyboardButton("📄 PDF إلى صورة", callback_data="student:pdf2img")],
            [InlineKeyboardButton("📝 ملخص texto", callback_data="student:summarize")],
            [InlineKeyboardButton("🖼️ استخراج نص من صورة", callback_data="student:ocr")],
            [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main:menu")],
        ]
    )


def _media_sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Sub-menu inside the Media Tools Hub."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎵 فيديو إلى MP3", callback_data="media:mp3")],
            [InlineKeyboardButton("✂️ قص فيديو", callback_data="media:trim")],
            [InlineKeyboardButton("📝 تحويل صوتي", callback_data="media:stt")],
            [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main:menu")],
        ]
    )


def _games_sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Sub-menu inside the Games & Loyalty system."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 اختبار يومي", callback_data="games:quiz")],
            [InlineKeyboardButton("🎁 نظام الإحالة", callback_data="games:referral")],
            [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main:menu")],
        ]
    )


def _profile_sub_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Sub-menu inside the User Profile."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 الحالة الحالية", callback_data="profile:status")],
            [InlineKeyboardButton("💎 الاشتراك بريميوم", callback_data="profile:premium")],
            [InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="main:menu")],
        ]
    )


def _media_type_keyboard(job_id: str, has_video: bool, lang: str) -> InlineKeyboardMarkup:
    rows = []
    if has_video:
        rows.append(
            [InlineKeyboardButton(tr(lang, "btn_video"), callback_data=f"tp:{job_id}:video")]
        )
    rows.append(
        [InlineKeyboardButton(tr(lang, "btn_audio"), callback_data=f"tp:{job_id}:audio")]
    )
    rows.append(
        [
            InlineKeyboardButton(tr(lang, "btn_trim_video") if has_video else "✂️ قص مقطع صوت",
                                 callback_data=f"trim:{job_id}:{'video' if has_video else 'audio'}"),
            InlineKeyboardButton(tr(lang, "back_btn"), callback_data="nav:main"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _format_options_keyboard(job_id: str, available_keys: List[str], lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key in available_keys:
        label = _quality_label(key, lang)
        if not label:
            continue
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
    rows.append(
        [InlineKeyboardButton(tr(lang, "back_btn"), callback_data=f"tp:{job_id}:back")]
    )
    return InlineKeyboardMarkup(rows)


def _playlist_keyboard(job_id: str, total: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr(lang, "btn_pl_all", n=total), callback_data=f"pl:{job_id}:all"
                ),
                InlineKeyboardButton(
                    tr(lang, "btn_pl_pick"), callback_data=f"pl:{job_id}:pick"
                ),
            ],
            [InlineKeyboardButton(tr(lang, "back_btn"), callback_data="nav:main")],
        ]
    )


def _playlist_pick_keyboard(job_id: str, entries: List[dict], lang: str) -> InlineKeyboardMarkup:
    rows = []
    for e in entries[: config.PLAYLIST_PICK_LIMIT]:
        title = (e.get("title") or f"#{e.get('index')}").strip().replace("\n", " ")
        if len(title) > 45:
            title = title[:45] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{e.get('index')}. {title}",
                    callback_data=f"pl:{job_id}:item:{e.get('index')}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(tr(lang, "back_btn"), callback_data=f"nav:{job_id}")]
    )
    return InlineKeyboardMarkup(rows)


def _referral_link(bot_username: str, user_id: int) -> str:
    uname = bot_username or "TurboDL_Iraq_bot"
    return f"https://t.me/{uname}?start=ref_{user_id}"


# ---------------------------------------------------------------------------
# Force-sub channels guard (optional) + admin notifications
# ---------------------------------------------------------------------------
def _force_invite_for(channel: str) -> Optional[str]:
    """Best static join link for a channel entry ('@name' or numeric id)."""
    if channel.startswith("@"):
        return f"https://t.me/{channel.lstrip('@')}"
    if config.FORCE_SUB_INVITE:
        return config.FORCE_SUB_INVITE
    return None


async def _resolve_force_link(
    context: ContextTypes.DEFAULT_TYPE, channel: str
) -> Optional[str]:
    """Resolves (and caches) a join link for any force-sub channel.

    '@name' entries map straight to t.me; numeric ids are looked up through
    getChat (public username or primary invite link) once per startup."""
    cache = context.bot_data.setdefault("force_links", {})
    if channel in cache:
        return cache[channel]
    url = _force_invite_for(channel)
    if url is None:
        try:
            chat = await context.bot.get_chat(int(channel))
            if getattr(chat, "username", None):
                url = f"https://t.me/{chat.username}"
            else:
                url = getattr(chat, "invite_link", None)
        except TelegramError as exc:
            log.warning("Could not resolve join link for %s: %s", channel, exc)
            url = None
    cache[channel] = url
    return url


def _progress_bar(done: int, total: int, width: int = 8) -> str:
    filled = round(width * done / total) if total > 0 else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


async def _is_member(
    context: ContextTypes.DEFAULT_TYPE, channel: str, user_id: int
) -> bool:
    chat_id: Any = int(channel) if re.fullmatch(r"-?\d+", channel) else channel
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramError:
        # Bot lacks admin rights in the channel or the API call failed —
        # treat as not joined so the guard stays strict.
        return False
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    return status == "restricted" and getattr(member, "is_member", False)


async def _missing_channels(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> List[str]:
    missing = []
    for channel in config.FORCE_SUB_CHANNELS:
        if not await _is_member(context, channel, user_id):
            missing.append(channel)
    return missing


def _force_lock_text(lang: str, joined: int, total: int) -> str:
    bar = _progress_bar(joined, total)
    return (
        f"🔒 **{tr(lang, 'lock_title')}**\n\n"
        f"`[{bar}]` {joined}/{total}\n\n"
        f"{tr(lang, 'lock_hint')}"
    )


async def _force_keyboard(
    context: ContextTypes.DEFAULT_TYPE, missing: List[str], lang: str
) -> InlineKeyboardMarkup:
    rows = []
    for channel in missing:
        url = await _resolve_force_link(context, channel)
        label = tr(lang, "force_join_btn", channel=channel)
        rows.append([InlineKeyboardButton(label, url=url or "https://t.me")])
    rows.append(
        [InlineKeyboardButton(tr(lang, "force_check"), callback_data="force:check")]
    )
    return InlineKeyboardMarkup(rows)


async def _send_force_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str
) -> None:
    total = len(config.FORCE_SUB_CHANNELS)
    missing = await _missing_channels(context, update.effective_user.id)
    await update.effective_message.reply_text(
        _force_lock_text(lang, total - len(missing), total),
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=await _force_keyboard(context, missing, lang),
        disable_web_page_preview=True,
    )


async def _force_guard(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> bool:
    """Strict middleware: True only when the user may use the bot.

    Runs the ban check for every guarded handler, then force-sub.
    Admins/owner bypass both.
    """
    user = update.effective_user
    if user and not is_owner(user.id) and database.is_banned(user.id):
        await update.effective_message.reply_text(tr(lang, "banned"))
        return False
    if not config.FORCE_SUB_CHANNELS:
        return True
    if user and is_owner(user.id):
        return True
    missing = await _missing_channels(context, user.id)
    if not missing:
        return True
    total = len(config.FORCE_SUB_CHANNELS)
    await update.effective_message.reply_text(
        _force_lock_text(lang, total - len(missing), total),
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=await _force_keyboard(context, missing, lang),
        disable_web_page_preview=True,
    )
    return False


def _admin_new_user_text(user, via: str) -> str:
    # User-supplied names/usernames may contain Markdown specials (e.g. "_")
    # which would break parsing — escape them.
    username = _md_escape(f"@{user.username}" if user.username else "—")
    name = _md_escape(getattr(user, "full_name", "") or "")
    return (
        "🔔 **مستخدم جديد!**\n"
        f"👤 الاسم: {name}\n"
        f"🆔 الآيدي: `{user.id}`\n"
        f"Username: {username}\n"
        f"🔗 طريق الانضمام: {via}"
    )


async def _log_event(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Sends a system-log entry to LOG_CHANNEL_ID; never raises on failure."""
    if not config.LOG_CHANNEL_ID:
        return
    try:
        await context.bot.send_message(
            chat_id=config.LOG_CHANNEL_ID,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN,
        )
    except TelegramError as exc:
        log.warning("Log entry to %s failed: %s", config.LOG_CHANNEL_ID, exc)


async def verify_log_channel(bot: ExtBot) -> bool:
    """Probes LOG_CHANNEL_ID at startup.

    Sends the 'Bot Online & Operational' banner. Returns True when the
    channel accepted the message; on failure prints a clear warning to
    stdout (via logging) instead of raising, so the bot keeps running.
    """
    if not config.LOG_CHANNEL_ID:
        log.warning(
            "LOG_CHANNEL_ID is not configured - system logs are disabled "
            "(set ADMIN_ID or LOG_CHANNEL_ID to receive them)."
        )
        return False
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = (
        "🟢 **Bot Online & Operational**\n"
        f"🤖 التشغيل السليم مؤكد — البوت يعمل الآن\n"
        f"🕒 {stamp}"
    )
    try:
        await bot.send_message(
            chat_id=config.LOG_CHANNEL_ID,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return True
    except Forbidden:
        log.error(
            "STARTUP CHECK FAILED: bot was blocked/kicked from log channel %s "
            "(Forbidden). Re-add the bot as a member/admin. System logs are "
            "disabled until fixed, but the bot keeps running.",
            config.LOG_CHANNEL_ID,
        )
    except BadRequest as exc:
        log.error(
            "STARTUP CHECK FAILED: cannot post to LOG_CHANNEL_ID %s (%s). "
            "Check the chat id - group/channel ids look like '-100xxxxxxxxxx'. "
            "System logs are disabled until fixed, but the bot keeps running.",
            config.LOG_CHANNEL_ID,
            exc.message if hasattr(exc, "message") else exc,
        )
    except TelegramError as exc:
        log.error(
            "STARTUP CHECK FAILED: could not reach log channel %s (%s). "
            "System logs are disabled until fixed, but the bot keeps running.",
            config.LOG_CHANNEL_ID,
            exc,
        )
    return False


async def log_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler: reports failures to stdout and the log channel.

    Routine network hiccups are only logged to stdout; real errors also go
    to LOG_CHANNEL_ID. Users never see these - their chats only ever get
    the direct result of their own request.
    """
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        log.warning("Transient network error: %s", err)
        return

    log.error("Unhandled exception while processing an update:", exc_info=err)

    where = "-"
    user_id = "-"
    if isinstance(update, Update):
        where = (
            update.callback_query.data
            if update.callback_query
            else (update.effective_message.text or "")[:80] if update.effective_message else "?"
        )
        if update.effective_user:
            user_id = str(update.effective_user.id)

    summary = (
        f"🔴 {type(err).__name__}: {_md_escape(str(err)[:300])}\n"
        f"👤 المستخدم: `{user_id}`\n"
        f"📍 السياق: {_md_escape(where)}"
    )
    await _log_event(context, summary)


async def _log_download(
    context: ContextTypes.DEFAULT_TYPE, user, url: str, title: str
) -> None:
    """Reports one completed download to the log channel."""
    safe_url = (url or "").replace("`", "").strip()
    name = _md_escape(getattr(user, "full_name", "") or "")
    item = _md_escape((title or "ملف").strip())
    await _log_event(
        context,
        "📥 **تحميل جديد**\n"
        f"👤 المستخدم: {name} (`{user.id}`)\n"
        f"🔗 الرابط: `{safe_url}`\n"
        f"⚡ المادة: {item}",
    )


# ---------------------------------------------------------------------------
# Entry / welcome
# ---------------------------------------------------------------------------
async def _process_referral(
    update: Update, context: ContextTypes.DEFAULT_TYPE, arg: str, lang: str
) -> None:
    """Handles a /start ref_<id> deep link. Caller must have added the user."""
    user = update.effective_user
    token = arg.split("_", 1)[1] if "_" in arg else ""
    if not token.isdigit():
        return
    referrer = int(token)
    if referrer == user.id:
        await update.effective_message.reply_text(tr(lang, "ref_self"))
        return
    if database.has_referral(user.id):
        return  # already referred once; stay quiet on repeat /starts
    bonus = config.REFERRAL_BONUS_DOWNLOADS
    if database.add_referral(referrer, user.id, bonus):
        log.info("Referral recorded: %s -> %s", referrer, user.id)
        await _log_event(
            context,
            _admin_new_user_text(user, f"رابط دعوة بواسطة {referrer}"),
        )
        if config.REFERRAL_BONUS_PREMIUM_DAYS > 0:
            database.activate_premium(referrer, config.REFERRAL_BONUS_PREMIUM_DAYS)
        try:
            await context.bot.send_message(
                chat_id=referrer,
                text=tr("ar", "ref_bonus_granted", bonus=bonus),
            )
        except TelegramError as exc:
            log.warning("Could not notify referrer %s: %s", referrer, exc)
    else:
        await update.effective_message.reply_text(tr(lang, "ref_dup"))


def _banner_media() -> Tuple[Optional[str], Optional[str]]:
    """Resolves the configured welcome banner to ('url', url) or ('file', path).

    A local path may be absolute or relative to the project root. Returns
    (None, None) when no banner is configured.
    """
    if config.WELCOME_BANNER_URL:
        return "url", config.WELCOME_BANNER_URL
    if config.WELCOME_BANNER_PATH:
        path = config.WELCOME_BANNER_PATH
        if not os.path.isabs(path):
            path = os.path.join(config.BASE_DIR, path)
        if os.path.exists(path):
            return "file", path
        log.warning("WELCOME_BANNER_PATH file not found: %s", config.WELCOME_BANNER_PATH)
    return None, None


async def _send_with_banner(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    caption: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    *,
    edit_message_id: Optional[int] = None,
) -> None:
    """Sends (or re-renders) a menu message with the welcome banner photo above
    the buttons. When no banner is set — or the photo fails — it falls back to
    a plain text message. With a banner, the old text message is deleted after
    the new photo lands (text messages can't be edited into photos)."""
    kind, source = _banner_media()
    if kind:
        try:
            if kind == "url":
                await context.bot.send_photo(
                    chat_id,
                    photo=source,
                    caption=caption,
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            else:
                with open(source, "rb") as fh:
                    await context.bot.send_photo(
                        chat_id,
                        photo=fh,
                        caption=caption,
                        parse_mode=constants.ParseMode.MARKDOWN,
                        reply_markup=reply_markup,
                    )
            if edit_message_id is not None:
                try:
                    await context.bot.delete_message(
                        chat_id=chat_id, message_id=edit_message_id
                    )
                except TelegramError:
                    pass
            return
        except TelegramError as exc:
            log.warning("Welcome banner photo failed, falling back to text: %s", exc)
    if edit_message_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=caption,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        except TelegramError:
            pass
    else:
        await context.bot.send_message(
            chat_id,
            caption,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    is_new_user = database.get_user(user.id) is None
    database.add_user(user.id, user.username or "", user.first_name or "")
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if is_new_user:
        # INVARIANT: the "مستخدم جديد!" alert goes ONLY to LOG_CHANNEL_ID
        # (_log_event). Never send it to the user's private chat or to
        # ADMIN_ID - the user must only receive the welcome banner + menu.
        log.info("New user joined: %s (%s)", user.full_name, user.id)
        await _log_event(
            context, _admin_new_user_text(user, "انضمام جديد للبوت")
        )

    if _clear_stuck_active(context):
        await update.effective_message.reply_text(tr(lang, "stuck_cleared"))

    args = context.args or []
    if args and args[0].startswith("ref_"):
        await _process_referral(update, context, args[0], lang)

    if not await _force_guard(update, context, lang):
        return

    if db_user and db_user["language"] in ("ar", "en"):
        await _send_with_banner(
            context, user.id, tr(lang, "start"), _category_keyboard(lang)
        )
    else:
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("العربية 🇮🇶", callback_data="lang:ar"),
                 InlineKeyboardButton("English 🇬🇧", callback_data="lang:en")]
            ]
        )
        await _send_with_banner(
            context,
            user.id,
            "⭐ TurboDL\n\nاختر لغتك / Choose your language:",
            kb,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    if not await _force_guard(update, context, lang):
        return
    await update.effective_message.reply_text(
        tr(lang, "help"), parse_mode=constants.ParseMode.MARKDOWN
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually clears the user's own download queue / stuck state."""
    user = update.effective_user
    if not user:
        return
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)
    if not await _force_guard(update, context, lang):
        return

    was_stuck = context.user_data.get("active_download", False) or bool(
        context.user_data.get("jobs")
    )
    for job in context.user_data.get("jobs", {}).values():
        job["cancel"] = True
    context.user_data["active_download"] = False
    context.user_data.pop("active_download_since", None)
    context.user_data.pop("jobs", None)
    context.user_data.pop("awaiting_payment", None)

    await update.effective_message.reply_text(
        tr(lang, "reset_done") if was_stuck else tr(lang, "reset_done_idle")
    )


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)
    if not await _force_guard(update, context, lang):
        return

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
    if not await _force_guard(update, context, lang):
        return

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

    await _log_event(
        context,
        f"💳 **طلب اشتراك بريميوم**\n"
        f"👤 المستخدم: {_md_escape(user.full_name or '')} (`{user.id}`)\n"
        f"💰 المبلغ: {config.PREMIUM_PRICE_IQD} د.ع",
    )

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
    started = database.stats_get("started_at")
    uptime = _fmt_uptime(int(time.time()) - started) if started else "-"
    await update.effective_message.reply_text(
        tr(
            lang,
            "stats",
            users=database.user_count(),
            premium=database.premium_count(),
            downloads=database.total_downloads(),
            today=database.downloads_today(),
            active=download_queue.active_count,
            queued=download_queue.queued_count,
            files=database.stats_get("files_processed"),
            data=_fmt_bytes(database.stats_get("bytes_processed")),
            cache=database.stats_get("cache_hits"),
            revenue=database.revenue_today(),
            uptime=uptime,
        ),
        parse_mode=constants.ParseMode.MARKDOWN,
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return

    text = (update.effective_message.text or "").split(maxsplit=1)
    caption = text[1].strip() if len(text) > 1 else ""
    db_user = database.get_user(update.effective_user.id)
    lang = lang_of(db_user)

    reply = update.effective_message.reply_to_message
    photo = getattr(reply, "photo", None) if reply else None
    video = getattr(reply, "video", None) if reply else None
    audio = getattr(reply, "audio", None) if reply else None
    document = getattr(reply, "document", None) if reply else None
    media = None
    if photo:
        media = ("photo", photo[-1].file_id)
    elif video:
        media = ("video", video.file_id)
    elif audio:
        media = ("audio", audio.file_id)
    elif document:
        media = ("document", document.file_id)

    if not caption and not media:
        await update.effective_message.reply_text(tr(lang, "broadcast_usage"))
        return

    users = database.all_users()
    total = len(users)
    if not total:
        await update.effective_message.reply_text(tr(lang, "broadcast_sent", ok=0, total=0))
        return

    async def _send_one(uid: int) -> bool:
        try:
            if media and media[0] == "photo":
                await context.bot.send_photo(
                    chat_id=uid, photo=media[1], caption=caption
                )
            elif media and media[0] == "video":
                await context.bot.send_video(
                    chat_id=uid, video=media[1], caption=caption
                )
            elif media and media[0] == "audio":
                await context.bot.send_audio(
                    chat_id=uid, audio=media[1], caption=caption
                )
            elif media and media[0] == "document":
                await context.bot.send_document(
                    chat_id=uid, document=media[1], caption=caption
                )
            else:
                await context.bot.send_message(chat_id=uid, text=caption)
            return True
        except TelegramError:
            return False

    ok = 0
    # Send in bounded batches so broadcasts finish quickly without hammering
    # the API all at once.
    batch = [u["telegram_id"] for u in users]
    for i in range(0, len(batch), config.BROADCAST_BATCH_SIZE):
        results = await asyncio.gather(*(_send_one(uid) for uid in batch[i:i + config.BROADCAST_BATCH_SIZE]))
        ok += sum(1 for r in results if r)
        await asyncio.sleep(0.05)

    await update.effective_message.reply_text(
        tr(lang, "broadcast_report", ok=ok, total=total, failed=total - ok)
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
# Admin control panel & management commands (owner/admins only)
# ---------------------------------------------------------------------------
def _admin_stats_text() -> str:
    started = database.stats_get("started_at")
    uptime = _fmt_uptime(int(time.time()) - started) if started else "-"
    return (
        f"🛠 *لوحة تحكم الأدمن* — TurboDL\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: `{database.user_count()}`\n"
        f"⭐ بريميوم: `{database.premium_count()}`\n"
        f"📥 إجمالي التحميلات: `{database.total_downloads()}` (اليوم: `{database.downloads_today()}`)\n"
        f"⚡ قيد التنفيذ: `{download_queue.active_count}` | انتظار: `{download_queue.queued_count}`\n"
        f"🗂 ملفات معالجة: `{database.stats_get('files_processed')}` ({_fmt_bytes(database.stats_get('bytes_processed'))})\n"
        f"🎯 إصابات الكاش: `{database.stats_get('cache_hits')}`\n"
        f"💰 إيراد اليوم: `{database.revenue_today():,}` د.ع\n"
        f"🚫 المحظورون: `{len(database.banned_users())}`\n"
        f"🕒 مدة التشغيل: {uptime}"
    )


def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 تحديث", callback_data="adm:refresh"),
                InlineKeyboardButton("📜 السجلات", callback_data="adm:logs"),
            ],
            [
                InlineKeyboardButton("🚫 المحظورون", callback_data="adm:banned"),
                InlineKeyboardButton("📢 بث رسالة", callback_data="adm:broadcast"),
            ],
            [
                InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="nav:main"),
            ],
        ]
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin - opens the admin control panel (owner/admins only)."""
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    await _send_with_banner(
        context,
        update.effective_user.id,
        _admin_stats_text(),
        _admin_panel_keyboard(),
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all adm:* panel buttons."""
    query = update.callback_query
    if not is_admin(update):
        try:
            await query.answer(tr("ar", "not_admin"), show_alert=True)
        except TelegramError:
            pass
        return
    action = query.data.split(":", 1)[1]

    if action == "refresh":
        try:
            await query.answer()
        except TelegramError:
            pass
        try:
            await query.edit_message_caption(
                caption=_admin_stats_text(),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_admin_panel_keyboard(),
            )
        except TelegramError:
            pass
        return

    if action == "logs":
        await query.answer()
        path = _latest_log_file()
        if not path:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="📜 لا يوجد ملف سجل متاح (في الاستضافة السحابية تُطبع السجلات إلى console).",
            )
            return
        with open(path, "rb") as fh:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=fh,
                filename=os.path.basename(path),
                caption=f"📜 أحدث سجل تشغيل (`{os.path.basename(path)}`)",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        return

    if action == "banned":
        ids = database.banned_users()
        listing = "\n".join(f"• `{uid}`" for uid in ids[:30]) or "—"
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=(
                f"🚫 المحظورون ({len(ids)}):\n{listing}\n\n"
                f"لرفع الحظر: `/unban <user_id>`"
            ),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    if action == "broadcast":
        await query.answer()
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=(
                "📢 لبث رسالة لجميع المستخدمين:\n"
                "`/broadcast نص الرسالة`\n"
                "أو ردّ على رسالة/مادة بـ `/broadcast` لإعادة إرسالها للجميع."
            ),
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    try:
        await query.answer()
    except TelegramError:
        pass


def _latest_log_file() -> Optional[str]:
    """Newest runtime log file, or None when nothing is on disk."""
    candidates = [
        os.path.join(config.BASE_DIR, "logs", "service_output.log"),
        os.path.join(config.BASE_DIR, "logs", "turbodl.log"),
        os.path.join(config.BASE_DIR, "bot.log"),
        os.path.join(config.BASE_DIR, "bot_err.log"),
    ]
    existing = [p for p in candidates if os.path.isfile(p)]
    if not existing:
        return None
    return max(existing, key=os.path.getmtime)


def _parse_uid(args: List[str]) -> Optional[int]:
    if not args or not args[0].lstrip("-").isdigit():
        return None
    return int(args[0])


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ban <user_id> - blocks a user from using the bot."""
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    uid = _parse_uid(context.args or [])
    if uid is None:
        await update.effective_message.reply_text(
            "الاستخدام: `/ban <user_id>`", parse_mode=constants.ParseMode.MARKDOWN
        )
        return
    if is_owner(uid):
        await update.effective_message.reply_text("⛔ لا يمكن حظر مشرف/مالك.")
        return
    if not database.set_banned(uid, True):
        await update.effective_message.reply_text(tr("ar", "user_not_found"))
        return
    await update.effective_message.reply_text(f"🚫 تم حظر المستخدم `{uid}`.", parse_mode=constants.ParseMode.MARKDOWN)
    await _log_event(
        context,
        f"🚫 **حظر مستخدم**\n👤 المعرف: `{uid}`\n✍️ بواسطة: `{update.effective_user.id}`",
    )


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unban <user_id> - lifts a user's ban."""
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    uid = _parse_uid(context.args or [])
    if uid is None:
        await update.effective_message.reply_text(
            "الاستخدام: `/unban <user_id>`", parse_mode=constants.ParseMode.MARKDOWN
        )
        return
    if not database.set_banned(uid, False):
        await update.effective_message.reply_text(tr("ar", "user_not_found"))
        return
    await update.effective_message.reply_text(f"✅ تم رفع الحظر عن `{uid}`.", parse_mode=constants.ParseMode.MARKDOWN)
    await _log_event(
        context,
        f"✅ **رفع حظر**\n👤 المعرف: `{uid}`\n✍️ بواسطة: `{update.effective_user.id}`",
    )


async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/setlimit <user_id> <limit_in_mb|off> - per-user download size cap."""
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    args = context.args or []
    uid = _parse_uid(args)
    if uid is None or len(args) < 2:
        await update.effective_message.reply_text(
            "الاستخدام: `/setlimit <user_id> <limit_in_mb>`\n"
            "مثال: `/setlimit 123456789 2048`\n"
            "لإزالة الحد المخصص: `/setlimit 123456789 off`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    raw = args[1].lower().strip()
    if raw in ("off", "none", "clear", "0"):
        if not database.set_size_limit(uid, None):
            await update.effective_message.reply_text(tr("ar", "user_not_found"))
            return
        await update.effective_message.reply_text(
            f"♻️ أُزيل الحد المخصص للمستخدم `{uid}` — عاد للخطة الافتراضية.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    if not raw.isdigit():
        await update.effective_message.reply_text(
            "❌ الحد يجب أن يكون رقماً بالميجابايت (أو `off`).",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    mb = int(raw)
    if mb < 1 or mb > 2048:
        await update.effective_message.reply_text(
            "❌ الحد يجب أن يكون بين 1 و 2048 ميجابايت."
        )
        return

    if not database.set_size_limit(uid, mb):
        # User never /started the bot - create the row, then apply.
        database.add_user(uid, "-", "-")
        database.set_size_limit(uid, mb)

    label = _fmt_bytes(mb * 1024 * 1024)
    await update.effective_message.reply_text(
        f"✅ تم تعيين حد التحميل للمستخدم `{uid}` إلى *{label}*.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    await _log_event(
        context,
        f"⚙️ **تعديل حد تحميل**\n👤 المعرف: `{uid}`\n📏 الحد الجديد: {label}\n✍️ بواسطة: `{update.effective_user.id}`",
    )


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/logs - sends the latest runtime log file into this chat."""
    if not is_admin(update):
        await update.effective_message.reply_text(tr("ar", "not_admin"))
        return
    path = _latest_log_file()
    if not path:
        await update.effective_message.reply_text(
            "📜 لا يوجد ملف سجل متاح محلياً (في الاستضافة السحابية تُطبع السجلات إلى console)."
        )
        return
    await update.effective_message.reply_document(
        document=open(path, "rb"),
        filename=os.path.basename(path),
        caption=f"📜 أحدث سجل تشغيل (`{os.path.basename(path)}`)",
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    await _log_event(
        context,
        f"📜 **إرسال سجل**\n📄 الملف: `{os.path.basename(path)}`\n✍️ بواسطة: `{update.effective_user.id}`",
    )


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------
def _parse_ts(ts: str) -> Optional[float]:
    """Parses 'MM:SS' or 'HH:MM:SS' into total seconds."""
    parts = [p for p in ts.strip().split(":") if p != ""]
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


TRIM_RE = re.compile(r"^\s*(\d+(?::\d+)?):\d{2}\s*[-–—]\s*(\d+(?::\d+)?):\d{2}\s*$")


ADULT_KEYWORDS = {
    "ar": [
        "xxx", "porn", "sex", "xnxx", "xvideos",
    ],
    "en": [
        "sex", "porn", "xxx", "xnxx", "xvideos",
    ],
}


def _is_adult_content(text: str, lang: str) -> bool:
    """Check if text contains adult/NSFW keywords. Returns True if unsafe."""
    keywords = ADULT_KEYWORDS.get(lang, ADULT_KEYWORDS["en"])
    lowered = (text or "").lower()
    return any(kw.lower() in lowered for kw in keywords)


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

    if not await _force_guard(update, context, lang):
        return

    text = update.effective_message.text or ""
    match = downloader.URL_RE.search(text)
    if not match:
        await update.effective_message.reply_text(tr(lang, "no_url"))
        return
    url = match.group(0)

    # --- NSFW / Adult content filter ---
    if _is_adult_content(url, lang):
        await update.effective_message.reply_text(
            "⛔ عفواً، لا يمكن تحميل هذا النوع من المحتوى."
        )
        return
    # -------------------------------------

    was_stuck = _clear_stuck_active(context)
    if context.user_data.get("active_download"):
        await update.effective_message.reply_text(tr(lang, "busy"))
        return
    if was_stuck:
        await update.effective_message.reply_text(tr(lang, "stuck_cleared"))

    await _process_link(update, context, url, db_user, lang, check_playlist=True)


async def _offer_playlist(context, url, info, entries, lang, status):
    job_id = uuid.uuid4().hex[:10]
    context.user_data.setdefault("jobs", {})
    context.user_data["jobs"][job_id] = {"url": url, "info": info, "playlist": entries}
    pl_title = (info.get("title") or "Playlist").strip()
    if len(pl_title) > 60:
        pl_title = pl_title[:60] + "…"
    if len(entries) > config.PLAYLIST_MAX_ITEMS:
        try:
            await status.edit_text(
                tr(lang, "pl_too_many", n=len(entries)),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_playlist_keyboard(job_id, len(entries), lang),
            )
        except TelegramError:
            pass
    else:
        try:
            await status.edit_text(
                tr(lang, "choose_pl", title=pl_title),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_playlist_keyboard(job_id, len(entries), lang),
            )
        except TelegramError:
            pass


async def _process_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    db_user,
    lang: str,
    status=None,
    forced_key: Optional[str] = None,
    check_playlist: bool = False,
) -> None:
    """Core download flow: quota check -> info -> playlist/type/quality chooser
    -> _run_format. Reused by link messages, playlist picks and search results."""
    user = update.effective_user
    premium = database.is_premium(user.id)
    if not premium:
        remaining = database.remaining_daily_downloads(user.id)
        if remaining <= 0:
            msg = tr(lang, "limit_reached")
            if status is not None:
                try:
                    await status.edit_text(msg, parse_mode=constants.ParseMode.MARKDOWN)
                except TelegramError:
                    pass
            else:
                await update.effective_message.reply_text(
                    msg, parse_mode=constants.ParseMode.MARKDOWN
                )
            return

    if status is None:
        status = await update.effective_message.reply_text(tr(lang, "checking"))

    if check_playlist:
        info, err = await asyncio.to_thread(
            downloader.get_info, url, False, config.PLAYLIST_MAX_ITEMS + 1
        )
    else:
        info, err = await asyncio.to_thread(downloader.get_info, url)
    if err or not info:
        if downloader.is_instagram(url):
            # Instagram extraction often fails on anonymous rate limits even
            # when the media itself is downloadable. Skip the menu and go
            # straight to download - downloader.download() has a dedicated
            # gallery-dl fallback for exactly this case.
            log.info("Instagram get_info failed (%s); trying direct download", err)
            info = {
                "id": "ig",
                "title": "Instagram",
                "_type": "regular",
                "extractor": "instagram",
                "formats": [],
                "webpage_url": url,
            }
        else:
            try:
                await status.edit_text(
                    tr(lang, "unsupported"), parse_mode=constants.ParseMode.MARKDOWN
                )
            except TelegramError:
                pass
            return

    # ---- Playlist? ----
    entries = None
    if info.get("_type") in ("playlist", "multi_video"):
        entries = [e for e in (info.get("entries") or []) if e]
    if entries and len(entries) > 1:
        await _offer_playlist(context, url, info, entries, lang, status)
        return
    if info.get("_type") in ("playlist", "multi_video"):
        info = (entries or [None])[0] or info

    override_mb = database.get_size_limit_mb(user.id)
    limit = (
        (override_mb * 1024 * 1024)
        if override_mb
        else (config.PREMIUM_MAX_FILE_SIZE if premium else config.FREE_MAX_FILE_SIZE)
    )
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
    has_video = max_h > 0 or any(
        (f.get("vcodec") or "none") != "none" for f in formats
    )

    job_id = uuid.uuid4().hex[:10]
    context.user_data.setdefault("jobs", {})
    context.user_data["jobs"][job_id] = {"url": url, "info": info}

    available = ["best"]
    if max_h > 720:
        available.append("720")
    if max_h > 480:
        available.append("480")
    elif max_h > 360:
        available.append("360")
    available.append("audio")
    context.user_data["jobs"][job_id]["available"] = available
    context.user_data["jobs"][job_id]["has_video"] = has_video

    # Direct/single-format files (and instant search picks) skip the chooser.
    direct = len(formats) <= 1 or info.get("_type") == "url_transparent"
    if forced_key and forced_key in available:
        context.user_data["jobs"][job_id]["format"] = forced_key
        try:
            await status.edit_text(tr(lang, "downloading"))
        except TelegramError:
            pass
        await _run_format(update, context, job_id, forced_key, status, db_user)
        return
    if forced_key and not has_video:
        context.user_data["jobs"][job_id]["format"] = "audio"
        try:
            await status.edit_text(tr(lang, "downloading"))
        except TelegramError:
            pass
        await _run_format(update, context, job_id, "audio", status, db_user)
        return
    if direct:
        context.user_data["jobs"][job_id]["format"] = "best"
        try:
            await status.edit_text(tr(lang, "downloading"))
        except TelegramError:
            pass
        await _run_format(update, context, job_id, "best", status, db_user)
        return

    title = (info.get("title") or "Video").strip()
    if len(title) > 60:
        title = title[:60] + "…"
    # --- NSFW / Adult content filter (title check) ---
    if _is_adult_content(title, lang):
        try:
            await status.edit_text(
                "⛔ عفواً، لا يمكن تحميل هذا النوع من المحتوى."
            )
        except TelegramError:
            await update.effective_message.reply_text(
                "⛔ عفواً، لا يمكن تحميل هذا النوع من المحتوى."
            )
        return
    # ------------------------------------------------
    site = info.get("extractor_key") or info.get("extractor") or ""

    try:
        await status.edit_text(
            tr(lang, "choose_type", title=title, site=site),
            reply_markup=_media_type_keyboard(job_id, has_video, lang),
        )
    except TelegramError:
        pass


async def _upload_path(
    context, chat_id: int, lang: str, path: str, title: str,
    bot_username: str, premium: bool, duration: Any = None,
):
    """Uploads a downloaded file, choosing the right Telegram media type."""
    ext = path.lower()
    caption = _file_caption(
        lang, title, _quality_label("best", lang),
        max(1, os.path.getsize(path) // 1024 // 1024), bot_username, duration,
    )
    if ext.endswith((".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav", ".aac")):
        with open(path, "rb") as fh:
            return await context.bot.send_audio(
                chat_id=chat_id, audio=fh, title=title, caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN, filename=os.path.basename(path),
            )
    if ext.endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
        with open(path, "rb") as fh:
            return await context.bot.send_video(
                chat_id=chat_id, video=fh, caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN, supports_streaming=True,
            )
    with open(path, "rb") as fh:
        return await context.bot.send_document(
            chat_id=chat_id, document=fh, filename=os.path.basename(path),
            caption=caption, parse_mode=constants.ParseMode.MARKDOWN,
        )


async def _process_playlist_entry(
    context, job, lang, premium, bot_username, info,
    e, i, total, status, user,
):
    try:
        await status.edit_text(
            tr(lang, "pl_start", done=i - 1, total=total)
        )
    except TelegramError:
        pass

    def pcb(percent: float, text: str) -> None:
        if job.get("cancel"):
            raise downloader.DownloadCancelled()
        event_loop.call_soon_threadsafe(lambda t=text: _pl_edit(t))

    event_loop = asyncio.get_running_loop()

    def _pl_edit(text: str) -> None:
        try:
            context.application.create_task(
                status.edit_text(tr(lang, "pl_start", done=i - 1, total=total))
            )
        except TelegramError:
            pass

    try:
        path, title, err = await asyncio.to_thread(
            downloader.download,
            e.get("url"), "best", False, premium, pcb, allow_hls=premium,
        )
    except downloader.DownloadError:
        return False
    if err or not path:
        return False

    size = os.path.getsize(path)
    upload_limit = _upload_limit_for(user.id)
    too_big = size > upload_limit
    sent = None
    try:
        if not too_big:
            sent = await _upload_path(
                context, user.id, lang, path, title or e.get("title"),
                bot_username, premium, info.get("duration"),
            )
    except TelegramError as exc:
        log.warning("Playlist upload failed: %s", exc)
        sent = None
    finally:
        await asyncio.to_thread(_cleanup_file, path)

    if sent is None:
        return False

    if not premium:
        database.consume_download(user.id)
    database.stats_increment("files_processed")
    database.stats_increment("bytes_processed", size)
    await _log_download(context, user, e.get("url") or "", title or e.get("title") or "Video")
    if config.CACHE_ENABLED:
        kind = "video" if path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")) else "audio"
        file_id = getattr(getattr(sent, kind, None), "file_id", None)
        if file_id or getattr(sent, "document", None):
            file_id = file_id or getattr(sent.document, "file_id", None)
            kind = kind if file_id == getattr(getattr(sent, kind, None), "file_id", None) else "document"
        if file_id:
            database.cache_put(
                _url_hash(e.get("url")), file_id, kind, title or e.get("title"),
                None, "best", size, user.id,
            )
    try:
        await status.edit_text(
            tr(lang, "pl_item_done", i=i, total=total, title=title or e.get("title"))
        )
    except TelegramError:
        pass
    return True


async def _download_playlist(
    update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str,
    status, db_user,
) -> None:
    user = update.effective_user
    lang = lang_of(db_user)
    job = context.user_data.get("jobs", {}).get(job_id)
    if not job or not job.get("playlist"):
        try:
            await status.edit_text(tr(lang, "no_url"))
        except TelegramError:
            pass
        return

    premium = database.is_premium(user.id)
    entries = job["playlist"]
    bot_username = context.bot_data.get("bot_username", "")
    info = job.get("info") or {}
    max_h = 0
    formats = info.get("formats") or []
    if not formats:
        max_h = 0
    heights = sorted({f.get("height") for f in formats if f.get("height")}, reverse=True)
    max_h = heights[0] if heights else 0

    context.user_data["active_download"] = True
    context.user_data["active_download_since"] = time.time()

    async def _pos(_pos: int) -> None:
        pass

    slot = await download_queue.acquire(_pos)
    ok, failed = 0, 0
    try:
        for i, e in enumerate(entries, start=1):
            if job.get("cancel"):
                break
            try:
                ok_flag = await _process_playlist_entry(
                    context, job, lang, premium, bot_username, info,
                    e, i, len(entries), status, user,
                )
            except downloader.DownloadCancelled:
                break
            if ok_flag:
                ok += 1
            else:
                failed += 1
    finally:
        await slot.release()

    context.user_data["active_download"] = False
    context.user_data["jobs"].pop(job_id, None)
    try:
        await status.edit_text(tr(lang, "pl_finished", ok=ok, total=ok + failed))
    except TelegramError:
        pass


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    database.add_user(user.id, user.username or "", user.first_name or "")
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)

    if not await _force_guard(update, context, lang):
        return

    query = " ".join(context.args or [""]).strip()
    if not query:
        await update.effective_message.reply_text(tr(lang, "search_prompt"))
        return

    status = await update.effective_message.reply_text(tr(lang, "checking"))
    results, err = await asyncio.to_thread(
        downloader.search_youtube, query, config.SEARCH_RESULTS
    )
    if err or not results:
        try:
            await status.edit_text(
                tr(lang, "unsupported" if err else "search_none"),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass
        return

    token = uuid.uuid4().hex[:8]
    context.user_data["search"] = {"token": token, "results": results}
    rows = []
    for i, r in enumerate(results):
        title = (r.get("title") or f"Result {i + 1}").strip().replace("\n", " ")
        if len(title) > 45:
            title = title[:45] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🎬 {title}", callback_data=f"sch:{token}:{i}:video"
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    f"🎵 {title}", callback_data=f"sch:{token}:{i}:audio"
                )
            ]
        )
    try:
        await status.edit_text(
            tr(lang, "search_results", q=query),
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except TelegramError:
        pass


async def handle_trim_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    awaiting = context.user_data.get("awaiting_trim")
    if not awaiting:
        return
    db_user = database.get_user(user.id)
    lang = lang_of(db_user)
    if not await _force_guard(update, context, lang):
        return
    text = (update.effective_message.text or "").strip()
    m = TRIM_RE.match(text)
    if not m:
        await update.effective_message.reply_text(tr(lang, "trim_bad"))
        return
    start = _parse_ts(m.group(1))
    end = _parse_ts(m.group(2))
    if start is None or end is None or end <= start:
        await update.effective_message.reply_text(tr(lang, "trim_bad"))
        return

    job_id = awaiting.get("job_id")
    mode = awaiting.get("mode", "video")
    job = context.user_data.get("jobs", {}).get(job_id)
    if not job:
        context.user_data.pop("awaiting_trim", None)
        await update.effective_message.reply_text(tr(lang, "no_url"))
        return

    job["trim"] = (start, end)
    context.user_data.pop("awaiting_trim", None)

    if mode == "video":
        # Let the user pick the quality on the trim-prompt message.
        available = job.get("available") or ["best"]
        try:
            await awaiting["status"].edit_text(
                tr(lang, "choose_format",
                   title=(job.get("info") or {}).get("title") or "Video",
                   site=""),
                reply_markup=_format_options_keyboard(job_id, [k for k in available if k != "audio"], lang),
            )
        except TelegramError:
            pass
        return

    try:
        await awaiting["status"].edit_text(tr(lang, "downloading"))
    except TelegramError:
        pass
    await _run_format(update, context, job_id, "audio", awaiting["status"], db_user)


async def _send_media_file(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    path: str,
    title: str,
    caption: str,
    audio_only: bool,
):
    if audio_only:
        with open(path, "rb") as fh:
            return await context.bot.send_audio(
                chat_id=chat_id,
                audio=fh,
                title=title,
                caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN,
                filename=os.path.basename(path),
            )
    if path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
        with open(path, "rb") as fh:
            return await context.bot.send_video(
                chat_id=chat_id,
                video=fh,
                caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN,
                supports_streaming=True,
            )
    with open(path, "rb") as fh:
        return await context.bot.send_document(
            chat_id=chat_id,
            document=fh,
            filename=os.path.basename(path),
            caption=caption,
            parse_mode=constants.ParseMode.MARKDOWN,
        )


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
    context.user_data["active_download_since"] = time.time()
    job["cancel"] = False
    job["done"] = False
    chat_id = user.id
    message_id = status.message_id

    state = {"last_text": ""}

    # Capture the running asyncio loop so the worker thread can hand work back
    # to the event loop safely (Application.create_task needs a running loop in
    # the *current* thread, which the download thread does not have).
    event_loop = asyncio.get_running_loop()

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

    def _schedule_edit(text: str) -> None:
        # Runs on the event-loop thread (via call_soon_threadsafe), so
        # Application.create_task has a running loop available.
        if job.get("done") or text == state["last_text"]:
            return
        context.application.create_task(edit_progress(text))

    def progress_cb(percent: float, text: str) -> None:
        if job.get("cancel"):
            raise downloader.DownloadCancelled()
        event_loop.call_soon_threadsafe(_schedule_edit, text)

    bot_username = context.bot_data.get("bot_username", "")

    # A trimmed segment is cached under its own hash so a repeated identical
    # trim request can be forwarded instantly without re-downloading.
    trim = job.get("trim")
    if trim:
        url_hash = _url_hash(f"{url}#trim:{trim[0]}:{trim[1]}")
    else:
        url_hash = _url_hash(url)
    limit_bytes = _upload_limit_for(user.id)
    for kind in (_cache_kinds(opt) if config.CACHE_ENABLED else ()):
        entry = database.cache_get(url_hash, kind, format_key)
        if not entry or (entry.get("size_bytes") or 0) > limit_bytes:
            continue
        caption = _file_caption(
            lang,
            entry.get("title") or "Video",
            _quality_label(format_key, lang),
            max(1, (entry.get("size_bytes") or 0) // 1024 // 1024),
            bot_username,
            entry.get("duration"),
        )
        try:
            await _send_cached(
                context,
                chat_id=user.id,
                entry=entry,
                caption=caption,
                title=entry.get("title") or "Video",
                filename=_cache_filename(entry, entry.get("title") or "Video"),
            )
        except TelegramError:
            # Stale file_id — drop it and fall through to a real download.
            database.cache_delete(url_hash, kind, format_key)
            continue
        markup = _share_keyboard(lang, bot_username) if bot_username else None
        try:
            await status.edit_text(tr(lang, "cached"), reply_markup=markup)
        except TelegramError:
            pass
        database.stats_increment("files_processed")
        database.stats_increment("bytes_processed", int(entry.get("size_bytes") or 0))
        database.stats_increment("cache_hits")
        context.user_data["active_download"] = False
        context.user_data["jobs"].pop(job_id, None)
        return

    # ---- Queue: wait for a global slot, showing position updates ----
    async def queue_position_cb(pos: int) -> None:
        if job.get("done"):
            return
        text = tr(lang, "queued", pos=pos)
        if text == state["last_text"]:
            return
        state["last_text"] = text
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text
            )
        except TelegramError:
            pass

    async def _execute() -> None:
        try:
            try:
                await status.edit_text(tr(lang, "downloading"))
            except TelegramError:
                pass
            ctx_jobs = context.user_data.get("jobs") or {}
            if job_id in ctx_jobs:
                ctx_jobs[job_id]["format"] = format_key

            path, title, err = await asyncio.to_thread(
                downloader.download,
                url,
                opt.format_selector,
                opt.audio_only,
                premium,
                progress_cb,
                allow_hls=premium,
                trim=trim,
                size_limit=(
                    database.get_size_limit_mb(user.id) * 1024 * 1024
                    if database.get_size_limit_mb(user.id)
                    else None
                ),
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
            if downloader.is_instagram(url):
                await _log_event(
                    context,
                    f"❌ **فشل تحميل انستغرام**\n"
                    f"🔗 الرابط: `{url}`\n"
                    f"👤 المستخدم: `{user.id}`\n"
                    f"⚠️ السبب: {_md_escape(str(exc)[:200])}",
                )
            try:
                await status.edit_text(tr(lang, "download_error", error=str(exc)))
            except TelegramError:
                pass
            context.user_data["active_download"] = False
            return

        if err or not path:
            job["done"] = True
            if downloader.is_instagram(url):
                await _log_event(
                    context,
                    f"❌ **فشل تحميل انستغرام**\n"
                    f"🔗 الرابط: `{url}`\n"
                    f"👤 المستخدم: `{user.id}`\n"
                    f"⚠️ السبب: {_md_escape((err or 'Unknown error')[:200])}",
                )
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
        upload_limit = _upload_limit_for(user.id)
        if size > upload_limit:
            try:
                await status.edit_text(
                    tr(lang, "too_big", limit=upload_limit // 1024 // 1024),
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

        info = job.get("info") or {}
        caption = _file_caption(
            lang,
            title,
            _quality_label(format_key, lang),
            max(1, size // 1024 // 1024),
            bot_username,
            info.get("duration"),
        )

        try:
            sent = await _send_media_file(
                context, chat_id, path, title, caption, opt.audio_only
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

        # Remember the file_id so a duplicate URL/format can be sent instantly
        # from cache instead of re-downloading.
        kind = (
            "audio"
            if opt.audio_only
            else (
                "video"
                if path.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi"))
                else "document"
            )
        )
        file_id = getattr(getattr(sent, kind, None), "file_id", None)
        if config.CACHE_ENABLED and file_id:
            try:
                duration = int(float(info.get("duration") or 0)) or None
            except (TypeError, ValueError):
                duration = None
            database.cache_put(
                url_hash, file_id, kind, title or "Video",
                duration, format_key, size, chat_id,
            )
        database.stats_increment("files_processed")
        database.stats_increment("bytes_processed", size)
        database.consume_download(user.id)
        await _log_download(context, user, url, title or "Video")

        done_markup = None
        if not premium and not opt.audio_only:
            done_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(tr(lang, "subscribe_btn"), callback_data="menu:subscribe")]]
            )
        elif bot_username:
            done_markup = _share_keyboard(lang, bot_username)

        done_text = tr(lang, "done")
        if not premium:
            left = database.remaining_daily_downloads(user.id)
            if left >= 0:
                done_text += f"\n\n📅 باقي لك اليوم: {left}"
        try:
            await status.edit_text(done_text, reply_markup=done_markup)
        except TelegramError:
            pass

        context.user_data["active_download"] = False
        context.user_data["jobs"].pop(job_id, None)

    slot = None
    try:
        slot = await download_queue.acquire(queue_position_cb)
    except asyncio.CancelledError:
        context.user_data["active_download"] = False
        return
    try:
        await _execute()
    finally:
        await slot.release()


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
async def _navigate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: Optional[str], lang: str
) -> None:
    """Renders the right 'back' screen: return to a job's chooser or the main menu."""
    query = update.callback_query
    if job_id:
        job = context.user_data.get("jobs", {}).get(job_id)
        if job and job.get("playlist"):
            entries = job["playlist"]
            total = len(entries)
            if total > config.PLAYLIST_MAX_ITEMS:
                text = tr(lang, "pl_too_many", n=total)
                markup = _playlist_keyboard(job_id, total, lang)
            else:
                text = tr(lang, "choose_pl", title=(job.get("info") or {}).get("title") or "Playlist")
                markup = _playlist_keyboard(job_id, total, lang)
            try:
                await query.edit_message_text(
                    text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=markup
                )
            except TelegramError:
                pass
            return
        if job:
            info = job.get("info") or {}
            title = ((info.get("title") or "Video").strip())[:60]
            site = info.get("extractor_key") or info.get("extractor") or ""
            try:
                await query.edit_message_text(
                    tr(lang, "choose_type", title=title, site=site),
                    reply_markup=_media_type_keyboard(job_id, job.get("has_video", True), lang),
                )
            except TelegramError:
                pass
            return
    await _send_with_banner(
        context,
        update.effective_chat.id,
        tr(lang, "start"),
        _menu_keyboard(lang),
        edit_message_id=query.message.message_id,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = lang_of(db_user) if db_user else config.DEFAULT_LANGUAGE

    # Banned users cannot press any button.
    if user and not is_owner(user.id) and database.is_banned(user.id):
        try:
            await query.answer(tr(lang, "banned"), show_alert=True)
        except TelegramError:
            pass
        return

    # Strict middleware: only the force-sub verify button works while locked.
    if (
        config.FORCE_SUB_CHANNELS
        and user
        and not is_owner(user.id)
        and not query.data.startswith("force:")
    ):
        if await _missing_channels(context, user.id):
            try:
                await query.answer(tr(lang, "locked_toast"), show_alert=True)
            except TelegramError:
                pass
            return

    if query.data.startswith("lang:"):
        code = query.data.split(":", 1)[1]
        if code in ("ar", "en"):
            database.set_language(user.id, code)
        await query.answer()
        await _send_with_banner(
            context,
            user.id,
            tr(code, "start"),
            _menu_keyboard(code),
            edit_message_id=query.message.message_id,
        )
        return

    if query.data.startswith("menu:"):
        action = query.data.split(":", 1)[1]
        await query.answer()
        if action == "subscribe":
            await query.edit_message_text(
                tr(lang, "subscribe", price=config.PREMIUM_PRICE_IQD, number=config.ZAIN_CASH_NUMBER),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_back_keyboard(lang),
            )
        elif action == "help":
            await query.edit_message_text(
                tr(lang, "help"), parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_back_keyboard(lang),
            )
        elif action == "referral":
            bot_username = context.bot_data.get("bot_username", "")
            link = _referral_link(bot_username, user.id)
            current = database.get_user(user.id)
            quota = (current or {}).get("bonus_quota", 0)
            await query.edit_message_text(
                tr(lang, "referral_menu", link=link, count=database.count_referrals(user.id),
                   bonus=config.REFERRAL_BONUS_DOWNLOADS, quota=quota),
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=_back_keyboard(lang),
                disable_web_page_preview=True,
            )
        elif action.startswith("cat:"):
            cat = action.split(":", 1)[1]
            if cat == "download":
                await query.edit_message_text(
                    tr(lang, "download_hub_title"),
                    reply_markup=_download_sub_keyboard(lang),
                )
            elif cat == "student":
                await query.edit_message_text(
                    tr(lang, "student_hub_title"),
                    reply_markup=_student_sub_keyboard(lang),
                )
            elif cat == "media":
                await query.edit_message_text(
                    tr(lang, "media_hub_title"),
                    reply_markup=_media_sub_keyboard(lang),
                )
            elif cat == "games":
                await query.edit_message_text(
                    tr(lang, "games_hub_title"),
                    reply_markup=_games_sub_keyboard(lang),
                )
            elif cat == "profile":
                await query.edit_message_text(
                    tr(lang, "profile_hub_title"),
                    reply_markup=_profile_sub_keyboard(lang),
                )
        return

    if query.data.startswith("nav:"):
        await query.answer()
        target = query.data.split(":", 1)[1]
        if target == "main":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "start"),
                _category_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        elif target == "downloader":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "download_hub_title"),
                _download_sub_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        elif target == "student":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "student_hub_title"),
                _student_sub_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        elif target == "media":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "media_hub_title"),
                _media_sub_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        elif target == "games":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "games_hub_title"),
                _games_sub_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        elif target == "profile":
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "profile_hub_title"),
                _profile_sub_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        else:
            # fallback to main menu for unknown targets
            await _send_with_banner(
                context,
                update.effective_chat.id,
                tr(lang, "start"),
                _category_keyboard(lang),
                edit_message_id=query.message.message_id,
            )
        return

    if query.data.startswith("tp:"):
        await query.answer()
        _, job_id, action = query.data.split(":", 2)
        job = context.user_data.get("jobs", {}).get(job_id)
        if not job:
            try:
                await query.edit_message_text(tr(lang, "no_url"))
            except TelegramError:
                pass
            return
        if action == "video":
            info = job.get("info") or {}
            title = ((info.get("title") or "Video").strip())[:60]
            site = info.get("extractor_key") or info.get("extractor") or ""
            available = [k for k in (job.get("available") or ["best"]) if k != "audio"]
            try:
                await query.edit_message_text(
                    tr(lang, "choose_format", title=title, site=site),
                    reply_markup=_format_options_keyboard(job_id, available or ["best"], lang),
                )
            except TelegramError:
                pass
            return
        if action == "audio":
            try:
                await query.edit_message_text(tr(lang, "downloading"))
            except TelegramError:
                pass
            await _run_format(update, context, job_id, "audio", query.message, db_user)
            return
        if action == "back":
            await _navigate(update, context, job_id, lang)
            return
        return

    if query.data.startswith("trim:"):
        await query.answer()
        _, job_id, mode = query.data.split(":", 2)
        if job_id not in (context.user_data.get("jobs") or {}):
            try:
                await query.edit_message_text(tr(lang, "no_url"))
            except TelegramError:
                pass
            return
        context.user_data["awaiting_trim"] = {"job_id": job_id, "mode": mode, "status": query.message}
        try:
            await query.edit_message_text(tr(lang, "trim_prompt"))
        except TelegramError:
            pass
        return

    if query.data.startswith("pl:"):
        await query.answer()
        parts = query.data.split(":")
        job_id = parts[1]
        action = parts[2]
        job = context.user_data.get("jobs", {}).get(job_id)
        if not job or not job.get("playlist"):
            try:
                await query.edit_message_text(tr(lang, "no_url"))
            except TelegramError:
                pass
            return
        if action == "all":
            await _download_playlist(update, context, job_id, query.message, db_user)
            return
        if action == "pick":
            pl_title = (job.get("info") or {}).get("title") or "Playlist"
            try:
                await query.edit_message_text(
                    tr(lang, "pl_pick_title", title=pl_title),
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=_playlist_pick_keyboard(job_id, job["playlist"], lang),
                )
            except TelegramError:
                pass
            return
        if action == "item":
            index = int(parts[3])
            entry = next((e for e in job["playlist"] if e.get("index") == index), None)
            if not entry or not entry.get("url"):
                return
            await _process_link(update, context, entry["url"], db_user, lang, status=query.message)
            return
        return

    if query.data.startswith("sch:"):
        await query.answer()
        parts = query.data.split(":")
        if len(parts) < 4:
            return
        token, idx, kind = parts[1], int(parts[2]), parts[3]
        data = context.user_data.get("search") or {}
        results = data.get("results") or []
        if data.get("token") != token or idx >= len(results) or not results[idx].get("url"):
            return
        context.user_data.pop("search", None)
        forced = "audio" if kind == "audio" else "best"
        await _process_link(
            update, context, results[idx]["url"], db_user, lang,
            status=query.message, forced_key=forced,
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

    if query.data.startswith("force:"):
        if not user:
            return
        missing = await _missing_channels(context, user.id)
        if missing:
            # Toast popup naming exactly which channels are still missing.
            try:
                await query.answer(
                    tr(lang, "still_need", channels=", ".join(missing)),
                    show_alert=True,
                )
            except TelegramError:
                pass
            return
        try:
            await query.answer()
        except TelegramError:
            pass

        first_time = not database.is_force_verified(user.id)
        if first_time:
            database.mark_force_verified(user.id)
            database.grant_bonus_quota(user.id, config.FORCE_SUB_BONUS_CREDITS)
            log.info("Force-sub verified: %s (+%d credits)", user.id, config.FORCE_SUB_BONUS_CREDITS)
            await _log_event(
                context, _admin_new_user_text(user, "اشتراك بالقناة")
            )

        # Animated unlock transition: 🔒 -> 🔓 -> welcome menu.
        try:
            await query.edit_message_text(f"🔓 {tr(lang, 'unlock_open')}")
        except TelegramError:
            pass
        await asyncio.sleep(0.9)
        bonus_note = (
            tr(lang, "bonus_added", n=config.FORCE_SUB_BONUS_CREDITS)
            if first_time
            else ""
        )
        welcome = tr(lang, "force_welcome")
        if bonus_note:
            welcome += "\n\n" + bonus_note
        await _send_with_banner(
            context,
            user.id,
            welcome,
            _menu_keyboard(lang),
            edit_message_id=query.message.message_id,
        )
        return

    if query.data.startswith("fmt:"):
        await query.answer()
        if _clear_stuck_active(context):
            try:
                await query.edit_message_text(tr(lang, "stuck_cleared"))
            except TelegramError:
                pass
        _, job_id, key = query.data.split(":", 2)
        if key == "cancel":
            jobs = context.user_data.get("jobs", {})
            job = jobs.get(job_id)
            if job:
                job["cancel"] = True
                job["done"] = True
            context.user_data["active_download"] = False
            context.user_data.pop("jobs", None)
            try:
                await query.edit_message_text(tr(lang, "cancel"))
            except TelegramError:
                pass
            return
        try:
            status = query.message
            await _run_format(update, context, job_id, key, status, db_user)
        except KeyError:
            pass
        return


# ---------------------------------------------------------------------------
# Start screen profile (run once on startup)
# ---------------------------------------------------------------------------
async def _set_bot_profile_photo() -> Tuple[bool, str]:
    """Attempts to register the welcome banner as the bot's profile / intro
    picture via the raw setMyPhoto endpoint (PTB 21.x has no helper).

    Note: as of Bot API 9.x there is no official setMyPhoto method — the
    profile picture can only be changed through @BotFather (/setuserpic).
    We still probe the Local Bot API server and the Cloud API so the banner
    is picked up automatically if Telegram ever exposes the method."""
    kind, source = _banner_media()
    if kind is None:
        return False, "no banner configured (WELCOME_BANNER_URL / WELCOME_BANNER_PATH)"
    upload = source
    try:
        if kind == "url":
            tmp = os.path.join(tempfile.gettempdir(), "turbodl_profile_photo.png")
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                resp = await client.get(source)
                resp.raise_for_status()
            with open(tmp, "wb") as fh:
                fh.write(resp.content)
            upload = tmp
        bases = [
            base for base in (config.TELEGRAM_LOCAL_API_URL, "https://api.telegram.org")
            if base
        ]
        last_err = "no API base to try"
        for base in bases:
            base = base.rstrip("/")
            url = f"{base}/bot{config.BOT_TOKEN}/setMyPhoto"
            with open(upload, "rb") as fh:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        url, files={"photo": ("profile.png", fh, "image/png")}
                    )
                    data = resp.json()
            if data.get("ok"):
                return True, f"{base} ({upload})"
            last_err = (
                data.get("description")
                or data.get("error_code")
                or str(resp.status_code)
            )
        return False, last_err
    except Exception as exc:  # network / file errors must never block startup
        return False, str(exc)


async def configure_start_screen(app: Application) -> None:
    """Sets the bot's start-screen / profile description texts and picture.

    Runs from post_init on every startup: setMyShortDescription and
    setMyDescription for ar/en/the default language, then setMyPhoto with the
    welcome banner. Failures are logged and never block polling."""
    bot = app.bot
    if not config.BOT_PROFILE_SETUP:
        log.info("Start-screen profile setup skipped (BOT_PROFILE_SETUP=false)")
        return

    setups = [
        ("ar", config.BOT_SHORT_DESCRIPTION_AR, config.BOT_DESCRIPTION_AR),
        ("en", config.BOT_SHORT_DESCRIPTION_EN, config.BOT_DESCRIPTION_EN),
        (None, config.BOT_SHORT_DESCRIPTION_EN, config.BOT_DESCRIPTION_EN),
    ]
    ok_short = ok_desc = 0
    for code, short, desc in setups:
        if short:
            try:
                await bot.set_my_short_description(
                    short_description=short, language_code=code
                )
                ok_short += 1
            except TelegramError as exc:
                log.error("setMyShortDescription(%s) failed: %s", code, exc)
        if desc:
            try:
                await bot.set_my_description(description=desc, language_code=code)
                ok_desc += 1
            except TelegramError as exc:
                log.error("setMyDescription(%s) failed: %s", code, exc)

    log.info(
        "Start-screen description updated: short=%d/3 full=%d/3",
        ok_short, ok_desc,
    )
    if ok_short + ok_desc == 0:
        log.warning(
            "Could not update the bot description. Use BotFather (/setdescription, "
            "/setshortdescription) until the API path is fixed."
        )
    else:
        # Read the values back so the log confirms what Telegram actually shows.
        try:
            sd = await bot.get_my_short_description()
            d = await bot.get_my_description()
            log.info(
                "Verified start screen: short=%r full=%r",
                (sd.short_description or "")[:60],
                (d.description or "")[:60],
            )
        except TelegramError as exc:
            log.warning("Could not read back the description for verification: %s", exc)

    photo_ok, note = await _set_bot_profile_photo()
    if photo_ok:
        log.info("Start-screen profile picture set from %s", note)
    else:
        log.warning(
            "Profile picture not set via API (%s). The Bot API has no setMyPhoto "
            "method yet — set it once with @BotFather /setuserpic using banner.png.",
            note,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _start_health_server() -> None:
    """Bind a tiny HTTP health endpoint when PORT is set.

    Platforms like Koyeb route/health-check web services over HTTP, so a
    long-polling bot must still listen on $PORT. No-op locally.
    """
    try:
        port = int(os.environ.get("PORT", "0") or 0)
    except ValueError:
        port = 0
    if not port:
        return

    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"TurboDL OK")

        def log_message(self, *_args) -> None:
            pass

    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(
        target=server.serve_forever, name="health-server", daemon=True
    ).start()
    log.info("Health server listening on 0.0.0.0:%s", port)


def main() -> None:
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
        raise SystemExit(1)

    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    database.init_db()
    database.cache_prune()
    database.stats_set("started_at", int(time.time()))

    builder = Application.builder().token(config.BOT_TOKEN)

    if config.TELEGRAM_LOCAL_API_URL:
        # python-telegram-bot appends the token directly after base_url
        # (default "https://api.telegram.org/bot"), so the local base must
        # end with "/bot" to yield ".../bot<token>/method".
        local_url = config.TELEGRAM_LOCAL_API_URL
        if not local_url.endswith("/bot"):
            local_url = local_url + "/bot"
        builder = builder.base_url(local_url)
        log.info(
            "Using Telegram Local Bot API server at %s (2 GB uploads enabled)",
            config.TELEGRAM_LOCAL_API_URL,
        )

    app = builder.read_timeout(120).write_timeout(120).connect_timeout(30).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("revoke", revoke_user))
    app.add_handler(CommandHandler("setexpiry", set_expiry))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("setlimit", set_limit_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm:"))
    app.add_handler(
        CallbackQueryHandler(
            callback_handler, pattern=r"^(lang|menu|sub|pay|fmt|nav|tp|trim|pl|sch|force):"
        )
    )
    app.add_handler(MessageHandler(filters.PHOTO, receive_payment_photo))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Entity("url"),
            handle_trim_input,
        )
    )
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
        await configure_start_screen(app_ref)
        # Startup safety check: probe the log channel and announce uptime.
        await verify_log_channel(app_ref.bot)

    app.post_init = cache_username
    app.add_error_handler(log_error_handler)

    async def prune_cache(_ctx) -> None:
        database.cache_prune()

    if app.job_queue:
        app.job_queue.run_repeating(prune_cache, interval=6 * 60 * 60, first=60 * 60)

    log.info("TurboDL started")
    _start_health_server()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()