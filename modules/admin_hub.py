# Admin Hub - Broadcast & Maintenance Commands
import asyncio
from telegram import Update, constants
from telegram.error import Forbidden, BadRequest, TelegramError
from typing import List, Optional

# Owner ID check
BOT_OWNER_ID = 5283516841

# Module-level maintenance state (can be overridden by bot_data)
_maintenance_active = False


async def broadcast_command(update: Update, context) -> None:
    """ /broadcast <message> or /announce - send message to all registered users """
    user = update.effective_user
    if not user or user.id != BOT_OWNER_ID:
        await update.message.reply_text("⛔ only the bot owner can use this command")
        return

    # Get the message text from command arguments
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    broadcast_text = " ".join(args)

    # Get all user IDs from database
    user_ids: List[int] = []
    try:
        # Try to get users from database
        # In production, replace with proper database query
        from database import get_user
        # Placeholder - iterate known users
        all_user_ids = []  # Replace with database.get_all_users() or similar
    except Exception:
        all_user_ids = []

    # Send messages in batches to avoid flooding and rate limits
    batch_size = 30
    delay = 0.5  # seconds between batches
    sent = 0
    failed = 0

    for i in range(0, len(all_user_ids), batch_size):
        batch = all_user_ids[i:i+batch_size]
        for chat_id in batch:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=broadcast_text,
                    parse_mode=constants.ParseMode.MARKDOWN
                )
                sent += 1
            except (Forbidden, BadRequest, TelegramError):
                failed += 1

        # Wait between batches to avoid flooding
        if i + batch_size < len(all_user_ids):
            await asyncio.sleep(delay)

    await update.message.reply_text(
        f"✅ broadcast completed: {sent} sent, {failed} failed"
    )


async def maintenance_toggle(update: Update, context) -> None:
    """ /maintenance on|off - toggle maintenance mode """
    global _maintenance_active

    user = update.effective_user
    if not user or user.id != BOT_OWNER_ID:
        await update.message.reply_text("⛔ only the bot owner can use this command")
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /maintenance on|off")
        return

    state = args[0].lower() == "on"
    
    # Store in bot_data for persistence
    context.bot_data["maintenance"] = state
    
    # Update module-level variable
    global _maintenance_active
    _maintenance_active = state
    
    status = "enabled" if state else "disabled"
    await update.message.reply_text(f"✅ maintenance mode {status}")


async def maintenance_middleware(update: Update, context) -> Optional[bool]:
    """
    Middleware handler that checks maintenance mode.
    Returns True if the update should be blocked,
    False if it should proceed, None if unclear.
    """
    global _maintenance_active
    
    # Check maintenance mode from bot_data or module state
    if context.bot_data.get("maintenance", _maintenance_active):
        user = update.effective_user
        # Owner can always use the bot
        if user and user.id == BOT_OWNER_ID:
            return None  # Allow owner
        
        # Block all other users
        try:
            await update.message.reply_text(
                "⚠️ البوت تحت الصيانة حالياً، سنعود إليكم خلال دقائق!"
            )
            return True  # Block the update
        except Exception:
            return True  # Block on error
    
    return None  # Allow update to proceed