import asyncio
import logging

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

import config
from telegram.ext import Application

import bot as botmod


async def main() -> None:
    builder = Application.builder().token(config.BOT_TOKEN)
    if config.TELEGRAM_LOCAL_API_URL:
        local_url = config.TELEGRAM_LOCAL_API_URL
        if not local_url.endswith("/bot"):
            local_url = local_url + "/bot"
        builder = builder.base_url(local_url)
    app = builder.build()
    async with app:
        me = await app.bot.get_me()
        print("bot:", me.username)

        ch = config.FORCE_SUB_CHANNELS[0]
        chat = await app.bot.get_chat(int(ch))
        print("channel title:", chat.title, "| username:", chat.username,
              "| invite_link:", (chat.invite_link or "")[:40])

        # Membership check for the admin (expected: member -> not missing)
        missing_admin = await botmod._missing_channels(app, config.ADMIN_ID)
        print("missing for admin:", missing_admin)

        # Membership check for an arbitrary non-member id (expected: missing)
        missing_stranger = await botmod._missing_channels(app, 123456789012)
        print("missing for stranger:", missing_stranger)

        # Lock UI keyboard with resolved join link
        kb = await botmod._force_keyboard(app, [ch], "ar")
        print("keyboard rows:", [[b.text for b in row] for row in kb.inline_keyboard])
        print("join url:", kb.inline_keyboard[0][0].url)

        # Lock text preview
        print("--- lock text ---")
        print(botmod._force_lock_text("ar", 1, 2))

        # Live log-channel alert test
        class FakeUser:
            id = config.ADMIN_ID
            username = "owner_test"
            full_name = "Owner Test"
        await botmod._log_event(
            app, botmod._admin_new_user_text(FakeUser(), "اختبار النظام / system test")
        )
        print("system alert sent to", config.LOG_CHANNEL_ID)


asyncio.run(main())