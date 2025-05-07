import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

# Создаем диспетчер
dp = Dispatcher()

# Список подписчиков (вместо базы данных)
subscribers = set()


# Функция для ежемесячной рассылки
async def monthly_notification():
    for user_id in subscribers:
        try:
            await bot.send_message(
                user_id,
                "📅 Это ваше ежемесячное уведомление!\n"
                f"Сегодня {datetime.now().strftime('%d.%m.%Y')}"
            )
        except Exception as e:
            logging.error(f"Ошибка отправки для {user_id}: {e}")


# Обработчик команды /start
@dp.message(Command('start'))
async def process_start_command(message: types.Message):
    user_id = message.from_user.id
    subscribers.add(user_id)
    await message.reply(
        "✅ Вы подписаны на ежемесячные уведомления!\n"
        "Я буду присылать вам сообщение 15-го числа каждого месяца."
    )


# Обработчик команды /unsubscribe
@dp.message(Command('unsubscribe'))
async def process_unsubscribe_command(message: types.Message):
    user_id = message.from_user.id
    if user_id in subscribers:
        subscribers.remove(user_id)
        await message.reply("❌ Вы отписались от уведомлений.")
    else:
        await message.reply("ℹ Вы не были подписаны.")


async def main():
    global bot
    bot = Bot(token=BOT_TOKEN)

    # Настройка планировщика (15-го числа каждого месяца в 12:00)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        monthly_notification,
        'cron',
        day=7,
        hour=19,
        minute=18
    )
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())