import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.handlers import router
from app.utils import ensure_dirs


async def main():
    logging.basicConfig(level=logging.INFO)

    ensure_dirs(
        settings.generated_dir,
        settings.temp_dir,
        settings.stamps_dir,
        settings.signatures_dir,
    )

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
