# Games & Loyalty Hub State Handlers and Utilities
import datetime
import logging
import sqlite3
import time
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

import config
import database

log = logging.getLogger("turbodl.games")


def _t(lang: str, ar: str, en: str) -> str:
    return en if lang == "en" else ar


# ============================================================
# Question Bank (Bilingual)
# ============================================================

QUESTION_BANK = [
    {
        "q": "ما هي أكبر شبكة مشاركة فيديوهات في العالم؟",
        "q_en": "What is the largest video sharing platform in the world?",
        "options": ["يوتيوب", "تيك توك", "فيسبوك", "إنستغرام"],
        "options_en": ["YouTube", "TikTok", "Facebook", "Instagram"],
        "answer": 0,
    },
    {
        "q": "ما هي لغة البرمجة الأكثر استخداماً في مشاريع الذكاء الاصطناعي؟",
        "q_en": "Which programming language is most used in AI development?",
        "options": ["Java", "C++", "Python", "PHP"],
        "options_en": ["Java", "C++", "Python", "PHP"],
        "answer": 2,
    },
    {
        "q": "كم بت (Bit) يوجد في البايت الواحد (Byte)؟",
        "q_en": "How many bits are in one Byte?",
        "options": ["4", "8", "16", "32"],
        "options_en": ["4", "8", "16", "32"],
        "answer": 1,
    },
    {
        "q": "أي من هذه المنصات تختص بمقاطع الفيديو القصيرة العمودية فقط في بدايتها؟",
        "q_en": "Which platform originally focused strictly on short vertical videos?",
        "options": ["YouTube", "TikTok", "Vimeo", "Dailymotion"],
        "options_en": ["YouTube", "TikTok", "Vimeo", "Dailymotion"],
        "answer": 1,
    },
    {
        "q": "ما هو الامتداد القياسي للملفات الصوتية المضغوطة الأكثر شيوعاً؟",
        "q_en": "What is the most common standard compressed audio format?",
        "options": ["MP3", "WAV", "FLAC", "MIDI"],
        "options_en": ["MP3", "WAV", "FLAC", "MIDI"],
        "answer": 0,
    },
    {
        "q": "ماذا تعني أداة OCR في معالجة المستندات والصور؟",
        "q_en": "What does OCR stand for in document processing?",
        "options": [
            "التعرف البصري على الحروف",
            "ضغط الصور الرقمية",
            "تحرير الفيديو المتقدم",
            "تشفير البيانات"
        ],
        "options_en": [
            "Optical Character Recognition",
            "Online Compression Ratio",
            "Open Code Reader",
            "Optimal Color Rendering"
        ],
        "answer": 0,
    },
    {
        "q": "ما هو الحد الأقصى لحجم الملف المجاني في بوت TurboDL؟",
        "q_en": "What is the maximum free file size limit in TurboDL Bot?",
        "options": ["20 MB", "50 MB", "100 MB", "2 GB"],
        "options_en": ["20 MB", "50 MB", "100 MB", "2 GB"],
        "answer": 1,
    },
]


def _init_games_db():
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games_points (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    points INTEGER DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    last_quiz TEXT
                )
                """
            )
        conn.close()
    except Exception as e:
        log.warning("Games DB init warning: %s", e)


_init_games_db()


def _get_user_points_data(user_id: int) -> Dict[str, any]:
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM games_points WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception:
        pass
    return {"user_id": user_id, "username": "", "points": 0, "streak": 0, "last_quiz": ""}


def _update_user_quiz(user_id: int, username: str, pts_delta: int, today_str: str) -> None:
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        with conn:
            conn.execute(
                """
                INSERT INTO games_points (user_id, username, points, streak, last_quiz)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    points = points + excluded.points,
                    streak = streak + 1,
                    last_quiz = excluded.last_quiz
                """,
                (user_id, username or "-", pts_delta, today_str)
            )
        conn.close()
    except Exception as e:
        log.error("Failed to update quiz score: %s", e)


def _get_leaderboard(limit: int = 10) -> List[Dict[str, any]]:
    try:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, points FROM games_points ORDER BY points DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ============================================================
# 1. Daily Quiz System
# ============================================================

async def quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the daily quiz question."""
    query = update.callback_query
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    today_str = database.today()
    user_data = _get_user_points_data(user.id)

    if user_data.get("last_quiz") == today_str:
        text = _t(
            lang,
            f"✅ لقد أجبت على اختبار اليوم مسبقاً!\n🏆 نقاطك الحالية: `{user_data.get('points', 0)}` نقطة.\nعد غداً لاختبار جديد.",
            f"✅ You already completed today's quiz!\n🏆 Your current score: `{user_data.get('points', 0)}` points.\nCome back tomorrow!"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(_t(lang, "🏆 لوحة الصدارة", "🏆 Leaderboard"), callback_data="games:top")],
                [InlineKeyboardButton(_t(lang, "⬅️ القائمة الرئيسية", "⬅️ Main Menu"), callback_data="nav:main")],
            ]
        )
        if query:
            await query.answer()
            await query.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)
        return

    # Seed daily question by date
    day_idx = (datetime.date.today().toordinal()) % len(QUESTION_BANK)
    q_data = QUESTION_BANK[day_idx]

    q_text = q_data["q_en"] if lang == "en" else q_data["q"]
    options = q_data["options_en"] if lang == "en" else q_data["options"]

    buttons = []
    for i, opt in enumerate(options):
        buttons.append([InlineKeyboardButton(opt, callback_data=f"gq:{day_idx}:{i}")])
    buttons.append([InlineKeyboardButton(_t(lang, "⬅️ رجوع", "⬅️ Back"), callback_data="nav:games")])

    msg_text = (
        f"📝 *{_t(lang, 'اختبار اليوم السريع', 'Daily Quick Quiz')}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❓ {q_text}\n\n"
        f"💡 {_t(lang, 'اختر الإجابة الصحيحة واكسب 10 نقاط!', 'Choose the right answer to win 10 points!')}"
    )

    if query:
        await query.answer()
        await query.edit_message_text(msg_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(msg_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process user's selected quiz answer."""
    query = update.callback_query
    if not query or not query.data:
        return
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    q_idx = int(parts[1])
    ans_idx = int(parts[2])

    today_str = database.today()
    q_data = QUESTION_BANK[q_idx % len(QUESTION_BANK)]
    correct_idx = q_data["answer"]

    is_correct = (ans_idx == correct_idx)
    pts = 10 if is_correct else 0

    _update_user_quiz(user.id, user.username or user.first_name, pts, today_str)
    cur_data = _get_user_points_data(user.id)

    if is_correct:
        res_text = _t(
            lang,
            f"🎉 *إجابة صحيحة!*\nحصلت على +10 نقاط.\n🏆 رصيدك الآن: `{cur_data.get('points', 0)}` نقطة.",
            f"🎉 *Correct answer!*\nYou earned +10 points.\n🏆 Total points: `{cur_data.get('points', 0)}`."
        )
    else:
        correct_ans_txt = q_data["options_en"][correct_idx] if lang == "en" else q_data["options"][correct_idx]
        res_text = _t(
            lang,
            f"❌ *إجابة خاطئة!*\nالإجابة الصحيحة هي: `{correct_ans_txt}`.\n🏆 رصيدك الآن: `{cur_data.get('points', 0)}` نقطة.",
            f"❌ *Wrong answer!*\nThe correct answer was: `{correct_ans_txt}`.\n🏆 Total points: `{cur_data.get('points', 0)}`."
        )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, "🏆 لوحة الصدارة", "🏆 Leaderboard"), callback_data="games:top")],
            [InlineKeyboardButton(_t(lang, "⬅️ القائمة الرئيسية", "⬅️ Main Menu"), callback_data="nav:main")],
        ]
    )
    await query.answer()
    await query.edit_message_text(res_text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)


# ============================================================
# 2. Leaderboard
# ============================================================

async def leaderboard_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display top users by quiz score."""
    query = update.callback_query
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    top = _get_leaderboard(10)
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    lines = []
    if not top:
        lines.append(_t(lang, "لا توجد نقاط مسجلة بعد. كن أول من يشارك!", "No scores yet. Be the first to play!"))
    else:
        for i, row in enumerate(top):
            medal = medals[i] if i < len(medals) else "👤"
            name = row.get("username") or f"User_{row.get('user_id')}"
            pts = row.get("points", 0)
            lines.append(f"{medal} *{name}* — `{pts}` {_t(lang, 'نقطة', 'pts')}")

    header = _t(lang, "🏆 *لوحة صدارة الألعاب والاختبارات:*\n━━━━━━━━━━━━━━━━━━\n", "🏆 *Quiz Leaderboard:*\n━━━━━━━━━━━━━━━━━━\n")
    body = "\n".join(lines)
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, "📝 ابدأ الاختبار", "📝 Start Quiz"), callback_data="games:quiz")],
            [InlineKeyboardButton(_t(lang, "⬅️ القائمة الرئيسية", "⬅️ Main Menu"), callback_data="nav:main")],
        ]
    )

    if query:
        await query.answer()
        await query.edit_message_text(header + body, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await update.effective_message.reply_text(header + body, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb)


# ============================================================
# 3. User Referral System
# ============================================================

async def referral_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user's invitation link and referral stats."""
    query = update.callback_query
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    bot_uname = context.bot_data.get("bot_username", "TurboDL_Iraq_bot")
    ref_link = f"https://t.me/{bot_uname}?start=ref_{user.id}"
    ref_count = database.count_referrals(user.id)
    bonus_quota = (db_user or {}).get("bonus_quota", 0)

    text = _t(
        lang,
        f"🎁 *نظام دعوة الأصدقاء (الإحالة)*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 رابط الدعوة الخاص بك:\n`{ref_link}`\n\n"
        f"👥 عدد الإحالات الناجحة: `{ref_count}`\n"
        f"⚡ رصيد التحميل الإضافي: `{bonus_quota}` ملف\n\n"
        f"💡 كل صديق ينضم عبر رابطك يمنحك +{config.REFERRAL_BONUS_DOWNLOADS} تحميلات مجانية فوراً!",
        f"🎁 *Referral Program*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 Your referral link:\n`{ref_link}`\n\n"
        f"👥 Successful referrals: `{ref_count}`\n"
        f"⚡ Bonus download quota: `{bonus_quota}` files\n\n"
        f"💡 Every invited friend grants you +{config.REFERRAL_BONUS_DOWNLOADS} free downloads instantly!"
    )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, "📤 مشاركة الرابط", "📤 Share Link"), url=f"https://t.me/share/url?url={ref_link}&text=TurboDL%20Bot")],
            [InlineKeyboardButton(_t(lang, "⬅️ القائمة الرئيسية", "⬅️ Main Menu"), callback_data="nav:main")],
        ]
    )

    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
    else:
        await update.effective_message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)


# Backward compatibility wrappers
async def quiz_handler(update, context):
    await quiz_start(update, context)

async def referral_handler(update, context):
    await referral_show(update, context)
