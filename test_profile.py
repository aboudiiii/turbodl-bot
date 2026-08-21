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
        await app.bot.get_me()
        await botmod.configure_start_screen(app)
        print("OK: profile startup step completed")


asyncio.run(main())