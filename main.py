import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
import hashlib
from threading import Thread

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask, render_template, redirect, request, abort, flash
from data import db_session
from data.subscribes import Subscribes
from data.users import User
from forms.add_sub import SubscribesForm
from forms.login import LoginForm
from forms.register import RegisterForm
from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from forms.add_sud import SubscridesForm
import requests
from bs4 import BeautifulSoup

# Конфигурация
BOT_TOKEN = "7431447438:AAF2tyceUxIBqQq7kYOXNaj8sxFG8_q7yYw"
FLASK_SECRET_KEY = 'yandexlyceum_secret_key'
DB_NAME = 'db/subscribes.db'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== Telegram Bot Part ==================

class AuthStates(StatesGroup):
    email = State()
    password = State()

class Database:
    def __init__(self, db_name=DB_NAME):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def verify_password(self, hashed_password, input_password):
        return hashed_password == hashlib.sha256(input_password.encode()).hexdigest()

    def get_user_by_email(self, email):
        self.cursor.execute("SELECT id, email, hashed_password, tg_id FROM users WHERE email=?", (email,))
        return self.cursor.fetchone()

    def get_today_subscriptions(self):
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

async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Привет! Я бот для уведомлений о подписках.\n"
        "Для получения уведомлений необходимо авторизоваться.\n"
        "Введите ваш email:"
    )
    await state.set_state(AuthStates.email)

async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    user = db.get_user_by_email(email)

    if not user:
        await message.answer("Пользователь с таким email не найден. Попробуйте еще раз.")
        return

    await state.update_data(email=email, user_id=user[0])
    await message.answer("Введите ваш пароль:")
    await state.set_state(AuthStates.password)

async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    email = data['email']
    user = db.get_user_by_email(email)

    if not user[2] == message.text:
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

        try:
            payment_date = datetime.strptime(
                f"{current_year}-{current_month}-{payment_day}",
                "%Y-%m-%d"
            ).strftime('%d.%m.%Y')
        except ValueError:
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
            await bot.send_message(chat_id=tg_id, text=message_text)
            logger.info(f"Уведомление отправлено для tg_id {tg_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления для tg_id {tg_id}: {e}")

async def run_bot():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message(CommandStart())(cmd_start)
    dp.message(AuthStates.email)(process_email)
    dp.message(AuthStates.password)(process_password)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_notifications,
        'cron',
        hour=16,
        minute=38,
        args=[bot]
    )
    scheduler.start()

    try:
        logger.info("Starting Telegram bot...")
        await dp.start_polling(bot)
    finally:
        db.close()
        await bot.session.close()
        scheduler.shutdown()

# ================== Flask App Part ==================

app = Flask(__name__)
flask_scheduler = BackgroundScheduler()
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
login_manager = LoginManager()
login_manager.init_app(app)

def auth(username, password):
    data = {"username": username, "password": password}
    url_auth = 'https://elfin-circular-octagon.glitch.me/login'
    url_subscribe = 'https://elfin-circular-octagon.glitch.me/subscription'
    session = requests.Session()
    session.post(url_auth, data=data)
    response = session.get(url_subscribe).text
    soup = BeautifulSoup(response, 'lxml')
    block_main = soup.find('div', class_='container content')
    block_data_1 = block_main.find('div', class_='alert alert-info mb-4')
    block_data_2 = block_data_1.find_all('p')
    block_costs_1 = block_main.find('div', class_='row justify-content-center')
    block_costs_2 = block_costs_1.find('div', class_='card-body text-center')
    block_costs_3 = block_costs_2.find('h4', class_='text-primary')
    return [int(str(block_data_2[0]).split()[-1].split(".")[0]), int(str(block_costs_3)[25: -11])]

@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(user_id)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")

def check_payment_dates():
    with app.app_context():
        db_sess = db_session.create_session()
        today = datetime.now().day
        subscriptions = db_sess.query(Subscribes).filter(
            Subscribes.payment_date == today,
            Subscribes.is_paid == True
        ).all()

        for sub in subscriptions:
            sub.is_paid = False
            db_sess.commit()
            logger.info(f"Сброшен статус оплаты для подписки {sub.id}")

def run_flask():
    db_session.global_init(DB_NAME)
    flask_scheduler.add_job(
        check_payment_dates,
        'cron',
        hour=0,
        minute=1,
        id='daily_payment_check'
    )
    flask_scheduler.start()
    app.run(port=5000)

# Flask routes...
@app.route("/")
def index():
    db_sess = db_session.create_session()
    if current_user.is_authenticated:
        subscribes = db_sess.query(Subscribes).filter(
            (Subscribes.user == current_user) | (Subscribes.is_private != True))
    else:
        subscribes = db_sess.query(Subscribes).filter(Subscribes.is_private != True)
    return render_template("index.html", subscribes=subscribes)

@app.route('/register', methods=['GET', 'POST'])
def reqister():
    form = RegisterForm()
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form, message="Пароли не совпадают")
        db_sess = db_session.create_session()
        if db_sess.query(User).filter(User.email == form.email.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form, message="Такой пользователь уже есть")
        user = User(
            name=form.name.data,
            surname=form.surname.data,
            email=form.email.data,
            about=form.about.data
        )
        user.set_password(form.password.data)
        db_sess.add(user)
        db_sess.commit()
        return redirect('/login')
    return render_template('register.html', title='Регистрация', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.email == form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html',
                               message="Неправильный логин или пароль",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)

# ... (остальные Flask-роуты остаются без изменений)

# ================== Main Execution ==================

def run_telegram_bot():
    asyncio.run(run_bot())

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Запускаем Telegram бота в основном потоке
    run_telegram_bot()