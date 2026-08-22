# Student & AI Hub State Handlers
# Extracted from bot.py callback_handler and related functions

async def collect_pdf_images(update, context):
    """Collect photos for Image-to-PDF conversion."""
    from bot import collect_pdf_images
    await collect_pdf_images(update, context)

async def collect_summary_text(update, context):
    """Collect text for AI summarization using Google Gemini."""
    from bot import collect_summary_text
    await collect_summary_text(update, context)

async def collect_ocr_text(update, context):
    """Extract text from photo using OCR."""
    from bot import collect_ocr_text
    await collect_ocr_text(update, context)

async def finish_pdf_conversion(update, context):
    """Process the collected images into a PDF document."""
    from bot import finish_pdf_conversion
    await finish_pdf_conversion(update, context)