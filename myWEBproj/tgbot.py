import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
import hashlib

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from werkzeug.security import check_password_hash

from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

router = Router()
dp = Dispatcher()
dp.include_router(router)


class AuthStates(StatesGroup):
    email = State()
    password = State()


class Database:
    def __init__(self, db_name='db/subscribes.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def verify_password(self, hashed_password, input_password):
        """Проверяем пароль с хешем"""
        return hashed_password == hashlib.sha256(input_password.encode()).hexdigest()

    def get_user_by_email(self, email):
        self.cursor.execute("SELECT id, email, hashed_password, tg_id FROM users WHERE email=?", (email,))
        return self.cursor.fetchone()

    def get_today_subscriptions(self):
        """Получаем подписки, у которых завтра день оплаты (1-31)"""
        today = datetime.now()
        tomorrow_day = (today + timedelta(days=1)).day

        self.cursor.execute("""
        SELECT u.tg_id, s.name_serv, s.price, s.payment_date, s.link 
        FROM subscribes s
        JOIN users u ON s.user_id = u.id
        WHERE s.payment_date = ? AND u.tg_id IS NOT NULL
        """, (tomorrow_day,))
        return self.cursor.fetchall()

    def update_telegram_id(self, email, telegram_id):
        """Обновляем tg_id в таблице users"""
        try:
            self.cursor.execute(
                "UPDATE users SET tg_id = ? WHERE email = ?",
                (telegram_id, email))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении tg_id: {e}")
            return False

    def close(self):
        self.conn.close()


db = Database()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Привет! Я бот для уведомлений о подписках.\n"
        "Для получения уведомлений необходимо авторизоваться.\n"
        "Введите ваш email:"
    )
    await state.set_state(AuthStates.email)


@router.message(AuthStates.email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    user = db.get_user_by_email(email)

    if not user:
        await message.answer("Пользователь с таким email не найден. Попробуйте еще раз.")
        return

    await state.update_data(email=email, user_id=user[0])
    await message.answer("Введите ваш пароль:")
    await state.set_state(AuthStates.password)


@router.message(AuthStates.password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    email = data['email']
    user = db.get_user_by_email(email)

    if not check_password_hash(user[2], message.text):  # Проверяем хеш пароля
        await message.answer("Неверный пароль. Попробуйте еще раз.")
        return

    if db.update_telegram_id(email, message.from_user.id):
        await message.answer(
            f"✅ Авторизация успешна!\n"
            f"Теперь вы будете получать уведомления о ваших подписках.\n"
            f"Уведомления приходят за день до даты оплаты в 17:00."
        )
    else:
        await message.answer("⚠ Произошла ошибка при сохранении данных. Попробуйте позже.")

    await state.clear()


async def send_daily_notifications(bot: Bot):
    logger.info("Проверка подписок для уведомлений...")
    subscriptions = db.get_today_subscriptions()

    if not subscriptions:
        logger.info("Нет подписок для уведомления сегодня")
        return

    current_month = datetime.now().strftime('%m')
    current_year = datetime.now().strftime('%Y')

    for sub in subscriptions:
        tg_id, name_serv, price, payment_day, link = sub

        # Формируем полную дату следующего платежа
        try:
            payment_date = datetime.strptime(
                f"{current_year}-{current_month}-{payment_day}",
                "%Y-%m-%d"
            ).strftime('%d.%m.%Y')
        except ValueError:
            # Обработка случая, когда дня нет в текущем месяце (например, 31 февраля)
            payment_date = f"{payment_day}-е число следующего месяца"

        message_text = (
            "🔔 Напоминание о подписке!\n\n"
            f"💳 Сервис: {name_serv}\n"
            f"💰 Сумма: {price}\n"
            f"📅 Дата оплаты: {payment_date}\n"
            f"🔗 Ссылка: {link}\n\n"
            f"Оплата требуется завтра!"
        )

        try:
            await bot.send_message(
                chat_id=tg_id,
                text=message_text
            )
            logger.info(f"Уведомление отправлено для tg_id {tg_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления для tg_id {tg_id}: {e}")


async def main():
    bot = Bot(token=BOT_TOKEN)

    # Настройка планировщика (каждый день в 19:30)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_notifications,
        'cron',
        hour=17,
        minute=00,
        args=[bot]
    )
    scheduler.start()

    try:
        logger.info("Starting bot...")
        await dp.start_polling(bot)
    finally:
        db.close()
        await bot.session.close()
        scheduler.shutdown()


if __name__ == '__main__':
    asyncio.run(main())