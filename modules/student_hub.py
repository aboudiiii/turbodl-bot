# Student & AI Hub State Handlers and Utilities
import asyncio
import io
import logging
import os
import time
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

import config
import database

log = logging.getLogger("turbodl.student")


def _t(lang: str, ar: str, en: str) -> str:
    return en if lang == "en" else ar


def _get_gemini():
    """Lazy initialize Gemini GenerativeModel if api key is configured."""
    if not getattr(config, "GEMINI_API_KEY", ""):
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        model_name = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
        return genai.GenerativeModel(model_name)
    except Exception as e:
        log.warning("Failed to initialize Gemini: %s", e)
        return None


async def _download_file(msg, context: ContextTypes.DEFAULT_TYPE, prefix: str, ext: str) -> Optional[str]:
    """Helper to download photo/document/voice/audio to DOWNLOAD_DIR safely."""
    try:
        tg_file_obj = None
        if msg.photo:
            tg_file_obj = msg.photo[-1]
        elif msg.document:
            tg_file_obj = msg.document
        elif msg.voice:
            tg_file_obj = msg.voice
        elif msg.audio:
            tg_file_obj = msg.audio
        
        if not tg_file_obj:
            return None

        file_obj = await tg_file_obj.get_file()
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        out_path = os.path.join(config.DOWNLOAD_DIR, f"{prefix}_{int(time.time() * 1000)}{ext}")
        await file_obj.download_to_drive(out_path)
        return out_path
    except Exception as e:
        log.error("Download failed in student hub: %s", e)
        return None


# ============================================================
# 1. OCR Text Extraction (pytesseract + Gemini Vision fallback)
# ============================================================

async def ocr_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Extract text from an uploaded image using pytesseract or Gemini Vision fallback."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_ocr_image", None)

    status_msg = await update.effective_message.reply_text(
        _t(lang, "🔍 جاري استخراج النص من الصورة...", "🔍 Extracting text from image...")
    )

    img_path = await _download_file(update.message, context, f"ocr_{user.id}", ".jpg")
    if not img_path:
        await status_msg.edit_text(_t(lang, "❌ فشل تحميل الصورة.", "❌ Failed to download image."))
        return

    extracted_text = ""
    # Try pytesseract first
    try:
        import pytesseract
        from PIL import Image
        loop = asyncio.get_running_loop()
        def _run_tesseract():
            img = Image.open(img_path)
            return pytesseract.image_to_string(img, lang="ara+eng")
        extracted_text = await loop.run_in_executor(None, _run_tesseract)
    except Exception as e:
        log.info("pytesseract OCR error/unavailable: %s", e)

    # If tesseract gave little or no text, try Gemini Vision fallback
    if len(extracted_text.strip()) < 15:
        gemini = _get_gemini()
        if gemini:
            try:
                from PIL import Image
                img = Image.open(img_path)
                loop = asyncio.get_running_loop()
                def _run_gemini_ocr():
                    prompt = "Extract all readable text from this image faithfully. If Arabic, preserve Arabic. Output only the extracted text."
                    res = gemini.generate_content([prompt, img])
                    return res.text if res else ""
                ai_text = await loop.run_in_executor(None, _run_gemini_ocr)
                if ai_text and len(ai_text.strip()) > len(extracted_text.strip()):
                    extracted_text = ai_text
            except Exception as e:
                log.warning("Gemini Vision OCR failed: %s", e)

    try:
        if os.path.exists(img_path):
            os.remove(img_path)
    except Exception:
        pass

    extracted_text = extracted_text.strip()
    if not extracted_text:
        await status_msg.edit_text(
            _t(lang, "⚠️ لم يتم العثور على نص واضح في الصورة.", "⚠️ No readable text found in the image.")
        )
        return

    if len(extracted_text) <= 3800:
        header = _t(lang, "📝 *النص المستخرج:*\n\n", "📝 *Extracted Text:*\n\n")
        await status_msg.edit_text(header + extracted_text, parse_mode=constants.ParseMode.MARKDOWN)
    else:
        bio = io.BytesIO(extracted_text.encode("utf-8"))
        bio.name = f"extracted_ocr_{int(time.time())}.txt"
        await update.effective_message.reply_document(
            document=bio,
            caption=_t(lang, "📝 تم استخراج النص في ملف مرفق.", "📝 Extracted text attached as a file.")
        )
        await status_msg.delete()


# ============================================================
# 2. PDF Utilities: Images to PDF & Merge PDFs
# ============================================================

async def pdf_image_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect images for Image-to-PDF conversion."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    images = context.user_data.setdefault("pdf_images", [])
    img_path = await _download_file(update.message, context, f"pdfimg_{user.id}", ".jpg")
    if img_path:
        images.append(img_path)

    count = len(images)
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, f"📄 إنشاء PDF ({count} صور)", f"📄 Build PDF ({count} images)"), callback_data="student:pdffinish")],
            [InlineKeyboardButton(_t(lang, "❌ إلغاء", "❌ Cancel"), callback_data="nav:main")],
        ]
    )
    await update.effective_message.reply_text(
        _t(
            lang,
            f"📸 تم استلام الصورة رقم {count}!\nأرسل المزيد من الصور أو اضغط زر الإنشاء عند الانتهاء.",
            f"📸 Image #{count} received!\nSend more images or tap 'Build PDF' when ready."
        ),
        reply_markup=kb
    )


async def pdf_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert all collected images into a single PDF document."""
    query = update.callback_query
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_pdf_images", None)
    images = context.user_data.pop("pdf_images", [])

    if not images:
        if query:
            await query.answer(_t(lang, "⚠️ لا توجد صور محددة.", "⚠️ No images collected."), show_alert=True)
        return

    if query:
        await query.answer()
        await query.edit_message_text(_t(lang, "⏳ جاري تجميع الصور وإنشاء ملف PDF...", "⏳ Building PDF file..."))

    pdf_out = os.path.join(config.DOWNLOAD_DIR, f"doc_{user.id}_{int(time.time())}.pdf")

    loop = asyncio.get_running_loop()
    def _create_pdf():
        from PIL import Image
        pil_images = []
        for path in images:
            try:
                im = Image.open(path).convert("RGB")
                pil_images.append(im)
            except Exception:
                pass
        if not pil_images:
            return False
        pil_images[0].save(pdf_out, save_all=True, append_images=pil_images[1:])
        return True

    success = await loop.run_in_executor(None, _create_pdf)

    # Cleanup temp images
    for p in images:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    if success and os.path.exists(pdf_out):
        with open(pdf_out, "rb") as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename=f"TurboDL_Document_{int(time.time())}.pdf",
                caption=_t(lang, "✅ تم إنشاء ملف PDF بنجاح!", "✅ PDF document created successfully!")
            )
        try:
            os.remove(pdf_out)
        except Exception:
            pass
    else:
        await context.bot.send_message(
            chat_id=user.id,
            text=_t(lang, "❌ فشل إنشاء ملف PDF.", "❌ Failed to create PDF.")
        )


async def merge_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect PDF files to merge."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE

    doc = update.message.document
    if not doc or not (doc.file_name or "").lower().endswith(".pdf"):
        await update.effective_message.reply_text(
            _t(lang, "⚠️ يرجى إرسال ملف بصيغة PDF فقط.", "⚠️ Please send a PDF file only.")
        )
        return

    merges = context.user_data.setdefault("merge_pdfs", [])
    pdf_path = await _download_file(update.message, context, f"merge_{user.id}", ".pdf")
    if pdf_path:
        merges.append(pdf_path)

    count = len(merges)
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(lang, f"📑 دمج الملفات ({count} ملفات)", f"📑 Merge ({count} files)"), callback_data="student:mergefinish")],
            [InlineKeyboardButton(_t(lang, "❌ إلغاء", "❌ Cancel"), callback_data="nav:main")],
        ]
    )
    await update.effective_message.reply_text(
        _t(
            lang,
            f"📥 تم استلام ملف PDF رقم {count}!\nأرسل ملفات أخرى أو اضغط زر الدمج.",
            f"📥 PDF #{count} received!\nSend more PDFs or tap 'Merge'."
        ),
        reply_markup=kb
    )


async def merge_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Merge all collected PDF documents into one."""
    query = update.callback_query
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_merge_pdfs", None)
    files = context.user_data.pop("merge_pdfs", [])

    if len(files) < 2:
        if query:
            await query.answer(_t(lang, "⚠️ يلزم إرسال ملفين PDF على الأقل للدمج.", "⚠️ Send at least 2 PDF files to merge."), show_alert=True)
        return

    if query:
        await query.answer()
        await query.edit_message_text(_t(lang, "⏳ جاري دمج ملفات PDF...", "⏳ Merging PDF files..."))

    out_merged = os.path.join(config.DOWNLOAD_DIR, f"merged_{user.id}_{int(time.time())}.pdf")

    loop = asyncio.get_running_loop()
    def _run_merge():
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for p in files:
                writer.append(p)
            writer.write(out_merged)
            writer.close()
            return True
        except Exception as e:
            log.error("PDF merge failed: %s", e)
            return False

    success = await loop.run_in_executor(None, _run_merge)

    for p in files:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    if success and os.path.exists(out_merged):
        with open(out_merged, "rb") as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename=f"TurboDL_Merged_{int(time.time())}.pdf",
                caption=_t(lang, "✅ تم دمج ملفات PDF بنجاح!", "✅ PDFs merged successfully!")
            )
        try:
            os.remove(out_merged)
        except Exception:
            pass
    else:
        await context.bot.send_message(
            chat_id=user.id,
            text=_t(lang, "❌ فشل دمج ملفات PDF.", "❌ Failed to merge PDFs.")
        )


# ============================================================
# 3. Gemini AI Text & Document Summarizer
# ============================================================

async def summary_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Summarize text or document using Gemini AI."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_summary_text", None)

    raw_text = ""
    doc = update.message.document
    if doc:
        status = await update.effective_message.reply_text(_t(lang, "⏳ جاري قراءة الملف وتلخيصه...", "⏳ Reading file..."))
        doc_path = await _download_file(update.message, context, f"sum_{user.id}", os.path.splitext(doc.file_name or "")[1] or ".txt")
        if doc_path:
            if doc_path.lower().endswith(".pdf"):
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(doc_path)
                    for page in reader.pages[:20]:  # Up to 20 pages
                        raw_text += (page.extract_text() or "") + "\n"
                except Exception as e:
                    log.warning("PDF extraction failed: %s", e)
            else:
                try:
                    with open(doc_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read(50000)
                except Exception:
                    pass
            try:
                os.remove(doc_path)
            except Exception:
                pass
    else:
        raw_text = update.message.text or ""
        status = await update.effective_message.reply_text(_t(lang, "🤖 جاري تلخيص النص بالذكاء الاصطناعي...", "🤖 Generating summary with AI..."))

    raw_text = raw_text.strip()
    if not raw_text:
        await status.edit_text(_t(lang, "⚠️ لم يتم العثور على نص للتلخيص.", "⚠️ No text found to summarize."))
        return

    summary_result = ""
    gemini = _get_gemini()
    if gemini:
        try:
            loop = asyncio.get_running_loop()
            def _ai_summarize():
                prompt = (
                    "Summarize the following content comprehensively yet concisely in bullet points. "
                    "Respond in the same language as the input (if Arabic, respond in clear Arabic):\n\n"
                    + raw_text[:30000]
                )
                res = gemini.generate_content(prompt)
                return res.text if res else ""
            summary_result = await loop.run_in_executor(None, _ai_summarize)
        except Exception as e:
            log.warning("Gemini summarize call failed: %s", e)

    # Naive fallback if no Gemini key or error
    if not summary_result:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        first_few = lines[:6]
        summary_result = "\n• " + "\n• ".join(first_few)

    header = _t(lang, "💡 *ملخص الذكاء الاصطناعي:*\n\n", "💡 *AI Summary:*\n\n")
    if len(summary_result) <= 3800:
        await status.edit_text(header + summary_result, parse_mode=constants.ParseMode.MARKDOWN)
    else:
        bio = io.BytesIO(summary_result.encode("utf-8"))
        bio.name = f"summary_{int(time.time())}.txt"
        await update.effective_message.reply_document(
            document=bio,
            caption=_t(lang, "💡 تم توليد التلخيص الكامل في ملف مرفق.", "💡 Full summary attached.")
        )
        await status.delete()


# ============================================================
# 4. Voice to Text (STT) Transcription
# ============================================================

async def stt_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transcribe voice message or audio to text using Gemini."""
    user = update.effective_user
    db_user = database.get_user(user.id) if user else None
    lang = db_user.get("language", config.DEFAULT_LANGUAGE) if db_user else config.DEFAULT_LANGUAGE
    context.user_data.pop("awaiting_stt", None)

    msg = update.effective_message
    if not msg.voice and not msg.audio:
        await msg.reply_text(_t(lang, "⚠️ يرجى إرسال رسالة صوتية أو ملف صوتي.", "⚠️ Please send a voice or audio note."))
        return

    status = await msg.reply_text(_t(lang, "🎙️ جاري تحويل الصوت إلى نص...", "🎙️ Transcribing audio to text..."))
    ext = ".ogg" if msg.voice else ".mp3"
    audio_path = await _download_file(msg, context, f"stt_{user.id}", ext)
    if not audio_path:
        await status.edit_text(_t(lang, "❌ فشل تحميل الصوت.", "❌ Failed to download audio."))
        return

    transcript = ""
    gemini = _get_gemini()
    if gemini:
        try:
            loop = asyncio.get_running_loop()
            def _run_gemini_audio():
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                mime = "audio/ogg" if ext == ".ogg" else "audio/mp3"
                res = gemini.generate_content([
                    "Transcribe this audio faithfully word for word. Output only the transcript.",
                    {"mime_type": mime, "data": audio_bytes}
                ])
                return res.text if res else ""
            transcript = await loop.run_in_executor(None, _run_gemini_audio)
        except Exception as e:
            log.warning("Gemini audio transcription error: %s", e)

    try:
        os.remove(audio_path)
    except Exception:
        pass

    if not transcript:
        await status.edit_text(
            _t(lang, "⚠️ تعذر تفريغ الصوت (تأكد من وضوح الصوت وإعداد GEMINI_API_KEY).",
               "⚠️ Could not transcribe audio (ensure GEMINI_API_KEY is configured).")
        )
        return

    header = _t(lang, "🗣️ *النص المفرغ من الصوت:*\n\n", "🗣️ *Audio Transcript:*\n\n")
    await status.edit_text(header + transcript.strip(), parse_mode=constants.ParseMode.MARKDOWN)


# Backward compatibility helpers
async def collect_pdf_images(update, context):
    await pdf_image_receive(update, context)

async def collect_summary_text(update, context):
    await summary_receive(update, context)

async def collect_ocr_text(update, context):
    await ocr_receive(update, context)

async def finish_pdf_conversion(update, context):
    await pdf_finish(update, context)
