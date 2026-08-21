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
        # 1. Guard must be disabled (no channels configured)
        print("force channels:", config.FORCE_SUB_CHANNELS)

        class FakeUser:
            id = 5283516841
            username = "owner_test"
            full_name = "Owner Test"

        missing = await botmod._missing_channels(app, FakeUser.id)
        print("missing channels (should be []):", missing)

        # 2. Download-activity log entry to the channel
        await botmod._log_download(
            app, FakeUser(), "https://youtu.be/dQw4w9WgXcQ", "Test Video _ with_underscores"
        )
        print("download log sent to", config.LOG_CHANNEL_ID)

        # 3. New-user alert to the channel (markdown underscore safety check)
        await botmod._notify_admin(
            app, botmod._admin_new_user_text(FakeUser(), "انضمام جديد للبوت")
        )
        print("join alert sent to", config.ADMIN_ID)


asyncio.run(main())